"""Data models for IRC messages and entities."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    """IRC user representation."""
    nick: str
    user: Optional[str] = None
    host: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


@dataclass
class Channel:
    """IRC channel representation."""
    name: str
    joined_at: Optional[datetime] = None
    message_count: int = 0


@dataclass
class Message:
    """IRC message representation."""
    id: Optional[int] = None
    timestamp: Optional[datetime] = None
    channel: Optional[str] = None
    nick: Optional[str] = None
    user: Optional[str] = None
    host: Optional[str] = None
    message: Optional[str] = None
    message_type: str = 'PRIVMSG'  # PRIVMSG, JOIN, PART, QUIT, etc.

    def to_dict(self):
        """Convert to dictionary."""
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'channel': self.channel,
            'nick': self.nick,
            'user': self.user,
            'host': self.host,
            'message': self.message,
            'message_type': self.message_type
        }

    def to_context_string(self) -> str:
        """Convert to human-readable context string."""
        if self.timestamp:
            time_str = self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            return f"[{time_str}] <{self.nick}> {self.message}"
        return f"<{self.nick}> {self.message}"
