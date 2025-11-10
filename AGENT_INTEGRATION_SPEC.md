# Terrarium IRC ↔ Terrarium Agent Integration Specification

**Version**: 1.0
**Date**: 2025-11-08
**Status**: Planning

## Executive Summary

This document specifies the integration between `terrarium-irc` (IRC bot) and `terrarium-agent` (HTTP API server for LLM responses). The integration migrates from direct Ollama integration to the terrarium-agent HTTP API, implementing a hybrid context management system with tool-based IRC history access.

**Key Goals**:
1. Replace Ollama with terrarium-agent HTTP API
2. Implement hybrid context management (in-memory + DB)
3. Provide AI tools for IRC history access
4. Smart context reset based on conversation staleness
5. Maintain SQLite for human debugging and long-term analytics

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Why SQLite Over Logfiles](#why-sqlite-over-logfiles)
3. [Context Management Strategy](#context-management-strategy)
4. [Tool System Design](#tool-system-design)
5. [API Integration](#api-integration)
6. [Migration Plan](#migration-plan)
7. [Implementation Details](#implementation-details)
8. [Configuration](#configuration)
9. [Testing Strategy](#testing-strategy)

---

## Architecture Overview

### Current Architecture (Ollama-based)

```
IRC Messages → Bot Handler → Ollama Client → Ollama Local API
                    ↓
              SQLite Logger
                    ↓
         Context from DB (last 50 messages)
```

**Issues**:
- Direct Ollama dependency
- No conversation continuity (rebuilds context from DB each time)
- No tool-based history access for AI
- Simple but not scalable for agent features

### New Architecture (terrarium-agent-based)

```
┌─────────────────────────────────────────────────────────────┐
│ IRC Bot (terrarium-irc)                                     │
│                                                              │
│  ┌────────────────┐         ┌──────────────────┐           │
│  │ IRC Handler    │────────→│ Context Manager  │           │
│  │ (miniirc)      │         │ - Per-channel    │           │
│  └────────────────┘         │ - Staleness      │           │
│         │                   │ - Auto-inject    │           │
│         │                   └──────────────────┘           │
│         │                            │                      │
│         ↓                            ↓                      │
│  ┌────────────────┐         ┌──────────────────┐           │
│  │ SQLite Logger  │←────────│ Tool Registry    │           │
│  │ - IRC history  │         │ - search_history │           │
│  │ - Analytics    │         │ - get_recent     │           │
│  └────────────────┘         │ - get_stats      │           │
│                             └──────────────────┘           │
│                                      │                      │
│                                      ↓                      │
│                             ┌──────────────────┐           │
│                             │ Agent Client     │           │
│                             │ (HTTP)           │           │
│                             └──────────────────┘           │
└──────────────────────────────────────┼──────────────────────┘
                                       │ HTTP POST
                                       │ /v1/chat/completions
                                       ↓
                            ┌─────────────────────┐
                            │ terrarium-agent     │
                            │ (server.py:8080)    │
                            │                     │
                            │ - Stateless         │
                            │ - OpenAI API        │
                            │ - Tool support      │
                            │ - vLLM backend      │
                            └─────────────────────┘
```

**Key Principles**:
1. **Stateless Server**: terrarium-agent doesn't store conversation state
2. **Client Responsibility**: IRC bot manages conversation history per channel
3. **Hybrid Context**: In-memory conversation + DB for IRC history
4. **Tool-Based Access**: AI can request deeper history via tool calls
5. **Smart Reset**: Context cleared when conversation goes stale

---

## Why SQLite Over Logfiles

### Decision: Keep SQLite

**Rationale**:
The user has multiple use cases that SQLite serves better than text logfiles:

1. **AI Short-Term Context** ✅
   - SQLite: `SELECT * FROM messages WHERE channel = ? ORDER BY timestamp DESC LIMIT 50`
   - Logfiles: Parse entire file, filter by channel, sort by time (slower)

2. **AI Long-Term Memory via Tools** ✅
   - SQLite: `SELECT * FROM messages WHERE message LIKE ? AND timestamp > ?`
   - Logfiles: grep + awk (works but less flexible for structured queries)

3. **Human Debugging/Analysis** ✅
   - SQLite: SQL queries, export to CSV, JOIN with other data
   - Logfiles: grep/awk (good) but limited for complex analysis

4. **Stats/Analytics** ✅
   - SQLite: `SELECT COUNT(*), nick FROM messages GROUP BY nick`
   - Logfiles: Complex parsing, no aggregation without additional tools

### Database Schema (Current - Keep As Is)

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    channel TEXT,
    nick TEXT,
    user TEXT,
    host TEXT,
    message TEXT,
    message_type TEXT DEFAULT 'PRIVMSG'
);

-- Critical index for AI context queries
CREATE INDEX idx_messages_channel_timestamp
ON messages(channel, timestamp DESC);
```

**Why This Works**:
- Fast queries for recent messages (auto-inject context)
- Search/filter capabilities for tool calls
- Human-readable with any SQLite client
- Compact storage (binary format)
- ACID guarantees (no log corruption)

---

## Context Management Strategy

### Overview

Hybrid approach combining conversation state (in-memory) with IRC history (database).

### Per-Channel Context State

Each IRC channel maintains its own conversation context:

```python
class ChannelContext:
    def __init__(self, channel: str):
        self.channel = channel
        self.conversation_history = []  # List of OpenAI-format messages
        self.last_activity = datetime.now()
        self.system_prompt = self._build_system_prompt()

    def is_stale(self, threshold_hours: int = 2) -> bool:
        """Check if conversation has gone stale."""
        elapsed = datetime.now() - self.last_activity
        return elapsed.total_seconds() > (threshold_hours * 3600)

    def add_user_message(self, nick: str, message: str):
        """Add IRC message to conversation."""
        self.conversation_history.append({
            "role": "user",
            "content": f"{nick}: {message}"
        })
        self.last_activity = datetime.now()

    def add_assistant_message(self, message: str):
        """Add agent response to conversation."""
        self.conversation_history.append({
            "role": "assistant",
            "content": message
        })

    def get_messages_for_api(self, max_turns: int = 10) -> list:
        """
        Build message list for API call.

        Includes:
        - System prompt
        - Last N conversation turns
        - Recent IRC context (from DB)
        """
        # System prompt (always first)
        messages = [{"role": "system", "content": self.system_prompt}]

        # Add recent conversation history (last N turns)
        recent_conversation = self.conversation_history[-max_turns:]
        messages.extend(recent_conversation)

        return messages

    def reset(self):
        """Clear conversation (when stale)."""
        self.conversation_history = []
        self.last_activity = datetime.now()
```

### Context Injection Strategy

**On Each `!terrarium` Command**:

1. **Check Staleness**
   ```python
   if context.is_stale(threshold_hours=2):
       context.reset()
       # Start fresh - will auto-inject recent IRC
   ```

2. **Build Message List**
   ```python
   messages = context.get_messages_for_api(max_turns=10)
   # Includes: system prompt + last 10 conversation turns
   ```

3. **Auto-Inject Recent IRC** (if conversation is fresh/empty)
   ```python
   if len(context.conversation_history) == 0:
       # First interaction or after reset
       recent_irc = await db.get_recent_messages(channel, limit=30)
       irc_context = format_irc_context(recent_irc)

       # Add as user message with special formatting
       messages.append({
           "role": "user",
           "content": f"[Recent IRC context]\n{irc_context}"
       })
   ```

4. **Add Current User Message**
   ```python
   context.add_user_message(nick, user_question)
   messages.append({
       "role": "user",
       "content": f"{nick}: {user_question}"
   })
   ```

### Staleness Detection

**Thresholds**:
- **2 hours**: Default staleness threshold (configurable)
- **Behavior**: After 2 hours of inactivity, reset conversation and re-inject IRC context
- **Rationale**: IRC conversations have natural breaks; fresh context prevents outdated continuity

**Example Timeline**:
```
10:00 AM - User: "!terrarium what's Python?"
          → New context, auto-inject last ~20 IRC messages
          → Agent responds, adds to conversation history

10:05 AM - User: "!terrarium can you explain decorators?"
          → Context active (5 min gap)
          → Use existing conversation history
          → No IRC re-injection

12:30 PM - User: "!terrarium what is asyncio?"
          → Context stale (2.5 hour gap)
          → Reset conversation, re-inject IRC
          → Start fresh conversation
```

### Context Window Management

**Token Budget** (assuming ~8K context window with summaries):
- System prompt: ~200 tokens
- Conversation summary block: ~200-400 tokens when present
- Last 10-12 raw conversation turns: ~1500-2200 tokens
- Recent IRC context (~20 messages): ~600-900 tokens
- User query: ~100-500 tokens
- **Total input**: ~3200-4200 tokens
- **Reserve for output**: 2000-3000 tokens

**Limits**:
- Max raw conversation turns retained: ~12 (older turns summarized automatically)
- Max IRC context: defaults to 20 messages (`MAX_CONTEXT_MESSAGES`)
- Auto-summarize if conversation exceeds ~40 turns

---

## Tool System Design

### Overview

Provide AI with tools to access IRC history when automatic context isn't sufficient.

### Tool Definitions

Tools are exposed to the AI via system prompt and handled by the bot.

#### 1. `search_irc_history`

**Purpose**: Search past IRC messages by keyword/phrase

**Definition**:
```json
{
  "name": "search_irc_history",
  "description": "Search IRC message history for specific keywords or phrases. Use when you need to find old discussions about a topic.",
  "parameters": {
    "query": {
      "type": "string",
      "description": "Search query (keywords or phrase)"
    },
    "channel": {
      "type": "string",
      "description": "IRC channel to search (defaults to current channel)",
      "optional": true
    },
    "hours": {
      "type": "integer",
      "description": "Only search messages from last N hours (optional)",
      "optional": true
    },
    "limit": {
      "type": "integer",
      "description": "Maximum results to return (default: 20)",
      "optional": true
    }
  }
}
```

**Implementation**:
```python
async def tool_search_irc_history(query, channel=None, hours=None, limit=20):
    """Search IRC history."""
    results = await db.search_messages(
        query=query,
        channel=channel or current_channel,
        limit=limit
    )

    if hours:
        cutoff = datetime.now() - timedelta(hours=hours)
        results = [r for r in results if r.timestamp > cutoff]

    # Format results for AI
    return format_search_results(results, query)
```

**Example Tool Call** (by AI):
```json
{
  "tool": "search_irc_history",
  "arguments": {
    "query": "deployment script",
    "hours": 72,
    "limit": 10
  }
}
```

**Tool Response**:
```
Search results for "deployment script" (10 messages found):

[2025-11-05 14:23] <alice> I updated the deployment script to handle migrations
[2025-11-05 14:25] <bob> Thanks! Does it work with the new docker setup?
[2025-11-05 14:27] <alice> Yes, tested on staging. Run ./deploy.sh prod
...
```

#### 2. `get_recent_irc_messages`

**Purpose**: Get recent IRC messages beyond auto-injected context

**Definition**:
```json
{
  "name": "get_recent_irc_messages",
  "description": "Get recent IRC messages from the channel. Use when you need more context than what was automatically provided.",
  "parameters": {
    "channel": {
      "type": "string",
      "description": "IRC channel (defaults to current channel)",
      "optional": true
    },
    "limit": {
      "type": "integer",
      "description": "Number of messages to retrieve (default: 50)",
      "optional": true
    },
    "hours": {
      "type": "integer",
      "description": "Only get messages from last N hours (optional)",
      "optional": true
    }
  }
}
```

**Implementation**:
```python
async def tool_get_recent_irc_messages(channel=None, limit=50, hours=None):
    """Get recent IRC messages."""
    messages = await db.get_recent_messages(
        channel=channel or current_channel,
        limit=limit,
        hours=hours
    )

    return format_irc_context(messages)
```

#### 3. `get_channel_stats`

**Purpose**: Get channel activity statistics

**Definition**:
```json
{
  "name": "get_channel_stats",
  "description": "Get statistics about channel activity (message counts, active users, etc.)",
  "parameters": {
    "channel": {
      "type": "string",
      "description": "IRC channel (defaults to current channel)",
      "optional": true
    }
  }
}
```

**Implementation**:
```python
async def tool_get_channel_stats(channel=None):
    """Get channel statistics."""
    stats = await db.get_channel_stats(channel or current_channel)

    return format_stats(stats)
```

### System Prompt with Tools

```python
SYSTEM_PROMPT_WITH_TOOLS = """You are Terrarium, a helpful IRC bot assistant.

You have access to IRC channel history through these tools:

1. **search_irc_history(query, hours=None, limit=20)**
   - Search past messages by keyword
   - Example: search_irc_history("bug fix", hours=24)

2. **get_recent_irc_messages(limit=50, hours=None)**
   - Get more recent IRC context
   - Example: get_recent_irc_messages(limit=100)

3. **get_channel_stats()**
   - Get channel activity statistics

When to use tools:
- User asks about past discussions → use search_irc_history
- Need more context than provided → use get_recent_irc_messages
- User asks about channel activity → use get_channel_stats

Guidelines:
- Be concise (IRC has character limits)
- Be friendly and helpful
- Reference nicknames when discussing IRC history
- Acknowledge when you don't have enough context

Current channel: {channel}
Recent IRC context is provided automatically.
"""
```

### Tool Execution Flow

**Standard Flow** (terrarium-agent with tool support):

1. User: `!terrarium what did alice say about the bug?`
2. Bot builds message list with system prompt (includes tool definitions)
3. Send to terrarium-agent API
4. Agent responds with tool call:
   ```json
   {
     "tool_calls": [{
       "name": "search_irc_history",
       "arguments": {"query": "bug", "hours": 24}
     }]
   }
   ```
5. Bot executes tool, gets results
6. Bot sends tool results back to agent
7. Agent generates final response using tool data

**Fallback Flow** (if terrarium-agent doesn't support tool calls yet):

For initial implementation, we can simulate tools by detecting keywords in the agent's response and executing tools proactively:

```python
# If agent's response contains "I need to search" or similar
if "search" in response.lower() or "need more context" in response.lower():
    # Execute search based on user's original question
    results = await tool_search_irc_history(extract_keywords(user_question))

    # Add tool result and re-query
    messages.append({"role": "assistant", "content": response})
    messages.append({"role": "user", "content": f"[Search results]\n{results}"})
    response = await agent_client.chat(messages)
```

---

### Enhancement Request Tools (New)

Terrarium can now capture her own enhancement ideas via three helper tools:

1. `create_enhancement_request(title, summary)`  
   - Writes a markdown file to `data/enhancements/` with the summary plus the last ~20 IRC messages for context  
   - Limited to 10 open files to keep requests actionable

2. `list_enhancement_requests()`  
   - Returns filenames, titles, and timestamps of existing requests

3. `read_enhancement_request(filename)`  
   - Reads the content of a specific request so Terra can reference or update it

These tools give Terra a lightweight backlog she can maintain without human intervention, and they provide engineers with ready-made reproduction context when they pick up the work.

## API Integration

### terrarium-agent Client

Replace `llm/client.py` (Ollama) with new `llm/agent_client.py`:

```python
"""
terrarium-agent HTTP API client.

Replaces Ollama integration with terrarium-agent server.
Based on terrarium-agent/client_library.py.
"""

import requests
from typing import List, Dict, Optional
from requests.exceptions import RequestException, Timeout, ConnectionError


class AgentClientError(Exception):
    """Base exception for agent client errors."""
    pass


class AgentClient:
    """
    Client for Terrarium Agent HTTP API.

    Provides interface for generating responses from the agent server.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout: int = 60,
        max_retries: int = 3
    ):
        """
        Initialize agent client.

        Args:
            base_url: Agent server URL (default: http://localhost:8080)
            timeout: Request timeout in seconds (default: 60)
            max_retries: Maximum retry attempts (default: 3)
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512
    ) -> str:
        """
        Generate response with conversation history.

        Args:
            messages: Conversation history (OpenAI format)
            temperature: Sampling temperature 0.0-2.0
            max_tokens: Maximum tokens to generate

        Returns:
            Assistant's response text

        Raises:
            AgentClientError: Request failed
        """
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        response_data = await self._request_with_retry(
            "POST",
            "/v1/chat/completions",
            json=payload
        )

        try:
            return response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise AgentClientError(f"Invalid response format: {e}")

    async def health_check(self) -> bool:
        """
        Check if agent server is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            response = requests.get(
                f"{self.base_url}/health",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False

    async def _request_with_retry(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make HTTP request with retry logic."""
        url = f"{self.base_url}{endpoint}"

        for attempt in range(self.max_retries):
            try:
                response = requests.request(
                    method,
                    url,
                    timeout=self.timeout,
                    **kwargs
                )

                if response.status_code >= 500:
                    if attempt < self.max_retries - 1:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    else:
                        raise AgentClientError(f"Server error: {response.text}")

                elif response.status_code >= 400:
                    raise AgentClientError(f"Request error: {response.text}")

                response.raise_for_status()
                return response.json()

            except Timeout:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    raise AgentClientError("Request timed out")

            except ConnectionError:
                raise AgentClientError(f"Cannot connect to {self.base_url}")

        raise AgentClientError("Unexpected error")
```

### API Request Flow

**Example Request to terrarium-agent**:

```python
# User message in IRC
channel = "#terrarium"
nick = "alice"
message = "what did bob say about docker?"

# Build context
context = channel_contexts[channel]
messages = context.get_messages_for_api()

# Add current message
context.add_user_message(nick, message)
messages.append({
    "role": "user",
    "content": f"{nick}: {message}"
})

# Send to agent
response = await agent_client.chat(
    messages=messages,
    temperature=0.8,
    max_tokens=512
)

# Add response to context
context.add_assistant_message(response)

# Send to IRC
send_to_channel(channel, response)
```

**HTTP Request** (to terrarium-agent):

```http
POST http://localhost:8080/v1/chat/completions
Content-Type: application/json

{
  "messages": [
    {
      "role": "system",
      "content": "You are Terrarium, a helpful IRC bot..."
    },
    {
      "role": "user",
      "content": "[Recent IRC context]\n[14:20] <bob> I updated the docker compose file\n[14:22] <carol> does it work now?\n..."
    },
    {
      "role": "user",
      "content": "alice: what did bob say about docker?"
    }
  ],
  "temperature": 0.8,
  "max_tokens": 512
}
```

**HTTP Response**:

```json
{
  "id": "chatcmpl-xyz",
  "object": "chat.completion",
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "Bob mentioned that he updated the docker compose file at 14:20. Carol asked if it works now."
    }
  }]
}
```

---

## Migration Plan

### Phase 1: Core Infrastructure (Week 1)

**Goal**: Replace Ollama with terrarium-agent, basic functionality working

**Tasks**:
1. Create `llm/agent_client.py` based on terrarium-agent client library
2. Create `llm/context_manager.py` for per-channel context tracking
3. Update `main.py` to use AgentClient instead of Ollama
4. Update configuration (`.env`) for terrarium-agent URL
5. Test basic `!terrarium` command with new client

**Deliverables**:
- Basic chat working with terrarium-agent
- Per-channel context tracking
- Staleness detection (but no reset yet)

**Testing**:
```bash
# Terminal 1: Start terrarium-agent
cd ~/Programming/terrarium-agent
python server.py

# Terminal 2: Start IRC bot
cd ~/Programming/terrarium-irc
source venv/bin/activate
python main.py

# IRC: Test
!terrarium hello
!terrarium can you remember what I just said? (should work - same conversation)
```

### Phase 2: Context Management (Week 2)

**Goal**: Implement hybrid context with smart reset

**Tasks**:
1. Implement staleness detection and reset
2. Auto-inject IRC context on fresh/reset conversations
3. Optimize context window management
4. Add context pruning (max turns limit)
5. Test multi-turn conversations and staleness

**Deliverables**:
- Smart context reset after 2 hours
- Auto-injection of IRC context
- Token budget management

**Testing**:
```bash
# Test conversation continuity
!terrarium what is python?
!terrarium can you expand on that? (should remember previous response)

# Test staleness (manually set time or wait)
# After 2+ hours of inactivity:
!terrarium what is docker? (should reset and inject fresh IRC context)
```

### Phase 3: Tool System (Week 3)

**Goal**: Add IRC history tools for AI

**Tasks**:
1. Create `llm/tools.py` with tool definitions
2. Implement tool handlers (search, get_recent, get_stats)
3. Update system prompt to include tool descriptions
4. Add tool execution logic to command handler
5. Test tool calls (initial version may use keyword detection)

**Deliverables**:
- `search_irc_history` tool working
- `get_recent_irc_messages` tool working
- `get_channel_stats` tool working
- System prompt with tool instructions

**Testing**:
```bash
# Test search tool
!terrarium what did alice say about the deployment?
# Should trigger search_irc_history tool

# Test recent messages tool
!terrarium can you give me more context about what happened?
# Should trigger get_recent_irc_messages tool
```

### Phase 4: Polish & Documentation (Week 4)

**Goal**: Production-ready with full documentation

**Tasks**:
1. Add error handling and graceful degradation
2. Update CLAUDE.md with new architecture
3. Create migration guide from current setup
4. Add configuration documentation
5. Performance testing and optimization

**Deliverables**:
- Comprehensive error handling
- Updated documentation
- Migration guide
- Performance benchmarks

---

## Implementation Details

### File Structure Changes

```
terrarium-irc/
├── llm/
│   ├── __init__.py
│   ├── agent_client.py       # NEW: terrarium-agent HTTP client
│   ├── context_manager.py    # NEW: Per-channel context management
│   ├── tools.py              # NEW: Tool definitions and handlers
│   ├── context.py            # KEEP: Context formatting utilities
│   └── client.py             # REMOVE: Ollama client (deprecated)
├── bot/
│   ├── commands.py           # MODIFY: Update to use new context manager
│   └── irc_client.py         # MODIFY: Update initialization
├── main.py                   # MODIFY: Use AgentClient instead of Ollama
├── .env.example              # MODIFY: Add AGENT_API_URL
└── AGENT_INTEGRATION_SPEC.md # NEW: This document
```

### Key Code Changes

#### `llm/context_manager.py` (New)

```python
"""
Per-channel conversation context management.

Manages hybrid context: in-memory conversation + DB IRC history.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional
from storage import Database


class ChannelContext:
    """Manages conversation context for a single IRC channel."""

    def __init__(self, channel: str, db: Database, max_turns: int = 10):
        self.channel = channel
        self.db = db
        self.max_turns = max_turns
        self.conversation_history: List[Dict[str, str]] = []
        self.last_activity = datetime.now()

    def is_stale(self, threshold_hours: int = 2) -> bool:
        """Check if conversation has gone stale."""
        elapsed = datetime.now() - self.last_activity
        return elapsed.total_seconds() > (threshold_hours * 3600)

    async def get_messages_for_api(
        self,
        include_irc_context: bool = True,
        irc_context_limit: int = 30
    ) -> List[Dict[str, str]]:
        """
        Build message list for API call.

        Returns:
            List of messages in OpenAI format
        """
        messages = []

        # 1. System prompt
        messages.append({
            "role": "system",
            "content": self._build_system_prompt()
        })

        # 2. Auto-inject IRC context if conversation is fresh/empty
        if include_irc_context and len(self.conversation_history) == 0:
            irc_messages = await self.db.get_recent_messages(
                channel=self.channel,
                limit=irc_context_limit
            )

            if irc_messages:
                irc_context = self._format_irc_context(irc_messages)
                messages.append({
                    "role": "user",
                    "content": f"[Recent IRC context from {self.channel}]\n{irc_context}"
                })

        # 3. Recent conversation history (last N turns)
        recent_conversation = self.conversation_history[-self.max_turns:]
        messages.extend(recent_conversation)

        return messages

    def add_user_message(self, nick: str, message: str):
        """Add user message to conversation."""
        self.conversation_history.append({
            "role": "user",
            "content": f"{nick}: {message}"
        })
        self.last_activity = datetime.now()

    def add_assistant_message(self, message: str):
        """Add assistant response to conversation."""
        self.conversation_history.append({
            "role": "assistant",
            "content": message
        })

    def reset(self):
        """Reset conversation (clear history)."""
        self.conversation_history = []
        self.last_activity = datetime.now()

    def _build_system_prompt(self) -> str:
        """Build system prompt for this channel."""
        return f"""You are Terrarium, a helpful IRC bot assistant in {self.channel}.

Guidelines:
- Be concise and IRC-friendly (keep responses under 400 characters when possible)
- Be helpful, friendly, and respectful
- Reference users by their IRC nicknames
- If you don't know something, say so

Current channel: {self.channel}
Recent IRC context may be provided automatically."""

    def _format_irc_context(self, messages) -> str:
        """Format IRC messages for context."""
        lines = []
        for msg in messages:
            time_str = msg.timestamp.strftime('%H:%M')
            lines.append(f"[{time_str}] <{msg.nick}> {msg.message}")
        return "\n".join(lines)


class ContextManager:
    """Manages contexts for all channels."""

    def __init__(self, db: Database):
        self.db = db
        self.contexts: Dict[str, ChannelContext] = {}

    def get_context(self, channel: str) -> ChannelContext:
        """Get or create context for a channel."""
        if channel not in self.contexts:
            self.contexts[channel] = ChannelContext(channel, self.db)

        context = self.contexts[channel]

        # Check staleness and reset if needed
        if context.is_stale():
            print(f"Context for {channel} is stale, resetting...")
            context.reset()

        return context

    def clear_channel(self, channel: str):
        """Clear context for a channel."""
        if channel in self.contexts:
            self.contexts[channel].reset()
```

#### `bot/commands.py` Updates

```python
# OLD: cmd_terrarium (Ollama version)
@staticmethod
async def cmd_terrarium(bot: 'TerrariumBot', channel: str, nick: str, args: str):
    # Get recent context
    context = await bot.get_recent_context(channel, limit=50)

    # Generate response
    response = await bot.llm_client.generate(
        prompt=args,
        system_prompt=system_prompt,
        context=context
    )

# NEW: cmd_terrarium (terrarium-agent version)
@staticmethod
async def cmd_terrarium(bot: 'TerrariumBot', channel: str, nick: str, args: str):
    if not args:
        bot.send_message(channel, f"{nick}: Usage: !terrarium <question>")
        return

    bot.send_message(channel, f"{nick}: Thinking...")

    try:
        # Get channel context
        context = bot.context_manager.get_context(channel)

        # Build message list for API
        messages = await context.get_messages_for_api()

        # Add current user message
        context.add_user_message(nick, args)
        messages.append({
            "role": "user",
            "content": f"{nick}: {args}"
        })

        # Get response from agent
        response = await bot.agent_client.chat(
            messages=messages,
            temperature=0.8,
            max_tokens=512
        )

        # Add to conversation history
        context.add_assistant_message(response)

        # Send to IRC (split if needed)
        chunks = bot.context_builder.split_long_response(response, max_length=400)
        for i, chunk in enumerate(chunks):
            if i == 0:
                bot.send_message(channel, f"{nick}: {chunk}")
            else:
                bot.send_message(channel, f"... {chunk}")
            await asyncio.sleep(0.5)

    except Exception as e:
        bot.send_message(channel, f"{nick}: Error: {str(e)}")
        import traceback
        traceback.print_exc()
```

---

## Configuration

### Environment Variables

Update `.env.example`:

```bash
# IRC Configuration
IRC_SERVER=irc.libera.chat
IRC_PORT=6667
IRC_USE_SSL=false
IRC_NICK=Terra
IRC_CHANNELS=#test,#mychannel

# Agent Configuration (terrarium-agent)
AGENT_API_URL=http://localhost:8080  # NEW
AGENT_TEMPERATURE=0.8                # NEW
AGENT_MAX_TOKENS=512                 # NEW

# Bot Configuration
COMMAND_PREFIX=!
MAX_CONTEXT_MESSAGES=20
DB_PATH=./data/irc_logs.db

# Legacy (Ollama) configuration for reference
# LLM_MODEL=qwen2.5:7b
# LLM_API_URL=http://localhost:11434
```

### `main.py` Updates

```python
# OLD: Initialize Ollama client
llm_client = LLMClient(
    model=llm_model,
    api_url=llm_api_url,
    temperature=llm_temperature,
    max_tokens=llm_max_tokens
)

# NEW: Initialize terrarium-agent client
from llm import AgentClient, ContextManager

agent_client = AgentClient(
    base_url=os.getenv('AGENT_API_URL', 'http://localhost:8080'),
    timeout=60
)

# Check health
if await agent_client.health_check():
    print("Agent server is healthy")
else:
    print("Warning: Agent server not available")
    print("Make sure terrarium-agent is running:")
    print("  cd ~/Programming/terrarium-agent && python server.py")

# Create context manager
context_manager = ContextManager(database)

# Pass to bot
bot = TerrariumBot(
    ...
    agent_client=agent_client,
    context_manager=context_manager,
    ...
)
```

---

## Testing Strategy

### Unit Tests

Create `tests/test_context_manager.py`:

```python
import pytest
from datetime import datetime, timedelta
from llm.context_manager import ChannelContext, ContextManager


@pytest.mark.asyncio
async def test_staleness_detection():
    """Test that contexts become stale after threshold."""
    context = ChannelContext("#test", mock_db)

    # Fresh context
    assert not context.is_stale(threshold_hours=2)

    # Manually set old timestamp
    context.last_activity = datetime.now() - timedelta(hours=3)

    # Should be stale
    assert context.is_stale(threshold_hours=2)


@pytest.mark.asyncio
async def test_auto_inject_irc_context():
    """Test IRC context auto-injection on fresh conversations."""
    context = ChannelContext("#test", mock_db)

    # Empty conversation - should inject IRC
    messages = await context.get_messages_for_api(include_irc_context=True)

    # Should have: system prompt + IRC context
    assert len(messages) >= 2
    assert messages[0]["role"] == "system"
    assert "[Recent IRC context" in messages[1]["content"]


@pytest.mark.asyncio
async def test_conversation_continuity():
    """Test that conversation history is maintained."""
    context = ChannelContext("#test", mock_db)

    # Add messages
    context.add_user_message("alice", "hello")
    context.add_assistant_message("hi alice")
    context.add_user_message("bob", "what's up?")

    # Get messages (no IRC re-injection)
    messages = await context.get_messages_for_api(include_irc_context=True)

    # Should have: system + 3 conversation messages (no IRC context)
    assert len(messages) == 4
```

### Integration Tests

Test with actual terrarium-agent:

```bash
# 1. Start terrarium-agent
cd ~/Programming/terrarium-agent
python server.py

# 2. Run integration test
cd ~/Programming/terrarium-irc
python -m pytest tests/test_integration.py
```

`tests/test_integration.py`:

```python
@pytest.mark.integration
async def test_full_conversation_flow():
    """Test complete conversation with terrarium-agent."""
    client = AgentClient("http://localhost:8080")

    # Check health
    assert await client.health_check()

    # Simple conversation
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"}
    ]

    response = await client.chat(messages)
    assert "4" in response.lower()
```

### Manual Testing Checklist

- [ ] Basic chat: `!terrarium hello`
- [ ] Conversation continuity: Ask follow-up question
- [ ] Staleness: Wait 2+ hours, verify context resets
- [ ] IRC context injection: Verify recent messages included
- [ ] Multi-channel: Test context isolation between channels
- [ ] Error handling: Stop terrarium-agent, verify graceful error
- [ ] Tool calls: Ask question requiring search
- [ ] Long responses: Test IRC message splitting

---

## Open Questions & Future Work

### Open Questions

1. **Tool Call Format**: Does terrarium-agent support OpenAI-style tool/function calling yet?
   - If yes: Implement proper tool calling
   - If no: Use keyword detection fallback initially

2. **Token Counting**: Should we implement client-side token estimation?
   - Useful for staying under context limits
   - Could use tiktoken library

3. **Context Persistence**: Should conversation history survive bot restarts?
   - Could serialize to SQLite
   - Adds complexity

### Future Enhancements

1. **Enhancement Request Tool** (postponed for now)
   - Let AI request new tools/features
   - Write to `./enhancement_requests.log`

2. **Semantic Search**
   - Embed IRC messages for semantic search
   - Store vectors in SQLite or separate DB

3. **Multi-Agent Architecture**
   - Context Manager Agent
   - Research Agent for deep history
   - IRC Ambassador Agent

4. **Advanced Context Strategies**
   - Summarization for old messages
   - Importance scoring for message selection
   - Cross-channel context

5. **Performance Optimization**
   - Cache formatted IRC context
   - Batch DB queries
   - Connection pooling for agent API

---

## Appendix: Comparison Matrix

### Current (Ollama) vs. New (terrarium-agent)

| Feature | Ollama (Current) | terrarium-agent (New) |
|---------|------------------|----------------------|
| **Integration** | Direct Python library | HTTP API |
| **Context Management** | Rebuild from DB each time | Hybrid (in-memory + DB) |
| **Conversation Continuity** | ❌ None | ✅ Per-channel tracking |
| **IRC History Access** | Auto-inject only | Auto-inject + tools |
| **Staleness Detection** | ❌ No | ✅ Time-based reset |
| **Multi-turn Conversations** | ❌ Limited | ✅ Full support |
| **Tool Support** | ❌ No | ✅ Planned |
| **Service Isolation** | ❌ Coupled | ✅ Separate process |
| **Scalability** | Limited | Better (stateless server) |
| **Setup Complexity** | Simple (one process) | Moderate (two processes) |

### Database vs. Logfiles

| Aspect | SQLite (Chosen) | Text Logfiles |
|--------|-----------------|---------------|
| **AI Short-term Context** | Fast indexed queries | Parse entire file |
| **AI Long-term Search** | SQL LIKE queries | grep (slower) |
| **Human Debugging** | SQL client, export CSV | grep, awk, tail |
| **Stats/Analytics** | Built-in aggregation | Manual parsing |
| **Storage Efficiency** | Binary (compact) | Text (larger) |
| **Query Complexity** | Full SQL | Limited (grep) |
| **Structured Access** | ✅ Excellent | ❌ Limited |
| **Setup Complexity** | Moderate | Simple |
| **Corruption Resistance** | ACID guarantees | ✅ Append-only safe |

**Decision**: SQLite wins for multi-use case requirements (AI + human analysis + stats)

---

## Change Log

- **2025-11-08**: Initial specification created
- Version 1.0: Planning phase

---

## References

- [terrarium-agent/INTEGRATION.md](file:///home/consulear/Programming/terrarium-agent/INTEGRATION.md)
- [terrarium-agent/AGENT_API.md](file:///home/consulear/Programming/terrarium-agent/AGENT_API.md)
- [terrarium-agent/client_library.py](file:///home/consulear/Programming/terrarium-agent/client_library.py)
- [terrarium-irc/ARCHITECTURE.md](file:///home/consulear/Programming/terrarium-irc/ARCHITECTURE.md)
- [terrarium-irc/DATABASE.md](file:///home/consulear/Programming/terrarium-irc/DATABASE.md)
#### 4. `search_web`

**Purpose**: Fetch up-to-date information from an external search API (Brave, searxng, SerpAPI, etc.).

**Definition**:
```json
{
  "name": "search_web",
  "description": "Search the web for current information when IRC logs aren't enough.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": { "type": "string" },
      "max_results": { "type": "integer", "minimum": 1, "maximum": 10 }
    },
    "required": ["query"]
  }
}
```

**Implementation Notes**:
- Terra-irc calls whatever endpoint is configured via `SEARCH_API_URL` and expects JSON with a `results` array (`title`, `url`, `snippet`).
- Requests are capped at ~5 results by default (`SEARCH_MAX_RESULTS`) to minimize token usage.
- If no endpoint is configured the tool returns an explanatory error.
