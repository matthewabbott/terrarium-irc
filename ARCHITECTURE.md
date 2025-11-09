# Agent Architecture Plan

## Vision

Build an IRC bot with LLM integration that can intelligently participate in conversations by accessing channel history and context. The bot should be easy to extend toward more sophisticated agent architectures (agent swarms, always-on context management, etc.).

## Architectural Pattern: Inverted MCP

**Current State (November 2024):**

We've implemented an interesting architectural pattern that's essentially an **inverted Model Context Protocol (MCP)**:

**Traditional MCP:**
- Multiple LLM clients (different apps/services)
- Connect to multiple MCP servers (tool providers)
- Each client can access many tool servers

**Our Pattern (Inverted MCP):**
- **One LLM server** (terrarium-agent HTTP server)
- **Multiple harnesses** (terrarium-irc, future: terrarium-web, terrarium-cron, etc.)
- Each harness provides **different tools** to the same underlying LLM
- Each harness maintains its own **context and state**

**Why This Pattern?**

This creates specialized agent "tendrils" from a single intelligence:
- Terra-irc: Has IRC-specific tools (search_chat_logs, get_current_users)
- Terra-web: Could have web-scraping tools, database queries
- Terra-cron: Could have scheduling tools, system monitoring

All using the same LLM (e.g., GLM-4.5-Air-4bit), but with different:
- Tool sets (defined per harness)
- Context (IRC logs vs web data vs system logs)
- Personalities (system prompts)
- Memory (separate conversation histories)

**Benefits:**
- Single LLM deployment handles multiple agent roles
- Efficient GPU utilization (one model serves many agents)
- Consistent intelligence across different domains
- Easy to add new "tendrils" without deploying new models

**Future:**
- These tendrils could communicate via MCP (Terra-irc exposing IRC as MCP server)
- Multi-agent coordination while sharing underlying intelligence
- "Swarm of tendrils" from one neural core

**Note:** This is worth documenting/blogging about as it's a novel pattern we haven't seen elsewhere.

## Design Philosophy

### Agent-First Thinking

The codebase is designed with the assumption that **agents will consume the data**. This means:

1. **Tool-based interface** over raw SQL access
2. **Clean abstractions** that won't break when implementation changes
3. **Sensible defaults** that match how humans think about chat history
4. **Composable operations** that agents can chain together

### Hybrid Approach

We use a **hybrid model** for context management:

1. **Automatic (default)**: `.terrarium` auto-injects recent channel context
2. **Tool-based (when needed)**: Agent can explicitly request more context via tools

This balances simplicity with flexibility.

## Current Implementation: .terrarium Command

### How It Works

```
User: .terrarium what did Alice say about the bug?

1. Bot receives command
2. Automatically fetches last 50 messages from channel
3. Includes this as context in LLM prompt
4. LLM responds with context-aware answer
```

### Implementation

Located in `bot/commands.py`:

```python
async def cmd_terrarium(bot, channel, nick, args):
    # Get recent context (last 50 messages)
    context = await bot.get_recent_context(channel, limit=50)

    # Build system prompt
    system_prompt = bot.context_builder.build_system_prompt(channel)

    # Generate response with context
    response = await bot.llm_client.generate(
        prompt=args,
        system_prompt=system_prompt,
        context=context
    )
```

**Key Points:**
- Default: 50 messages, PRIVMSG only (no JOIN/PART noise)
- Context is formatted as human-readable chat log
- LLM sees: `[timestamp] <nick> message`

## Tool Interface Design

### Core Principle

**Agents should never write SQL.** They interact through well-defined tools that abstract storage details.

### Tool Methods

These methods in `storage/database.py` define the agent tool interface:

```python
# Get recent messages
await db.get_recent_messages(
    channel='#terrarium',      # Which channel
    limit=50,                   # How many messages
    hours=None,                 # Time filter (optional)
    message_types=['PRIVMSG']   # Filter types (default: conversation only)
)

# Search for specific content
await db.search_messages(
    query='deployment',         # What to search for
    channel='#terrarium',       # Where to search (optional)
    limit=100,                  # How many results
    message_types=['PRIVMSG']   # Filter types
)

# Get channel statistics
await db.get_channel_stats(
    channel='#terrarium'
)
```

