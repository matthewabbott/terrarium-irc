"""
Tool definitions for Terra's AI capabilities.

These tools allow Terra to search chat logs, get user lists, and perform
other actions beyond simple text responses.
"""

from typing import List, Dict, Any


# Tool definitions in OpenAI function calling format
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_chat_logs",
            "description": "Search IRC message history for specific content. Use this when users ask about past conversations or specific topics discussed in the channel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text to search for. Can be multiple words (all must match), or use + for OR (e.g., 'docker+kubernetes'), or use quotes for exact phrase."
                    },
                    "user": {
                        "type": "string",
                        "description": "Optional: Filter to only search messages from this specific user nickname"
                    },
                    "hours": {
                        "type": "integer",
                        "description": "Optional: Only search messages from the last N hours (e.g., 24 for last day, 168 for last week)"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_users",
            "description": "Get a list of users currently in the IRC channel. Use this when users ask who's present or online.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]


def get_tool_definitions() -> List[Dict[str, Any]]:
    """
    Get all available tool definitions.

    Returns:
        List of tool definitions in OpenAI function calling format
    """
    return TOOLS
