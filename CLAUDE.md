# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Terrarium is an IRC bot with local LLM integration designed for the NVIDIA DGX Spark. It logs IRC conversations to SQLite and provides context-aware AI responses using terrarium-agent HTTP server.

**Key Feature**: Agent-first architecture designed to support future multi-agent systems and LLM tool usage.

## Development Commands

### Environment Setup
```bash
# Activate virtual environment (required for all commands)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Bot
```bash
# Start terrarium-agent server first (on port 8080)
# (Refer to terrarium-agent documentation)

# Run the bot (make sure venv is activated)
python main.py

# The bot works without terrarium-agent - LLM commands will fail gracefully
# To enable LLM features: ensure terrarium-agent HTTP server is running at localhost:8080
```

### Database Operations
```bash
# View database schema
sqlite3 ./data/irc_logs.db ".schema"

# Query recent messages
sqlite3 ./data/irc_logs.db "SELECT * FROM messages ORDER BY timestamp DESC LIMIT 10;"

# Backup database
cp ./data/irc_logs.db ./data/irc_logs.db.backup-$(date +%Y%m%d-%H%M%S)
```

### Testing
There are no automated tests yet. Manual testing is done via IRC interaction.

## Architecture

### Three-Layer Design

1. **IRC Layer** (`bot/`)
   - `irc_client.py`: IRC connection, message handling, command routing
   - `commands.py`: Command implementations (help, ping, ask, terrarium, search, stats)
   - Uses `miniirc` library with async handlers
   - **Critical**: All IRC handlers use `colon=False` to strip protocol prefix

2. **Storage Layer** (`storage/`)
   - `database.py`: Agent-friendly data access interface
   - `models.py`: Data models (Message, Channel, User)
   - SQLite with optimized composite indexes for agent queries
   - **Key Methods**: `get_recent_messages()`, `search_messages()`, `get_channel_stats()`

3. **LLM Layer** (`llm/`)
   - `agent_client.py`: terrarium-agent HTTP client with async API
   - `context_manager.py`: Dual-context architecture and persistent conversation memory
   - `tools.py`: Tool definitions for Terra's capabilities
   - `tool_executor.py`: Tool execution handlers (search_chat_logs, get_current_users)

### Agent-First Data Access

The database layer provides **tool-style methods** designed for LLM agent consumption:

```python
# Get recent context (most common pattern)
messages = await db.get_recent_messages(
    channel='#terrarium',
    limit=50,
    message_types=['PRIVMSG']  # Filters out JOIN/PART noise
)

# Search historical messages
results = await db.search_messages(
    query='deployment',
    channel='#terrarium',
    limit=20
)

# Get statistics
stats = await db.get_channel_stats(channel='#terrarium')
```

**Design Principle**: Agents should never write SQL. All data access goes through these abstracted methods.

### Database Optimization

The composite index `idx_messages_channel_timestamp` on `messages(channel, timestamp DESC)` eliminates temp B-tree creation for the most common query pattern (fetching recent messages by channel). This is critical for agent performance.

### Context Management Strategy

**Current Implementation**: Dual-context architecture with persistent conversation memory

Terra-irc maintains TWO separate types of context:

1. **IRC Logs** (public, searchable, decorated):
   - Stored in `messages` table
   - Recent 50 messages auto-fetched and shown as system message
   - Formatted with timestamps: `[20:15] <alice> hello`
   - Shows "room state" - what's visible in the channel
   - Includes JOIN/PART/QUIT events for context

2. **Conversation Memory** (Terra's private memory, clean):
   - Stored in `conversation_history` table (per-channel)
   - Contains Terra's actual conversation with users
   - Clean format (no timestamps or IRC decorations)
   - Includes:
     - User messages (clean text only)
     - Terra's responses (WITH thinking tags preserved)
     - Tool calls Terra has made
     - Tool results Terra has received
   - Persists across bot restarts
   - Can be cleared with `!clear` command

**Why Dual Context?**
- Prevents "context contamination" - Terra's thoughts don't include IRC formatting
- Distinction between "reading room logs" vs "remembering conversation"
- Tool calling history is preserved in conversation memory
- Thinking tags saved in memory but stripped from IRC output

**How `!terrarium` Works**:
1. Fetch recent IRC logs (decorated, as system message)
2. Load conversation history (clean, from database)
3. Add new user message (clean)
4. Send all to terrarium-agent
5. Execute any tool calls, add to conversation
6. Save final response WITH thinking tags to conversation
7. Strip thinking tags and send to IRC

**Future Vision**: Multi-agent coordination
- Terra communicating with other Terrarium agents
- Shared knowledge across agent ecosystem
- Cross-agent tool calling

## IRC Protocol Handling

### Colon Prefix Issue
IRC protocol uses `:` prefix for trailing parameters:
```
:nick!user@host PRIVMSG #channel :Hello world
```

The message is `:Hello world` (with leading colon). **Solution**: All handlers use `colon=False` parameter in miniirc handlers to automatically strip this.

### Event Loop Management
`miniirc` runs in its own thread. All async operations use `asyncio.run_coroutine_threadsafe()` to safely interact with the main event loop stored in `bot.loop`.

## Configuration

Environment variables are loaded from `.env` (see `.env.example`):

**IRC Settings**:
- `IRC_SERVER`, `IRC_PORT`, `IRC_USE_SSL`, `IRC_NICK`, `IRC_CHANNELS`

**Agent Settings**:
- `AGENT_API_URL` (default: `http://localhost:8080`)
- `AGENT_TEMPERATURE`, `AGENT_MAX_TOKENS`

