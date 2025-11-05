# Python Setup Guide

## Your System Setup

- **Python Version**: 3.12.3 (Ubuntu 24.04 LTS)
- **Location**: `/usr/bin/python3`
- **pip**: 25.3 (upgraded in venv)
- **venv module**: ✅ Available

## For This Project (terrarium-irc)

### Quick Start

```bash
# 1. Activate virtual environment
source venv/bin/activate

# 2. Run the bot
python main.py

# 3. When done, deactivate
deactivate
```

### What's Installed

```
✓ miniirc 1.10.0      - IRC client library
✓ aiosqlite 0.21.0    - Async SQLite
✓ ollama 0.6.0        - LLM client (for future use)
✓ python-dotenv 1.2.1 - Environment variables
✓ pyyaml 6.0.3        - YAML parsing
```

## For Future Projects

### Clean Pattern (Recommended)

```bash
# 1. Create new project directory
mkdir my-new-project
cd my-new-project

# 2. Create virtual environment
python3 -m venv venv

# 3. Activate it
source venv/bin/activate

# 4. Upgrade pip (optional but recommended)
pip install --upgrade pip

# 5. Install packages
pip install package-name

# Or from requirements.txt:
pip install -r requirements.txt

# 6. Save your dependencies
pip freeze > requirements.txt

# 7. Deactivate when done
deactivate
```

### Why Virtual Environments?

- **Isolation**: Each project has its own dependencies
- **Clean**: No conflicts between projects
- **Reproducible**: `requirements.txt` lets others install exact versions
- **Safe**: Won't mess up system Python

### Common Commands

```bash
# Activate venv
source venv/bin/activate

# Check what's installed
pip list

# Install a package
pip install package-name

# Uninstall a package
pip uninstall package-name

# Save current dependencies
pip freeze > requirements.txt

# Deactivate venv
deactivate
```

### .gitignore for Python Projects

Always add to `.gitignore`:
```
venv/
__pycache__/
*.pyc
.env
```

## Troubleshooting

**Virtual environment not activating?**
- Make sure you're in the project directory
- Use `source venv/bin/activate` (not just `venv/bin/activate`)

**Module not found error?**
- Check if venv is activated: `which python` should show `path/to/project/venv/bin/python`
- Reinstall: `pip install -r requirements.txt`

**Wrong Python version?**
- Create venv with specific version: `python3.12 -m venv venv`

## Best Practices

1. **Always use virtual environments** for Python projects
2. **Never install packages system-wide** with sudo pip (use venv instead)
3. **Keep requirements.txt updated** when adding packages
4. **Commit requirements.txt** to git (but not venv/)
5. **Use .env files** for secrets/config (and .gitignore them)
