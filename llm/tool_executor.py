"""
Tool execution handlers for Terra's AI capabilities.

Executes tool calls requested by the AI and returns results.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, TYPE_CHECKING, List

if TYPE_CHECKING:
    from storage import Database


class ToolExecutor:
    """Executes tool calls from the AI."""

    MAX_ENHANCEMENTS = 10
    CONTEXT_MESSAGES = 20

    def __init__(self, database: 'Database'):
        """
        Initialize tool executor.

        Args:
            database: Database instance for accessing IRC data
        """
        self.database = database
        self.enhancement_dir = Path("data/enhancements")
        self.enhancement_dir.mkdir(parents=True, exist_ok=True)

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        channel: str
    ) -> str:
        """
        Execute a tool call and return the result.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments as dictionary
            channel: IRC channel context

        Returns:
            XML-wrapped JSON string with tool execution results
        """
        print(f"  Executing tool: {tool_name} with args: {arguments}")

        if tool_name == "search_chat_logs":
            result = await self._search_chat_logs(arguments, channel)
        elif tool_name == "get_current_users":
            result = await self._get_current_users(arguments, channel)
        elif tool_name == "create_enhancement_request":
            result = await self._create_enhancement_request(arguments, channel)
        elif tool_name == "list_enhancement_requests":
            result = self._list_enhancement_requests()
        elif tool_name == "read_enhancement_request":
            result = self._read_enhancement_request(arguments)
        else:
            result = json.dumps({"error": f"Unknown tool: {tool_name}"})

        # Wrap result in XML tags for clarity
        return f"<tool_result tool=\"{tool_name}\">\n{result}\n</tool_result>"

    async def _search_chat_logs(
        self,
        arguments: Dict[str, Any],
        channel: str
    ) -> str:
        """
        Search IRC message history.

        Args:
            arguments: Tool arguments (query, user, hours)
            channel: IRC channel to search

        Returns:
            JSON string with search results
        """
        query = arguments.get("query", "")
        user = arguments.get("user")
        hours = arguments.get("hours")

        if not query:
            return json.dumps({"error": "query parameter is required"})

        # Determine search mode based on query format
        search_mode = "and"
        if query.startswith('"') and query.endswith('"'):
            query = query[1:-1]
            search_mode = "phrase"
        elif '+' in query:
            search_mode = "or"

        # Execute search
        results = await self.database.search_messages(
            query=query,
            channel=channel,
            nick=user,
            hours=hours,
            limit=10,
            search_mode=search_mode
        )

        # Format results
        if not results:
            return json.dumps({
                "result": "No messages found",
                "count": 0
            })

        messages = []
        for msg in results[:10]:
            messages.append({
                "timestamp": msg.timestamp.strftime('%Y-%m-%d %H:%M') if msg.timestamp else None,
                "nick": msg.nick,
                "message": msg.message
            })

        return json.dumps({
            "result": f"Found {len(results)} messages",
            "count": len(results),
            "messages": messages,
            "query": query,
            "filters": {
                "user": user,
                "hours": hours,
                "mode": search_mode
            }
        })

    async def _get_current_users(
        self,
        arguments: Dict[str, Any],
        channel: str
    ) -> str:
        """
        Get list of users currently in channel.

        Args:
            arguments: Tool arguments (none expected)
            channel: IRC channel

        Returns:
            JSON string with user list
        """
        users = await self.database.get_channel_users(channel)
        count = len(users)

        return json.dumps({
            "result": f"{count} users in {channel}",
            "count": count,
            "users": users
        })

    async def _create_enhancement_request(
        self,
        arguments: Dict[str, Any],
        channel: str
    ) -> str:
        """
        Create a markdown enhancement request with recent IRC context.
        """
        title = (arguments.get("title") or "").strip()
        summary = (arguments.get("summary") or "").strip()

        if not title or not summary:
            return json.dumps({"error": "Both 'title' and 'summary' are required"})

        existing = sorted(self.enhancement_dir.glob("*.md"))
        if len(existing) >= self.MAX_ENHANCEMENTS:
            return json.dumps({
                "error": f"Maximum of {self.MAX_ENHANCEMENTS} enhancement requests reached. Please close or prune existing files.",
                "existing": [path.name for path in existing]
            })

        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-') or "request"
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        filename = f"{timestamp}-{slug}.md"
        filepath = self.enhancement_dir / filename

        recent_messages = await self.database.get_recent_messages(
            channel=channel,
            limit=self.CONTEXT_MESSAGES,
            message_types=None
        )
        recent_messages = list(recent_messages)[::-1]  # chronological

        context_lines: List[str] = []
        for msg in recent_messages:
            time_str = msg.timestamp.strftime('%Y-%m-%d %H:%M') if msg.timestamp else "unknown"
            if msg.message_type == 'PRIVMSG':
                line = f"[{time_str}] <{msg.nick}> {msg.message}"
            elif msg.message_type == 'JOIN':
                line = f"[{time_str}] * {msg.nick} joined"
            elif msg.message_type == 'PART':
                reason = f" ({msg.message})" if msg.message else ""
                line = f"[{time_str}] * {msg.nick} left{reason}"
            elif msg.message_type == 'QUIT':
                reason = f" ({msg.message})" if msg.message else ""
                line = f"[{time_str}] * {msg.nick} quit{reason}"
            elif msg.message_type == 'NICK':
                new_nick = msg.message or "unknown"
                line = f"[{time_str}] * {msg.nick} is now known as {new_nick}"
            else:
                line = f"[{time_str}] * {msg.message_type} event from {msg.nick}"
            context_lines.append(line)

        body = [
            f"# Enhancement: {title}",
            "",
            f"- Created: {datetime.utcnow().isoformat()}Z",
            f"- Channel: {channel}",
            f"- File: {filename}",
            "",
            "## Summary",
            summary,
            "",
            f"## Recent IRC Context (last {len(context_lines)} messages)",
            *(context_lines or ["(No recent context captured)"]),
            ""
        ]

        filepath.write_text("\n".join(body), encoding="utf-8")

        return json.dumps({
            "result": "Enhancement request created",
            "file": filename,
            "messages_captured": len(context_lines)
        })

    def _list_enhancement_requests(self) -> str:
        """List all enhancement request files."""
        files = sorted(self.enhancement_dir.glob("*.md"))
        entries = []
        for path in files:
            try:
                with path.open(encoding="utf-8") as f:
                    first_line = f.readline().strip()
            except UnicodeDecodeError:
                first_line = "(binary or unreadable)"
            title = first_line.lstrip("# ").strip() if first_line.startswith("#") else first_line
            stats = path.stat()
            entries.append({
                "file": path.name,
                "title": title or "(untitled)",
                "modified": datetime.fromtimestamp(stats.st_mtime).isoformat() + "Z",
                "size_bytes": stats.st_size
            })
        return json.dumps({
            "result": f"{len(entries)} enhancement request(s)",
            "requests": entries
        })

    def _read_enhancement_request(self, arguments: Dict[str, Any]) -> str:
        """Return the contents of a specific enhancement request file."""
        filename = (arguments.get("filename") or "").strip()
        if not filename:
            return json.dumps({"error": "filename is required"})

        target = (self.enhancement_dir / filename).resolve()
        base = self.enhancement_dir.resolve()
        if not str(target).startswith(str(base)):
            return json.dumps({"error": "Invalid filename"})

        if not target.exists():
            return json.dumps({"error": f"File '{filename}' not found"})

        content = target.read_text(encoding="utf-8")
        truncated = content if len(content) <= 4000 else content[:4000] + f"... ({len(content)} chars total)"

        return json.dumps({
            "result": "ok",
            "file": filename,
            "content": truncated
        })
