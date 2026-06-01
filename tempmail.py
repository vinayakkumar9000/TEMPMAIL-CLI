#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
# Temp Mail Watcher - A Professional Temporary Email Client
# Copyright © 2024‑2025  zebbern  <https://github.com/zebbern>
# ─────────────────────────────────────────────────────────────────────────────
# A professional CLI utility for managing throw‑away e‑mail inboxes in real‑time.
# Polls the chosen service at customizable intervals and displays incoming 
# messages with rich formatting. Supports multiple temporary email providers.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import logging
import os
import platform
import random
import signal
import string
import sys
import time
import traceback
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

# Clear screen function
def clear_screen():
    """Clear the terminal screen based on the operating system."""
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")

# Clear the screen immediately when script starts
clear_screen()

try:
    import requests
    from rich.console import Console
    from rich.live import Live
    from rich.logging import RichHandler
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table
    from rich.text import Text
    from rich.theme import Theme
except ImportError:
    print("Required dependencies not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "rich"])
    import requests
    from rich.console import Console
    from rich.live import Live
    from rich.logging import RichHandler
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table
    from rich.text import Text
    from rich.theme import Theme

# Set up rich console with custom theme
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "email_from": "bold blue",
    "email_subject": "bold yellow",
    "email_date": "magenta",
    "email_body": "white",
    "header": "bold cyan",
})

console = Console(theme=custom_theme)

# Set up rich logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, console=console)]
)

LOGGER = logging.getLogger("temp-mail-watcher")

##############################################################################
# Configuration and state management
##############################################################################

CONFIG_DIR = Path.home() / ".config" / "tempmail-watcher"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.json"

def ensure_config_dir() -> None:
    """Ensure the configuration directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def load_config() -> Dict[str, Any]:
    """Load configuration from file or return defaults."""
    defaults = {
        "default_provider": "mail.tm",
        "poll_interval": 5,
        "max_history_entries": 50,
        "save_messages": True,
        "display_mode": "rich",
    }
    
    if not CONFIG_FILE.exists():
        return defaults.copy()
    
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    except Exception as e:
        LOGGER.warning(f"Failed to load config: {e}. Using defaults.")
        return defaults.copy()
    
    # Validate and fix config values
    fixed = []
    
    # Validate poll_interval
    if not isinstance(config.get("poll_interval"), int) or config.get("poll_interval", 0) < 1:
        config["poll_interval"] = defaults["poll_interval"]
        fixed.append("poll_interval")
    
    # Validate display_mode
    if config.get("display_mode") not in ["rich", "plain"]:
        config["display_mode"] = defaults["display_mode"]
        fixed.append("display_mode")
    
    # Validate default_provider
    valid_providers = ["guerrillamail", "mail.tm", "tempmail.lol", "mail.gw", "dropmail.me"]
    if config.get("default_provider") not in valid_providers:
        config["default_provider"] = defaults["default_provider"]
        fixed.append("default_provider")
    
    # Validate max_history_entries
    if not isinstance(config.get("max_history_entries"), int) or not (1 <= config.get("max_history_entries", 0) <= 500):
        config["max_history_entries"] = defaults["max_history_entries"]
        fixed.append("max_history_entries")
    
    # If any values were fixed, save the corrected config and warn user
    if fixed:
        console.print(f"[warning]Config values corrected: {', '.join(fixed)}[/]")
        save_config(config)
    
    return config

def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to file."""
    ensure_config_dir()
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        LOGGER.error(f"Failed to save config: {e}")

def save_message_to_history(provider: str, address: str, message: Dict[str, Any]) -> None:
    """Save a received message to history."""
    config = load_config()
    if not config.get("save_messages", True):
        return
    
    ensure_config_dir()
    
    try:
        if HISTORY_FILE.exists():
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
        else:
            history = []
        
        history.append({
            "provider": provider,
            "address": address,
            "timestamp": datetime.now().isoformat(),
            "message": message
        })
        
        # Limit history size
        max_entries = config.get("max_history_entries", 50)
        if len(history) > max_entries:
            history = history[-max_entries:]
        
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        LOGGER.warning(f"Failed to save message to history: {e}")

##############################################################################
# Retry logic with exponential backoff
##############################################################################