### Why These Tools?

These match **natural language queries** users might ask:

| User Query | Tool Call |
|------------|-----------|
| "What did Alice say about X?" | `search_messages(query="X", ...)` |
| "What happened in the last hour?" | `get_recent_messages(hours=1)` |
| "Show me recent discussion" | `get_recent_messages(limit=50)` |

## Context Management Strategy

### Automatic Context (Current)

**When:** User invokes `.terrarium`

**What:** Bot automatically fetches:
- Last 50 PRIVMSG messages from current channel
- Formatted as chronological chat log
- Includes timestamps and nicknames

**Why:**
- Simple for users
- Covers 90% of use cases
- Consistent token usage

**Implementation:** `bot/irc_client.py:get_recent_context()`

### Explicit Tool Calls (Future)

**When:** Agent needs different context than default

**Examples:**
```python
# Agent needs more history
context = await get_recent_messages(limit=200)

# Agent needs older messages
context = await search_messages("topic", limit=50)

# Agent needs cross-channel context
ctx1 = await get_recent_messages(channel='#dev')
ctx2 = await get_recent_messages(channel='#ops')
```

**Status:** Infrastructure exists, not yet exposed to LLM agents

## Message Formatting

### For LLM Context

Messages are formatted via `Message.to_context_string()`:

```
[2025-11-04 21:10:18] <consultx> .ping
[2025-11-04 21:10:16] <consultx> .help ping
[2025-11-04 21:09:57] <consultx> .help
```

**Design decisions:**
- Chronological order (oldest first)
- Timestamps for temporal reasoning
- Nickname clearly marked with `<>`
- Simple format that LLMs understand intuitively

### Context Builder

Located in `llm/context.py`:

```python
class ContextBuilder:
    def build_context(messages: List[Message], channel: str) -> str:
        """Format messages as LLM-readable context"""

    def build_system_prompt(channel: str) -> str:
        """Create system prompt with channel info"""

    def build_search_context(results, query) -> str:
        """Format search results distinctly"""

    def split_long_response(text, max_length=400) -> List[str]:
        """Split LLM output for IRC message limits"""
```

## Future Architecture: Agent Swarms

### Vision

Multiple specialized agents working together:

```
IRC Ambassador Agent
  ├─ Monitors channels
  ├─ Responds to .terrarium
  └─ Has access to context tools

Context Manager Agent
  ├─ Maintains working memory
  ├─ Decides what context is relevant
  └─ Manages token budgets

Research Agent
  ├─ Deep dives into history
  ├─ Can search across time/channels
  └─ Summarizes findings
```

### What's Ready Now

✅ **Storage layer**: Database with agent-friendly interface
✅ **Tool abstraction**: Methods designed for agent consumption
✅ **Message formatting**: LLM-readable chat logs
✅ **Basic context injection**: .terrarium working

### What's Needed for Swarms

⏳ **Agent framework**: Choose/build multi-agent system
⏳ **Inter-agent communication**: Message passing between agents
⏳ **Context handoff**: How agents share information
⏳ **State management**: Persistent agent memory
⏳ **Orchestration**: Coordinator to route tasks to agents

### Migration Path

The current architecture supports this future:

1. **Phase 1 (Current)**: Single agent, automatic context
2. **Phase 2**: Single agent, explicit tool calls
3. **Phase 3**: Multiple agents, shared context
4. **Phase 4**: Agent swarm with specialization

Each phase builds on previous without breaking changes.

## Agent Client & Context Pipeline

### Agent Client (`llm/agent_client.py`)

- Thin async wrapper over the terrarium-agent HTTP server (`/v1/chat/completions`)
- Handles retries/backoff when the shared LLM endpoint is busy
- Exposes both `chat()` and `generate()` for compatibility with older call sites
- Keeps configuration simple: `AGENT_API_URL`, `AGENT_TEMPERATURE`, `AGENT_MAX_TOKENS`

### Dual-Context Manager (`llm/context_manager.py`)

