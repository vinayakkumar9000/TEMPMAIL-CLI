<h2 align="center">Temp Mail</h2> 

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.7%2B-blue)](https://www.python.org/downloads/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

</div>

> A professional CLI utility for managing temporary email inboxes in real-time. Polls your chosen service and displays incoming messages with rich formatting.

![temp watcher](https://github.com/user-attachments/assets/c016d682-ede9-4619-853a-3ed90df97cae)

## Features

- **Multiple Service Support** - Works with GuerrillaMail and mail.tm
- **Rich Terminal UI** - Beautiful, colorful display with clear message formatting
- **Robust Retry Logic** - Automatic exponential backoff on network errors
- **Session Keepalive** - Automatic JWT token refresh for mail.tm
- **Message History** - Save and review past messages
- **Configuration System** - Save your preferences between sessions
- **Cross-Platform** - Works on Windows, macOS, and Linux

## Installation

### One-Command Setup (Recommended)

```bash
# Clone the repository
git clone https://github.com/vinayakkumar9000/TEMPMAIL-CLI.git
cd tempmail

# Run the installer (works on all platforms)
python install.py
```

The installer will:
- Check Python version (3.7+ required)
- Create a virtual environment in `.venv/`
- Install all dependencies from `requirements.txt`
- Display platform-specific instructions to run the app

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/zebbern/cli-temp-mails.git tempmail
cd tempmail

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
# Launch with interactive menu
python tempmail.py

# Specify a provider directly
python tempmail.py mail.tm

# Change polling interval (seconds)
python tempmail.py --poll 10 guerrillamail
```

### Advanced Options

```bash
# Use plain text display mode
python tempmail.py --display plain

# Don't save messages to history
python tempmail.py --no-save

# Enable debug mode with detailed error messages
python tempmail.py --debug

# View help information
python tempmail.py --help
```

## CLI Reference

| Flag | Short | Description | Example |
|------|-------|-------------|---------|
| `provider` | - | Provider to use (optional, shows menu if omitted) | `python tempmail.py mail.tm` |
| `--poll` | `-p` | Polling interval in seconds (default: 5) | `--poll 10` |
| `--display` | `-d` | Display mode: `rich` or `plain` (default: rich) | `--display plain` |
| `--no-save` | `-n` | Don't save messages to history | `--no-save` |
| `--list-providers` | `-l` | List all available providers and exit | `--list-providers` |
| `--history` | - | View saved message history and exit | `--history` |
| `--clear-history` | - | Clear all saved messages and exit | `--clear-history` |
| `--export` | - | Export messages to JSON file and exit | `--export emails.json` |
| `--debug` | - | Enable debug mode with detailed errors | `--debug` |
| `--version` | `-v` | Show version information and exit | `--version` |
| `--help` | `-h` | Show help message and exit | `--help` |

## Supported Providers

| Provider | Features | Notes |
|----------|----------|-------|
| mail.tm | Full body text, HTML support, JWT auth | Fast, reliable with auto token refresh |
| GuerrillaMail | Text & HTML, attachments | Well-established service |

## Configuration

Temp Mail saves your preferences in `~/.config/tempmail-watcher/config.json`. Settings include:

- **default_provider** - Your preferred provider (default: mail.tm)
- **poll_interval** - Seconds between checks (default: 5, min: 1)
- **display_mode** - `rich` or `plain` (default: rich)
- **max_history_entries** - Maximum saved messages (default: 50, range: 1-500)
- **save_messages** - Whether to save messages (default: true)

All config values are validated on startup and automatically corrected if invalid.

## History & Message Export

Received messages are saved to `~/.config/tempmail-watcher/history.json`.

### View History
```bash
python tempmail.py --history
```

### Export Messages
```bash
# Export to default file (email_export.json)
python tempmail.py --export

# Export to custom file
python tempmail.py --export my_emails.json
```

### Clear History
```bash
python tempmail.py --clear-history
```

## Robustness Features

- **Automatic Retry Logic** - All HTTP requests retry up to 3 times with exponential backoff (2s, 4s, 8s)
- **Session Keepalive** - JWT tokens for mail.tm are automatically refreshed on 401 errors
- **Graceful Failover** - In interactive mode, failed providers return to menu instead of crashing
- **Signal Handling** - Clean exit on SIGTERM and Ctrl+C
- **Config Validation** - Invalid config values are automatically corrected on startup
- **Live Countdown** - Visual countdown timer between polls (in rich mode)

## Version

Current version: **v2.2.0**

---

<p align="center">
  Developed with ❤️ by <a href="https://github.com/zebbern">zebbern</a>
</p>