def retry_with_backoff(max_retries: int = 3, base_delay: float = 2.0):
    """
    Decorator that retries a function with exponential backoff.
    Retries on: requests.Timeout, requests.ConnectionError, requests.HTTPError (5xx only)
    Wait times: 2s, 4s, 8s between retries
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (requests.Timeout, requests.ConnectionError) as e:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        console.print(f"[dim]Retrying ({attempt + 1}/{max_retries})…[/dim]")
                        time.sleep(delay)
                    else:
                        raise NetworkError(f"Failed after {max_retries} retries: {e}") from e
                except requests.HTTPError as e:
                    # Only retry on 5xx errors
                    if e.response is not None and 500 <= e.response.status_code < 600:
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)
                            console.print(f"[dim]Retrying ({attempt + 1}/{max_retries})…[/dim]")
                            time.sleep(delay)
                        else:
                            raise NetworkError(f"Failed after {max_retries} retries: {e}") from e
                    else:
                        # Don't retry on 4xx errors
                        raise
        return wrapper
    return decorator

##############################################################################
# Utility helpers
##############################################################################

def _countdown_sleep(seconds: int, display_mode: str = "rich") -> None:
    """Sleep with a live countdown indicator (only in rich mode)."""
    if display_mode != "rich":
        time.sleep(seconds)
        return
    
    try:
        with Live(console=console, refresh_per_second=1, transient=True) as live:
            for remaining in range(seconds, 0, -1):
                live.update(f"  ⏳ Next check in {remaining}s…")
                time.sleep(1)
    except Exception:
        # Fallback to regular sleep if Live fails
        time.sleep(seconds)

def _rand_string(n: int = 10) -> str:
    """Generate a random alphanumeric string of length n."""
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))

def _format_timestamp(timestamp: Optional[str]) -> str:
    """Format a timestamp in a human-readable way."""
    if not timestamp:
        return "unknown time"
    
    try:
        # Try different timestamp formats
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(timestamp, fmt)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
        
        # If none of the formats match, just return the original
        return timestamp
    except Exception:
        return timestamp

def _print_email_rich(
    provider: str,
    sender: Optional[str],
    subject: Optional[str],
    date_: Optional[str],
    body: Optional[str],
) -> None:
    """Print an email using rich formatting."""
    # Instead of using a Table object, create a simple string representation directly
    email_info = []
    email_info.append(f"[bold]From:[/] [email_from]{sender or '(unknown)'}[/]")
    email_info.append(f"[bold]Subject:[/] [email_subject]{subject or '(no subject)'}[/]")
    if date_:
        email_info.append(f"[bold]Date:[/] [email_date]{_format_timestamp(date_)}[/]")
    
    email_header = "\n".join(email_info)
    
    formatted_body = body.strip() if body else "(no body)"
    
    panel = Panel(
        f"{email_header}\n\n{formatted_body}", 
        title=f"New Email [{provider}]",
        title_align="left",
        border_style="cyan"
    )
    
    console.print(panel)

def _print_email_plain(
    provider: str,
    sender: Optional[str],
    subject: Optional[str],
    date_: Optional[str],
    body: Optional[str],
) -> None:
    """Print an email in plain text format."""
    print("─" * 60)
    print(f"[{provider}] New Email")
    print(f"From:    {sender or '(unknown)'}")
    print(f"Subject: {subject or '(no subject)'}")
    if date_:
        print(f"Date:    {_format_timestamp(date_)}")
    print()
    print(body.strip() if body else "(no body)")
    print(flush=True)

def print_email(
    provider: str,
    address: str,
    sender: Optional[str],
    subject: Optional[str],
    date_: Optional[str],
    body: Optional[str],
    message_data: Dict[str, Any],
) -> None:
    """Print an email message with the configured display format."""
    config = load_config()
    
    if config.get("display_mode", "rich") == "rich":
        _print_email_rich(provider, sender, subject, date_, body)
    else:
        _print_email_plain(provider, sender, subject, date_, body)
    
    # Save message to history
    save_message_to_history(provider, address, {
        "from": sender,
        "subject": subject,
        "date": date_,
        "body": body,
        "raw_data": message_data
    })

##############################################################################
# Provider implementations
##############################################################################

def make_requests_session(timeout: int = 15) -> requests.Session:
    """Create a requests session with proper headers and timeout."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "TempMailWatcher/2.0 (https://github.com/zebbern/temp-mail-watcher)"
    })
    return session

class ProviderError(Exception):
    """Base exception for provider errors."""
    pass

class NetworkError(ProviderError):
    """Network-related errors."""
    pass

class APIError(ProviderError):
    """API response errors."""
    pass

##############################################################################
# Provider 1 – GuerrillaMail
##############################################################################

@retry_with_backoff()
def _setup_guerrillamail(sess, GM_API, GM_UA):
    """Setup GuerrillaMail account with retry logic."""
    params = {"f": "get_email_address", "ip": "127.0.0.1", "agent": GM_UA}
    res = sess.get(GM_API, params=params, timeout=15)
    res.raise_for_status()
    init = res.json()
    return init["sid_token"], init["email_addr"]

