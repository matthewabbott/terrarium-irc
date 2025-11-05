"""Command handlers for the IRC bot."""

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .irc_client import TerrariumBot


class CommandHandler:
    """Handler for bot commands."""

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
        help_text = [
            f"{nick}: Available commands:",
            f"{bot.command_prefix}help - Show this help message",
            f"{bot.command_prefix}ask <question> - Ask the LLM a question",
            f"{bot.command_prefix}terrarium <question> - Ask with IRC context",
            f"{bot.command_prefix}search <term> - Search message history",
            f"{bot.command_prefix}stats - Show channel statistics",
            f"{bot.command_prefix}ping - Check if bot is alive"
        ]
        bot.send_messages(channel, help_text)

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
        """Ask the LLM with IRC context."""
        if not args:
            bot.send_message(
                channel,
                f"{nick}: Usage: {bot.command_prefix}terrarium <question>"
            )
            return

        # Send thinking message
        bot.send_message(channel, f"{nick}: Analyzing context...")

        try:
            # Get recent context
            context = await bot.get_recent_context(channel, limit=50)

            # Check if query might need search
            search_keywords = ['when', 'who said', 'did someone', 'find', 'search']
            needs_search = any(keyword in args.lower() for keyword in search_keywords)

            if needs_search:
                # Try to extract search terms and search
                search_terms = args.lower()
                for keyword in search_keywords:
                    search_terms = search_terms.replace(keyword, '')
                search_terms = search_terms.strip()

                if search_terms:
                    search_results = await bot.database.search_messages(
                        query=search_terms,
                        channel=channel,
                        limit=20
                    )
                    if search_results:
                        search_context = bot.context_builder.build_search_context(
                            search_results,
                            search_terms
                        )
                        context += "\n\n" + search_context

            # Generate response with context
            system_prompt = bot.context_builder.build_system_prompt(channel)
            response = await bot.llm_client.generate(
                prompt=args,
                system_prompt=system_prompt,
                context=context
            )

            # Split into IRC-friendly chunks
            chunks = bot.context_builder.split_long_response(response, max_length=400)

            # Send response
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
