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

        # Create indexes for performance
        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp
            ON messages(timestamp)
        """)

        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_channel
            ON messages(channel)
        """)

        await self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_nick
            ON messages(nick)
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
        hours: Optional[int] = None
    ) -> List[Message]:
        """Get recent messages, optionally filtered by channel and time."""
        query = "SELECT * FROM messages WHERE 1=1"
        params = []

        if channel:
            query += " AND channel = ?"
            params.append(channel)

        if hours:
            cutoff = datetime.now() - timedelta(hours=hours)
            query += " AND timestamp > ?"
            params.append(cutoff)

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
        limit: int = 100
    ) -> List[Message]:
        """Search messages by content."""
        sql = "SELECT * FROM messages WHERE message LIKE ?"
        params = [f"%{query}%"]

        if channel:
            sql += " AND channel = ?"
            params.append(channel)

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

    async def close(self):
        """Close database connection."""
        if self.db:
            await self.db.close()