**Bot Settings**:
- `COMMAND_PREFIX` (default: `!`)
- `MAX_CONTEXT_MESSAGES` (default: 20)

**Tuning IRC Context Size** (`MAX_CONTEXT_MESSAGES`):
- Controls how many recent IRC messages are fetched and shown to Terra
- Lower (10-20): Faster, less tokens, relies on the automatic summaries
- Higher (40-60): More raw IRC history, slower, higher token cost
- Above ~60 is rarely needed because older turns are summarized automatically

## Command System

Commands are registered in `CommandHandler.register_all()` and routed by `TerrariumBot._handle_command()`.

**Available Commands**:
- `!help [command]` - Show all commands or help for specific command
- `!ping` - Bot health check
- `!terrarium <question>` / `!ask <question>` - Query Terra with persistent conversation context
- `!search <term>` - Search message history
- `!stats` - Show channel statistics
- `!who` - Show users currently in channel
- `!clear` - Clear Terra's conversation memory for this channel
- `!compact` - Force Terra to summarize older context and shrink the prompt

**Adding New Commands**:
1. Add method to `CommandHandler` class
2. Add description to `COMMAND_HELP` dict
3. Register in `register_all()` method

## LLM Response Formatting

Responses are split into IRC-friendly chunks by `ContextBuilder.split_long_response()`:
- Max 400 characters per message
- Splits by sentences first, then words if needed
- Avoids flooding with 0.5s delay between chunks

## Enhancement Requests

Terra has three tools for tracking her own wish-list:
- `create_enhancement_request(title, summary)` — writes a markdown file (with the last ~20 IRC messages) to `data/enhancements/` and is capped at 10 concurrent files
- `list_enhancement_requests()` — enumerates the existing markdown files
- `read_enhancement_request(filename)` — returns the contents of a specific file

If `SEARCH_API_URL` is configured, Terra also gets `search_web(query, max_results?)`, which hits the configured endpoint (typically searx/Brave/SerpAPI) and returns structured title/url/snippet results.

These files are gitignored but should be backed up with the rest of `data/`. When editing tooling or prompts, keep the limit logic (`ToolExecutor.MAX_ENHANCEMENTS`) in mind.

## Common Development Patterns

### Adding New Data Access Methods
When adding new database queries for agents, follow the pattern:
1. Add method to `Database` class with clear docstring
2. Use sensible defaults (e.g., `message_types=['PRIVMSG']` to filter noise)
3. Return `List[Message]` for consistency
4. Add appropriate indexes if needed

### Working with IRC Events
All IRC event handlers follow this pattern:
```python
@self.irc.Handler("EVENT_TYPE", colon=False)
def handle_event(irc, hostmask, args):
    # Extract data
    # Use asyncio.run_coroutine_threadsafe() for async operations
    asyncio.run_coroutine_threadsafe(
        self._async_method(...),
        self.loop
    )
```

### Message Type Filtering
- `PRIVMSG`: Regular conversation (default for agent queries)
- `JOIN`, `PART`, `QUIT`: User events (usually filtered out)
- `NOTICE`: Server/bot notices
- Pass `message_types=None` to include all types

## Known Issues & Gotchas

1. **Nickname conflicts**: If `IRC_NICK` is taken, bot will fail to connect. Change in `.env`.
2. **terrarium-agent not required**: Bot runs without terrarium-agent server, but `!terrarium` won't work.
3. **Thread safety**: IRC runs in separate thread - always use `run_coroutine_threadsafe()` for async ops.
4. **Message order**: Database returns DESC, but methods reverse to chronological for LLM context.
5. **Dual contexts**: Remember IRC logs (decorated) vs conversation memory (clean) - see Context Management Strategy.
6. **Thinking tags**: Saved in conversation_history but stripped from IRC output - Terra can reference past reasoning.
7. **Tool call persistence**: All tool calls and results are saved to conversation_history and persist across restarts.
8. **Context contamination**: User messages in conversation memory are CLEAN (no timestamps/decorations).

## Related Documentation

- `ARCHITECTURE.md` - Detailed architectural vision and agent design philosophy
- `DATABASE.md` - Database schema, indexes, and query patterns
- `README.md` - User-facing setup and usage guide
- `PYTHON_SETUP.md` - Python environment best practices
- `INSTALL.md` - Installation guide
