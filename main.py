#!/usr/bin/env python3
"""Main entry point for Terrarium IRC Bot."""

import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

from bot import TerrariumBot, CommandHandler
from storage import Database
from llm import LLMClient


async def main():
    """Main function."""
    # Load environment variables
    load_dotenv()

    # IRC Configuration
    irc_server = os.getenv('IRC_SERVER', 'irc.libera.chat')
    irc_port = int(os.getenv('IRC_PORT', '6667'))
    irc_use_ssl = os.getenv('IRC_USE_SSL', 'false').lower() == 'true'
    irc_nick = os.getenv('IRC_NICK', 'terrarium-bot')
    irc_channels = os.getenv('IRC_CHANNELS', '#test').split(',')
    irc_channels = [ch.strip() for ch in irc_channels]

    # LLM Configuration
    llm_backend = os.getenv('LLM_BACKEND', 'ollama')
    llm_model = os.getenv('LLM_MODEL', 'qwen2.5:7b')
    llm_api_url = os.getenv('LLM_API_URL', 'http://localhost:11434')

    # Bot Configuration
    command_prefix = os.getenv('COMMAND_PREFIX', '.')
    max_context_messages = int(os.getenv('MAX_CONTEXT_MESSAGES', '50'))

    # Database Configuration
    db_path = os.getenv('DB_PATH', './data/irc_logs.db')

    print("="*60)
    print("Terrarium IRC Bot")
    print("="*60)
    print(f"Server: {irc_server}:{irc_port} (SSL: {irc_use_ssl})")
    print(f"Nick: {irc_nick}")
    print(f"Channels: {', '.join(irc_channels)}")
    print(f"LLM: {llm_backend} ({llm_model})")
    print(f"Database: {db_path}")
    print("="*60)

    # Initialize database
    print("\nInitializing database...")
    database = Database(db_path)
    await database.connect()
    print("Database ready.")

    # Initialize LLM client
    print(f"\nInitializing LLM client ({llm_backend})...")
    llm_client = LLMClient(
        backend=llm_backend,
        model=llm_model,
        api_url=llm_api_url
    )

    try:
        await llm_client.initialize()
        print("LLM client ready.")
    except Exception as e:
        print(f"Warning: Failed to initialize LLM client: {e}")
        print("Bot will run but LLM commands may fail.")

    # Create bot instance
    bot = TerrariumBot(
        server=irc_server,
        port=irc_port,
        nick=irc_nick,
        channels=irc_channels,
        database=database,
        llm_client=llm_client,
        use_ssl=irc_use_ssl,
        command_prefix=command_prefix
    )

    # Register commands
    CommandHandler.register_all(bot)

    # Run bot
    print("\nStarting bot...\n")
    await bot.run_forever()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested...")
        sys.exit(0)
