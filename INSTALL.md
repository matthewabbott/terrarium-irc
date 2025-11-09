# Installation Guide for NVIDIA DGX Spark

This guide provides step-by-step instructions for setting up the Terrarium IRC Bot on your NVIDIA DGX Spark machine.

## Prerequisites

- NVIDIA DGX Spark with CUDA-capable GPU(s)
- Ubuntu 20.04+ or similar Linux distribution
- Python 3.10 or higher
- terrarium-agent HTTP server running (see terrarium-agent documentation)
- Access to an IRC server

## Installation Steps

### 1. System Preparation

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install required system packages
sudo apt install -y python3 python3-pip python3-venv git sqlite3

# Verify GPU is available
nvidia-smi
```

### 2. Clone Repository

```bash
git clone <your-repository-url>
cd terrarium-irc
```

### 3. Run Setup Script

```bash
./setup.sh
```

This will:
- Create a Python virtual environment
- Install all required dependencies
- Create a `.env` configuration file
- Set up the data directory

### 4. Setup terrarium-agent Server

The bot requires the terrarium-agent HTTP server for AI features.

**Prerequisites:**
- terrarium-agent installed and configured
- Model loaded in terrarium-agent
- Server running on default port 8080

**Starting terrarium-agent:**

```bash
# Start terrarium-agent HTTP server (refer to terrarium-agent documentation)
terrarium-agent serve --port 8080

# Verify server is running
curl http://localhost:8080/health
```

**Note:** Refer to terrarium-agent documentation for detailed setup instructions, model selection, and configuration options.

### 5. Configure the Bot

Edit the `.env` file with your settings:

```bash
nano .env
```

**IRC Configuration:**

```ini
IRC_SERVER=irc.libera.chat    # Your IRC server
IRC_PORT=6667                  # Port (6667 for plain, 6697 for SSL)
IRC_USE_SSL=false             # Use true for SSL/TLS
IRC_NICK=Terra                # Your bot's nickname (e.g., Terra)
IRC_CHANNELS=#test,#mychannel # Comma-separated channel list
```

**Agent Configuration (terrarium-agent):**

```ini
AGENT_API_URL=http://localhost:8080
AGENT_TEMPERATURE=0.8
AGENT_MAX_TOKENS=512
```

**Bot Configuration:**

```ini
COMMAND_PREFIX=.              # Command prefix (default: .)
MAX_CONTEXT_MESSAGES=50       # Number of IRC messages to show Terra
```

### 6. Test the Bot

```bash
# Activate virtual environment
source venv/bin/activate

# Run the bot
python main.py
```

You should see output like:

```
============================================================
Terrarium IRC Bot
============================================================
Server: irc.libera.chat:6667 (SSL: False)
Nick: Terra
Channels: #test, #mychannel
Agent: http://localhost:8080
Database: ./data/irc_logs.db
============================================================

Initializing database...
Database ready.

Initializing Agent client (terrarium-agent)...
Agent client ready.

Initializing context manager...
  Loaded 0 conversation turns for #test
  Loaded 0 conversation turns for #mychannel

Starting bot...

Connecting to irc.libera.chat:6667...
Connected as Terra
Joining channels: #test, #mychannel
Joined #test
Joined #mychannel
```

### 7. Test Commands in IRC

Join the channel(s) with your IRC client and test:

```
.ping
.help
.ask What is 2 + 2?
.terrarium What are we talking about?
.who
```

## Running as a Service (Production)

### 1. Edit the Service File

```bash
cp terrarium-irc.service /etc/systemd/system/
nano /etc/systemd/system/terrarium-irc.service
```

Update the following lines:
- Replace `USER_TO_REPLACE` with your username
- Replace `/path/to/terrarium-irc` with actual path

### 2. Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable terrarium-irc
sudo systemctl start terrarium-irc
```

### 3. Check Status

```bash
sudo systemctl status terrarium-irc
sudo journalctl -u terrarium-irc -f  # Follow logs
```

## GPU Memory Considerations

**Note:** GPU memory is managed by the terrarium-agent server, not by this IRC bot. The bot itself has minimal memory requirements. Refer to terrarium-agent documentation for model selection and VRAM requirements.

### Model Size vs. VRAM (Reference)

Common models and their approximate VRAM requirements:

| Model | VRAM Required | Notes |
|-------|---------------|-------|
| Qwen 2.5 7B | ~14GB | Good balance of quality and speed |
| Qwen 2.5 14B | ~28GB | Better quality, needs more VRAM |
| GLM-4.5-Air-4bit | ~8GB | Quantized, very efficient |
| Llama 3.1 8B | ~16GB | Alternative to Qwen |
| Llama 3.1 70B | ~140GB | Requires multiple GPUs or quantization |

### Check GPU Memory

```bash
# Monitor GPU usage
watch -n 1 nvidia-smi

# Or use detailed monitoring
nvidia-smi dmon
```

## Troubleshooting

### Bot won't start

```bash
# Check Python version
python3 --version  # Should be 3.10+

# Check virtual environment
source venv/bin/activate
which python  # Should point to venv

# Check dependencies
pip list | grep -E "miniirc|requests|aiosqlite"
```

### terrarium-agent not responding

```bash
# Check if terrarium-agent is running
curl http://localhost:8080/health

# Test API endpoint
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "test"}]}'

# Check terrarium-agent logs (refer to terrarium-agent documentation)
```

### Database issues

```bash
# Check database file
ls -lh data/irc_logs.db

# Test database
sqlite3 data/irc_logs.db "SELECT COUNT(*) FROM messages;"

# Reset database (WARNING: deletes all logs)
rm data/irc_logs.db
```

### IRC connection issues

```bash
# Test IRC server connectivity
telnet irc.libera.chat 6667

# For SSL:
openssl s_client -connect irc.libera.chat:6697

# Check firewall
sudo ufw status
```

## Performance Tuning

### For terrarium-agent

Refer to terrarium-agent documentation for performance tuning options (batch size, memory utilization, tensor parallelism, etc.).

### For Bot

Adjust in `.env`:

```ini
# More IRC context for better responses (uses more tokens)
MAX_CONTEXT_MESSAGES=100

# Less IRC context for faster responses (uses fewer tokens)
MAX_CONTEXT_MESSAGES=25

# Note: This only affects IRC logs shown to Terra
# Conversation memory has no limit and persists across restarts
```

## Upgrading

```bash
# Pull latest code
git pull

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Restart bot
sudo systemctl restart terrarium-irc
```

## Next Steps

- Customize commands in `bot/commands.py`
- Adjust Terra's system prompt in `llm/context_manager.py`
- Add new tools in `llm/tools.py` and `llm/tool_executor.py`
- Set up log rotation for the database
- Configure backup for IRC logs and conversation history
- Monitor GPU usage with `nvidia-smi` (if running terrarium-agent locally)
- Explore dual-context architecture in `llm/context_manager.py`

For more information, see:
- [README.md](README.md) - User guide
- [CLAUDE.md](CLAUDE.md) - Developer documentation
- [ARCHITECTURE.md](ARCHITECTURE.md) - Architectural vision
