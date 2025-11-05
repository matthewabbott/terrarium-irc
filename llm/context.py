"""Context preparation for LLM queries."""

from typing import List, Optional
from datetime import datetime
from storage.models import Message


class ContextBuilder:
    """Build context from IRC messages for LLM queries."""

    def __init__(self, max_messages: int = 50, max_chars: int = 4000):
        """
        Initialize context builder.

        Args:
            max_messages: Maximum number of messages to include
            max_chars: Maximum total characters in context
        """
        self.max_messages = max_messages
        self.max_chars = max_chars

    def build_context(
        self,
        messages: List[Message],
        channel: Optional[str] = None,
        include_timestamps: bool = True
    ) -> str:
        """
        Build context string from messages.

        Args:
            messages: List of Message objects
            channel: Channel name (for context)
            include_timestamps: Whether to include timestamps

        Returns:
            Formatted context string
        """
        if not messages:
            return "No recent messages available."

        # Limit to max_messages
        messages = messages[-self.max_messages:]

        # Build context
        context_lines = []

        if channel:
            context_lines.append(f"IRC Channel: {channel}")
            context_lines.append(f"Recent conversation ({len(messages)} messages):\n")

        for msg in messages:
            if msg.message:  # Only include messages with content
                if include_timestamps and msg.timestamp:
                    time_str = msg.timestamp.strftime('%H:%M:%S')
                    context_lines.append(f"[{time_str}] <{msg.nick}> {msg.message}")
                else:
                    context_lines.append(f"<{msg.nick}> {msg.message}")

        context = "\n".join(context_lines)

        # Truncate if too long
        if len(context) > self.max_chars:
            context = context[-self.max_chars:]
            # Try to start from a complete line
            first_newline = context.find('\n')
            if first_newline > 0:
                context = context[first_newline + 1:]
            context = "...(context truncated)...\n" + context

        return context

    def build_search_context(
        self,
        search_results: List[Message],
        query: str
    ) -> str:
        """
        Build context from search results.

        Args:
            search_results: List of messages matching search
            query: Search query used

        Returns:
            Formatted context string
        """
        if not search_results:
            return f"No messages found matching '{query}'."

        context_lines = [
            f"Search results for '{query}' ({len(search_results)} messages found):\n"
        ]

        for msg in search_results:
            if msg.message:
                time_str = msg.timestamp.strftime('%Y-%m-%d %H:%M:%S') if msg.timestamp else 'unknown'
                context_lines.append(
                    f"[{time_str}] {msg.channel} <{msg.nick}> {msg.message}"
                )

        return "\n".join(context_lines)

    def build_system_prompt(self, channel: Optional[str] = None) -> str:
        """
        Build system prompt for the LLM.

        Args:
            channel: Channel name (for context)

        Returns:
            System prompt string
        """
        base_prompt = """You are a helpful IRC bot assistant named Terrarium. You have access to the conversation history from an IRC channel and can help answer questions, provide information, or engage in discussion.

Guidelines:
- Be concise and IRC-friendly (avoid very long responses)
- Be helpful, friendly, and respectful
- If you don't know something, say so
- Use the provided IRC context to inform your responses
- Keep responses under 400 characters when possible (IRC convention)"""

        if channel:
            base_prompt += f"\n- You are currently in the channel: {channel}"

        return base_prompt

    def split_long_response(self, response: str, max_length: int = 400) -> List[str]:
        """
        Split a long response into IRC-friendly chunks.

        Args:
            response: Response text to split
            max_length: Maximum length per message

        Returns:
            List of message chunks
        """
        if len(response) <= max_length:
            return [response]

        chunks = []
        current_chunk = ""

        # Split by sentences first
        sentences = response.replace('. ', '.|').replace('! ', '!|').replace('? ', '?|').split('|')

        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= max_length:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        # If still too long, split by words
        final_chunks = []
        for chunk in chunks:
            if len(chunk) <= max_length:
                final_chunks.append(chunk)
            else:
                words = chunk.split()
                current = ""
                for word in words:
                    if len(current) + len(word) + 1 <= max_length:
                        current += " " + word if current else word
                    else:
                        if current:
                            final_chunks.append(current)
                        current = word
                if current:
                    final_chunks.append(current)

        return final_chunks
