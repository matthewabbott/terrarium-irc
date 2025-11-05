# Terrarium IRC Bot

An IRC bot with local LLM integration for the NVIDIA DGX Spark. Logs IRC conversations and provides context-aware AI responses using Ollama.

## Features

- **IRC Logging**: Automatically logs all messages to SQLite
- **LLM Integration**: Uses Ollama for local AI responses
- **Context-Aware**: References recent conversation history
- **Commands**: `.help`, `.ping`, `.ask`, `.terrarium`, `.search`, `.stats`

## Quick Start

### 1. Setup

```bash
# Install dependencies
./setup.sh
source venv/bin/activate
```

### 2. Install Ollama

```bash
# Install Ollama and pull a model
./setup_ollama.sh

# Or manually:
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b
```

### 3. Configure

Create `.env` from the example:

```bash
cp .env.example .env
```

Edit `.env` with your IRC settings:

```bash
IRC_SERVER=irc.libera.chat
IRC_PORT=6667
IRC_NICK=mybot
IRC_CHANNELS=#mychannel
```

### 4. Run

```bash
python main.py
```

## Commands

In IRC:

- `.help` - Show available commands
- `.ping` - Check if bot is alive
- `.ask <question>` - Ask the LLM without IRC context
- `.terrarium <question>` - Ask with IRC conversation context
- `.search <term>` - Search message history
- `.stats` - Show channel statistics

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

**Bot won't connect:**
- Check IRC server and port in `.env`
- Try with/without SSL

**LLM commands fail:**
- Make sure Ollama is running: `ollama list`
- Check model is pulled: `ollama pull qwen2.5:7b`

**Out of memory:**
- Use a smaller model: `qwen2.5:7b` instead of `:14b`

## Future Plans

- Support for more local LLM backends (vLLM, etc.)
- Additional bot commands
- Web dashboard for logs

## License

MIT License
