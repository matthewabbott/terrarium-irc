# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Terrarium is an IRC bot with local LLM integration designed for the NVIDIA DGX Spark. It logs IRC conversations to SQLite and provides context-aware AI responses using Ollama.

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
# Run the bot (make sure venv is activated)
python main.py

# The bot works without Ollama - LLM commands will fail gracefully
# To enable LLM features: install Ollama and pull a model
./setup_ollama.sh
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
   - `client.py`: Ollama integration with async API
   - `context.py`: Context formatting for LLM consumption

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

**Current Implementation**: Automatic context injection
- `.terrarium` command auto-fetches last 50 PRIVMSG from channel
- Formatted as chronological chat log with timestamps
- Passed to LLM along with user's question

**Future Vision**: Multi-agent architecture with explicit tool calls
- Context Manager Agent decides what context to fetch
- Research Agent can deep-dive into history
- IRC Ambassador Agent coordinates responses

Infrastructure for this exists but isn't yet exposed to LLM agents.

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

**LLM Settings**:
- `LLM_MODEL` (default: `qwen2.5:7b`)
- `LLM_API_URL` (default: `http://localhost:11434`)
- `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`

**Bot Settings**:
- `COMMAND_PREFIX` (default: `.`)
- `MAX_CONTEXT_MESSAGES` (default: 50)

**Tuning Context Size**:
- Lower (20-30): Faster, less tokens, might miss context
- Higher (100-200): More context, slower, higher token cost
- Sweet spot (50): Good balance for most conversations

## Command System

Commands are registered in `CommandHandler.register_all()` and routed by `TerrariumBot._handle_command()`.

**Available Commands**:
- `.help [command]` - Show all commands or help for specific command
- `.ping` - Bot health check
- `.ask <question>` - Query LLM without IRC context
- `.terrarium <question>` - Query LLM with full channel context
- `.search <term>` - Search message history
- `.stats` - Show channel statistics

**Adding New Commands**:
1. Add method to `CommandHandler` class
2. Add description to `COMMAND_HELP` dict
3. Register in `register_all()` method

## LLM Response Formatting

Responses are split into IRC-friendly chunks by `ContextBuilder.split_long_response()`:
- Max 400 characters per message
- Splits by sentences first, then words if needed
- Avoids flooding with 0.5s delay between chunks

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
2. **Ollama not required**: Bot runs without Ollama, but `.ask` and `.terrarium` commands won't work.
3. **Thread safety**: IRC runs in separate thread - always use `run_coroutine_threadsafe()` for async ops.
4. **Context truncation**: `ContextBuilder` truncates at 4000 chars. Adjust `max_chars` if needed.
5. **Message order**: Database returns DESC, but methods reverse to chronological for LLM context.

## Related Documentation

- `ARCHITECTURE.md` - Detailed architectural vision and agent design philosophy
- `DATABASE.md` - Database schema, indexes, and query patterns
- `README.md` - User-facing setup and usage guide
- `PYTHON_SETUP.md` - Python environment best practices
- `INSTALL.md` - Installation guide
