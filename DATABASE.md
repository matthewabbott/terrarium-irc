# Database Design Documentation

## Overview

The Terrarium IRC bot uses SQLite to store IRC channel logs, user information, and channel metadata. The database is designed to be easily queryable by LLM agents for context retrieval.

## Design Principles

1. **Agent-First Design**: The schema prioritizes queries that LLM agents will need to make:
   - Get recent messages from a channel
   - Search historical messages
   - Filter by timeframe
   - Exclude noise (JOIN/PART events)

2. **Performance**: Composite indexes optimize the most common query patterns

3. **Completeness**: All identifying information is preserved (who said what, when, where)

4. **Simplicity**: Flat schema, no complex joins needed for basic queries

## Schema

### Messages Table

The core table storing all IRC events and messages.

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    channel TEXT,
    nick TEXT,
    user TEXT,      -- IRC username (from hostmask)
    host TEXT,      -- IRC hostname (from hostmask)
    message TEXT,
    message_type TEXT DEFAULT 'PRIVMSG'
);
```

**Fields:**
- `id`: Auto-incrementing primary key
- `timestamp`: When the message occurred (ISO 8601 format)
- `channel`: Channel name (e.g., `#terrarium`) or target for private messages
- `nick`: User's nickname
- `user`: Username from IRC hostmask (e.g., `~consul` from `consultx!~consul@host`)
- `host`: Hostname from IRC hostmask
- `message`: The actual message text (empty for events like JOIN)
- `message_type`: Type of message/event (`PRIVMSG`, `JOIN`, `PART`, `QUIT`, etc.)

### Channels Table

Metadata about channels the bot has joined.

```sql
CREATE TABLE channels (
    name TEXT PRIMARY KEY,
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    message_count INTEGER DEFAULT 0
);
```

### Users Table

Information about users the bot has seen.

```sql
CREATE TABLE users (
    nick TEXT PRIMARY KEY,
    user TEXT,
    host TEXT,
    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## Indexes

Indexes are optimized for the most common agent query patterns:

```sql
-- Composite index for "get recent messages from channel X"
-- This is THE most important query for LLM context
CREATE INDEX idx_messages_channel_timestamp
ON messages(channel, timestamp DESC);

-- For time-based queries across all channels
CREATE INDEX idx_messages_timestamp
ON messages(timestamp DESC);

-- For user-specific message lookups
CREATE INDEX idx_messages_nick
ON messages(nick);

-- For filtering by message type (e.g., exclude JOIN/PART)
CREATE INDEX idx_messages_type
ON messages(message_type);
```

### Why These Indexes?

1. **`(channel, timestamp DESC)`**: Composite index eliminates temp B-tree for the query pattern:
   ```sql
   SELECT * FROM messages
   WHERE channel = '#terrarium'
   ORDER BY timestamp DESC
   LIMIT 50;
   ```
   This is what agents do 90% of the time.

2. **`timestamp DESC`**: For queries like "show me all messages from the last hour across all channels"

3. **`nick`**: For "show me everything Alice said"

4. **`message_type`**: For efficiently filtering conversation (`PRIVMSG`) vs noise (`JOIN`/`PART`)

## Query Patterns for Agents

### Get Recent Context (Most Common)

```python
# Get last 50 conversation messages from a channel
messages = await db.get_recent_messages(
    channel='#terrarium',
    limit=50,
    message_types=['PRIVMSG']  # Default: excludes JOIN/PART
)
```

### Search Historical Messages

```python
# Find mentions of a topic
results = await db.search_messages(
    query='deployment',
    channel='#terrarium',
    limit=20
)
```

### Time-Based Queries

```python
# Get messages from last 2 hours
recent = await db.get_recent_messages(
    channel='#terrarium',
    hours=2
)
```

## Message Types

- `PRIVMSG`: Regular channel messages (conversation)
- `NOTICE`: Notice messages
- `JOIN`: User joined channel
- `PART`: User left channel
- `QUIT`: User disconnected
- `KICK`: User was kicked
- `MODE`: Channel mode change

**For LLM context**: Default to filtering for `PRIVMSG` only. JOIN/PART events are noise.

## IRC Protocol Handling

### Colon Prefix Issue

The IRC protocol uses `:` to denote "trailing parameters". For example:
```
:consultx!~consul@host PRIVMSG #channel :Hello world
```

The message content is `:Hello world` (with leading colon).

**Solution**: All IRC handlers use `colon=False` parameter in miniirc, which automatically strips this protocol artifact before storing to database.

### Hostmask Parsing

IRC hostmasks have the format: `nick!user@host`

Example: `consultx!~consul@Through.The.Power.Of.Friendship`
- nick: `consultx`
- user: `~consul`
- host: `Through.The.Power.Of.Friendship`

All three components are stored for complete identification.

## Future Considerations

### Potential Enhancements

1. **Full-Text Search**: SQLite FTS5 extension for better message search
2. **Vector Embeddings**: Store embeddings for semantic search
3. **Message Threading**: Track conversation threads/replies
4. **Sentiment/Metadata**: Store derived metadata from messages
5. **Compression**: Archive old messages to reduce database size

### Agent Tool Interface

The database provides these methods designed for agent consumption:

```python
class Database:
    async def get_recent_messages(
        channel: str,
        limit: int = 50,
        hours: Optional[int] = None,
        message_types: Optional[List[str]] = ['PRIVMSG']
    ) -> List[Message]

    async def search_messages(
        query: str,
        channel: Optional[str] = None,
        limit: int = 100,
        message_types: Optional[List[str]] = ['PRIVMSG']
    ) -> List[Message]

    async def get_channel_stats(
        channel: str
    ) -> dict
```

These methods abstract SQL complexity from agents. Agents should never write raw SQL.

## Maintenance

### Backup

Database is stored in `./data/irc_logs.db` (configurable via `DB_PATH` env var).

Backup before schema changes:
```bash
cp ./data/irc_logs.db ./data/irc_logs.db.backup-$(date +%Y%m%d-%H%M%S)
```

### Cleanup

To start fresh (new schema, remove malformed data):
```bash
# Backup first!
mv ./data/irc_logs.db ./data/irc_logs.db.old
# New DB will be created on next bot startup
```

## Related Files

- `storage/database.py` - Database operations and queries
- `storage/models.py` - Data models (Message, Channel, User)
- `storage/__init__.py` - Storage module exports
