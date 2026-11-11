"""
Data sources for Instagram following data.
Supports both CSV files and Apify API.
"""

import ast
import csv
import json
import os
from typing import List, Dict


def ensure_directories():
    """Create required data directories if they don't exist."""
    dirs = ['data/exports', 'data/processed']
    for d in dirs:
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
            print(f"[DataSource] Created directory: {d}")


def get_data_source(config: dict):
    """Factory function to get the appropriate data source based on config."""
    # Ensure directories exist
    ensure_directories()

    # Get source type and normalize it (remove quotes, whitespace)
    source_type = str(config.get('data_source', 'apify')).lower().strip().strip('"').strip("'")

    print(f"[DataSource] Config data_source = '{source_type}'")

    if source_type == 'csv':
        export_path = config.get('csv_export_path', 'data/exports')
        processed_path = config.get('processed_data_path', 'data/processed')
        print(f"[DataSource] Initializing CSVSource")
        print(f"[DataSource] Export path: {export_path}")
        print(f"[DataSource] Processed path: {processed_path}")
        return CSVSource(export_path, processed_path)
    else:
        # Default to Apify for any non-csv value (including 'apify')
        print(f"[DataSource] Initializing ApifySource (ignoring CSV folders)")
        return ApifySource(config)


class ApifySource:
    """Fetch following data from Apify Instagram scraper."""

    def __init__(self, config: dict = None):
        from apify_client import ApifyClient
        token = os.getenv('APIFY_API_TOKEN')
        if not token:
            raise ValueError("APIFY_API_TOKEN not set in .env file")
        self.client = ApifyClient(token)
        # Get actor_id from config or use default
        apify_config = config.get('apify', {}) if config else {}
        self.actor_id = apify_config.get('actor_id', 'louisdeconinck/instagram-following-scraper')
        # Get Instagram session ID from env or config
        self.session_id = os.getenv('INSTAGRAM_SESSION_ID') or apify_config.get('session_id', '')
        # Get cookies from config (raw JSON string from browser Copy Cookies extension)
        cookies_raw = apify_config.get('cookies', '')
        cookies_str = str(cookies_raw).strip() if cookies_raw and str(cookies_raw).strip() else ''

        self.cookies_raw = cookies_str      # original string, kept for debug
        self.cookies_list = None            # parsed array, what we actually send

        if cookies_str:
            try:
                parsed = json.loads(cookies_str)
                if isinstance(parsed, list):
                    self.cookies_list = parsed
                else:
                    print(f"[ApifySource] WARNING: Cookies parsed but is not a list (got {type(parsed).__name__})")
            except json.JSONDecodeError:
                # Fallback: cookies may be in Python repr format (single quotes, True/False)
                # ast.literal_eval safely handles this without executing any code
                try:
                    parsed = ast.literal_eval(cookies_str)
                    if isinstance(parsed, list):
                        self.cookies_list = parsed
                        print(f"[ApifySource] NOTE: Cookies were in Python format, not JSON — parsed via fallback. OK to continue.")
                    else:
                        print(f"[ApifySource] WARNING: Cookies parsed but is not a list (got {type(parsed).__name__})")
                except (ValueError, SyntaxError) as e:
                    print(f"[ApifySource] WARNING: Could not parse cookies as JSON or Python literal: {e}")

        print(f"[ApifySource] Initialized with actor: {self.actor_id}")

        # --- Cookie debug block ---
        if self.cookies_raw:
            print(f"[ApifySource] Cookie string length : {len(self.cookies_raw)} characters")
            print(f"[ApifySource] Cookie string preview: {self.cookies_raw[:100]}")
            if self.cookies_list is not None:
                print(f"[ApifySource] Cookies parsed OK  : {len(self.cookies_list)} cookies in array")
                cookie_names = [c.get('name', '?') for c in self.cookies_list[:5]]
                print(f"[ApifySource] First cookie names : {cookie_names}")
            else:
                print(f"[ApifySource] WARNING: Cookie string present but could not be parsed as JSON array")
        else:
            print(f"[ApifySource] WARNING: No cookies set in config.yaml — likely to get 401/403 errors")

        if self.session_id:
            print(f"[ApifySource] Instagram session ID configured")

    def get_source_name(self) -> str:
        return "Apify API"

    def get_following(self, username: str) -> List[Dict]:
        """Fetch following list from Apify API."""
        print(f"[ApifySource] Fetching following for @{username}...")
        print(f"[ApifySource] Actor: {self.actor_id}")

        # Input format for louisdeconinck/instagram-following-scraper
        run_input = {
            "usernames": [username],
            "limit": 5000
        }

        # Add session ID if available
        if self.session_id:
            run_input["sessionId"] = self.session_id

        # Add cookies — actor requires a JSON string (not an array)
        # If we parsed the cookies, re-serialize to valid JSON string (fixes Python-format cookies)
        if self.cookies_list is not None:
            cookies_to_send = json.dumps(self.cookies_list)
            run_input["cookies"] = cookies_to_send
        elif self.cookies_raw:
            # Fallback: send raw string as-is
            cookies_to_send = self.cookies_raw
            run_input["cookies"] = cookies_to_send
        else:
            cookies_to_send = None

        # --- Per-run cookie debug block ---
        print(f"[ApifySource] --- Run input debug ---")
        print(f"[ApifySource] usernames      : {run_input['usernames']}")
        print(f"[ApifySource] limit          : {run_input['limit']}")
        print(f"[ApifySource] sessionId      : {'set' if self.session_id else 'NOT SET'}")
        if cookies_to_send:
            print(f"[ApifySource] cookies format : JSON string ({len(self.cookies_list)} cookies)" if self.cookies_list else f"[ApifySource] cookies format : raw string fallback")
            print(f"[ApifySource] cookies preview: {cookies_to_send[:100]}")
        else:
            print(f"[ApifySource] cookies        : NOT SET")
        print(f"[ApifySource] ---------------------")

        try:
            print(f"[ApifySource] Starting actor run (this may take a few minutes)...")
            run = self.client.actor(self.actor_id).call(run_input=run_input)

            # Check run status
            run_status = run.get("status", "UNKNOWN")
            print(f"[ApifySource] Run finished with status: {run_status}")

            if run_status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise RuntimeError(
                    f"Apify run {run_status} for @{username}. "
                    f"Check the Apify console for details (run ID: {run.get('id', '?')}). "
                    f"This usually means cookies are expired or the Instagram account is blocked."
                )

            print(f"[ApifySource] Fetching results...")

            results = []
            for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
                # Standardized schema - handle various field names from different actors
                user_id = str(item.get('id') or item.get('pk') or item.get('userId') or item.get('username', ''))
                username_val = item.get('username', '')

                results.append({
                    'id': user_id,
                    'username': username_val,
                    'full_name': item.get('full_name') or item.get('fullName', ''),
                    'profile_url': f"https://instagram.com/{username_val}"
                })

            if len(results) == 0:
                raise RuntimeError(
                    f"Apify returned 0 results for @{username}. "
                    f"This usually means: (1) cookies are expired — update them in Settings > Cookies, "
                    f"(2) the Instagram account is blocked/banned, or "
                    f"(3) @{username} is a private account."
                )

            print(f"[ApifySource] Successfully fetched {len(results)} accounts")
            return results

        except RuntimeError:
            raise  # re-raise our own errors with clear messages
        except Exception as e:
            raise RuntimeError(
                f"Apify error for @{username}: {e}. "
                f"Check the Apify console for details."
            )