@retry_with_backoff()
def _check_guerrillamail(sess, GM_API, sid):
    """Check GuerrillaMail inbox with retry logic."""
    params = {"f": "check_email", "sid_token": sid, "seq": 0}
    box_res = sess.get(GM_API, params=params, timeout=15)
    box_res.raise_for_status()
    return box_res.json()

@retry_with_backoff()
def _fetch_guerrillamail(sess, GM_API, sid, mail_id):
    """Fetch full GuerrillaMail message with retry logic."""
    params = {"f": "fetch_email", "sid_token": sid, "email_id": mail_id}
    full_res = sess.get(GM_API, params=params, timeout=15)
    full_res.raise_for_status()
    return full_res.json()

def run_guerrillamail(poll: int = 5) -> None:
    """Run the GuerrillaMail provider listener."""
    GM_API = "https://api.guerrillamail.com/ajax.php"
    GM_UA = "Mozilla/5.0 (TempMailWatcher/2.0 by zebbern)"
    
    sess = make_requests_session()
    sess.headers.update({"User-Agent": GM_UA})
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Setting up GuerrillaMail account..."),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("setup", total=None)
        
        try:
            sid, address = _setup_guerrillamail(sess, GM_API, GM_UA)
        except (NetworkError, APIError) as e:
            raise
        except requests.RequestException as e:
            raise NetworkError(f"Network error: {e}") from e
        except Exception as e:
            raise APIError(f"API error: {e}") from e
    
    console.print(f"[success]✓[/] Email address ready: [bold]{address}[/]")
    console.print(f"Polling every [bold]{poll}s[/] for new messages. Press [bold]Ctrl+C[/] to stop.\n")
    
    seen: Set[str] = set()
    try:
        while True:
            try:
                box = _check_guerrillamail(sess, GM_API, sid)
                
                for m in box.get("list", []):
                    if m["mail_id"] in seen:
                        continue
                    
                    seen.add(m["mail_id"])
                    
                    full = _fetch_guerrillamail(sess, GM_API, sid, m["mail_id"])
                    
                    print_email(
                        "guerrillamail",
                        address,
                        full.get("mail_from"),
                        full.get("mail_subject"),
                        full.get("mail_date"),
                        full.get("mail_body", ""),
                        full,
                    )
            except NetworkError as e:
                LOGGER.warning(f"Network error during polling (all retries exhausted): {e}")
            except Exception as e:
                LOGGER.warning(f"Error during polling: {e}")
            
            config = load_config()
            _countdown_sleep(poll, config.get("display_mode", "rich"))
    except KeyboardInterrupt:
        console.print("[info]Stopped listening; goodbye![/]")

##############################################################################
# Provider 2 – mail.tm
##############################################################################

@retry_with_backoff()
def _setup_mail_tm(BASE):
    """Setup mail.tm account with retry logic."""
    # Get available domains
    domains_res = requests.get(f"{BASE}/domains?page=1", timeout=15)
    domains_res.raise_for_status()
    domain = domains_res.json()["hydra:member"][0]["domain"]
    
    # Create random account
    address = f"{_rand_string()}@{domain}"
    password = _rand_string(12)
    
    account_res = requests.post(
        f"{BASE}/accounts", 
        json={"address": address, "password": password},
        timeout=15
    )
    account_res.raise_for_status()
    
    # Get authentication token
    token_res = requests.post(
        f"{BASE}/token", 
        json={"address": address, "password": password},
        timeout=15
    )
    token_res.raise_for_status()
    auth = token_res.json()["token"]
    
    return address, password, auth

@retry_with_backoff()
def _authenticate_mail_tm(BASE, address, password):
    """Re-authenticate with mail.tm (for token refresh)."""
    token_res = requests.post(
        f"{BASE}/token", 
        json={"address": address, "password": password},
        timeout=15
    )
    token_res.raise_for_status()
    return token_res.json()["token"]

@retry_with_backoff()
def _check_mail_tm(BASE, headers):
    """Check mail.tm inbox with retry logic."""
    inbox_res = requests.get(f"{BASE}/messages", headers=headers, timeout=15)
    inbox_res.raise_for_status()
    return inbox_res.json()["hydra:member"]

@retry_with_backoff()
def _fetch_mail_tm(BASE, headers, message_id):
    """Fetch full mail.tm message with retry logic."""
    full_res = requests.get(f"{BASE}/messages/{message_id}", headers=headers, timeout=15)
    full_res.raise_for_status()
    return full_res.json()

