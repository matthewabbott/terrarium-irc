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
    },
    {
        "type": "function",
        "function": {
            "name": "create_enhancement_request",
            "description": "Capture an enhancement request for the maintainer. Saves a markdown file with your summary and the recent IRC context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short name for this enhancement (will be used in the filename)."
                    },
                    "summary": {
                        "type": "string",
                        "description": "Describe the requested change or system-prompt tweak."
                    }
                },
                "required": ["title", "summary"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_enhancement_requests",
            "description": "List the enhancement request files Terra has already created.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_enhancement_request",
            "description": "Read the contents of a previously created enhancement request markdown file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Filename (from list_enhancement_requests) to inspect."
                    }
                },
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for up-to-date information when IRC history is insufficient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keywords (e.g., 'python asyncio tutorial')."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (1-10).",
                        "minimum": 1,
                        "maximum": 10
                    }
                },
                "required": ["query"]
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
