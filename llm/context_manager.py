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
        self.conversation_history: List[Dict[str, any]] = []
        self._loaded = False

    async def load(self):
        """Load conversation history from database."""
        if self._loaded:
            return

        history = await self.db.get_conversation_history(self.channel)

        # Convert DB format to API format (preserving tool calls, thinking tags, etc.)
        self.conversation_history = [
            {"role": turn["role"], "content": turn["content"]}
            for turn in history
        ]

        self._loaded = True
        print(f"  Loaded {len(self.conversation_history)} conversation turns for {self.channel}")

    async def get_messages_for_api(
        self,
        irc_context_limit: int = 50
    ) -> List[Dict[str, str]]:
        """
        Build message list for API call.

        Dual-context approach:
        - Recent IRC activity (decorated with timestamps) as system message
        - Clean conversation history (tool calls, thinking preserved)

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

        # 2. Get recent IRC channel messages (last N messages from everyone)
        recent_irc = await self.db.get_recent_messages(
            channel=self.channel,
            limit=irc_context_limit,
            message_types=None  # Include all types (PRIVMSG, JOIN, PART, etc.)
        )

        # 3. Format IRC as context for the AI (decorated - shows "room state")
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

        # 4. Clean conversation history (includes tool calls, thinking tags, etc.)
        messages.extend(self.conversation_history)

        return messages

    async def add_user_message(self, content: str):
        """
        Add user message to conversation.

        Args:
            content: CLEAN message content (no timestamps, no IRC decorations)
        """
        message = {
            "role": "user",
            "content": content
        }

        self.conversation_history.append(message)

        # Save to database
        await self.db.save_conversation_turn(
            channel=self.channel,
            role="user",
            content=content
        )

    async def add_assistant_message(self, content: str):
        """
        Add assistant response to conversation.

        Args:
            content: CLEAN response (WITH thinking tags if present - they'll be stripped for IRC only)
        """
        message = {
            "role": "assistant",
            "content": content
        }

        self.conversation_history.append(message)

        # Save to database
        await self.db.save_conversation_turn(
            channel=self.channel,
            role="assistant",
            content=content
        )

    async def add_tool_call_message(self, message_dict: Dict):
        """
        Add assistant message with tool calls to conversation.

        Args:
            message_dict: Full message dict from API (includes role, content, tool_calls)
        """
        self.conversation_history.append(message_dict)

        # Save to database (serialize tool_calls as JSON)
        import json
        content = message_dict.get("content", "")
        if "tool_calls" in message_dict:
            content = json.dumps(message_dict)  # Store entire message as JSON

        await self.db.save_conversation_turn(
            channel=self.channel,
            role="assistant",
            content=content
        )

    async def add_tool_result(self, tool_result_dict: Dict):
        """
        Add tool result to conversation.

        Args:
            tool_result_dict: Tool result message (role="tool", tool_call_id, name, content)
        """
        self.conversation_history.append(tool_result_dict)

        # Save to database (serialize as JSON)
        import json
        await self.db.save_conversation_turn(
            channel=self.channel,
            role="tool",
            content=json.dumps(tool_result_dict)
        )

    async def clear(self):
        """Clear conversation history."""
        self.conversation_history = []
        await self.db.clear_conversation_history(self.channel)
        print(f"  Cleared conversation history for {self.channel}")

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
            await self.contexts[channel].load()

        return self.contexts[channel]

    async def clear_channel(self, channel: str):
        """
        Clear conversation history for a channel.

        Args:
            channel: IRC channel name
        """
        if channel in self.contexts:
            await self.contexts[channel].clear()