def run_mail_tm(poll: int = 5) -> None:
    """Run the mail.tm provider listener."""
    BASE = "https://api.mail.tm"
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Setting up mail.tm account..."),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("setup", total=None)
        
        try:
            address, password, auth = _setup_mail_tm(BASE)
            headers = {"Authorization": f"Bearer {auth}"}
        except (NetworkError, APIError) as e:
            raise
        except requests.RequestException as e:
            raise NetworkError(f"Network error: {e}") from e
        except Exception as e:
            raise APIError(f"API error: {e}") from e
    
    console.print(f"[success]✓[/] Email address ready: [bold]{address}[/]")
    console.print(f"Polling every [bold]{poll}s[/] for new messages. Press [bold]Ctrl+C[/] to stop.\n")
    
    seen: Set[str] = set()
    try:
        while True:
            try:
                inbox = _check_mail_tm(BASE, headers)
                
                for m in inbox:
                    if m["id"] in seen:
                        continue
                    
                    seen.add(m["id"])
                    
                    full = _fetch_mail_tm(BASE, headers, m["id"])
                    
                    print_email(
                        "mail.tm",
                        address,
                        full.get("from", {}).get("address"),
                        full.get("subject"),
                        full.get("createdAt"),
                        full.get("text", ""),
                        full,
                    )
            except requests.HTTPError as e:
                # Handle 401 (token expired) - re-authenticate
                if e.response is not None and e.response.status_code == 401:
                    try:
                        console.print("[info]Re-authenticated with mail.tm[/]")
                        auth = _authenticate_mail_tm(BASE, address, password)
                        headers = {"Authorization": f"Bearer {auth}"}
                    except Exception as reauth_error:
                        LOGGER.warning(f"Failed to re-authenticate: {reauth_error}")
                else:
                    LOGGER.warning(f"HTTP error during polling: {e}")
            except NetworkError as e:
                LOGGER.warning(f"Network error during polling (all retries exhausted): {e}")
            except Exception as e:
                LOGGER.warning(f"Error during polling: {e}")
            
            config = load_config()
            _countdown_sleep(poll, config.get("display_mode", "rich"))
    except KeyboardInterrupt:
        console.print("[info]Stopped listening; goodbye![/]")

##############################################################################
# Provider 3 – tempmail.lol
##############################################################################

@retry_with_backoff()
def _setup_tempmail_lol(BASE, rush):
    """Setup tempmail.lol account with retry logic."""
    endpoint = f"{BASE}/generate/rush" if rush else f"{BASE}/generate"
    gen_res = requests.get(endpoint, timeout=15)
    gen_res.raise_for_status()
    data = gen_res.json()
    return data["address"], data["token"]

@retry_with_backoff()
def _check_tempmail_lol(BASE, token):
    """Check tempmail.lol inbox with retry logic."""
    inbox_res = requests.get(f"{BASE}/auth/{token}", timeout=15)
    inbox_res.raise_for_status()
    return inbox_res.json().get("email", [])

def run_tempmail_lol(poll: int = 5, rush: bool = False) -> None:
    """Run the tempmail.lol provider listener."""
    BASE = "https://api.tempmail.lol"
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Setting up tempmail.lol account..."),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("setup", total=None)
        
        try:
            address, token = _setup_tempmail_lol(BASE, rush)
        except (NetworkError, APIError) as e:
            raise
        except requests.RequestException as e:
            raise NetworkError(f"Network error: {e}") from e
        except Exception as e:
            raise APIError(f"API error: {e}") from e
    
    console.print(f"[success]✓[/] Email address ready: [bold]{address}[/]")
    console.print(f"Polling every [bold]{poll}s[/] for new messages. Press [bold]Ctrl+C[/] to stop.\n")
    
    seen: Set[str] = set()
    try:
        while True:
            try:
                msgs = _check_tempmail_lol(BASE, token)
                
                for m in msgs:
                    # Create a message ID using SHA256 hash for better deduplication
                    msg_content = f"{m.get('from', '')}{m.get('subject', '')}{m.get('body', '')}"
                    msg_id = hashlib.sha256(msg_content.encode()).hexdigest()[:16]
                    
                    if msg_id in seen:
                        continue
                    
                    seen.add(msg_id)
                    
                    print_email(
                        "tempmail.lol",
                        address,
                        m.get("from"),
                        m.get("subject"),
                        None,  # No date provided by this API
                        m.get("body", ""),
                        m,
                    )
            except NetworkError as e:
                LOGGER.warning(f"Network error during polling (all retries exhausted): {e}")
            except Exception as e:
                LOGGER.warning(f"Error during polling: {e}")
            
            config = load_config()
            _countdown_sleep(poll, config.get("display_mode", "rich"))
    except KeyboardInterrupt:
        console.print("[info]Stopped listening; goodbye![/]")

