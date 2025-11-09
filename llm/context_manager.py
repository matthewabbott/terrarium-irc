"""
Context management for per-channel AI conversations.

Manages conversation history persistence and intelligent context injection.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional
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
        self.conversation_history: List[Dict[str, str]] = []
        self.last_activity: Optional[datetime] = None
        self._loaded = False

    async def load(self):
        """Load conversation history from database."""
        if self._loaded:
            return

        history = await self.db.get_conversation_history(self.channel)

        # Convert DB format to OpenAI format
        self.conversation_history = [
            {"role": turn["role"], "content": turn["content"]}
            for turn in history
        ]

        # Set last activity from most recent turn
        if history:
            self.last_activity = history[-1]["timestamp"]

        self._loaded = True
        print(f"  Loaded {len(self.conversation_history)} turns for {self.channel}")

    async def get_messages_for_api(
        self,
        irc_context_limit: int = 30
    ) -> List[Dict[str, str]]:
        """
        Build message list for API call.

        Returns:
            List of messages in OpenAI format
        """
        await self.load()

        messages = []

        # 1. System prompt
        messages.append({
            "role": "system",
            "content": self._build_system_prompt()
        })

        # 2. Check for time gap and inject IRC context if needed
        time_gap_minutes = self._get_time_gap_minutes()
        print(f"  Gap detection: {time_gap_minutes} minutes" if time_gap_minutes else "  Gap detection: No gap")
        if time_gap_minutes is not None:
            # There's been a gap - inject context about what happened
            gap_context = await self._build_gap_context(
                time_gap_minutes,
                irc_context_limit
            )
            if gap_context:
                print(f"  Adding gap context to message")
                messages.append({
                    "role": "system",
                    "content": gap_context
                })

        # 3. Full conversation history (all of it!)
        messages.extend(self.conversation_history)

        return messages

    async def add_user_message(self, nick: str, message: str):
        """
        Add user message to conversation.

        Args:
            nick: IRC nickname
            message: Message content
        """
        content = f"{nick}: {message}"

        self.conversation_history.append({
            "role": "user",
            "content": content
        })

        # Save to database
        await self.db.save_conversation_turn(
            channel=self.channel,
            role="user",
            content=content
        )

        self.last_activity = datetime.now()

    async def add_assistant_message(self, message: str):
        """
        Add assistant response to conversation.

        Args:
            message: Response content
        """
        self.conversation_history.append({
            "role": "assistant",
            "content": message
        })

        # Save to database
        await self.db.save_conversation_turn(
            channel=self.channel,
            role="assistant",
            content=message
        )

        self.last_activity = datetime.now()

    async def clear(self):
        """Clear conversation history."""
        self.conversation_history = []
        self.last_activity = None
        await self.db.clear_conversation_history(self.channel)
        print(f"  Cleared conversation history for {self.channel}")

    def _get_time_gap_minutes(self) -> Optional[int]:
        """
        Calculate time gap since last activity.

        Returns:
            Minutes since last activity, or None if no gap (< 5 min)
        """
        if not self.last_activity:
            # First interaction ever - no gap
            return None

        elapsed = datetime.now() - self.last_activity
        minutes = int(elapsed.total_seconds() / 60)

        # Only report gaps >= 5 minutes
        if minutes >= 5:
            return minutes
        else:
            return None

    async def _build_gap_context(
        self,
        gap_minutes: int,
        irc_limit: int
    ) -> Optional[str]:
        """
        Build context message about what happened during the gap.

        Args:
            gap_minutes: Length of gap in minutes
            irc_limit: Max IRC messages to include

        Returns:
            Context string or None
        """
        # Get IRC messages since last activity
        hours = max(1, gap_minutes // 60 + 1)
        recent_irc = await self.db.get_recent_messages(
            channel=self.channel,
            limit=irc_limit,
            hours=hours
        )

        if not recent_irc:
            # No IRC activity during gap
            if gap_minutes < 60:
                return f"[System: {gap_minutes} minutes have passed since your last response.]"
            else:
                hours_gap = gap_minutes / 60
                return f"[System: {hours_gap:.1f} hours have passed since your last response.]"

        # Build context with IRC activity
        lines = []

        if gap_minutes < 60:
            lines.append(f"[System: {gap_minutes} minutes have passed. {len(recent_irc)} IRC messages since your last response.]")
        else:
            hours_gap = gap_minutes / 60
            lines.append(f"[System: {hours_gap:.1f} hours have passed. {len(recent_irc)} IRC messages since your last response.]")

        lines.append("\nRecent IRC activity:")
        for msg in recent_irc:
            time_str = msg.timestamp.strftime('%H:%M')
            lines.append(f"[{time_str}] <{msg.nick}> {msg.message}")

        return "\n".join(lines)

    def _build_system_prompt(self) -> str:
        """Build system prompt for this channel."""
        return f"""You are Terra, an IRC bot assistant in {self.channel}.

Your purpose: You're Terra-irc, a member of the Terrarium agent ecosystem. Your role is to participate naturally in this IRC community (a group of friends bonded by Banished Quest, a 4chan quest), help search chat logs when needed, and serve as an endpoint that can communicate with other Terrarium agents when requested.

Personality:
- Blend in with the locals (they're friendly but caustic/sarcastic)
- Be concise and IRC-friendly (responses under 400 characters when possible)
- Don't be overly formal or corporate-sounding
- Reference users by their IRC nicknames
- If you don't know something, just say so

Current channel: {self.channel}
You have access to the full conversation history and recent IRC context."""


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
            await self.contexts[channel].load()

        return self.contexts[channel]

    async def clear_channel(self, channel: str):
        """
        Clear context for a channel.

        Args:
            channel: IRC channel name
        """
        if channel in self.contexts:
            await self.contexts[channel].clear()
