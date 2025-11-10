"""Command handlers for the IRC bot."""

import asyncio
import json
import re
import uuid
from typing import TYPE_CHECKING, Tuple

FALLBACK_TOOL_NAMES = {
    "search_chat_logs",
    "get_current_users",
    "create_enhancement_request",
    "list_enhancement_requests",
    "read_enhancement_request",
    "search_web"
}
_TOOL_RESULT_PATTERN = re.compile(
    r"<tool_result[^>]*>\s*(?P<body>.*?)\s*</tool_result>",
    re.IGNORECASE | re.DOTALL
)
_FUNCTION_CALL_PATTERN = re.compile(
    r"(?P<name>[a-zA-Z_][\w]*)\s*\((?P<args>[^)]*)\)"
)

MODEL_CONTEXT_LIMIT = 8192
MIN_COMPLETION_TOKENS = 128
MAX_COMPLETION_TOKENS = 512
COMPLETION_BUFFER = 256  # reserved for safety
MAX_TOOL_ITERATIONS = 8
TOOL_WARNING_ITERATION = 5


def _coerce_fallback_value(raw: str):
    """Best-effort conversion of textual arg values into native types."""
    value = raw.strip()
    if not value:
        return ""

    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    lowered = value.lower()
    if lowered in {"none", "null"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _parse_fallback_tool_request(content: str):
    """
    Parse textual tool requests like `<tool_result> search_chat_logs(query="x") </tool_result>`
    and turn them into (tool_name, args) tuples.
    """
    if not content:
        return None

    text = content.strip()

    match = _TOOL_RESULT_PATTERN.search(text)
    if match:
        candidate = match.group("body").strip()
    else:
        candidate = text

    func_match = _FUNCTION_CALL_PATTERN.search(candidate)
    if not func_match:
        return None

    tool_name = func_match.group("name")
    if tool_name not in FALLBACK_TOOL_NAMES:
        return None

    args_str = func_match.group("args").strip()
    args = {}
    if args_str:
        for part in re.split(r",(?![^()]*\))", args_str):
            if not part or "=" not in part:
                continue
            key, value = part.split("=", 1)
            args[key.strip()] = _coerce_fallback_value(value.strip())

    return tool_name, args


def _estimate_prompt_tokens(messages):
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total_chars += len(part.get("text", ""))
        else:
            total_chars += len(str(content))
        total_chars += 8  # account for role metadata
    # Rough heuristic: 1 token ≈ 4 characters
    return max(1, total_chars // 4)


def _determine_max_tokens(messages) -> Tuple[int, int]:
    prompt_tokens = _estimate_prompt_tokens(messages)
    available = MODEL_CONTEXT_LIMIT - prompt_tokens - COMPLETION_BUFFER
    if available <= 0:
        max_tokens = 32
    elif available < MIN_COMPLETION_TOKENS:
        max_tokens = max(32, available)
    else:
        max_tokens = min(MAX_COMPLETION_TOKENS, available)
    return max_tokens, prompt_tokens

if TYPE_CHECKING:
    from .irc_client import TerrariumBot


class CommandHandler:
    """Handler for bot commands."""

    # Command descriptions for help system
    COMMAND_HELP = {
        'help': 'Show available commands or get help for a specific command',
        'ping': 'Check if the bot is responsive',
        'terrarium': 'Ask Terra with full IRC channel context and tool access',
        'ask': 'Alias for !terrarium (same behavior, same context + tools)',
        'search': 'Search message history (!search [user:nick] [hours:N] word1 word2 OR "exact phrase" OR word1+word2)',
        'stats': 'Show channel statistics (messages, users, etc.)',
        'who': 'List the users currently in channel',
        'clear': 'Clear Terra\'s conversation memory for this channel',
        'compact': 'Summarize older conversation turns to free up context tokens'
    }

    @staticmethod
    def register_all(bot: 'TerrariumBot'):
        """Register all commands with the bot."""
        bot.register_command('help', CommandHandler.cmd_help)
        bot.register_command('terrarium', CommandHandler.cmd_terrarium)
        bot.register_command('ask', CommandHandler.cmd_terrarium)
        bot.register_command('search', CommandHandler.cmd_search)
        bot.register_command('stats', CommandHandler.cmd_stats)
        bot.register_command('who', CommandHandler.cmd_who)
        bot.register_command('clear', CommandHandler.cmd_clear)
        bot.register_command('compact', CommandHandler.cmd_compact)
        bot.register_command('ping', CommandHandler.cmd_ping)

    @staticmethod
    async def cmd_help(bot: 'TerrariumBot', channel: str, nick: str, args: str):
        """Show help information."""
        print(f"  cmd_help handler called for {nick} in {channel}")

        # If a specific command is requested, show detailed help
        if args:
            command = args.strip().lower()
            if command in CommandHandler.COMMAND_HELP:
                description = CommandHandler.COMMAND_HELP[command]
                bot.send_message(channel, f"{nick}: {bot.command_prefix}{command} - {description}")
            else:
                bot.send_message(channel, f"{nick}: Unknown command '{command}'. Try {bot.command_prefix}help for available commands.")
            return

        # Otherwise, show comma-separated list of commands
        commands = ', '.join(f"{bot.command_prefix}{cmd}" for cmd in sorted(CommandHandler.COMMAND_HELP.keys()))
        bot.send_message(channel, f"{nick}: Available commands: {commands}")

    @staticmethod
    async def cmd_ping(bot: 'TerrariumBot', channel: str, nick: str, args: str):
        """Simple ping command."""
        print(f"  cmd_ping handler called for {nick} in {channel}")
        bot.send_message(channel, f"{nick}: pong!")

    @staticmethod
    async def cmd_terrarium(bot: 'TerrariumBot', channel: str, nick: str, args: str):
        """Ask the LLM with persistent conversation context."""
        if not args:
            bot.send_message(
                channel,
                f"{nick}: Usage: {bot.command_prefix}terrarium <question>"
            )
            return

        # Send thinking message
        bot.send_message(channel, f"{nick}: Thinking...")

        try:
            # Get channel context
            context = await bot.context_manager.get_context(channel)

            # Add current user message - CLEAN (no timestamps, just the content)
            user_content = args  # Just the question, no decorations

            # Save to conversation history
            await context.add_user_message(user_content)
            await context.maybe_summarize(bot.llm_client)

            # Build message list for API (includes recent IRC activity + conversation history)
            messages = await context.get_messages_for_api(
                irc_context_limit=getattr(bot, "max_context_messages", 20)
            )

            # Add to messages for this request
            messages.append({
                "role": "user",
                "content": user_content
            })

            # Import tools
            from llm.tools import get_tool_definitions
            from llm.tool_executor import ToolExecutor

            tools = get_tool_definitions()
            tool_executor = ToolExecutor(bot.database, search_config=getattr(bot, "search_config", {}))

            # Summarize context instead of dumping entire transcript
            irc_context_block = next(
                (msg for msg in messages if msg["role"] == "system" and "<irc_logs>" in msg.get("content", "")),
                None
            )
            irc_lines = irc_context_block["content"].count("\n") if irc_context_block else 0
            irc_chars = len(irc_context_block["content"]) if irc_context_block else 0

            print("\n=== CONTEXT SUMMARY ===")
            print(f"Channel: {channel}")
            print(f"Conversation history turns (including latest user): {len(context.conversation_history)}")
            if irc_context_block:
                print(f"IRC log injected: yes ({irc_lines} lines / {irc_chars} chars)")
            else:
                print("IRC log injected: no")
            print(f"Conversation summary present: {'yes' if context.summary else 'no'}")
            prompt_preview = user_content if len(user_content) <= 200 else user_content[:200] + f"... ({len(user_content)} chars total)"
            print(f"User prompt appended: {prompt_preview}")
            print("=== END CONTEXT SUMMARY ===\n")

            # Tool calling loop - keep calling until we get a final text response
            max_iterations = MAX_TOOL_ITERATIONS
            iteration = 0
            final_response = None
            warning_sent = False

            while iteration < max_iterations:
                iteration += 1
                print(f"\n=== TOOL LOOP ITERATION {iteration} ===")
                if not warning_sent and iteration == TOOL_WARNING_ITERATION:
                    warning_sent = True
                    remaining = max_iterations - iteration + 1
                    bot.send_message(channel, f"{nick}: Still working... ({remaining} tool iterations left)")
                    warning_message = {
                        "role": "system",
                        "content": (
                            f"Tool usage warning: you have {remaining} more tool iterations before the harness stops. "
                            "Please wrap up as soon as possible."
                        )
                    }
                    messages.append(warning_message)
                max_completion_tokens, approx_prompt_tokens = _determine_max_tokens(messages)
                print(f"  Approx prompt tokens: {approx_prompt_tokens}; reserving {max_completion_tokens} for completion.")

                # Call API with tools
                response_message = await bot.llm_client.chat(
                    messages=messages,
                    temperature=0.8,
                    max_tokens=max_completion_tokens,
                    tools=tools
                )

                print(f"  Response type: {response_message.get('role', 'unknown')}")

                tool_calls = response_message.get("tool_calls") or []

                # Fallback: parse textual tool requests when model can't emit structured tool_calls
                if not tool_calls:
                    fallback = _parse_fallback_tool_request(response_message.get("content", ""))
                    if fallback:
                        fallback_name, fallback_args = fallback
                        print(f"  Parsed fallback tool request: {fallback_name} {fallback_args}")
                        tool_calls = [{
                            "id": f"fallback_{uuid.uuid4().hex}",
                            "type": "function",
                            "function": {
                                "name": fallback_name,
                                "arguments": json.dumps(fallback_args)
                            }
                        }]
                        response_message["tool_calls"] = tool_calls
                        response_message.setdefault("metadata", {})["fallback_tool_call"] = True

                # Check if response includes tool calls
                if tool_calls:
                    print(f"  AI wants to call {len(tool_calls)} tool(s)")

                    # Save assistant message with tool calls to conversation history
                    await context.add_tool_call_message(response_message)

                    # Add to messages array for this request
                    messages.append(response_message)

                    # Execute each tool call
                    for tool_call in tool_calls:
                        tool_id = tool_call["id"]
                        tool_name = tool_call["function"]["name"]
                        tool_args_str = tool_call["function"]["arguments"]

                        # Parse arguments
                        try:
                            tool_args = json.loads(tool_args_str)
                        except json.JSONDecodeError:
                            tool_args = {}

                        # Execute tool
                        tool_result = await tool_executor.execute_tool(
                            tool_name=tool_name,
                            arguments=tool_args,
                            channel=channel
                        )

                        # Build tool result message
                        tool_result_message = {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "name": tool_name,
                            "content": tool_result
                        }

                        # Save to conversation history
                        await context.add_tool_result(tool_result_message)

                        # Add to messages array for this request
                        messages.append(tool_result_message)

                        print(f"  Tool result added to conversation")

                    # Continue loop to get AI's response based on tool results
                    continue

                # No tool calls - this is the final response
                final_response = response_message.get("content", "")
                print(f"  Final response received ({len(final_response)} chars)")
                break

            if final_response is None:
                final_response = (
                    "Sorry, I couldn't complete that request because I hit the maximum number of tool iterations. "
                    "Try simplifying the request or ask again."
                )

            thinking_present = bool(re.search(r'<think(?:ing)?>|<thin>|<thought', final_response, flags=re.IGNORECASE))

            print(f"\n=== RAW RESPONSE FROM API ===")
            print(f"{final_response}")
            print(f"=== END RAW RESPONSE ===\n")
            print(f"  Contains thinking tags: {'yes' if thinking_present else 'no'}")

            # Save to conversation history (WITH thinking tags - they're part of Terra's memory)
            await context.add_assistant_message(final_response)

            # Strip thinking tags from response (internal reasoning shouldn't go to IRC)
            # Strip all thinking tag variants: <think>, <thinking>, <thought>, etc.
            response_cleaned = re.sub(r'<think(?:ing)?>.*?</think(?:ing)?>', '', final_response, flags=re.DOTALL | re.IGNORECASE)
            response_cleaned = re.sub(r'<thought>.*?</thought>', '', response_cleaned, flags=re.DOTALL | re.IGNORECASE)
            response_cleaned = re.sub(r'<thin>.*?</thin>', '', response_cleaned, flags=re.DOTALL | re.IGNORECASE)
            response_cleaned = response_cleaned.strip()

            # Also strip any timestamp/username prefix the AI might have added
            # Pattern: [HH:MM] <Terra> or [HH:MM] <Username> at start of message
            response_cleaned = re.sub(r'^\[\d{2}:\d{2}\]\s*<?[\w\s]+>?\s*', '', response_cleaned)
            response_cleaned = response_cleaned.strip()

            print(f"=== CLEANED RESPONSE (after stripping <think> and timestamps) ===")
            print(f"{response_cleaned}")
            print(f"=== END CLEANED RESPONSE ===\n")

            # Send to IRC (split if needed, use cleaned response)
            chunks = bot.context_builder.split_long_response(response_cleaned, max_length=400)
            for i, chunk in enumerate(chunks):
                if i == 0:
                    bot.send_message(channel, f"{nick}: {chunk}")
                else:
                    bot.send_message(channel, f"... {chunk}")
                await asyncio.sleep(0.5)

        except Exception as e:
            bot.send_message(channel, f"{nick}: Error: {str(e)}")

    @staticmethod
    async def cmd_compact(bot: 'TerrariumBot', channel: str, nick: str, args: str):
        """Summarize older conversation turns to reclaim context budget."""
        try:
            context = await bot.context_manager.get_context(channel)
            await context.maybe_summarize(bot.llm_client)
            bot.send_message(channel, f"{nick}: Conversation history compacted for {channel}")
        except Exception as e:
            bot.send_message(channel, f"{nick}: Error: {str(e)}")
            import traceback
            traceback.print_exc()

    @staticmethod
    async def cmd_search(bot: 'TerrariumBot', channel: str, nick: str, args: str):
        """Search message history with optional filters."""
        if not args:
            bot.send_message(channel, f"{nick}: Usage: {bot.command_prefix}search [user:nick] [hours:N] <query>")
            bot.send_message(channel, f"Query modes: word1 word2 (AND), word1+word2 (OR), \"exact phrase\"")
            return

        try:
            import re

            # Parse optional filters from args
            search_user = None
            search_hours = None
            remaining_args = args

            # Extract user: filter
            user_match = re.search(r'user:(\S+)', remaining_args)
            if user_match:
                search_user = user_match.group(1)
                remaining_args = remaining_args.replace(user_match.group(0), '', 1).strip()

            # Extract hours: filter
            hours_match = re.search(r'hours:(\d+)', remaining_args)
            if hours_match:
                search_hours = int(hours_match.group(1))
                remaining_args = remaining_args.replace(hours_match.group(0), '', 1).strip()

            query = remaining_args.strip()
            if not query:
                bot.send_message(channel, f"{nick}: Please provide a search query")
                return

            # Determine search mode based on query format
            search_mode = "and"  # default

            # Check for quoted phrase
            quote_match = re.match(r'^"(.+)"$', query)
            if quote_match:
                query = quote_match.group(1)
                search_mode = "phrase"
            # Check for OR mode (+ delimiter)
            elif '+' in query:
                search_mode = "or"
            # Otherwise use AND mode (default)

            # Build filter description
            filters = []
            if search_user:
                filters.append(f"user:{search_user}")
            if search_hours:
                filters.append(f"last {search_hours}h")
            if search_mode == "or":
                filters.append("OR mode")
            elif search_mode == "phrase":
                filters.append("exact phrase")
            filter_str = f" ({', '.join(filters)})" if filters else ""

            # Search with filters
            results = await bot.database.search_messages(
                query=query,
                channel=channel,
                nick=search_user,
                hours=search_hours,
                limit=10,
                search_mode=search_mode
            )

            if not results:
                bot.send_message(channel, f"{nick}: No messages found for '{query}'{filter_str}")
                return

            # Send results (max 5 to avoid flooding)
            bot.send_message(channel, f"{nick}: Found {len(results)} messages for '{query}'{filter_str}:")
            for msg in results[:5]:
                time_str = msg.timestamp.strftime('%Y-%m-%d %H:%M')
                preview = msg.message[:80] + '...' if len(msg.message) > 80 else msg.message
                bot.send_message(channel, f"[{time_str}] <{msg.nick}> {preview}")
                await asyncio.sleep(0.5)

            if len(results) > 5:
                bot.send_message(channel, f"... and {len(results) - 5} more results")

        except Exception as e:
            bot.send_message(channel, f"{nick}: Error: {str(e)}")

    @staticmethod
    async def cmd_stats(bot: 'TerrariumBot', channel: str, nick: str, args: str):
        """Show channel statistics."""
        try:
            stats = await bot.database.get_channel_stats(channel)

            messages = [
                f"{nick}: Channel statistics for {channel}:",
                f"Total messages: {stats['total_messages']}",
                f"Unique users: {stats['unique_users']}"
            ]

            if stats['first_message']:
                messages.append(f"First logged: {stats['first_message']}")

            bot.send_messages(channel, messages)

        except Exception as e:
            bot.send_message(channel, f"{nick}: Error: {str(e)}")

    @staticmethod
    async def cmd_who(bot: 'TerrariumBot', channel: str, nick: str, args: str):
        """Show users currently in the channel."""
        try:
            users = await bot.database.get_channel_users(channel)
            count = len(users)

            if count == 0:
                bot.send_message(channel, f"{nick}: No users tracked for {channel} yet")
                return

            # Format users list (show up to 50, then summarize)
            if count <= 50:
                users_str = ', '.join(users)
                bot.send_message(channel, f"{nick}: {count} users in {channel}: {users_str}")
            else:
                # Show first 50, then count
                users_str = ', '.join(users[:50])
                bot.send_message(channel, f"{nick}: {count} users in {channel} (showing first 50): {users_str}")

        except Exception as e:
            bot.send_message(channel, f"{nick}: Error: {str(e)}")

    @staticmethod
    async def cmd_clear(bot: 'TerrariumBot', channel: str, nick: str, args: str):
        """Clear Terra's conversation memory for this channel."""
        try:
            await bot.context_manager.clear_channel(channel)
            bot.send_message(channel, f"{nick}: Conversation memory cleared for {channel}")
        except Exception as e:
            bot.send_message(channel, f"{nick}: Error: {str(e)}")