##############################################################################
# Provider 4 – mail.gw (identical API to mail.tm, hosted elsewhere)
##############################################################################

@retry_with_backoff()
def _setup_mail_gw(BASE):
    """Setup mail.gw account with retry logic."""
    # Get available domains
    domains_res = requests.get(f"{BASE}/domains?page=1", timeout=15)
    domains_res.raise_for_status()
    domain = domains_res.json()["hydra:member"][0]["domain"]
    
    # Create random account
    address = f"{_rand_string()}@{domain}"
    password = _rand_string(12)
    
    account_res = requests.post(
        f"{BASE}/accounts", 
        json={"address": address, "password": password},
        timeout=15
    )
    account_res.raise_for_status()
    
    # Get authentication token
    token_res = requests.post(
        f"{BASE}/token", 
        json={"address": address, "password": password},
        timeout=15
    )
    token_res.raise_for_status()
    auth = token_res.json()["token"]
    
    return address, password, auth

@retry_with_backoff()
def _authenticate_mail_gw(BASE, address, password):
    """Re-authenticate with mail.gw (for token refresh)."""
    token_res = requests.post(
        f"{BASE}/token", 
        json={"address": address, "password": password},
        timeout=15
    )
    token_res.raise_for_status()
    return token_res.json()["token"]

@retry_with_backoff()
def _check_mail_gw(BASE, headers):
    """Check mail.gw inbox with retry logic."""
    inbox_res = requests.get(f"{BASE}/messages", headers=headers, timeout=15)
    inbox_res.raise_for_status()
    return inbox_res.json()["hydra:member"]

@retry_with_backoff()
def _fetch_mail_gw(BASE, headers, message_id):
    """Fetch full mail.gw message with retry logic."""
    full_res = requests.get(f"{BASE}/messages/{message_id}", headers=headers, timeout=15)
    full_res.raise_for_status()
    return full_res.json()

def run_mail_gw(poll: int = 5) -> None:
    """Run the mail.gw provider listener."""
    BASE = "https://api.mail.gw"
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Setting up mail.gw account..."),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("setup", total=None)
        
        try:
            address, password, auth = _setup_mail_gw(BASE)
            headers = {"Authorization": f"Bearer {auth}"}
        except (NetworkError, APIError) as e:
            raise
        except requests.RequestException as e:
            raise NetworkError(f"Network error: {e}") from e
        except Exception as e:
            raise APIError(f"API error: {e}") from e
    
    console.print(f"[success]✓[/] Email address ready: [bold]{address}[/]")
    console.print(f"Polling every [bold]{poll}s[/] for new messages. Press [bold]Ctrl+C[/] to stop.\n")
    
    seen: Set[str] = set()
    try:
        while True:
            try:
                inbox = _check_mail_gw(BASE, headers)
                
                for m in inbox:
                    if m["id"] in seen:
                        continue
                    
                    seen.add(m["id"])
                    
                    full = _fetch_mail_gw(BASE, headers, m["id"])
                    
                    print_email(
                        "mail.gw",
                        address,
                        full.get("from", {}).get("address"),
                        full.get("subject"),
                        full.get("createdAt"),
                        full.get("text", ""),
                        full,
                    )
            except requests.HTTPError as e:
                # Handle 401 (token expired) - re-authenticate
                if e.response is not None and e.response.status_code == 401:
                    try:
                        console.print("[info]Re-authenticated with mail.gw[/]")
                        auth = _authenticate_mail_gw(BASE, address, password)
                        headers = {"Authorization": f"Bearer {auth}"}
                    except Exception as reauth_error:
                        LOGGER.warning(f"Failed to re-authenticate: {reauth_error}")
                else:
                    LOGGER.warning(f"HTTP error during polling: {e}")
            except NetworkError as e:
                LOGGER.warning(f"Network error during polling (all retries exhausted): {e}")
            except Exception as e:
                LOGGER.warning(f"Error during polling: {e}")
            
            config = load_config()
            _countdown_sleep(poll, config.get("display_mode", "rich"))
    except KeyboardInterrupt:
        console.print("[info]Stopped listening; goodbye![/]")

##############################################################################
# Provider 5 – dropmail.me
##############################################################################

@retry_with_backoff()
def _setup_dropmail_me(BASE, token):
    """Setup dropmail.me account with retry logic."""
    query = """
    mutation {
      introduceSession {
        id
        expiresAt
        addresses {
          address
        }
      }
    }
    """
    
    res = requests.post(
        f"{BASE}/{token}",
        json={"query": query},
        headers={"Content-Type": "application/json"},
        timeout=15
    )
    res.raise_for_status()
    
    data = res.json().get("data", {})
    session = data.get("introduceSession", {})
    session_id = session.get("id")
    address = session.get("addresses", [{}])[0].get("address")
    
    if not session_id or not address:
        raise APIError("Failed to get valid session or address")
    
    return session_id, address