- Maintains per-channel state with TWO streams of information:
  1. `<irc_logs>`: Decorated public feed with timestamps and joins/parts
  2. Conversation memory: Clean assistant/user/tool turns persisted in SQLite
- Rehydrates tool calls/results from JSON when the bot restarts so the LLM keeps full awareness
- Wraps structured sections in XML tags so the model can easily parse them

### Tool Executor (`llm/tool_executor.py`)

- Executes harness-specific tools (`search_chat_logs`, `get_current_users`)
- Returns results wrapped in `<tool_result tool=\"...\">…</tool_result>` tags
- Keeps tool logic close to the storage layer for low-latency lookups
- Future harnesses can add their own executors while still sharing the same LLM server

## Data Flow

```
IRC Message
    ↓
IRC Handler (bot/irc_client.py)
    ↓
Database.log_message() (storage/database.py)
    ↓
SQLite Storage (data/irc_logs.db)

---

User: .terrarium <question>
    ↓
CommandHandler.cmd_terrarium (bot/commands.py)
    ↓
ContextManager.get_messages_for_api()
  ↳ Pulls conversation memory + `<irc_logs>` system message
    ↓
AgentClient.chat(..., tools=llm.tools.get_tool_definitions())
    ↓
If tool_calls → ToolExecutor executes search/get_current_users
    ↓
Tool results appended as `<tool_result>` messages
    ↓
Final assistant reply saved (thinking tags preserved) and stripped before IRC
    ↓
IRC Response ← Send answer back to channel
```

## Minimal Toolset (Now)

For immediate implementation, we keep it simple:

### Single Command: .terrarium

**Behavior:**
1. Fetch last 50 PRIVMSG from current channel
2. Format as chat log
3. Pass to LLM with user's question
4. Return LLM's answer

**That's it.** No complex tool selection, no multi-agent coordination, no explicit tool calls.

### Why Minimal?

- ✅ Proven to work
- ✅ Simple to understand
- ✅ Easy to debug
- ✅ Foundation for future expansion
- ✅ Tests the entire stack (IRC → DB → LLM → IRC)

### What It Validates

This minimal implementation proves:
1. IRC message logging works
2. Database queries are efficient
3. Context formatting is effective
4. LLM integration functions
5. Response handling doesn't flood IRC

Once this is solid, we can add:
- More sophisticated context selection
- Explicit tool calls for agents
- Multi-agent coordination
- Advanced context management

## Configuration

### Environment Variables

```bash
# IRC Configuration
IRC_SERVER=irc.libera.chat
IRC_PORT=6667
IRC_NICK=Terra
IRC_CHANNELS=#terrarium,#test

# Agent Configuration
AGENT_API_URL=http://localhost:8080
AGENT_TEMPERATURE=0.8
AGENT_MAX_TOKENS=512

# Bot Configuration
COMMAND_PREFIX=.
MAX_CONTEXT_MESSAGES=50

# Database
DB_PATH=./data/irc_logs.db
```

### Tuning Context Size

`MAX_CONTEXT_MESSAGES=50` is default. Considerations:

- **Lower (20-30)**: Faster, less token usage, might miss context
- **Higher (100-200)**: More context, slower, higher token cost
- **Sweet spot (50)**: Good balance for most conversations

## Related Documentation

- `DATABASE.md` - Database schema and design decisions
- `README.md` - Project overview and setup
- `bot/commands.py` - Command implementations
- `storage/database.py` - Data access layer
- `llm/context_manager.py` - Dual-context formatting and persistence

## Next Steps

1. ✅ **Fix IRC protocol handling** (colon prefix)
2. ✅ **Optimize database indexes** (composite channel+timestamp)
3. ✅ **Filter JOIN/PART noise** (PRIVMSG only for context)
4. ✅ **Document architecture** (this file)
5. ⏳ **Test .terrarium with real LLM** (ensure terrarium-agent server healthy)
6. ⏳ **Gather usage data** (what context size works best?)
7. ⏳ **Consider explicit tools** (if automatic context insufficient)
8. ⏳ **Explore agent frameworks** (when multi-agent needs arise)
