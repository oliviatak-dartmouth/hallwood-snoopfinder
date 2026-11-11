"""
Smart Tracker for Instagram A&R Following.
Rolling baseline logic - baseline grows with each run.
Only genuinely new follows from the current session are flagged.
"""

import os
import yaml
from datetime import datetime
from typing import Dict, List, Optional

from .data_sources import get_data_source
from .sheets_manager import GoogleSheetsManager


class FollowingTracker:
    """Main tracker class with rolling baseline detection."""

    def __init__(self, config_path: str = "config.yaml", clear_summary: bool = False, clear_summary_ar: Optional[str] = None):
        """Initialize tracker with configuration."""
        print(f"\n{'='*60}")
        print("SMART TRACKER - Initializing")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        # Load configuration
        print(f"[Tracker] Loading config from: {config_path}")
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        # Initialize data source (passes full config)
        self.data_source = get_data_source(self.config)
        print(f"[Tracker] Data source: {self.data_source.get_source_name()}")

        # Initialize Google Sheets manager
        from .config_manager import get_google_credentials_dict, get_spreadsheet_id
        credentials_dict = get_google_credentials_dict()
        spreadsheet_id = get_spreadsheet_id()

        if not spreadsheet_id:
            raise ValueError("GOOGLE_SPREADSHEET_ID not set")

        if credentials_dict:
            self.sheets = GoogleSheetsManager(
                credentials_dict=credentials_dict,
                spreadsheet_id=spreadsheet_id
            )
        else:
            credentials_file = self.config.get('credentials_file', 'credentials/google_credentials.json')
            self.sheets = GoogleSheetsManager(
                credentials_file=credentials_file,
                spreadsheet_id=spreadsheet_id
            )

        # Ensure summary sheet exists; only clear when running detect
        self.sheets.ensure_summary_sheet()
        if clear_summary:
            if clear_summary_ar:
                self.sheets.clear_summary_sheet(ar_username=clear_summary_ar)
            else:
                self.sheets.clear_summary_sheet()

    def track_ar_account(self, ar_username: str) -> Dict:
        """
        Track a single A&R account's following list.

        Cumulative Rolling Baseline Logic:
        1. Get ALL existing IDs from sheet (every row, regardless of BASELINE/NEW status)
        2. Fetch current following from data source (Apify or CSV)
        3. Compare - if ID exists in sheet, skip it; if not, append with 'NEW' status
        4. Baseline grows with each run (cumulative)
        5. Move CSV to processed folder after run (if using CSV mode)
        """
        ar_username = ar_username.lstrip('@')

        print(f"\n{'='*60}")
        print(f"TRACKING: @{ar_username}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        # Step 0: Backup the current A&R worksheet before any modifications
        self.sheets.export_worksheet_to_csv(ar_username)

        # Step 1: Get ALL existing IDs from sheet (cumulative rolling baseline)
        existing_ids, last_timestamp = self.sheets.get_existing_data(ar_username)
        is_first_run = len(existing_ids) == 0
        historical_count = len(existing_ids)

        if is_first_run:
            print(f"\n[Tracker] FIRST RUN - No existing data for @{ar_username}")
        else:
            print(f"\n[Tracker] Total historical database size for @{ar_username}: {historical_count}")
            if last_timestamp:
                print(f"[Tracker] Last run was at: {last_timestamp}")

        # Step 2: Fetch current following from data source
        print(f"\n[Tracker] Fetching current data via {self.data_source.get_source_name()}...")
        current_following = self.data_source.get_following(ar_username)

        if not current_following:
            print(f"[Tracker] WARNING: No data returned for @{ar_username}")
            return {
                'ar_account': ar_username,
                'status': 'error',
                'message': 'No data returned from source'
            }

        print(f"[Tracker] Retrieved {len(current_following)} accounts from source")

        # Step 3: Update sheet (compare against cumulative baseline)
        new_follows, skipped_count = self.sheets.update_following(
            ar_username,
            current_following,
            existing_ids,
            last_timestamp
        )

        # Step 4: Report results with detailed console logs
        print(f"\n{'='*40}")
        print(f"RESULTS for @{ar_username}")
        print(f"{'='*40}")

        if is_first_run:
            print(f"BASELINE ESTABLISHED: {len(current_following)} accounts")
            print(f"Status: All accounts marked as BASELINE")
            print(f"Next run will detect any NEW follows")
        else:
            print(f"Total historical database size for @{ar_username}: {historical_count}")
            print(f"New follows discovered in this session: {len(new_follows)}")

            if new_follows:
                print(f"\nNEW FOLLOWS:")
                for f in new_follows[:10]:
                    print(f"  + @{f['username']} ({f.get('full_name', 'N/A')})")
                if len(new_follows) > 10:
                    print(f"  ... and {len(new_follows) - 10} more")

                # Add to summary sheet
                self.sheets.add_to_summary(ar_username, new_follows)
            else:
                print("No new follows detected since last run")

        print(f"{'='*40}\n")

        # Step 5: Move CSV to processed folder (if using CSV source)
        if hasattr(self.data_source, 'move_to_processed'):
            moved = self.data_source.move_to_processed(ar_username)
            if moved:
                print(f"[Tracker] Successfully moved CSV to data/processed/")
            else:
                print(f"[Tracker] No CSV file to move (or file not found)")

        return {
            'ar_account': ar_username,
            'status': 'baseline' if is_first_run else 'updated',
            'total_following': len(current_following),
            'existing_baseline': historical_count,
            'new_follows': len(new_follows) if not is_first_run else 0,
            'new_follows_list': new_follows if not is_first_run else [],
            'last_timestamp': last_timestamp
        }

    def sync_accounts_from_sheets(self) -> list:
        """Return sorted list of A&R account names from spreadsheet worksheets."""
        excluded = {"New Follows", "Hot Artists"}
        return sorted([
            ws.title for ws in self.sheets.spreadsheet.worksheets()
            if ws.title not in excluded
        ])

    def track_all(self, exclude: Optional[List[str]] = None) -> List[Dict]:
        """Track all A&R accounts configured in config.yaml, optionally skipping some."""
        ar_accounts = [a for a in self.config.get('ar_accounts', []) if a]

        if not ar_accounts:
            print("[Tracker] No A&R accounts configured in config.yaml")
            print("[Tracker] Run: python3 run.py sync  to pull accounts from the spreadsheet")
            return []

        if exclude:
            exclude_set = {u.lstrip('@') for u in exclude}
            skipped = [a for a in ar_accounts if a in exclude_set]
            ar_accounts = [a for a in ar_accounts if a not in exclude_set]
            if skipped:
                print(f"[Tracker] Skipping {len(skipped)} account(s): {', '.join(skipped)}")
            if not ar_accounts:
                print("[Tracker] No accounts left to run after exclusions.")
                return []
            # Clear summary only for the accounts we're actually running
            for account in ar_accounts:
                self.sheets.clear_summary_sheet(ar_username=account)

        print(f"\n[Tracker] Tracking {len(ar_accounts)} A&R account(s)...")

        results = []
        for account in ar_accounts:
            try:
                result = self.track_ar_account(account)
                results.append(result)
            except Exception as e:
                print(f"[Tracker] ERROR tracking @{account}: {e}")
                results.append({
                    'ar_account': account,
                    'status': 'error',
                    'message': str(e)
                })

        # Print summary
        print(f"\n{'='*60}")
        print("TRACKING COMPLETE - SUMMARY")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        for r in results:
            status = r.get('status', 'unknown')
            if status == 'baseline':
                print(f"  @{r['ar_account']}: BASELINE established ({r.get('total_following', 0)} accounts)")
            elif status == 'updated':
                existing = r.get('existing_baseline', 0)
                new = r.get('new_follows', 0)
                print(f"  @{r['ar_account']}: {new} new follows (baseline: {existing})")
            else:
                print(f"  @{r['ar_account']}: ERROR - {r.get('message', 'Unknown error')}")

        return results

    def update_hot_artists(self) -> None:
        """Update the Hot Artists sheet based on ALL tracked A&R worksheets."""
        excluded = {"New Follows", "Hot Artists"}
        ar_accounts = [
            ws.title for ws in self.sheets.spreadsheet.worksheets()
            if ws.title not in excluded
        ]

        print(f"[Tracker] Found {len(ar_accounts)} A&R worksheets: {', '.join(ar_accounts)}")

        if len(ar_accounts) < 2:
            print(f"[Tracker] Need 2+ A&R accounts for Hot Artists analysis (have {len(ar_accounts)})")
            return

        self.sheets.update_hot_artists_sheet(ar_accounts, min_ar_count=3)