@retry_with_backoff()
def _check_dropmail_me(BASE, token, session_id):
    """Check dropmail.me inbox with retry logic."""
    query = """
    query($id: ID!){
      session(id: $id){
        mails{
          id
          fromAddr
          headerSubject
          text
          receivedAt
        }
      }
    }
    """
    
    res = requests.post(
        f"{BASE}/{token}",
        json={"query": query, "variables": {"id": session_id}},
        headers={"Content-Type": "application/json"},
        timeout=15
    )
    res.raise_for_status()
    
    data = res.json().get("data", {})
    session_data = data.get("session", {})
    
    if not session_data:
        raise APIError("Session expired or not found")
    
    return session_data.get("mails", [])

def run_dropmail_me(poll: int = 5) -> None:
    """Run the dropmail.me provider listener."""
    BASE = "https://dropmail.me/api/graphql"
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Setting up dropmail.me account..."),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("setup", total=None)
        
        try:
            token = _rand_string(12)
            session_id, address = _setup_dropmail_me(BASE, token)
        except (NetworkError, APIError) as e:
            raise
        except requests.RequestException as e:
            raise NetworkError(f"Network error: {e}") from e
        except Exception as e:
            raise APIError(f"API error: {e}") from e
    
    console.print(f"[success]✓[/] Email address ready: [bold]{address}[/]")
    console.print(f"Polling every [bold]{poll}s[/] for new messages. Press [bold]Ctrl+C[/] to stop.\n")
    
    seen: Set[str] = set()
    try:
        while True:
            try:
                mails = _check_dropmail_me(BASE, token, session_id)
                
                for m in mails:
                    if m["id"] in seen:
                        continue
                    
                    seen.add(m["id"])
                    
                    print_email(
                        "dropmail.me",
                        address,
                        m.get("fromAddr"),
                        m.get("headerSubject"),
                        m.get("receivedAt"),
                        m.get("text", ""),
                        m,
                    )
            except APIError as e:
                LOGGER.warning(f"API error during polling: {e}")
                break  # Session expired, exit gracefully
            except NetworkError as e:
                LOGGER.warning(f"Network error during polling (all retries exhausted): {e}")
            except Exception as e:
                LOGGER.warning(f"Error during polling: {e}")
            
            config = load_config()
            _countdown_sleep(poll, config.get("display_mode", "rich"))
    except KeyboardInterrupt:
        console.print("[info]Stopped listening; goodbye![/]")

##############################################################################
# CLI - argument parsing, interactive menu, dispatcher
##############################################################################

PROVIDERS: Dict[str, Callable[[int], None]] = {
    "guerrillamail": run_guerrillamail,
    "mail.tm": run_mail_tm,
    "tempmail.lol": run_tempmail_lol,
    "mail.gw": run_mail_gw,
    "dropmail.me": run_dropmail_me,
}

def print_ascii_banner() -> None:
    """Print the ASCII art banner."""
    # Clear the screen before printing banner
    clear_screen()
    
    banner = r"""
 _____                   __  __       _ _    __        __    _       _               
|_   _|__ _ __ ___  _ __|  \/  | __ _(_) |   \ \      / /_ _| |_ ___| |__   ___ _ __ 
  | |/ _ \ '_ ` _ \| '_ \ |\/| |/ _` | | |____\ \ /\ / / _` | __/ __| '_ \ / _ \ '__|
  | |  __/ | | | | | |_) | |  | | (_| | | |_____\ V  V / (_| | || (__| | | |  __/ |   
  |_|\___|_| |_| |_| .__/|_|  |_|\__,_|_|_|      \_/\_/ \__,_|\__\___|_| |_|\___|_|   
                   |_|                                                               
    """
    console.print(banner, style="bold cyan")
    console.print("Developed by [link=https://github.com/zebbern]zebbern[/link]", style="cyan")
    console.print("─" * 80 + "\n")

