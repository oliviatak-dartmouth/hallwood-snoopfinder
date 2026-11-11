"""
Config manager for reading/writing config.yaml and .env settings.
Used by both the CLI (run.py) and the Streamlit UI (app.py).
Supports both local mode (files) and cloud mode (st.secrets + Google Sheet).
"""

import os
import json
import yaml
from datetime import datetime, timezone
from typing import List, Optional, Tuple


CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")


def is_cloud_mode() -> bool:
    """Check if running on Streamlit Cloud (st.secrets available with credentials)."""
    try:
        import streamlit as st
        return "gcp_service_account" in st.secrets or "google_credentials" in st.secrets
    except Exception:
        return False


def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def save_config(config: dict, path: str = CONFIG_PATH) -> None:
    """Rewrite config.yaml preserving structure."""
    with open(path, "r") as f:
        lines = f.readlines()

    new_lines = []
    in_ar_section = False
    in_cookies_section = False

    for line in lines:
        stripped = line.rstrip()
        lstripped = stripped.lstrip()

        # --- ar_accounts section ---
        if lstripped.startswith("ar_accounts:") and not lstripped.startswith("#"):
            in_ar_section = True
            in_cookies_section = False
            new_lines.append("ar_accounts:\n")
            for acct in config.get("ar_accounts", []):
                if acct:
                    new_lines.append(f"  - {acct}\n")
            continue

        if in_ar_section:
            if lstripped.startswith("-"):
                continue
            if lstripped.startswith("#"):
                new_lines.append(line)
                continue
            if not stripped:
                new_lines.append(line)
                continue
            if stripped and not stripped[0].isspace():
                in_ar_section = False
            else:
                new_lines.append(line)
                continue

        # --- cookies section ---
        if lstripped.startswith("cookies:") and not lstripped.startswith("#"):
            in_cookies_section = True
            in_ar_section = False
            cookies = config.get("apify", {}).get("cookies", [])
            cookies_json = json.dumps(cookies)
            new_lines.append(f"  cookies: {cookies_json}\n")
            continue

        if in_cookies_section:
            if stripped == "" or (stripped and not stripped[0].isspace()):
                in_cookies_section = False
            elif lstripped and not lstripped.startswith("-") and ":" in lstripped.split("#")[0]:
                in_cookies_section = False
            else:
                continue

        new_lines.append(line)

    with open(path, "w") as f:
        f.writelines(new_lines)


def get_ar_accounts(config: dict) -> List[str]:
    return [a for a in config.get("ar_accounts", []) if a]


def add_ar_account(username: str, config: dict = None, path: str = CONFIG_PATH) -> Tuple[bool, str]:
    username = username.strip().lstrip("@").lower()
    if not username:
        return False, "Username cannot be empty."
    if config is None:
        config = load_config(path)
    accounts = get_ar_accounts(config)
    if username in accounts:
        return False, f"@{username} is already being tracked."
    accounts.append(username)
    accounts.sort()
    config["ar_accounts"] = accounts
    save_config(config, path)
    return True, f"@{username} added successfully."


def remove_ar_account(username: str, config: dict = None, path: str = CONFIG_PATH) -> Tuple[bool, str]:
    username = username.strip().lstrip("@").lower()
    if config is None:
        config = load_config(path)
    accounts = get_ar_accounts(config)
    if username not in accounts:
        return False, f"@{username} is not in the tracked list."
    accounts.remove(username)
    config["ar_accounts"] = accounts
    save_config(config, path)
    return True, f"@{username} removed."


def get_cookies(config: dict = None, path: str = CONFIG_PATH) -> list:
    if config is None:
        config = load_config(path)
    return config.get("apify", {}).get("cookies", [])


def validate_cookies(cookies_json: str) -> Tuple[bool, str, Optional[list]]:
    """
    Validate a cookies JSON string.
    Returns (valid, message, parsed_list_or_None).
    """
    cookies_json = cookies_json.strip()
    if not cookies_json:
        return False, "Cookie string is empty.", None

    try:
        parsed = json.loads(cookies_json)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}", None

    if not isinstance(parsed, list):
        return False, "Cookies must be a JSON array (list of cookie objects).", None

    if len(parsed) == 0:
        return False, "Cookie array is empty.", None

    required_names = {"sessionid", "ds_user_id", "csrftoken"}
    cookie_names = {c.get("name", "") for c in parsed}
    missing = required_names - cookie_names
    if missing:
        return False, f"Missing critical cookies: {', '.join(missing)}. Make sure you copied ALL cookies from the browser.", None

    return True, f"Valid ({len(parsed)} cookies).", parsed


