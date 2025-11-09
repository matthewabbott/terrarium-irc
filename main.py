#!/usr/bin/env python3
"""Main entry point for Terrarium IRC Bot."""

import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

from bot import TerrariumBot, CommandHandler
from storage import Database
from llm import AgentClient, ContextManager


async def main():
    """Main function."""
    # Load environment variables
    load_dotenv()

    # IRC Configuration
    irc_server = os.getenv('IRC_SERVER', 'irc.libera.chat')
    irc_port = int(os.getenv('IRC_PORT', '6667'))
    irc_use_ssl = os.getenv('IRC_USE_SSL', 'false').lower() == 'true'
    irc_nick = os.getenv('IRC_NICK', 'Terra')
    irc_channels = os.getenv('IRC_CHANNELS', '#test').split(',')
    irc_channels = [ch.strip() for ch in irc_channels]

    # Agent Configuration
    agent_api_url = os.getenv('AGENT_API_URL', 'http://localhost:8080')
    agent_temperature = float(os.getenv('AGENT_TEMPERATURE', '0.8'))
    agent_max_tokens = int(os.getenv('AGENT_MAX_TOKENS', '512'))

    # Bot Configuration
    command_prefix = os.getenv('COMMAND_PREFIX', '!')
    max_context_messages = int(os.getenv('MAX_CONTEXT_MESSAGES', '50'))

    # Database Configuration
    db_path = os.getenv('DB_PATH', './data/irc_logs.db')

    print("="*60)
    print("Terrarium IRC Bot")
    print("="*60)
    print(f"Server: {irc_server}:{irc_port} (SSL: {irc_use_ssl})")
    print(f"Nick: {irc_nick}")
    print(f"Channels: {', '.join(irc_channels)}")
    print(f"Agent: {agent_api_url}")
    print(f"Database: {db_path}")
    print("="*60)

    # Initialize database
    print("\nInitializing database...")
    database = Database(db_path)
    await database.connect()
    print("Database ready.")

    # Initialize Context Manager
    print("\nInitializing context manager...")
    context_manager = ContextManager(database)
    print("Context manager ready.")

    # Initialize Agent client
    print(f"\nInitializing Agent client...")
    agent_client = AgentClient(
        base_url=agent_api_url,
        timeout=60
    )

    try:
        await agent_client.initialize()
        if await agent_client.health_check():
            print("✓ Agent server is healthy")
        else:
            print("⚠ Agent server not responding")
            print("  LLM commands will be unavailable")
    except Exception as e:
        print(f"⚠ Failed to connect to agent: {e}")
        print("  Bot will run but LLM commands will fail")
        print("  Make sure terrarium-agent is running:")
        print("  http://localhost:8080")

    # Create bot instance
    bot = TerrariumBot(
        server=irc_server,
        port=irc_port,
        nick=irc_nick,
        channels=irc_channels,
        database=database,
        llm_client=agent_client,
        context_manager=context_manager,
        use_ssl=irc_use_ssl,
        command_prefix=command_prefix
    )

    # Register commands
    print("\nRegistering commands...")
    CommandHandler.register_all(bot)
    print(f"Registered commands: {list(bot.command_handlers.keys())}")
    print(f"Command prefix: '{command_prefix}'")

    # Run bot
    print("\nStarting bot...\n")
    await bot.run_forever()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested...")
        sys.exit(0)
