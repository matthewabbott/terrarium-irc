# Repository Guidelines

## Project Structure & Module Organization
`main.py` boots the IRC bot and wires the three core packages: `bot/` (MiniIRC event loop plus per-command handlers), `llm/` (terrarium-agent client, context management, and tool execution), and `storage/` (SQLite models and helpers that persist to `data/irc_logs.db`). Configuration lives in `.env` or `.env.example`, while service scripts (`setup.sh`, `setup_ollama.sh`, `terrarium-irc.service`) automate deployment. Keep generated artifacts inside `data/` or `storage/`—source files should stay importable from the repo root. Terra also writes enhancement markdowns to `data/enhancements/` via a tool call; check that directory into backups but keep it out of version control (already gitignored). Conversation history auto-summarizes when it grows; summaries live in `conversation_summaries` (SQLite) and appear as `<conversation_summary>` blocks before the remaining turns.

## Build, Test, and Development Commands
- `python3 -m venv venv && source venv/bin/activate` — create and enter the virtual environment used by all scripts.
- `pip install -r requirements.txt` (or `./setup.sh`) — install MiniIRC, aiosqlite, and supporting libraries.
- `terrarium-agent serve --port 8080` — start the local LLM service the bot calls for `!terrarium` / `!ask`.
- `python main.py` — run the bot; reads `./.env` and logs into channels listed in `IRC_CHANNELS`.
- `python -m pytest tests` — run the pytest suite; focus on async command handlers and storage logic.

## Coding Style & Naming Conventions
Follow standard PEP 8 with 4-space indents, snake_case functions, and UpperCamelCase classes. Modules should expose cohesive entry points (e.g., `bot.commands.handle_*`). Keep network or storage side-effects behind helper functions so command handlers stay pure and testable. Prefer async/await over callbacks, add docstrings describing IRC trigger phrases, and include minimal inline comments only where control flow is non-obvious.

## Testing Guidelines
Author tests under `tests/` mirroring the package path (e.g., `tests/bot/test_commands.py`). Name files `test_<module>.py` and async cases `test_<behavior>`. Use `pytest.mark.asyncio` for coroutine tests, and build fixtures that seed `data/irc_logs.db` into a temporary path. Aim to cover new command branches plus storage migrations, and require a passing `python -m pytest` before review.

## Commit & Pull Request Guidelines
History shows short imperative subject lines (“Implement dual-context architecture...”). Keep commits scoped to one concern, mention the touched subsystem (`bot`, `llm`, `storage`) early, and add body details only when rationale is not obvious. Pull requests should reference related issues, summarize behavioral impact, note any schema changes, and include manual test notes or screenshots demonstrating key commands (`!terrarium`, `!search`, `!who`).

## Security & Configuration Tips
IRC credentials, API URLs, and tokens stay in `.env`; never commit environment files with secrets. Log databases in `data/` can contain user messages—share them only when sanitized. When deploying, ensure `AGENT_API_URL` points to a trusted host and restrict filesystem permissions on `storage/` and `data/` to the bot user.