def interactive_menu() -> Tuple[Optional[str], int]:
    """Display an interactive menu for provider selection with failover support."""
    print_ascii_banner()
    
    config = load_config()
    default_provider = config.get("default_provider", "mail.tm")
    default_poll = config.get("poll_interval", 5)
    
    while True:  # Loop to allow retry on provider failure
        # Display provider options
        console.print("[header]Choose a temporary email provider:[/]")
        
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="cyan bold")
        table.add_column()
        
        for idx, name in enumerate(PROVIDERS, 1):
            default_marker = " [yellow](default)[/]" if name == default_provider else ""
            table.add_row(f"{idx})", f"{name}{default_marker}")
        
        console.print(table)
        
        # Get provider selection
        providers_list = list(PROVIDERS.keys())
        default_index = providers_list.index(default_provider) if default_provider in providers_list else 0
        
        while True:
            choice = console.input(f"[bold]Provider[/] [1-{len(PROVIDERS)}] [{default_index + 1}]: ")
            choice = choice.strip() or str(default_index + 1)
            
            if choice.isdigit() and 1 <= int(choice) <= len(PROVIDERS):
                provider = providers_list[int(choice) - 1]
                break
            console.print("[warning]Invalid selection. Please enter a number between " 
                          f"1 and {len(PROVIDERS)}.[/]")
        
        # Get polling interval
        while True:
            poll_str = console.input(f"[bold]Polling interval[/] (seconds) [{default_poll}]: ")
            poll_str = poll_str.strip() or str(default_poll)
            
            if poll_str.isdigit() and int(poll_str) > 0:
                poll = int(poll_str)
                break
            console.print("[warning]Invalid polling interval. Please enter a positive number.[/]")
        
        # Save selections as defaults for next time
        config["default_provider"] = provider
        config["poll_interval"] = poll
        save_config(config)
        
        # Try to run the provider
        try:
            # Print banner for the selected provider
            print_ascii_banner()
            
            # Run the selected provider
            if provider == "tempmail.lol":
                run_tempmail_lol(poll=poll, rush=False)
            else:
                PROVIDERS[provider](poll=poll)
            
            # If we reach here, provider exited normally (e.g., KeyboardInterrupt)
            return None, poll
            
        except (NetworkError, APIError) as e:
            console.print(f"[warning]Provider {provider} failed: {e}[/]")
            console.print("[warning]Try a different provider or press Ctrl+C to exit.[/]")
            console.print()
            # Loop continues to show menu again
        except KeyboardInterrupt:
            # User wants to exit
            return None, poll

def list_providers_table() -> None:
    """Display a table of all available providers and exit."""
    table = Table(title="Available Providers", show_header=True, header_style="bold cyan")
    table.add_column("Provider", style="cyan")
    table.add_column("Description", style="white")
    
    providers_info = {
        "guerrillamail": "Fast, reliable temporary email service",
        "mail.tm": "Privacy-focused with JWT authentication",
        "tempmail.lol": "Simple and quick temporary email",
        "mail.gw": "Alternative to mail.tm with same API",
        "dropmail.me": "GraphQL-based temporary email service"
    }
    
    for provider in PROVIDERS.keys():
        table.add_row(provider, providers_info.get(provider, "Temporary email provider"))
    
    console.print(table)
    sys.exit(0)

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    config = load_config()
    
    parser = argparse.ArgumentParser(
        description="Temp Mail Watcher - A professional CLI for temporary email inboxes."
    )
    parser.add_argument(
        "provider",
        nargs="?",
        choices=list(PROVIDERS.keys()),
        help="Temp-mail provider to use. If omitted, an interactive menu is shown.",
    )
    parser.add_argument(
        "--poll", "-p",
        type=int,
        default=config.get("poll_interval", 5),
        help=f"Polling interval in seconds (default: {config.get('poll_interval', 5)}).",
    )
    parser.add_argument(
        "--rush", "-r",
        action="store_true",
        help="Use rush mode for tempmail.lol (faster address generation).",
    )
    parser.add_argument(
        "--display", "-d",
        choices=["rich", "plain"],
        default=config.get("display_mode", "rich"),
        help="Display mode (default: rich).",
    )
    parser.add_argument(
        "--no-save", "-n",
        action="store_true",
        help="Don't save received messages to history.",
    )
    parser.add_argument(
        "--list-providers", "-l",
        action="store_true",
        help="List all available providers and exit.",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="View email history and exit.",
    )
    parser.add_argument(
        "--clear-history",
        action="store_true",
        help="Clear email history and exit.",
    )
    parser.add_argument(
        "--export",
        type=str,
        metavar="FILE",
        nargs="?",
        const="email_export.json",
        help="Export emails to JSON file (default: email_export.json) and exit.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with detailed error messages.",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="Temp Mail Watcher v2.1.0 by zebbern (https://github.com/zebbern)",
    )
    
    args = parser.parse_args(argv)
    
    # Handle mutually exclusive flags that exit immediately
    if args.list_providers:
        list_providers_table()
    
    if args.history:
        view_history()
        sys.exit(0)
    
    if args.clear_history:
        clear_history()
        sys.exit(0)
    
    if args.export:
        export_emails(args.export)
        sys.exit(0)
    
    # Set logging level based on debug flag
    if args.debug:
        LOGGER.setLevel(logging.DEBUG)
    
    # Update config with CLI options
    config["poll_interval"] = args.poll
    config["display_mode"] = args.display
    config["save_messages"] = not args.no_save
    save_config(config)
    
    return args

