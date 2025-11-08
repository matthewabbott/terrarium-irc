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
        'search': 'Search message history for a term',
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

            # Build message list for API
            messages = await context.get_messages_for_api()

            # Add current user message
            await context.add_user_message(nick, args)

            # Append to messages for this request
            messages.append({
                "role": "user",
                "content": f"{nick}: {args}"
            })

            # Get response from agent
            response = await bot.llm_client.chat(
                messages=messages,
                temperature=0.8,
                max_tokens=512
            )

            # Add to conversation history
            await context.add_assistant_message(response)

            # Send to IRC (split if needed)
            chunks = bot.context_builder.split_long_response(response, max_length=400)
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
        """Search message history."""
        if not args:
            bot.send_message(
                channel,
                f"{nick}: Usage: {bot.command_prefix}search <term>"
            )
            return

        try:
            results = await bot.database.search_messages(
                query=args,
                channel=channel,
                limit=5
            )

            if not results:
                bot.send_message(channel, f"{nick}: No messages found matching '{args}'")
                return

            # Send results
            bot.send_message(channel, f"{nick}: Found {len(results)} messages:")
            for msg in results[:5]:  # Show max 5 results
                time_str = msg.timestamp.strftime('%Y-%m-%d %H:%M')
                preview = msg.message[:100] + '...' if len(msg.message) > 100 else msg.message
                bot.send_message(
                    channel,
                    f"[{time_str}] <{msg.nick}> {preview}"
                )
                await asyncio.sleep(0.5)

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
