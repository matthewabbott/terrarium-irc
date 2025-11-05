# Terrarium IRC Bot

An intelligent IRC bot with local LLM integration for the NVIDIA DGX Spark. Features comprehensive logging, context-aware responses, and powerful search capabilities.

## Features

- **IRC Logging**: Automatically logs all messages, joins, parts, and other events
- **LLM Integration**: Supports both Ollama and vLLM backends
- **Context-Aware Responses**: Uses recent conversation history to inform LLM responses
- **Search Capabilities**: Search through message history
- **Multiple Commands**: `.help`, `.ask`, `.terrarium`, `.search`, `.stats`, and more
- **Production Ready**: Built for NVIDIA DGX Spark with GPU acceleration

## Architecture

```
terrarium-irc/
├── bot/                    # IRC bot implementation
│   ├── irc_client.py      # Main bot logic
│   └── commands.py        # Command handlers
├── llm/                   # LLM integration
│   ├── client.py          # Unified LLM client (Ollama/vLLM)
│   └── context.py         # Context preparation
├── storage/               # Database layer
│   ├── database.py        # SQLite operations
│   └── models.py          # Data models
├── main.py                # Entry point
└── setup scripts          # Installation helpers
```

## Quick Start

### 1. Clone and Setup

```bash
git clone <your-repo>
cd terrarium-irc
./setup.sh
```

### 2. Choose Your LLM Backend

#### Option A: Ollama (Recommended for Getting Started)

```bash
./setup_ollama.sh
```

Ollama is easier to set up and manages models automatically. Recommended models:
- **qwen2.5:7b** - Best balance of speed and quality (default)
- **qwen2.5:14b** - Better quality, requires more VRAM
- **qwen2.5:32b** - Highest quality, requires ~64GB VRAM

#### Option B: vLLM (Production Performance)

```bash
./setup_vllm.sh
```

vLLM offers better performance and throughput, optimized for NVIDIA GPUs. Recommended models:
- **Qwen/Qwen2.5-7B-Instruct** - Excellent all-around (14GB VRAM)
- **Qwen/Qwen2.5-14B-Instruct** - Better reasoning (28GB VRAM)
- **meta-llama/Llama-3.1-8B-Instruct** - Alternative option

### 3. Configure

Edit `.env` file:

```bash
# IRC Configuration
IRC_SERVER=irc.libera.chat
IRC_PORT=6667
IRC_USE_SSL=false
IRC_NICK=terrarium-bot
IRC_CHANNELS=#test,#mychannel

# LLM Configuration
LLM_BACKEND=ollama              # or 'vllm'
LLM_MODEL=qwen2.5:7b           # your chosen model
LLM_API_URL=http://localhost:11434  # Ollama default

# For vLLM, use:
# LLM_API_URL=http://localhost:8000/v1
# LLM_MODEL=Qwen/Qwen2.5-7B-Instruct

# Bot Configuration
COMMAND_PREFIX=.
MAX_CONTEXT_MESSAGES=50
```

### 4. Run the Bot

```bash
source venv/bin/activate
python main.py
```

## Commands

Once the bot is running in IRC channels, use these commands:

- **`.help`** - Show available commands
- **`.ping`** - Check if bot is alive
- **`.ask <question>`** - Ask the LLM a question (no context)
  - Example: `.ask What is the capital of France?`
- **`.terrarium <question>`** - Ask with full IRC conversation context
  - Example: `.terrarium What was the main topic we discussed?`
- **`.search <term>`** - Search message history
  - Example: `.search docker error`
- **`.stats`** - Show channel statistics

## Advanced Usage

### Using vLLM for Production

If you chose vLLM, start the server:

```bash
./start_vllm.sh
```

The vLLM server will run on port 8000. You can configure model parameters in `start_vllm.sh`.

### Running as a Service

Create a systemd service file `/etc/systemd/system/terrarium-bot.service`:

```ini
[Unit]
Description=Terrarium IRC Bot
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/terrarium-irc
Environment="PATH=/path/to/terrarium-irc/venv/bin"
ExecStart=/path/to/terrarium-irc/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl enable terrarium-bot
sudo systemctl start terrarium-bot
sudo systemctl status terrarium-bot
```

### Database Management

The bot uses SQLite to store logs in `./data/irc_logs.db`. You can query it directly:

```bash
sqlite3 ./data/irc_logs.db
```

Useful queries:

```sql
-- Get message count by user
SELECT nick, COUNT(*) as count FROM messages
WHERE channel='#mychannel'
GROUP BY nick ORDER BY count DESC;

-- Get recent messages
SELECT timestamp, nick, message FROM messages
WHERE channel='#mychannel'
ORDER BY timestamp DESC LIMIT 20;

-- Search for keywords
SELECT timestamp, nick, message FROM messages
WHERE message LIKE '%docker%'
ORDER BY timestamp DESC;
```

## Model Recommendations

Based on your DGX Spark capabilities:

### Open Source Models (January 2025)

1. **Qwen 2.5** (Recommended)
   - 7B: Fast, high quality, fits on most GPUs
   - 14B: Best balance for production
   - 32B: Highest quality for powerful hardware

2. **Llama 3.1/3.2**
   - 8B: Solid performance, good for general use
   - 70B: Enterprise-grade (requires multi-GPU)

3. **DeepSeek V3**
   - Cutting-edge reasoning capabilities
   - Requires significant VRAM

4. **Mistral Models**
   - 7B Instruct: Fast and efficient
   - Mixtral 8x7B: High quality with MoE architecture

## Troubleshooting

### Bot won't connect to IRC

- Check firewall settings
- Verify IRC server and port in `.env`
- Try with SSL enabled/disabled

### LLM commands fail

- Ensure LLM backend is running:
  - Ollama: `ollama list` should show your model
  - vLLM: Check `http://localhost:8000/v1/models`
- Verify `LLM_API_URL` in `.env`
- Check logs for detailed error messages

### Out of Memory errors

- Use a smaller model (7B instead of 14B/32B)
- For vLLM, reduce `--gpu-memory-utilization` in `start_vllm.sh`
- Close other GPU applications

## Development

### Adding New Commands

Edit `bot/commands.py`:

```python
@staticmethod
async def cmd_mycommand(bot: 'TerrariumBot', channel: str, nick: str, args: str):
    """Your command description."""
    bot.send_message(channel, f"{nick}: Response here")
```

Register in `CommandHandler.register_all()`:

```python
bot.register_command('mycommand', CommandHandler.cmd_mycommand)
```

### Customizing LLM Behavior

Edit system prompt in `llm/context.py`:

```python
def build_system_prompt(self, channel: Optional[str] = None) -> str:
    # Customize the base_prompt here
    pass
```

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests if applicable
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Acknowledgments

- Built for NVIDIA DGX Spark
- Uses [miniirc](https://github.com/luk3yx/miniirc) for IRC
- Supports [Ollama](https://ollama.ai/) and [vLLM](https://github.com/vllm-project/vllm)
- Inspired by classic IRC bots with modern LLM capabilities
