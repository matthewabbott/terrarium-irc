"""Command handlers for the IRC bot."""

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .irc_client import TerrariumBot


class CommandHandler:
    """Handler for bot commands."""

    # Command descriptions for help system
    COMMAND_HELP = {
        'help': 'Show available commands or get help for a specific command',
        'ping': 'Check if the bot is responsive',
        'ask': 'Ask the LLM a question without IRC context',
        'terrarium': 'Ask the LLM with full IRC channel context',
        'search': 'Search message history (usage: !search [user:nick] [hours:N] <query>)',
        'stats': 'Show channel statistics (messages, users, etc.)'
    }

    @staticmethod
    def register_all(bot: 'TerrariumBot'):
        """Register all commands with the bot."""
        bot.register_command('help', CommandHandler.cmd_help)
        bot.register_command('ask', CommandHandler.cmd_ask)
        bot.register_command('terrarium', CommandHandler.cmd_terrarium)
        bot.register_command('search', CommandHandler.cmd_search)
        bot.register_command('stats', CommandHandler.cmd_stats)
        bot.register_command('who', CommandHandler.cmd_who)
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
    async def cmd_ask(bot: 'TerrariumBot', channel: str, nick: str, args: str):
        """Ask the LLM a question without context."""
        if not args:
            bot.send_message(channel, f"{nick}: Usage: {bot.command_prefix}ask <question>")
            return

        # Send thinking message
        bot.send_message(channel, f"{nick}: Thinking...")

        try:
            # Generate response
            system_prompt = bot.context_builder.build_system_prompt(channel)
            response = await bot.llm_client.generate(
                prompt=args,
                system_prompt=system_prompt
            )

            # Split into IRC-friendly chunks
            chunks = bot.context_builder.split_long_response(response, max_length=400)

            # Send response
            for i, chunk in enumerate(chunks):
                if i == 0:
                    bot.send_message(channel, f"{nick}: {chunk}")
                else:
                    bot.send_message(channel, f"... {chunk}")
                await asyncio.sleep(0.5)  # Avoid flooding

        except Exception as e:
            bot.send_message(channel, f"{nick}: Error: {str(e)}")

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

            # Build message list for API (includes recent IRC activity)
            messages = await context.get_messages_for_api()

            # Add current user message (the !terrarium command they just sent)
            from datetime import datetime
            timestamp = datetime.now()
            time_str = timestamp.strftime('%H:%M')
            user_content = f"[{time_str}] <{nick}> !terrarium {args}"

            messages.append({
                "role": "user",
                "content": user_content
            })

            # DEBUG: Print full messages array
            print(f"\n=== MESSAGES BEING SENT TO API ({len(messages)} total) ===")
            for i, msg in enumerate(messages):
                role = msg['role']
                content = msg['content']
                # Truncate long content for readability
                if len(content) > 200:
                    content_preview = content[:200] + f"... ({len(content)} chars total)"
                else:
                    content_preview = content
                print(f"  [{i}] {role}: {content_preview}")
            print("=== END MESSAGES ===\n")

            # Get response from agent
            response = await bot.llm_client.chat(
                messages=messages,
                temperature=0.8,
                max_tokens=512
            )

            print(f"\n=== RAW RESPONSE FROM API ===")
            print(f"{response}")
            print(f"=== END RAW RESPONSE ===\n")

            # Strip thinking tags from response (internal reasoning shouldn't go to IRC)
            import re
            # Strip all thinking tag variants: <think>, <thinking>, <thought>, etc.
            response_cleaned = re.sub(r'<think(?:ing)?>.*?</think(?:ing)?>', '', response, flags=re.DOTALL | re.IGNORECASE)
            response_cleaned = re.sub(r'<thought>.*?</thought>', '', response_cleaned, flags=re.DOTALL | re.IGNORECASE)
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
            import traceback
            traceback.print_exc()

    @staticmethod
    async def cmd_search(bot: 'TerrariumBot', channel: str, nick: str, args: str):
        """Search message history with optional filters."""
        if not args:
            bot.send_message(
                channel,
                f"{nick}: Usage: {bot.command_prefix}search [user:nick] [hours:N] <query>"
            )
            return

        try:
            # Parse optional filters from args
            parts = args.split()
            search_user = None
            search_hours = None
            query_parts = []

            for part in parts:
                if part.startswith('user:'):
                    search_user = part[5:]  # Extract nickname after 'user:'
                elif part.startswith('hours:'):
                    try:
                        search_hours = int(part[6:])  # Extract hours after 'hours:'
                    except ValueError:
                        bot.send_message(channel, f"{nick}: Invalid hours value: {part}")
                        return
                else:
                    query_parts.append(part)

            # Reconstruct query from remaining parts
            query = ' '.join(query_parts)
            if not query:
                bot.send_message(channel, f"{nick}: Please provide a search query")
                return

            # Build filter description
            filters = []
            if search_user:
                filters.append(f"user:{search_user}")
            if search_hours:
                filters.append(f"last {search_hours}h")
            filter_str = f" ({', '.join(filters)})" if filters else ""

            # Search with filters
            results = await bot.database.search_messages(
                query=query,
                channel=channel,
                nick=search_user,
                hours=search_hours,
                limit=10
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
