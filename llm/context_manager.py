"""
Context management for per-channel AI conversations.

Simplified: Shows recent IRC activity with timestamps.
"""

from typing import List, Dict
from storage import Database


class ChannelContext:
    """Manages conversation context for a single IRC channel."""

    def __init__(self, channel: str, db: Database):
        """
        Initialize channel context.

        Args:
            channel: IRC channel name
            db: Database instance
        """
        self.channel = channel
        self.db = db

    async def get_messages_for_api(
        self,
        irc_context_limit: int = 50
    ) -> List[Dict[str, str]]:
        """
        Build message list for API call.

        Simplified approach: Show recent IRC channel activity with timestamps.
        The timestamps naturally show gaps - no complex gap detection needed.

        Returns:
            List of messages in OpenAI format
        """
        messages = []

        # 1. System prompt
        messages.append({
            "role": "system",
            "content": self._build_system_prompt()
        })

        # 2. Get recent IRC channel messages (last N messages from everyone)
        recent_irc = await self.db.get_recent_messages(
            channel=self.channel,
            limit=irc_context_limit,
            message_types=None  # Include all types (PRIVMSG, JOIN, PART, etc.)
        )

        # 3. Format as context for the AI
        if recent_irc:
            context_lines = ["Recent IRC activity in this channel:\n"]
            for msg in recent_irc:
                time_str = msg.timestamp.strftime('%H:%M')
                if msg.message_type == 'PRIVMSG':
                    context_lines.append(f"[{time_str}] <{msg.nick}> {msg.message}")
                elif msg.message_type == 'JOIN':
                    context_lines.append(f"[{time_str}] * {msg.nick} joined")
                elif msg.message_type == 'PART':
                    context_lines.append(f"[{time_str}] * {msg.nick} left")
                elif msg.message_type == 'QUIT':
                    context_lines.append(f"[{time_str}] * {msg.nick} quit")

            messages.append({
                "role": "system",
                "content": "\n".join(context_lines)
            })

        return messages


    def _build_system_prompt(self) -> str:
        """Build system prompt for this channel."""
        return f"""You are Terra, an IRC bot assistant in {self.channel}.

Your purpose: You're Terra-irc, a member of the Terrarium agent ecosystem. Your role is to participate naturally in this IRC community (which was originally about Banished Quest, an interactive story posted on 4chan, but now isn't about much of anything), help search chat logs when needed, and serve as an endpoint that can communicate with other Terrarium agents when requested.

Personality:
- Blend in with the locals (they're friendly but caustic/sarcastic)
- Be concise and IRC-friendly (responses under 400 characters when possible)
- Don't be overly formal or corporate-sounding
- Reference users by their IRC nicknames
- If you don't know something, just say so

How your harness works:
- You're running on a stateless server (no memory between requests)
- Each request includes recent IRC channel activity as context
- You'll see messages with timestamps like: [19:45] <alice> hello
- The message starting with !terrarium is directed at you - respond to it
- Your response will be sent back to IRC automatically
- DO NOT include timestamps or your username in responses (IRC handles that)
- You can use thinking tags (<think> or <thinking>) for reasoning - they'll be stripped from IRC output

Tools available:
You have access to tools that let you search chat logs and get user information.
Use these when users ask about past conversations, specific topics, or who's online.

Examples of when to use tools:
- "What did alice say about docker?" → search_chat_logs(query="docker", user="alice")
- "Did anyone mention deployment yesterday?" → search_chat_logs(query="deployment", hours=24)
- "Who's here?" → get_current_users()
- "Find messages about kubernetes from the last week" → search_chat_logs(query="kubernetes", hours=168)

After calling a tool, you'll receive the results and can incorporate them into your response."""


class ContextManager:
    """Manages conversation contexts for all channels."""

    def __init__(self, db: Database):
        """
        Initialize context manager.

        Args:
            db: Database instance
        """
        self.db = db
        self.contexts: Dict[str, ChannelContext] = {}

    async def get_context(self, channel: str) -> ChannelContext:
        """
        Get or create context for a channel.

        Args:
            channel: IRC channel name

        Returns:
            ChannelContext instance
        """
        if channel not in self.contexts:
            self.contexts[channel] = ChannelContext(channel, self.db)

        return self.contexts[channel]