def signal_handler(signum, frame):
    """Handle SIGTERM signal gracefully."""
    console.print("\n[info]Received SIGTERM. Goodbye![/]")
    sys.exit(0)

def main() -> None:
    """Main entry point for the application."""
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Clear the screen
        clear_screen()
        
        # Parse arguments
        args = parse_args()
        
        # If no provider specified, show interactive menu
        if not args.provider:
            provider_name, poll_interval = interactive_menu()
            # If interactive menu returns None, user exited
            if provider_name is None:
                console.print("[info]Goodbye![/]")
                sys.exit(0)
        else:
            provider_name = args.provider
            poll_interval = args.poll
        
        # Print banner for non-interactive mode
        if args.provider:
            print_ascii_banner()
        
        # Run the selected provider
        if provider_name == "tempmail.lol" and args.rush:
            run_tempmail_lol(poll=poll_interval, rush=True)
        else:
            PROVIDERS[provider_name](poll=poll_interval)
    except NetworkError as e:
        LOGGER.error(f"Network error: {e}")
        console.print("[error]Failed to connect to the service. Please check your internet connection.[/]")
        sys.exit(1)
    except APIError as e:
        LOGGER.error(f"API error: {e}")
        console.print("[error]The service API returned an error. The service might be down or has changed.[/]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[info]Stopped by user. Goodbye![/]")
        sys.exit(0)
    except Exception as e:
        LOGGER.error(f"Unexpected error: {e}")
        console.print(f"[error]An unexpected error occurred: {e}[/]")
        if args.debug:
            console.print_exception()
        sys.exit(1)

##############################################################################
# Additional features
##############################################################################

def view_history() -> None:
    """View email history from saved messages."""
    if not HISTORY_FILE.exists():
        console.print("[warning]No message history found.[/]")
        return
    
    try:
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
        
        if not history:
            console.print("[warning]Message history is empty.[/]")
            return
        
        console.print(f"[header]Message History[/] ({len(history)} entries)")
        
        for idx, entry in enumerate(history, 1):
            provider = entry.get("provider", "unknown")
            address = entry.get("address", "unknown")
            timestamp = entry.get("timestamp", "unknown")
            message = entry.get("message", {})
            
            panel = Panel(
                f"Provider: [bold]{provider}[/]\n"
                f"Address: [bold]{address}[/]\n"
                f"Time: [bold]{_format_timestamp(timestamp)}[/]\n"
                f"From: [email_from]{message.get('from', '(unknown)')}[/]\n"
                f"Subject: [email_subject]{message.get('subject', '(no subject)')}[/]\n\n"
                f"{message.get('body', '(no body)').strip()[:500]}",
                title=f"Message #{idx}",
                title_align="left",
                border_style="cyan"
            )
            console.print(panel)
            
            if idx < len(history):
                continue_viewing = console.input(
                    f"[bold]Press Enter to view next message or 'q' to quit[/] [{idx}/{len(history)}]: "
                )
                if continue_viewing.lower() == 'q':
                    break
    except Exception as e:
        console.print(f"[error]Error viewing history: {e}[/]")

def export_emails(output_file: str = "email_export.json") -> None:
    """Export emails to a JSON file."""
    if not HISTORY_FILE.exists():
        console.print("[warning]No message history to export.[/]")
        return
    
    try:
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
        
        with open(output_file, "w") as f:
            json.dump(history, f, indent=2)
        
        console.print(f"[success]Successfully exported {len(history)} messages to {output_file}[/]")
    except Exception as e:
        console.print(f"[error]Error exporting emails: {e}[/]")

def clear_history() -> None:
    """Clear email history."""
    if not HISTORY_FILE.exists():
        console.print("[warning]No message history to clear.[/]")
        return
    
    confirm = console.input("[bold red]This will permanently delete all saved messages. Continue? (y/N): [/]")
    if confirm.lower() != 'y':
        console.print("[info]Operation cancelled.[/]")
        return
    
    try:
        os.remove(HISTORY_FILE)
        console.print("[success]Message history cleared successfully.[/]")
    except Exception as e:
        console.print(f"[error]Error clearing history: {e}[/]")

##############################################################################
# Entry point
##############################################################################

if __name__ == "__main__":
    main()