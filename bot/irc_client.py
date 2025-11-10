"""IRC bot client using miniirc."""

import miniirc
import asyncio
from datetime import datetime
from typing import Optional, Callable, List
from storage import Database, Message
from llm import AgentClient, ContextBuilder, ContextManager


class TerrariumBot:
    """IRC bot with LLM integration."""

    def __init__(
        self,
        server: str,
        port: int,
        nick: str,
        channels: List[str],
        database: Database,
        llm_client: AgentClient,
        context_manager: ContextManager,
        use_ssl: bool = False,
        command_prefix: str = ".",
        max_context_messages: int = 50,
        search_config: Optional[dict] = None
    ):
        """
        Initialize IRC bot.

        Args:
            server: IRC server address
            port: IRC server port
            nick: Bot nickname
            channels: List of channels to join
            database: Database instance
            llm_client: Agent client instance
            context_manager: Context manager instance
            use_ssl: Use SSL/TLS connection
            command_prefix: Command prefix (default: '.')
        """
        self.server = server
        self.port = port
        self.nick = nick
        self.channels = channels
        self.database = database
        self.llm_client = llm_client
        self.context_manager = context_manager
        self.use_ssl = use_ssl
        self.command_prefix = command_prefix
        self.max_context_messages = max_context_messages
        self.search_config = search_config or {}

        self.context_builder = ContextBuilder()
        self.irc: Optional[miniirc.IRC] = None
        self.command_handlers = {}
        self.running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def register_command(self, command: str, handler: Callable):
        """Register a command handler."""
        self.command_handlers[command.lower()] = handler

    async def connect(self):
        """Connect to IRC server."""
        print(f"Connecting to {self.server}:{self.port}...")

        # Store the event loop for use in IRC handlers
        self.loop = asyncio.get_event_loop()

        # Create IRC connection
        print(f"Creating IRC client...")
        self.irc = miniirc.IRC(
            ip=self.server,
            port=self.port,
            nick=self.nick,
            channels=self.channels,
            ssl=self.use_ssl,
            debug=True,  # Enable debug output
            auto_connect=False
        )
        print(f"IRC client created.")

        # Register handlers
        @self.irc.Handler("001")  # RPL_WELCOME
        def handle_welcome(irc, hostmask, args):
            print(f"✓ Connected to server as {self.nick}")
            print(f"✓ Server message: {args}")

        @self.irc.Handler("376", "422")  # End of MOTD or MOTD missing
        def handle_motd_end(irc, hostmask, args):
            print(f"✓ MOTD received, joining channels: {', '.join(self.channels)}")

        @self.irc.Handler("PING")
        def handle_ping(irc, hostmask, args):
            print(f"← PING from server")
            print(f"→ PONG response sent")

        @self.irc.Handler("JOIN", colon=False)
        def handle_join(irc, hostmask, args):
            channel = args[0]
            nick = hostmask[0]

            if nick == self.nick:
                print(f"✓ Successfully joined {channel}")
            else:
                print(f"  {nick} joined {channel}")

            # Add user to channel tracking
            asyncio.run_coroutine_threadsafe(
                self.database.add_user_to_channel(channel, nick),
                self.loop
            )

            # Log join event (run from thread-safe context)
            asyncio.run_coroutine_threadsafe(
                self._log_event(
                    channel=channel,
                    nick=nick,
                    user=hostmask[1],
                    host=hostmask[2],
                    message_type="JOIN"
                ),
                self.loop
            )

        @self.irc.Handler("PART", colon=False)
        def handle_part(irc, hostmask, args):
            channel = args[0]
            nick = hostmask[0]
            reason = args[1] if len(args) > 1 else ""

            print(f"  {nick} left {channel}")

            # Remove user from channel tracking
            asyncio.run_coroutine_threadsafe(
                self.database.remove_user_from_channel(channel, nick),
                self.loop
            )

            # Log part event (run from thread-safe context)
            asyncio.run_coroutine_threadsafe(
                self._log_event(
                    channel=channel,
                    nick=nick,
                    user=hostmask[1],
                    host=hostmask[2],
                    message=reason,
                    message_type="PART"
                ),
                self.loop
            )

        @self.irc.Handler("QUIT", colon=False)
        def handle_quit(irc, hostmask, args):
            nick = hostmask[0]
            reason = args[0] if args else ""

            print(f"  {nick} quit ({reason})")

            async def process_quit():
                channels = await self.database.remove_user_from_all_channels(nick)
                for channel in channels:
                    await self._log_event(
                        channel=channel,
                        nick=nick,
                        user=hostmask[1],
                        host=hostmask[2],
                        message=reason,
                        message_type="QUIT"
                    )

            asyncio.run_coroutine_threadsafe(process_quit(), self.loop)

        @self.irc.Handler("NICK", colon=False)
        def handle_nick_change(irc, hostmask, args):
            old_nick = hostmask[0]
            new_nick = args[0]

            print(f"  {old_nick} is now known as {new_nick}")

            async def process_nick():
                channels = await self.database.get_channels_for_user(old_nick)
                await self.database.rename_user_in_channels(old_nick, new_nick)
                for channel in channels:
                    await self._log_event(
                        channel=channel,
                        nick=old_nick,
                        user=hostmask[1],
                        host=hostmask[2],
                        message_type="NICK",
                        message=new_nick
                    )

            asyncio.run_coroutine_threadsafe(process_nick(), self.loop)

        @self.irc.Handler("353", colon=False)  # RPL_NAMREPLY
        def handle_names(irc, hostmask, args):
            # Format: :server 353 nick = #channel :nick1 nick2 nick3
            channel = args[2]
            names_str = args[3]
            nicks = names_str.split()

            print(f"  NAMES for {channel}: {len(nicks)} users")

            # Add all users to channel tracking
            for nick in nicks:
                # Strip prefix characters (@, +, etc.)
                clean_nick = nick.lstrip('@+%~&')
                asyncio.run_coroutine_threadsafe(
                    self.database.add_user_to_channel(channel, clean_nick),
                    self.loop
                )

        @self.irc.Handler("PRIVMSG", "NOTICE", colon=False)
        def handle_message(irc, hostmask, args):
            channel = args[0]
            text = args[-1]
            nick = hostmask[0]

            print(f"← [{channel}] <{nick}> {text}")

            # Log message (run from thread-safe context)
            asyncio.run_coroutine_threadsafe(
                self._log_message(
                    channel=channel,
                    nick=nick,
                    user=hostmask[1],
                    host=hostmask[2],
                    message=text
                ),
                self.loop
            )

            # Handle commands (run from thread-safe context)
            if text.startswith(self.command_prefix):
                print(f"  Command detected: {text}")
                asyncio.run_coroutine_threadsafe(
                    self._handle_command(
                        channel=channel,
                        nick=nick,
                        text=text
                    ),
                    self.loop
                )

        # Add error handler
        @self.irc.Handler("ERROR")
        def handle_error(irc, hostmask, args):
            print(f"✗ IRC ERROR: {args}")

        # Add numeric handlers for common errors
        @self.irc.Handler("433")  # Nickname in use
        def handle_nick_in_use(irc, hostmask, args):
            print(f"✗ Nickname '{self.nick}' is already in use!")
            print(f"  Try changing IRC_NICK in .env")

        @self.irc.Handler("432", "431")  # Invalid nickname
        def handle_invalid_nick(irc, hostmask, args):
            print(f"✗ Invalid nickname: {args}")

        @self.irc.Handler("465")  # Banned
        def handle_banned(irc, hostmask, args):
            print(f"✗ Banned from server: {args}")

        # Connect
        print(f"Attempting connection...")
        try:
            self.irc.connect()
            self.running = True
            print("Bot connection initiated. Press Ctrl+C to stop.")
            print("Waiting for server response...\n")
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            raise

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
        print(f"  _handle_command called: channel={channel}, nick={nick}, text={text}")

        # Parse command
        parts = text[len(self.command_prefix):].split(None, 1)
        if not parts:
            print(f"  No command found after prefix")
            return

        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        print(f"  Parsed command: {command}, args: {args}")

        # Check if command exists
        if command in self.command_handlers:
            print(f"  Found handler for command: {command}")
            try:
                handler = self.command_handlers[command]
                await handler(self, channel, nick, args)
                print(f"  Handler completed successfully")
            except Exception as e:
                print(f"  Error handling command {command}: {e}")
                import traceback
                traceback.print_exc()
                self.send_message(channel, f"Error: {str(e)}")
        else:
            print(f"  Unknown command: {command}")
            print(f"  Available commands: {list(self.command_handlers.keys())}")

    def send_message(self, target: str, message: str):
        """Send a message to a channel or user."""
        print(f"→ [{target}] {message}")
        if self.irc:
            self.irc.msg(target, message)
            print(f"  Message sent via IRC")
        else:
            print(f"  ERROR: IRC client not initialized!")

    def send_messages(self, target: str, messages: List[str], delay: float = 0.5):
        """Send multiple messages with delay to avoid flooding."""
        print(f"  send_messages called for {target}, {len(messages)} messages")
        async def send_delayed():
            for msg in messages:
                self.send_message(target, msg)
                if delay > 0 and msg != messages[-1]:  # Don't delay after last message
                    await asyncio.sleep(delay)

        # Make sure to use the proper event loop
        if self.loop:
            asyncio.run_coroutine_threadsafe(send_delayed(), self.loop)
        else:
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