class CSVSource:
    """Load following data from CSV files in data/exports/."""

    def __init__(self, exports_path: str = 'data/exports', processed_path: str = 'data/processed'):
        self.exports_path = exports_path
        self.processed_path = processed_path

        # Auto-create directories if they don't exist
        os.makedirs(self.exports_path, exist_ok=True)
        os.makedirs(self.processed_path, exist_ok=True)

        print(f"[CSVSource] Initialized")
        print(f"[CSVSource] Exports path: {self.exports_path}")
        print(f"[CSVSource] Processed path: {self.processed_path}")

    def get_source_name(self) -> str:
        return "CSV File"

    def get_file_path(self, username: str) -> str:
        """Get the expected file path for a username."""
        return os.path.join(self.exports_path, f"{username}.csv")

    def get_following(self, username: str) -> List[Dict]:
        """Load following list from CSV file."""
        file_path = self.get_file_path(username)
        print(f"[CSVSource] Looking for: {file_path}")

        if not os.path.exists(file_path):
            print(f"[CSVSource] File not found: {file_path}")
            print(f"[CSVSource] Please place your CSV file at: {file_path}")
            return []

        print(f"[CSVSource] Found file: {file_path}")

        results = []
        with open(file_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            print(f"[CSVSource] CSV headers: {headers}")

            for row in reader:
                # Handle various column name formats
                user_id = (
                    row.get('id') or
                    row.get('ID') or
                    row.get('pk') or
                    row.get('username') or  # Fallback: use username as ID
                    row.get('userName', '')
                )

                username_val = (
                    row.get('username') or
                    row.get('userName') or
                    row.get('user', '')
                )

                full_name = (
                    row.get('full_name') or
                    row.get('fullName') or
                    row.get('name', '')
                )

                profile_url = (
                    row.get('profile_url') or
                    row.get('profileUrl') or
                    f"https://instagram.com/{username_val}"
                )

                if username_val:  # Only add if we have a username
                    results.append({
                        'id': str(user_id),
                        'username': username_val,
                        'full_name': full_name,
                        'profile_url': profile_url
                    })

        print(f"[CSVSource] Loaded {len(results)} accounts from CSV")
        return results

    def move_to_processed(self, username: str) -> bool:
        """
        Move processed CSV file to data/processed/ with high-resolution timestamp.
        Format: {username}_YYYY-MM-DD_HH-MM-SS.csv
        Returns True if successful, False otherwise.
        """
        from datetime import datetime
        import shutil

        source_path = self.get_file_path(username)

        if not os.path.exists(source_path):
            return False

        # Ensure processed directory exists
        os.makedirs(self.processed_path, exist_ok=True)

        # Create timestamped filename with high-resolution timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dest_filename = f"{username}_{timestamp}.csv"
        dest_path = os.path.join(self.processed_path, dest_filename)

        try:
            shutil.move(source_path, dest_path)
            print(f"[CSVSource] Moved to: {dest_path}")
            return True
        except Exception as e:
            print(f"[CSVSource] ERROR moving file: {e}")
            return False
