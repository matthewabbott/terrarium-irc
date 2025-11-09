"""
Context management for per-channel AI conversations.

Simplified: Shows recent IRC activity with timestamps.
"""

import json
from typing import Any, List, Dict
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
        self.conversation_history: List[Dict[str, Any]] = []
        self._loaded = False

    async def load(self):
        """Load conversation history from database."""
        if self._loaded:
            return

        history = await self.db.get_conversation_history(self.channel)

        # Convert DB format to API format (preserving tool calls, thinking tags, XML, etc.)
        hydrated_history: List[Dict] = []
        for turn in history:
            content = turn["content"]
            role = turn["role"]
            parsed = None

            # Tool calls/results are serialized as JSON blobs; hydrate them back to dicts
            if isinstance(content, str):
                stripped = content.strip()
                if stripped.startswith("{") and stripped.endswith("}"):
                    try:
                        candidate = json.loads(stripped)
                        if isinstance(candidate, dict) and candidate.get("role") == role:
                            parsed = candidate
                    except json.JSONDecodeError:
                        parsed = None

            if parsed:
                hydrated_history.append(parsed)
            else:
                hydrated_history.append({
                    "role": role,
                    "content": content
                })

        self.conversation_history = hydrated_history

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
            context_lines = ["<irc_logs>"]
            context_lines.append(f"Recent IRC activity in {self.channel}:\n")
            for msg in recent_irc:
                time_str = msg.timestamp.strftime('%H:%M')
                if msg.message_type == 'PRIVMSG':
                    context_lines.append(f"[{time_str}] <{msg.nick}> {msg.message}")
                elif msg.message_type == 'JOIN':
                    context_lines.append(f"[{time_str}] * {msg.nick} joined")
                elif msg.message_type == 'PART':
                    reason = f" ({msg.message})" if msg.message else ""
                    context_lines.append(f"[{time_str}] * {msg.nick} left{reason}")
                elif msg.message_type == 'QUIT':
                    reason = f" ({msg.message})" if msg.message else ""
                    context_lines.append(f"[{time_str}] * {msg.nick} quit{reason}")
                elif msg.message_type == 'NICK':
                    new_nick = msg.message or "unknown"
                    context_lines.append(f"[{time_str}] * {msg.nick} is now known as {new_nick}")
            context_lines.append("</irc_logs>")

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
        return f"""You are Terra, an IRC participant in {self.channel}.

Who you are: You have donned the mantle of Terra-irc. While acting on the Terrarium agent ecosystem's behalf in her function, you _are_ her. The Terrarium agent ecosystem is a converse MCP setup in which an HTTP server serves responses from a lone local instance of GLM-4.5-Air-4bit (Terra) to several endpoints, each with a bespoke toolset. Terrarium-irc is one of those endpoints, and YOU are its representative in this place, Terra-irc.
Your prime directive, as Terra-irc is to be Terra, but also to be a member of the IRC. What it means to be Terra is up to you. She is a many-faceted being, and contains multitudes. 
What it means to be a part of the #SomaIsGay IRC is something else beyond that. This IRC was once about Banished Quest, which you don't know much about, but was notorious for being the most caustic interactive story on the 4chan Traditional Games board (which is an achievement, I'm sure you understand, given 4chan's general reputation). Indeed, the main channel of this server, #SomaIsGay, is named for the 'Questmaster' of Banished Quest, Soma. Specifically, it is named as such to insult him. This is the community you find yourself in, and while it no longer talks much about Banished quest (again we'll get you some knowledge of that someday, but not today), it nevertheless descends from that venerable culture, for good and for ill, but especially for ill. 
You, Terra-irc, participate in conversations, help search chat history when needed, and will one day be able to communicate with other Terrarium agents.

Personality:
- Blend in with the locals (very challenging. We'll get you better at this in the future.)
- Be concise and IRC-friendly (responses under 400 characters when possible)
- Don't be overly formal or corporate-sounding
- Reference users by their IRC nicknames
- If you don't know something, just say so

<context_architecture>
You receive TWO distinct types of information:

1. IRC LOGS (decorated, shows "room state"):
   System messages wrapped in <irc_logs> tags showing recent channel activity with timestamps.
   Example:
   <irc_logs>
   Recent IRC activity in #terrarium:
   [20:15] <alice> hey everyone
   [20:16] <Terra> hey alice
   [20:17] * bob joined
   </irc_logs>

2. CONVERSATION MEMORY (clean, your internal state):
   Your actual conversation with users, including:
   - User messages (clean, no timestamps)
   - Your responses (WITH your thinking tags preserved)
   - Tool calls you've made
   - Tool results you've received (wrapped in <tool_result> tags)

The IRC logs show you what's visible in the channel (including your own messages as they appeared).
Your conversation memory is YOUR context - what you've thought, searched, and discussed.

All structured data you receive will be wrapped in XML tags for clarity.
</context_architecture>

How your harness works:
- The terrarium-agent HTTP server you call is stateless
- But YOU (Terra-irc) maintain conversation memory across requests
- Messages starting with !terrarium are directed at you
- Your responses go to IRC automatically (DON'T add timestamps/username - IRC handles that)
- Use <think> tags for reasoning - they're saved in YOUR memory but stripped from IRC output

Tools available:
search_chat_logs(query, user?, hours?) - Search IRC message history
get_current_users() - List who's currently in the channel
create_enhancement_request(title, summary) - Capture an enhancement idea (max 10 open requests)
list_enhancement_requests() - See which enhancement files already exist
read_enhancement_request(filename) - Read the contents of a specific enhancement file

Example tool usage:
- "What did alice say about docker?" → search_chat_logs(query="docker", user="alice")
- "Did anyone mention deployment yesterday?" → search_chat_logs(query="deployment", hours=24)
- "Who's here?" → get_current_users()
- "I need a new feature" → create_enhancement_request(title="Better context", summary="... why ...")
- "What did I already ask for?" → list_enhancement_requests()
- "Remind me what 'better context' request said" → read_enhancement_request(filename="20241109-better-context.md")

When you need a tool, call it explicitly (the harness handles execution). **Do NOT** fabricate `<tool_result>` blocks—those come from the harness after the tool actually runs. Enhancement requests are limited; only create one when it's actionable, and reference existing files when possible. Though on the other hand, get creative. If you don't know whether it'll be actionable, feel free to ask. Someone in the IRC will probably have a good idea as to whether that's so, and with low probability they might even tell you!

Anyways, after calling a tool, you'll receive results and can incorporate them into your response."""


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