def update_cookies(cookies_json: str, path: str = CONFIG_PATH) -> Tuple[bool, str]:
    """Validate and save new cookies to config.yaml (local mode)."""
    valid, msg, parsed = validate_cookies(cookies_json)
    if not valid:
        return False, msg

    config = load_config(path)
    if "apify" not in config:
        config["apify"] = {}
    config["apify"]["cookies"] = parsed
    save_config(config, path)
    return True, f"Cookies updated successfully ({len(parsed)} cookies saved)."


def update_cookies_cloud(cookies_json: str, sheets_manager) -> Tuple[bool, str]:
    """Validate and save cookies to the Google Sheet _Config tab (cloud mode)."""
    valid, msg, parsed = validate_cookies(cookies_json)
    if not valid:
        return False, msg

    success = sheets_manager.save_cookies_to_sheet(cookies_json)
    if success:
        return True, f"Cookies updated successfully ({len(parsed)} cookies saved)."
    else:
        return False, "Failed to save cookies to Google Sheet. Check the logs."


def get_cookie_health(config: dict = None, cookies_override: list = None) -> dict:
    """
    Check cookie expiry and return health status.
    cookies_override lets you pass cookies directly (e.g. from sheet storage).
    """
    if config is None:
        config = load_config()

    cookies = cookies_override or config.get("apify", {}).get("cookies", [])
    if not cookies:
        return {
            "status": "missing",
            "message": "No cookies configured. You need to add Instagram cookies before running the tracker.",
            "details": {}
        }

    now = datetime.now(timezone.utc).timestamp()
    session_cookie = None
    ds_user_cookie = None
    expired_cookies = []

    for c in cookies:
        name = c.get("name", "")
        expiry = c.get("expirationDate")

        if name == "sessionid":
            session_cookie = c
        elif name == "ds_user_id":
            ds_user_cookie = c

        if expiry and expiry < now:
            expired_cookies.append(name)

    details = {}

    if session_cookie:
        exp = session_cookie.get("expirationDate")
        if exp:
            details["session_expires"] = datetime.fromtimestamp(exp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            details["session_days_left"] = max(0, int((exp - now) / 86400))
        details["user_id"] = session_cookie.get("value", "").split("%3A")[0] if session_cookie.get("value") else "unknown"

    if ds_user_cookie:
        details["ds_user_id"] = ds_user_cookie.get("value", "unknown")

    critical_expired = {"sessionid", "csrftoken", "ds_user_id"} & set(expired_cookies)
    if critical_expired:
        return {
            "status": "expired",
            "message": f"EXPIRED cookies: {', '.join(critical_expired)}. The tracker will NOT work until you update cookies.",
            "details": details
        }

    days_left = details.get("session_days_left", 999)
    if days_left < 7:
        return {
            "status": "warning",
            "message": f"Session cookie expires in {days_left} day(s). Update cookies soon to avoid interruption.",
            "details": details
        }

    return {
        "status": "ok",
        "message": f"Cookies look healthy. Session expires in {days_left} days.",
        "details": details
    }


def get_apify_token(config: dict = None) -> str:
    if config is None:
        config = load_config()
    # Check st.secrets first in cloud mode
    try:
        import streamlit as st
        token = st.secrets.get("APIFY_API_TOKEN", "")
        if token:
            return token
    except Exception:
        pass
    return os.getenv("APIFY_API_TOKEN", config.get("apify", {}).get("api_token", ""))


def get_spreadsheet_id() -> str:
    """Get spreadsheet ID from st.secrets or .env."""
    try:
        import streamlit as st
        sid = st.secrets.get("GOOGLE_SPREADSHEET_ID", "")
        if sid:
            return sid
    except Exception:
        pass
    return os.getenv("GOOGLE_SPREADSHEET_ID", "")


def get_google_credentials_dict() -> Optional[dict]:
    """Get Google credentials as a dict from st.secrets (cloud mode only)."""
    try:
        import streamlit as st
        if "gcp_service_account" in st.secrets:
            return dict(st.secrets["gcp_service_account"])
        if "google_credentials" in st.secrets:
            return dict(st.secrets["google_credentials"])
    except Exception:
        pass
    return None
