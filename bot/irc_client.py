"""IRC bot client using miniirc."""

import miniirc
import asyncio
from datetime import datetime
from typing import Optional, Callable, List
from storage import Database, Message
from llm import LLMClient, ContextBuilder


class TerrariumBot:
    """IRC bot with LLM integration."""

    def __init__(
        self,
        server: str,
        port: int,
        nick: str,
        channels: List[str],
        database: Database,
        llm_client: LLMClient,
        use_ssl: bool = False,
        command_prefix: str = "."
    ):
        """
        Initialize IRC bot.

        Args:
            server: IRC server address
            port: IRC server port
            nick: Bot nickname
            channels: List of channels to join
            database: Database instance
            llm_client: LLM client instance
            use_ssl: Use SSL/TLS connection
            command_prefix: Command prefix (default: '.')
        """
        self.server = server
        self.port = port
        self.nick = nick
        self.channels = channels
        self.database = database
        self.llm_client = llm_client
        self.use_ssl = use_ssl
        self.command_prefix = command_prefix

        self.context_builder = ContextBuilder()
        self.irc: Optional[miniirc.IRC] = None
        self.command_handlers = {}
        self.running = False

    def register_command(self, command: str, handler: Callable):
        """Register a command handler."""
        self.command_handlers[command.lower()] = handler

    async def connect(self):
        """Connect to IRC server."""
        print(f"Connecting to {self.server}:{self.port}...")

        # Create IRC connection
        self.irc = miniirc.IRC(
            ip=self.server,
            port=self.port,
            nick=self.nick,
            channels=self.channels,
            ssl=self.use_ssl,
            debug=False,
            auto_connect=False
        )

        # Register handlers
        @self.irc.Handler("001")  # RPL_WELCOME
        def handle_welcome(irc, hostmask, args):
            print(f"Connected as {self.nick}")
            print(f"Joining channels: {', '.join(self.channels)}")

        @self.irc.Handler("JOIN")
        def handle_join(irc, hostmask, args):
            channel = args[0]
            nick = hostmask[0]

            if nick == self.nick:
                print(f"Joined {channel}")

            # Log join event
            asyncio.create_task(self._log_event(
                channel=channel,
                nick=nick,
                user=hostmask[1],
                host=hostmask[2],
                message_type="JOIN"
            ))

        @self.irc.Handler("PART")
        def handle_part(irc, hostmask, args):
            channel = args[0]
            nick = hostmask[0]
            reason = args[1] if len(args) > 1 else ""

            # Log part event
            asyncio.create_task(self._log_event(
                channel=channel,
                nick=nick,
                user=hostmask[1],
                host=hostmask[2],
                message=reason,
                message_type="PART"
            ))

        @self.irc.Handler("PRIVMSG", "NOTICE")
        def handle_message(irc, hostmask, args):
            channel = args[0]
            text = args[-1]
            nick = hostmask[0]

            # Log message
            asyncio.create_task(self._log_message(
                channel=channel,
                nick=nick,
                user=hostmask[1],
                host=hostmask[2],
                message=text
            ))

            # Handle commands
            if text.startswith(self.command_prefix):
                asyncio.create_task(self._handle_command(
                    channel=channel,
                    nick=nick,
                    text=text
                ))

        # Connect
        self.irc.connect()
        self.running = True
        print("Bot is running. Press Ctrl+C to stop.")

    async def _log_message(
        self,
        channel: str,
        nick: str,
        user: str,
        host: str,
        message: str
    ):
        """Log a message to the database."""
        msg = Message(
            timestamp=datetime.now(),
            channel=channel,
            nick=nick,
            user=user,
            host=host,
            message=message,
            message_type="PRIVMSG"
        )
        await self.database.log_message(msg)

    async def _log_event(
        self,
        channel: str,
        nick: str,
        user: str,
        host: str,
        message_type: str,
        message: str = ""
    ):
        """Log an IRC event to the database."""
        msg = Message(
            timestamp=datetime.now(),
            channel=channel,
            nick=nick,
            user=user,
            host=host,
            message=message,
            message_type=message_type
        )
        await self.database.log_message(msg)

    async def _handle_command(self, channel: str, nick: str, text: str):
        """Handle a command message."""
        # Parse command
        parts = text[len(self.command_prefix):].split(None, 1)
        if not parts:
            return

        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        # Check if command exists
        if command in self.command_handlers:
            try:
                handler = self.command_handlers[command]
                await handler(self, channel, nick, args)
            except Exception as e:
                print(f"Error handling command {command}: {e}")
                self.send_message(channel, f"Error: {str(e)}")

    def send_message(self, target: str, message: str):
        """Send a message to a channel or user."""
        if self.irc:
            self.irc.msg(target, message)

    def send_messages(self, target: str, messages: List[str], delay: float = 0.5):
        """Send multiple messages with delay to avoid flooding."""
        async def send_delayed():
            for msg in messages:
                self.send_message(target, msg)
                if delay > 0 and msg != messages[-1]:  # Don't delay after last message
                    await asyncio.sleep(delay)

        asyncio.create_task(send_delayed())

    async def get_recent_context(
        self,
        channel: str,
        limit: int = 50
    ) -> str:
        """Get recent context from a channel."""
        messages = await self.database.get_recent_messages(
            channel=channel,
            limit=limit
        )
        return self.context_builder.build_context(messages, channel)

    async def run_forever(self):
        """Run the bot forever."""
        await self.connect()

        try:
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            await self.shutdown()

    async def shutdown(self):
        """Shutdown the bot gracefully."""
        self.running = False
        if self.irc:
            self.irc.disconnect()
        await self.database.close()
        print("Bot stopped.")
