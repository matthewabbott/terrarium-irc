"""
Tool execution handlers for Terra's AI capabilities.

Executes tool calls requested by the AI and returns results.
"""

import json
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from storage import Database


class ToolExecutor:
    """Executes tool calls from the AI."""

    def __init__(self, database: 'Database'):
        """
        Initialize tool executor.

        Args:
            database: Database instance for accessing IRC data
        """
        self.database = database

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
