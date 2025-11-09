# Terrarium IRC Bot

An IRC bot with local LLM integration for the NVIDIA DGX Spark. Logs IRC conversations and provides context-aware AI responses using terrarium-agent HTTP server.

## Features

- **IRC Logging**: Automatically logs all messages to SQLite
- **LLM Integration**: Uses terrarium-agent HTTP API for local AI responses
- **Persistent Conversations**: Terra maintains conversation memory across requests
- **Tool Calling**: Terra can search chat history and get user lists
- **Dual-Context Architecture**: Separates IRC logs from conversation memory
- **Commands**: `.help`, `.ping`, `.ask`, `.terrarium`, `.search`, `.stats`, `.who`, `.clear`

## Quick Start

### 1. Setup Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

Or use the setup script:
```bash
./setup.sh
source venv/bin/activate
```

### 2. Configure IRC Settings

Edit `.env` with your IRC server and channels:

```bash
IRC_SERVER=irc.example.com
IRC_PORT=6667
IRC_NICK=terrarium
IRC_CHANNELS=#channel1,#channel2
```

### 3. Start terrarium-agent Server

The bot requires the terrarium-agent HTTP server for AI features:

```bash
# Start terrarium-agent server on port 8080
# (Refer to terrarium-agent documentation for setup)
terrarium-agent serve --port 8080
```

The server should be accessible at `http://localhost:8080`.

### 4. Run the Bot

```bash
# Activate venv if not already active
source venv/bin/activate

# Run the bot
python main.py
```

**Note**: The bot will log IRC messages and respond to `.ping`, `.help`, `.search`, `.stats`, `.who` even without terrarium-agent. LLM commands (`.ask`, `.terrarium`) require terrarium-agent server running.

## Commands

In IRC:

**Always Available:**
- `.help` - Show available commands
- `.ping` - Check if bot is alive
- `.search <term>` - Search message history
- `.stats` - Show channel statistics
- `.who` - Show users currently in channel

**Requires terrarium-agent:**
- `.ask <question>` - Ask the LLM without IRC context
- `.terrarium <question>` - Ask Terra with persistent conversation context
- `.clear` - Clear Terra's conversation memory for this channel

## Project Structure

```
terrarium-irc/
├── bot/
│   ├── irc_client.py    # IRC connection and event handling
│   └── commands.py      # Command handlers
├── llm/
│   ├── agent_client.py  # terrarium-agent HTTP client
│   ├── context_manager.py  # Conversation memory & dual-context
│   ├── tools.py         # Tool definitions for Terra
│   └── tool_executor.py # Tool execution handlers
├── storage/
│   ├── database.py      # Database interface
│   └── models.py        # Data models
├── main.py              # Entry point
└── .env                 # Configuration
```

## Configuration

See `.env.example` for all options. Key settings:

- **IRC**: Server, port, nickname, channels
- **Agent**: `AGENT_API_URL`, `AGENT_TEMPERATURE`, `AGENT_MAX_TOKENS`
- **Bot**: Command prefix and IRC context window (`MAX_CONTEXT_MESSAGES`)

## Troubleshooting

**Bot won't connect to IRC:**
- Check IRC server and port in `.env`
- Verify channels exist and are accessible
- Try toggling SSL: `IRC_USE_SSL=true` or `false`

**"Module not found" errors:**
- Make sure venv is activated: `source venv/bin/activate`
- Verify you're in project directory
- Reinstall: `pip install -r requirements.txt`

**LLM commands fail (.ask, .terrarium):**
- The bot works without terrarium-agent (just won't have AI features)
- To enable AI responses: Start terrarium-agent HTTP server
- Check server is running: `curl http://localhost:8080/health`
- Verify server URL in `.env`: `AGENT_API_URL=http://localhost:8080`

## How It Works

1. **IRC Connection**: Bot connects and joins configured channels
2. **Message Logging**: All messages stored in SQLite (`./data/irc_logs.db`)
3. **Command Detection**: Messages starting with `.` trigger commands
4. **LLM Integration**: `.ask` and `.terrarium` send requests to terrarium-agent HTTP server
5. **Dual-Context Architecture**: `.terrarium` provides:
   - **IRC Logs**: Recent channel activity with timestamps (decorated)
   - **Conversation Memory**: Terra's persistent conversation history (clean)
6. **Tool Calling**: Terra can call tools like `search_chat_logs` and `get_current_users`
7. **Persistent Memory**: Terra's conversation history persists across bot restarts

## Development

See [PYTHON_SETUP.md](PYTHON_SETUP.md) for Python environment best practices.

## Future Plans

- Multi-agent coordination (Terra communicating with other Terrarium agents)
- Web dashboard for browsing logs and conversation history
- Enhanced tool calling capabilities
- Docker containerization

## License

MIT License
