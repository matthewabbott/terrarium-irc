"""Database operations for IRC logs."""

import aiosqlite
from datetime import datetime, timedelta
from typing import List, Optional
from pathlib import Path
from .models import Message, Channel, User


class Database:
    """SQLite database handler for IRC logs."""

    def __init__(self, db_path: str = "./data/irc_logs.db"):
        """Initialize database connection."""
        self.db_path = db_path
        self.db: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """Connect to database and initialize schema."""
        # Ensure data directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db = await aiosqlite.connect(self.db_path)
        await self._init_schema()

    async def _init_schema(self):
        """Initialize database schema."""
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                channel TEXT,
                nick TEXT,
                user TEXT,
                host TEXT,
                message TEXT,
                message_type TEXT DEFAULT 'PRIVMSG'
            )
        """)

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                name TEXT PRIMARY KEY,
                joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                message_count INTEGER DEFAULT 0
            )
        """)

        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                nick TEXT PRIMARY KEY,
                user TEXT,
                host TEXT,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Conversation history for AI context persistence
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                role TEXT NOT NULL,
                content TEXT NOT NULL
            )
        """)

        # Track current users in each channel
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS channel_users (
                channel TEXT NOT NULL,
                nick TEXT NOT NULL,
                joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (channel, nick)
            )
        """)

        # Create indexes for performance
        # Composite index for the most common query: recent messages by channel
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_channel_timestamp
            ON messages(channel, timestamp DESC)
        """)

        # Index for time-based queries across all channels
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp
            ON messages(timestamp DESC)
        """)

        # Index for user message lookups
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_nick
            ON messages(nick)
        """)

        # Index for filtering by message type (e.g., exclude JOIN/PART events)
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_type
            ON messages(message_type)
        """)

        # Index for conversation history queries by channel
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_channel_timestamp
            ON conversation_history(channel, timestamp ASC)
        """)

        await self.db.commit()

    async def log_message(self, msg: Message):
        """Log a message to the database."""
        await self.db.execute("""
            INSERT INTO messages (timestamp, channel, nick, user, host, message, message_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            msg.timestamp or datetime.now(),
            msg.channel,
            msg.nick,
            msg.user,
            msg.host,
            msg.message,
            msg.message_type
        ))
        await self.db.commit()

        # Update channel message count
        if msg.channel:
            await self.db.execute("""
                INSERT INTO channels (name, message_count) VALUES (?, 1)
                ON CONFLICT(name) DO UPDATE SET message_count = message_count + 1
            """, (msg.channel,))
            await self.db.commit()

        # Update user last seen
        if msg.nick:
            await self.db.execute("""
                INSERT INTO users (nick, user, host) VALUES (?, ?, ?)
                ON CONFLICT(nick) DO UPDATE SET
                    user = excluded.user,
                    host = excluded.host,
                    last_seen = CURRENT_TIMESTAMP
            """, (msg.nick, msg.user, msg.host))
            await self.db.commit()

    async def get_recent_messages(
        self,
        channel: Optional[str] = None,
        limit: int = 50,
        hours: Optional[int] = None,
        message_types: Optional[List[str]] = None
    ) -> List[Message]:
        """
        Get recent messages, optionally filtered by channel and time.

        Args:
            channel: Filter by specific channel
            limit: Maximum number of messages to return
            hours: Only return messages from last N hours
            message_types: Filter by message types (default: ['PRIVMSG'] for conversation only)
                          Pass None to include all types including JOIN/PART
        """
        # Default to PRIVMSG only (conversation messages) unless explicitly specified
        if message_types is None:
            message_types = ['PRIVMSG']

        query = "SELECT * FROM messages WHERE 1=1"
        params = []

        if channel:
            query += " AND channel = ?"
            params.append(channel)

        if hours:
            cutoff = datetime.now() - timedelta(hours=hours)
            query += " AND timestamp > ?"
            params.append(cutoff)

        if message_types:
            placeholders = ','.join('?' * len(message_types))
            query += f" AND message_type IN ({placeholders})"
            params.extend(message_types)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with self.db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            messages = []
            for row in rows:
                messages.append(Message(
                    id=row[0],
                    timestamp=datetime.fromisoformat(row[1]) if row[1] else None,
                    channel=row[2],
                    nick=row[3],
                    user=row[4],
                    host=row[5],
                    message=row[6],
                    message_type=row[7]
                ))
            return list(reversed(messages))  # Return in chronological order

    async def search_messages(
        self,
        query: str,
        channel: Optional[str] = None,
        nick: Optional[str] = None,
        hours: Optional[int] = None,
        limit: int = 100,
        message_types: Optional[List[str]] = None,
        search_mode: str = "and"
    ) -> List[Message]:
        """
        Search messages by content.

        Args:
            query: Text to search for (can be phrase, words, or OR-separated with +)
            channel: Filter by specific channel
            nick: Filter by specific user nickname
            hours: Only search messages from last N hours
            limit: Maximum number of messages to return
            message_types: Filter by message types (default: ['PRIVMSG'] for conversation only)
            search_mode: "and" (all words), "or" (any word), "phrase" (exact substring)
        """
        # Default to PRIVMSG only (conversation messages)
        if message_types is None:
            message_types = ['PRIVMSG']

        # Build search condition based on mode
        if search_mode == "phrase":
            # Exact substring match
            sql = "SELECT * FROM messages WHERE message LIKE ?"
            params = [f"%{query}%"]
        elif search_mode == "or":
            # Any word matches (split on +)
            words = [w.strip() for w in query.split('+') if w.strip()]
            conditions = " OR ".join(["message LIKE ?"] * len(words))
            sql = f"SELECT * FROM messages WHERE ({conditions})"
            params = [f"%{word}%" for word in words]
        else:  # "and" mode (default)
            # All words must be present
            words = query.split()
            conditions = " AND ".join(["message LIKE ?"] * len(words))
            sql = f"SELECT * FROM messages WHERE ({conditions})"
            params = [f"%{word}%" for word in words]

        if channel:
            sql += " AND channel = ?"
            params.append(channel)

        if nick:
            sql += " AND nick = ?"
            params.append(nick)

        if hours:
            cutoff = datetime.now() - timedelta(hours=hours)
            sql += " AND timestamp > ?"
            params.append(cutoff)

        if message_types:
            placeholders = ','.join('?' * len(message_types))
            sql += f" AND message_type IN ({placeholders})"
            params.extend(message_types)

        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with self.db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            messages = []
            for row in rows:
                messages.append(Message(
                    id=row[0],
                    timestamp=datetime.fromisoformat(row[1]) if row[1] else None,
                    channel=row[2],
                    nick=row[3],
                    user=row[4],
                    host=row[5],
                    message=row[6],
                    message_type=row[7]
                ))
            return list(reversed(messages))

    async def get_channel_stats(self, channel: str) -> dict:
        """Get statistics for a channel."""
        async with self.db.execute("""
            SELECT
                COUNT(*) as total_messages,
                COUNT(DISTINCT nick) as unique_users,
                MIN(timestamp) as first_message,
                MAX(timestamp) as last_message
            FROM messages
            WHERE channel = ?
        """, (channel,)) as cursor:
            row = await cursor.fetchone()
            return {
                'total_messages': row[0],
                'unique_users': row[1],
                'first_message': row[2],
                'last_message': row[3]
            }

    async def save_conversation_turn(
        self,
        channel: str,
        role: str,
        content: str
    ):
        """
        Save a conversation turn to history.

        Args:
            channel: IRC channel
            role: 'user', 'assistant', or 'system'
            content: Message content
        """
        await self.db.execute("""
            INSERT INTO conversation_history (channel, role, content)
            VALUES (?, ?, ?)
        """, (channel, role, content))
        await self.db.commit()

    async def get_conversation_history(
        self,
        channel: str
    ) -> List[dict]:
        """
        Get full conversation history for a channel.

        Args:
            channel: IRC channel

        Returns:
            List of conversation turns in chronological order
        """
        async with self.db.execute("""
            SELECT timestamp, role, content
            FROM conversation_history
            WHERE channel = ?
            ORDER BY timestamp ASC
        """, (channel,)) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "timestamp": datetime.fromisoformat(row[0]) if row[0] else None,
                    "role": row[1],
                    "content": row[2]
                }
                for row in rows
            ]

    async def clear_conversation_history(self, channel: str):
        """Clear conversation history for a channel."""
        await self.db.execute("""
            DELETE FROM conversation_history
            WHERE channel = ?
        """, (channel,))
        await self.db.commit()

    async def add_user_to_channel(self, channel: str, nick: str):
        """
        Add user to channel (on JOIN or NAMES).

        Args:
            channel: Channel name
            nick: User nickname
        """
        await self.db.execute("""
            INSERT OR REPLACE INTO channel_users (channel, nick, joined_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (channel, nick))
        await self.db.commit()

    async def remove_user_from_channel(self, channel: str, nick: str):
        """
        Remove user from channel (on PART).

        Args:
            channel: Channel name
            nick: User nickname
        """
        await self.db.execute("""
            DELETE FROM channel_users
            WHERE channel = ? AND nick = ?
        """, (channel, nick))
        await self.db.commit()

    async def remove_user_from_all_channels(self, nick: str):
        """
        Remove user from all channels (on QUIT).

        Args:
            nick: User nickname
        """
        await self.db.execute("""
            DELETE FROM channel_users
            WHERE nick = ?
        """, (nick,))
        await self.db.commit()

    async def get_channel_users(self, channel: str) -> List[str]:
        """
        Get list of users currently in a channel.

        Args:
            channel: Channel name

        Returns:
            List of nicknames
        """
        cursor = await self.db.execute("""
            SELECT nick FROM channel_users
            WHERE channel = ?
            ORDER BY nick
        """, (channel,))
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_channel_user_count(self, channel: str) -> int:
        """
        Get count of users in a channel.

        Args:
            channel: Channel name

        Returns:
            Number of users
        """
        cursor = await self.db.execute("""
            SELECT COUNT(*) FROM channel_users
            WHERE channel = ?
        """, (channel,))
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def close(self):
        """Close database connection."""
        if self.db:
            await self.db.close()
