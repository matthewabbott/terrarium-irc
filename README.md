# Terrarium IRC Bot

An IRC bot with local LLM integration for the NVIDIA DGX Spark. Logs IRC conversations and provides context-aware AI responses using Ollama.

## Features

- **IRC Logging**: Automatically logs all messages to SQLite
- **LLM Integration**: Uses Ollama for local AI responses
- **Context-Aware**: References recent conversation history
- **Commands**: `.help`, `.ping`, `.ask`, `.terrarium`, `.search`, `.stats`

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

### 3. Run the Bot (IRC only)

```bash
# Activate venv if not already active
source venv/bin/activate

# Run the bot
python main.py
```

**Note**: The bot will work without Ollama - it will log IRC messages and respond to `.ping`, `.help`, `.search`, `.stats`. LLM commands (`.ask`, `.terrarium`) require Ollama (see below).

### 4. Install Ollama (Optional - for LLM features)

```bash
# Install Ollama and pull a model
./setup_ollama.sh

# Or manually:
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b

# Then restart the bot to enable LLM commands
```

## Commands

In IRC:

**Always Available:**
- `.help` - Show available commands
- `.ping` - Check if bot is alive
- `.search <term>` - Search message history
- `.stats` - Show channel statistics

**Requires Ollama:**
- `.ask <question>` - Ask the LLM without IRC context
- `.terrarium <question>` - Ask with IRC conversation context

## Project Structure

```
terrarium-irc/
├── bot/           # IRC bot logic
├── llm/           # LLM integration (Ollama)
├── storage/       # Database (SQLite)
├── main.py        # Entry point
└── .env           # Configuration
```

## Configuration

See `.env.example` for all options. Key settings:

- **IRC**: Server, port, nickname, channels
- **LLM**: Model name, temperature, max tokens
- **Bot**: Command prefix, context window size

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
- The bot works without Ollama (just won't have LLM features)
- To enable LLM: Install Ollama and pull a model
- Check Ollama is running: `ollama list`
- Verify model: `ollama pull qwen2.5:7b`

**Out of memory (Ollama):**
- Use a smaller model: `qwen2.5:7b` instead of `:14b` or `:32b`
- Check available VRAM: `nvidia-smi`

## How It Works

1. **IRC Connection**: Bot connects and joins configured channels
2. **Message Logging**: All messages stored in SQLite (`./data/irc_logs.db`)
3. **Command Detection**: Messages starting with `.` trigger commands
4. **LLM Integration**: When Ollama is available, `.ask` and `.terrarium` send queries to local LLM
5. **Context Building**: `.terrarium` includes recent IRC history in the LLM prompt

## Development

See [PYTHON_SETUP.md](PYTHON_SETUP.md) for Python environment best practices.

## Future Plans

- Support for more local LLM backends (vLLM, llama.cpp, etc.)
- Additional bot commands
- Web dashboard for browsing logs
- Better message search and filtering

## License

MIT License
