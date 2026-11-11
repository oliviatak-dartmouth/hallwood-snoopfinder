"""
Google Sheets manager for Instagram A&R tracking.
Uses gspread library for reliable sheet interactions.
Rolling baseline logic - baseline grows with each run.
"""

import gspread
import os
import csv
from google.oauth2.service_account import Credentials
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Set


class GoogleSheetsManager:
    """Manages Google Sheets operations for A&R following tracking."""

    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

    # Column headers for A&R sheets
    AR_HEADERS = ["Timestamp", "A&R", "Username", "Full Name", "Profile Pic", "Profile URL", "Instagram ID", "Status"]

    # Column headers for New Follows summary
    SUMMARY_HEADERS = ["Timestamp", "A&R Account", "New Follow", "Full Name", "Profile Pic", "Profile URL"]

    # Column headers for Hot Artists (followed by multiple A&Rs)
    HOT_ARTISTS_HEADERS = [
        "Artist Username", "Full Name", "Profile Pic", "Profile URL",
        "# of A&Rs", "A&Rs Following", "Date First Spotted", "Date Last Followed",
        "Checked", "Account Type"
    ]

    # Column headers for Scan Log
    SCAN_LOG_HEADERS = [
        "Timestamp", "Mode", "Accounts Scanned",
        "Succeeded", "Failed", "New Follows Found", "Failed Accounts"
    ]

    def __init__(self, credentials_file: str = None, spreadsheet_id: str = None, credentials_dict: dict = None):
        """Initialize with service account credentials (file path or dict)."""
        print(f"[Sheets] Connecting to spreadsheet: {spreadsheet_id}")
        if credentials_dict:
            creds = Credentials.from_service_account_info(credentials_dict, scopes=self.SCOPES)
        elif credentials_file:
            creds = Credentials.from_service_account_file(credentials_file, scopes=self.SCOPES)
        else:
            raise ValueError("Must provide either credentials_file or credentials_dict")
        self.client = gspread.authorize(creds)
        self.spreadsheet_id = spreadsheet_id
        self._spreadsheet = None

    @property
    def spreadsheet(self):
        """Lazy-load spreadsheet."""
        if self._spreadsheet is None:
            self._spreadsheet = self.client.open_by_key(self.spreadsheet_id)
        return self._spreadsheet

    def format_headers(self, sheet: gspread.Worksheet, num_cols: int) -> None:
        """Make header row bold with background color and freeze it."""
        try:
            col_letter = chr(ord('A') + num_cols - 1)
            header_range = f"A1:{col_letter}1"

            # Bold headers with dark blue background and white text
            sheet.format(header_range, {
                'textFormat': {
                    'bold': True,
                    'fontSize': 11,
                    'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}
                },
                'backgroundColor': {
                    'red': 0.2,
                    'green': 0.4,
                    'blue': 0.6
                },
                'horizontalAlignment': 'CENTER',
                'verticalAlignment': 'MIDDLE'
            })

            # Freeze the header row
            sheet.freeze(rows=1)
        except Exception as e:
            print(f"[Sheets] Warning: Could not format headers: {e}")

    def set_column_widths(self, sheet: gspread.Worksheet, is_summary: bool = False) -> None:
        """Set specific column widths for better readability."""
        try:
            sheet_id = sheet._properties['sheetId']

            if is_summary:
                # Summary sheet: Timestamp, A&R Account, New Follow, Full Name, Profile Pic, Profile URL
                widths = [160, 180, 150, 180, 280, 280]
            else:
                # A&R sheet: Timestamp, A&R, Username, Full Name, Profile Pic, Profile URL, Instagram ID, Status
                widths = [160, 180, 150, 180, 280, 280, 120, 90]

            requests = []
            for i, width in enumerate(widths):
                requests.append({
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": i,
                            "endIndex": i + 1
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize"
                    }
                })

            self.spreadsheet.batch_update({"requests": requests})
        except Exception as e:
            print(f"[Sheets] Warning: Could not set column widths: {e}")

    def _format_separator_row(self, sheet: gspread.Worksheet, row_index: int, num_cols: int) -> None:
        """Format a separator/divider row between detection runs."""
        try:
            sheet_id = sheet._properties['sheetId']
            requests = [
                {
                    "mergeCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_index - 1,
                            "endRowIndex": row_index,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols
                        },
                        "mergeType": "MERGE_ALL"
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_index - 1,
                            "endRowIndex": row_index,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {
                                    "red": 0.25,
                                    "green": 0.25,
                                    "blue": 0.35
                                },
                                "textFormat": {
                                    "bold": True,
                                    "fontSize": 10,
                                    "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}
                                },
                                "horizontalAlignment": "CENTER",
                                "verticalAlignment": "MIDDLE"
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
                    }
                }
            ]
            self.spreadsheet.batch_update({"requests": requests})
        except Exception as e:
            print(f"[Sheets] Warning: Could not format separator row: {e}")

    def format_data_cells(self, sheet: gspread.Worksheet, num_rows: int, is_summary: bool = False) -> None:
        """Format data cells with proper alignment and styling."""
        if num_rows < 2:
            return

        try:
            sheet_id = sheet._properties['sheetId']
            requests = []

            # Determine column indices
            if is_summary:
                url_col = 5  # Profile URL is column F (index 5)
                num_cols = 6
            else:
                url_col = 5  # Profile URL is column F (index 5)
                status_col = 7  # Status is column H (index 7)
                num_cols = 8

            # Format all data rows with light borders and vertical alignment
            last_col_letter = chr(ord('A') + num_cols - 1)
            data_range = f"A2:{last_col_letter}{num_rows}"

            sheet.format(data_range, {
                'verticalAlignment': 'MIDDLE',
                'wrapStrategy': 'CLIP'
            })

            # Format timestamp column (left align)
            sheet.format(f"A2:A{num_rows}", {'horizontalAlignment': 'LEFT'})

            # Format username columns (left align)
            sheet.format(f"C2:D{num_rows}", {'horizontalAlignment': 'LEFT'})

            # Format URL column with link color (blue, underlined)
            sheet.format(f"F2:F{num_rows}", {
                'textFormat': {
                    'foregroundColor': {'red': 0.0, 'green': 0.4, 'blue': 0.8},
                    'underline': True
                },
                'horizontalAlignment': 'LEFT'
            })

            if not is_summary:
                # Format Instagram ID column (center)
                sheet.format(f"G2:G{num_rows}", {'horizontalAlignment': 'CENTER'})

                # Format Status column (center, bold)
                sheet.format(f"H2:H{num_rows}", {
                    'horizontalAlignment': 'CENTER',
                    'textFormat': {'bold': True}
                })

            # Add alternating row colors for better readability
            requests.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": num_rows,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols
                        }],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [{"userEnteredValue": "=ISEVEN(ROW())"}]
                            },
                            "format": {
                                "backgroundColor": {
                                    "red": 0.95,
                                    "green": 0.95,
                                    "blue": 0.97
                                }
                            }
                        }
                    },
                    "index": 0
                }
            })

            if not is_summary:
                # Conditional formatting for Status column - NEW = green, BASELINE = gray
                requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": num_rows,
                                "startColumnIndex": status_col,
                                "endColumnIndex": status_col + 1
                            }],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "NEW"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.7, "green": 0.9, "blue": 0.7},
                                    "textFormat": {
                                        "foregroundColor": {"red": 0.0, "green": 0.4, "blue": 0.0},
                                        "bold": True
                                    }
                                }
                            }
                        },
                        "index": 1
                    }
                })

                requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": num_rows,
                                "startColumnIndex": status_col,
                                "endColumnIndex": status_col + 1
                            }],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "BASELINE"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85},
                                    "textFormat": {
                                        "foregroundColor": {"red": 0.4, "green": 0.4, "blue": 0.4}
                                    }
                                }
                            }
                        },
                        "index": 2
                    }
                })

            if requests:
                self.spreadsheet.batch_update({"requests": requests})

        except Exception as e:
            print(f"[Sheets] Warning: Could not format data cells: {e}")

    def apply_full_formatting(self, sheet: gspread.Worksheet, is_summary: bool = False) -> None:
        """Apply complete formatting to a sheet."""
        try:
            num_cols = len(self.SUMMARY_HEADERS) if is_summary else len(self.AR_HEADERS)
            num_rows = len(sheet.get_all_values())

            self.format_headers(sheet, num_cols)
            self.set_column_widths(sheet, is_summary)

            if num_rows > 1:
                self.format_data_cells(sheet, num_rows, is_summary)

            print(f"[Sheets] Applied formatting to '{sheet.title}'")
        except Exception as e:
            print(f"[Sheets] Warning: Could not apply full formatting: {e}")

    def format_all_sheets(self) -> None:
        """Apply formatting to all existing sheets in the spreadsheet."""
        print(f"[Sheets] Formatting all sheets...")
        try:
            for sheet in self.spreadsheet.worksheets():
                sheet_name = sheet.title
                is_summary = (sheet_name == "New Follows")
                self.apply_full_formatting(sheet, is_summary)
            print(f"[Sheets] All sheets formatted")
        except Exception as e:
            print(f"[Sheets] Warning: Could not format all sheets: {e}")

    def get_or_create_worksheet(self, sheet_name: str, headers: List[str]) -> gspread.Worksheet:
        """Get existing worksheet or create new one with formatted headers."""
        is_summary = (sheet_name == "New Follows")
        try:
            sheet = self.spreadsheet.worksheet(sheet_name)
            print(f"[Sheets] Found existing worksheet: '{sheet_name}'")
        except gspread.WorksheetNotFound:
            print(f"[Sheets] Creating new worksheet: '{sheet_name}'")
            sheet = self.spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=len(headers))
            sheet.append_row(headers)
            print(f"[Sheets] Added headers: {headers}")

        # Apply formatting
        self.apply_full_formatting(sheet, is_summary)
        return sheet

    def get_existing_data(self, ar_username: str) -> Tuple[Set[str], Optional[str]]:
        """
        Get ALL Instagram IDs already tracked for this A&R (cumulative rolling baseline).
        Reads EVERY row in the worksheet regardless of status (BASELINE or NEW).
        Returns: (set of IDs, last timestamp or None)
        """
        print(f"[Sheets] Fetching ALL historical records for @{ar_username}...")

        try:
            sheet = self.spreadsheet.worksheet(ar_username)

            # Use get_all_values() for reliability - returns list of lists
            all_values = sheet.get_all_values()

            if not all_values or len(all_values) < 2:
                print(f"[Sheets] Worksheet exists but has no data rows")
                return set(), None

            # Find column indices from header row
            headers = all_values[0]
            try:
                id_col_idx = headers.index('Instagram ID')
            except ValueError:
                print(f"[Sheets] ERROR: 'Instagram ID' column not found in headers: {headers}")
                return set(), None

            try:
                ts_col_idx = headers.index('Timestamp')
            except ValueError:
                ts_col_idx = None

            # Collect ALL IDs from every row (skip header)
            existing_ids = set()
            last_timestamp = None

            for row in all_values[1:]:  # Skip header row
                if len(row) > id_col_idx:
                    ig_id = str(row[id_col_idx]).strip()
                    if ig_id:
                        existing_ids.add(ig_id)

                # Track latest timestamp
                if ts_col_idx is not None and len(row) > ts_col_idx:
                    ts = row[ts_col_idx].strip()
                    if ts and (last_timestamp is None or ts > last_timestamp):
                        last_timestamp = ts

            print(f"[Sheets] Total historical database size for @{ar_username}: {len(existing_ids)}")
            return existing_ids, last_timestamp

        except gspread.WorksheetNotFound:
            print(f"[Sheets] No existing worksheet for @{ar_username} (first run)")
            return set(), None
        except Exception as e:
            print(f"[Sheets] Error reading existing data: {e}")
            import traceback
            traceback.print_exc()
            return set(), None

    def update_following(
        self,
        ar_username: str,
        current_data: List[Dict],
        existing_ids: Set[str],
        last_timestamp: Optional[str] = None
    ) -> Tuple[List[Dict], int]:
        """
        Update the A&R's sheet with new following data.
        Compares against cumulative rolling baseline (all historical IDs).
        Only genuinely NEW accounts are appended with status 'NEW'.
        """
        sheet = self.get_or_create_worksheet(ar_username, self.AR_HEADERS)

        is_first_run = len(existing_ids) == 0
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        new_follows = []
        rows_to_add = []
        skipped_count = 0
        rejected_count = 0
        warn_count = 0

        for item in current_data:
            item_id = str(item.get('id', '')).strip()
            item_username = str(item.get('username', '')).strip()

            # Data validation: check both id and username fields
            if not item_id and not item_username:
                print(f"[Sheets] ERROR: Skipping account with no ID or username")
                rejected_count += 1
                continue
            if not item_id and item_username:
                print(f"[Sheets] WARNING: {item_username} has no Instagram ID - tracking may be unreliable")
                warn_count += 1
            elif item_id and not item_username:
                print(f"[Sheets] WARNING: Account {item_id} has no username")
                warn_count += 1

            # Skip if ID already exists in historical database
            if item_id and item_id in existing_ids:
                skipped_count += 1
                continue

            status = "BASELINE" if is_first_run else "NEW"

            row = [
                timestamp,
                ar_username,
                item.get('username', ''),
                item.get('full_name', ''),
                item.get('profile_pic_url', ''),
                item.get('profile_url', ''),
                item_id,
                status
            ]
            rows_to_add.append(row)

            if not is_first_run:
                new_follows.append(item)

        # Detailed console logs
        if is_first_run:
            print(f"[Sheets] FIRST RUN - Establishing baseline with {len(rows_to_add)} accounts")
        else:
            print(f"[Sheets] Total historical database size for @{ar_username}: {len(existing_ids)}")
            print(f"[Sheets] Accounts already in database (skipped): {skipped_count}")
            print(f"[Sheets] New follows discovered in this session: {len(new_follows)}")

        if rejected_count > 0:
            print(f"[Sheets] REJECTED: {rejected_count} rows had no ID or username")
        if warn_count > 0:
            print(f"[Sheets] WARNINGS: {warn_count} rows had partial data (missing ID or username)")

        if rows_to_add:
            if is_first_run:
                # First run: append baseline rows at the bottom (no separator needed)
                print(f"[Sheets] Appending {len(rows_to_add)} baseline rows to '{ar_username}'")
                sheet.append_rows(rows_to_add)
            else:
                # Subsequent runs: insert at top (row 2) with separator
                print(f"[Sheets] Inserting {len(rows_to_add)} new follows at top of '{ar_username}'")
                separator_text = f"--- Run: {timestamp} | {len(rows_to_add)} new follows ---"
                separator_row = [separator_text] + [''] * (len(self.AR_HEADERS) - 1)
                all_insert_rows = [separator_row] + rows_to_add
                sheet.insert_rows(all_insert_rows, row=2)
                # Format the separator row (now at row 2)
                self._format_separator_row(sheet, row_index=2, num_cols=len(self.AR_HEADERS))
            # Apply full formatting after adding data
            self.apply_full_formatting(sheet, is_summary=False)
        else:
            print(f"[Sheets] No new accounts to add")

        return new_follows, skipped_count

    def ensure_summary_sheet(self) -> gspread.Worksheet:
        """Ensure 'New Follows' summary sheet exists with headers."""
        return self.get_or_create_worksheet("New Follows", self.SUMMARY_HEADERS)

    def clear_summary_sheet(self, ar_username: Optional[str] = None) -> None:
        """
        Clear the 'New Follows' sheet data (keep headers).
        If ar_username is None, clears ALL data rows (used for 'detect' all).
        If ar_username is provided, only removes rows for that specific A&R account.
        """
        try:
            sheet = self.spreadsheet.worksheet("New Follows")
            all_data = sheet.get_all_values()

            if len(all_data) <= 1:
                return  # Only headers or empty

            if ar_username is None:
                # Clear everything except header row (original behavior)
                sheet.batch_clear([f"A2:F{len(all_data) + 1}"])
                print(f"[Sheets] Cleared entire 'New Follows' sheet for fresh run")
            else:
                # Selective clear: remove only rows for this A&R account
                headers = all_data[0]
                try:
                    ar_col_idx = headers.index("A&R Account")
                except ValueError:
                    print(f"[Sheets] WARNING: 'A&R Account' column not found in summary headers")
                    return

                rows_to_keep = []
                removed_count = 0
                for row in all_data[1:]:
                    if len(row) > ar_col_idx and row[ar_col_idx].strip().lower() == ar_username.lower():
                        removed_count += 1
                    else:
                        rows_to_keep.append(row)

                if removed_count == 0:
                    print(f"[Sheets] No existing rows for @{ar_username} in 'New Follows'")
                    return

                # Clear all data rows then rewrite the ones we're keeping
                sheet.batch_clear([f"A2:F{len(all_data) + 1}"])

                if rows_to_keep:
                    sheet.append_rows(rows_to_keep)

                print(f"[Sheets] Removed {removed_count} rows for @{ar_username} from 'New Follows' "
                      f"(kept {len(rows_to_keep)} rows from other A&Rs)")

        except gspread.WorksheetNotFound:
            pass  # Sheet doesn't exist yet, will be created
        except Exception as e:
            print(f"[Sheets] Warning: Could not clear summary sheet: {e}")

    def add_to_summary(self, ar_username: str, new_follows: List[Dict]) -> None:
        """Add new follows to the 'New Follows' summary sheet."""
        if not new_follows:
            print(f"[Sheets] No new follows to add to summary")
            return

        print(f"[Sheets] Adding {len(new_follows)} entries to 'New Follows' summary...")

        summary = self.ensure_summary_sheet()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        rows = [
            [
                timestamp,
                ar_username,
                f.get('username', ''),
                f.get('full_name', ''),
                f.get('profile_pic_url', ''),
                f.get('profile_url', ''),
            ]
            for f in new_follows
        ]

        summary.append_rows(rows)
        # Apply full formatting after adding data
        self.apply_full_formatting(summary, is_summary=True)
        print(f"[Sheets] Summary updated with timestamp: {timestamp}")

    def export_worksheet_to_csv(self, sheet_name: str, backup_dir: str = "data/backups") -> Optional[str]:
        """Export a worksheet to a local CSV as a pre-run backup."""
        try:
            sheet = self.spreadsheet.worksheet(sheet_name)
            all_values = sheet.get_all_values()

            if not all_values or len(all_values) < 2:
                print(f"[Backup] No data to backup for '{sheet_name}'")
                return None

            os.makedirs(backup_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"{sheet_name}_{timestamp}.csv"
            filepath = os.path.join(backup_dir, filename)

            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(all_values)

            print(f"[Backup] Backed up '{sheet_name}' to {filepath} ({len(all_values) - 1} data rows)")
            return filepath

        except gspread.WorksheetNotFound:
            print(f"[Backup] No worksheet '{sheet_name}' to backup (first run)")
            return None
        except Exception as e:
            print(f"[Backup] WARNING: Backup failed for '{sheet_name}': {e}")
            return None

    def list_backups(self, sheet_name: str, backup_dir: str = "data/backups") -> List[str]:
        """List available backup files for a given sheet, newest first."""
        if not os.path.isdir(backup_dir):
            return []
        prefix = f"{sheet_name}_"
        files = [
            f for f in os.listdir(backup_dir)
            if f.startswith(prefix) and f.endswith('.csv')
        ]
        files.sort(reverse=True)  # Newest first (timestamp in filename)
        return [os.path.join(backup_dir, f) for f in files]

    def restore_worksheet_from_csv(self, sheet_name: str, csv_path: str) -> bool:
        """
        Restore a worksheet from a backup CSV file.
        Clears the existing sheet and rewrites all data from the CSV.
        Returns True on success.
        """
        if not os.path.isfile(csv_path):
            print(f"[Restore] ERROR: Backup file not found: {csv_path}")
            return False

        # Read CSV
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            all_rows = list(reader)

        if not all_rows:
            print(f"[Restore] ERROR: Backup file is empty: {csv_path}")
            return False

        headers = all_rows[0]
        data_rows = all_rows[1:]

        print(f"[Restore] Restoring '{sheet_name}' from {csv_path}")
        print(f"[Restore] Backup contains {len(data_rows)} data rows")

        try:
            # Get or create the worksheet
            try:
                sheet = self.spreadsheet.worksheet(sheet_name)
            except gspread.WorksheetNotFound:
                sheet = self.spreadsheet.add_worksheet(
                    title=sheet_name, rows=max(1000, len(all_rows) + 100), cols=len(headers)
                )

            # Clear the entire sheet
            sheet.clear()

            # Resize if needed
            if sheet.row_count < len(all_rows) + 10:
                sheet.resize(rows=len(all_rows) + 100)
            if sheet.col_count < len(headers):
                sheet.resize(cols=len(headers))

            # Write all data back (headers + data)
            sheet.update(f"A1", all_rows)

            # Re-apply formatting
            self.apply_full_formatting(sheet, is_summary=False)

            print(f"[Restore] Successfully restored '{sheet_name}' ({len(data_rows)} data rows)")
            return True

        except Exception as e:
            print(f"[Restore] ERROR: Failed to restore '{sheet_name}': {e}")
            import traceback
            traceback.print_exc()
            return False

    # ------------------------------------------------------------------
    # Config storage in Google Sheet (for cloud deployment)
    # ------------------------------------------------------------------

    def _get_config_sheet(self) -> gspread.Worksheet:
        """Get or create the _Config worksheet for storing app settings."""
        try:
            return self.spreadsheet.worksheet("_Config")
        except gspread.WorksheetNotFound:
            sheet = self.spreadsheet.add_worksheet(title="_Config", rows=10, cols=2)
            sheet.update("A1:B1", [["Key", "Value"]])
            return sheet

    def load_cookies_from_sheet(self) -> Optional[str]:
        """Load cookies JSON string from _Config sheet. Returns None if not found."""
        try:
            sheet = self._get_config_sheet()
            all_values = sheet.get_all_values()
            for row in all_values[1:]:
                if len(row) >= 2 and row[0] == "cookies":
                    return row[1] if row[1].strip() else None
            return None
        except Exception as e:
            print(f"[Sheets] Could not load cookies from sheet: {e}")
            return None

    def save_cookies_to_sheet(self, cookies_json: str) -> bool:
        """Save cookies JSON string to _Config sheet."""
        try:
            sheet = self._get_config_sheet()
            all_values = sheet.get_all_values()
            # Find existing cookies row
            for i, row in enumerate(all_values):
                if len(row) >= 1 and row[0] == "cookies":
                    sheet.update_cell(i + 1, 2, cookies_json)
                    print(f"[Sheets] Cookies updated in _Config sheet")
                    return True
            # Not found — append
            sheet.append_row(["cookies", cookies_json])
            print(f"[Sheets] Cookies saved to _Config sheet")
            return True
        except Exception as e:
            print(f"[Sheets] Could not save cookies to sheet: {e}")
            return False

    def load_tracking_account(self) -> dict:
        """Load tracking Instagram account details from _Config sheet."""
        try:
            sheet = self._get_config_sheet()
            all_values = sheet.get_all_values()
            info = {}
            for row in all_values[1:]:
                if len(row) >= 2 and row[0].startswith("tracking_ig_"):
                    key = row[0].replace("tracking_ig_", "")
                    info[key] = row[1]
            return info
        except Exception as e:
            print(f"[Sheets] Could not load tracking account: {e}")
            return {}

    def save_tracking_account(self, info: dict) -> bool:
        """Save tracking Instagram account details to _Config sheet."""
        try:
            sheet = self._get_config_sheet()
            all_values = sheet.get_all_values()
            existing_keys = {}
            for i, row in enumerate(all_values):
                if len(row) >= 1 and row[0].startswith("tracking_ig_"):
                    existing_keys[row[0]] = i

            for key, value in info.items():
                sheet_key = f"tracking_ig_{key}"
                if sheet_key in existing_keys:
                    sheet.update_cell(existing_keys[sheet_key] + 1, 2, value)
                else:
                    sheet.append_row([sheet_key, value])
            print(f"[Sheets] Tracking account details saved to _Config sheet")
            return True
        except Exception as e:
            print(f"[Sheets] Could not save tracking account: {e}")
            return False

    def get_all_follows_for_ar(self, ar_username: str) -> List[Dict]:
        """
        Get all follows for an A&R account with full details.
        Returns list of dicts with username, full_name, profile_url, instagram_id, timestamp.
        """
        try:
            sheet = self.spreadsheet.worksheet(ar_username)
            all_values = sheet.get_all_values()

            if not all_values or len(all_values) < 2:
                return []

            headers = all_values[0]
            follows = []

            # Find column indices
            col_indices = {}
            for col_name in ['Timestamp', 'Username', 'Full Name', 'Profile Pic', 'Profile URL', 'Instagram ID']:
                try:
                    col_indices[col_name] = headers.index(col_name)
                except ValueError:
                    col_indices[col_name] = None

            for row in all_values[1:]:
                follow = {
                    'timestamp': row[col_indices['Timestamp']] if col_indices['Timestamp'] is not None and len(row) > col_indices['Timestamp'] else '',
                    'username': row[col_indices['Username']] if col_indices['Username'] is not None and len(row) > col_indices['Username'] else '',
                    'full_name': row[col_indices['Full Name']] if col_indices['Full Name'] is not None and len(row) > col_indices['Full Name'] else '',
                    'profile_pic_url': row[col_indices['Profile Pic']] if col_indices['Profile Pic'] is not None and len(row) > col_indices['Profile Pic'] else '',
                    'profile_url': row[col_indices['Profile URL']] if col_indices['Profile URL'] is not None and len(row) > col_indices['Profile URL'] else '',
                    'instagram_id': row[col_indices['Instagram ID']] if col_indices['Instagram ID'] is not None and len(row) > col_indices['Instagram ID'] else '',
                    'ar_account': ar_username
                }
                if follow['username']:
                    follows.append(follow)

            return follows

        except gspread.WorksheetNotFound:
            return []
        except Exception as e:
            print(f"[Sheets] Error getting follows for @{ar_username}: {e}")
            return []

    def analyze_hot_artists(self, ar_accounts: List[str], min_ar_count: int = 2) -> List[Dict]:
        """
        Cross-reference follows across all A&R accounts to find "hot" artists.
        Returns artists followed by min_ar_count or more A&Rs.
        """
        print(f"\n[HotArtists] Analyzing follows across {len(ar_accounts)} A&R accounts...")

        # Collect all follows from all A&R accounts
        # Key: username (lowercase), Value: list of follow records
        artist_follows = {}

        for ar_account in ar_accounts:
            follows = self.get_all_follows_for_ar(ar_account)
            print(f"[HotArtists] @{ar_account}: {len(follows)} follows")

            for follow in follows:
                username_key = follow['username'].lower()
                if username_key not in artist_follows:
                    artist_follows[username_key] = []
                artist_follows[username_key].append(follow)

        # Find artists followed by multiple A&Rs
        hot_artists = []

        for username_key, follows in artist_follows.items():
            # Get unique A&R accounts that follow this artist
            ar_list = list(set(f['ar_account'] for f in follows))

            if len(ar_list) >= min_ar_count:
                # Get the first follow's details for display
                first_follow = min(follows, key=lambda x: x['timestamp'] or '9999')
                last_follow = max(follows, key=lambda x: x['timestamp'] or '0000')

                hot_artists.append({
                    'username': follows[0]['username'],  # Original case
                    'full_name': follows[0]['full_name'],
                    'profile_pic_url': follows[0].get('profile_pic_url', ''),
                    'profile_url': follows[0]['profile_url'],
                    'ar_count': len(ar_list),
                    'ar_list': ar_list,
                    'ar_list_str': ', '.join(sorted(ar_list)),
                    'date_first_spotted': first_follow['timestamp'],
                    'date_last_followed': last_follow['timestamp']
                })

        # Sort by number of A&Rs (descending)
        hot_artists.sort(key=lambda x: (-x['ar_count'], x['username'].lower()))

        print(f"[HotArtists] Found {len(hot_artists)} artists followed by {min_ar_count}+ A&Rs")
        return hot_artists

    def get_existing_hot_artists(self) -> Tuple[Set[str], Optional[gspread.Worksheet]]:
        """
        Read existing Hot Artists sheet and return set of lowercase usernames.
        Auto-migrates old 7-column sheets by adding "Checked" header.
        Returns: (set of lowercase usernames, worksheet or None)
        """
        try:
            sheet = self.spreadsheet.worksheet("Hot Artists")
            all_values = sheet.get_all_values()

            if not all_values:
                return set(), sheet

            headers = all_values[0]

            # Auto-migrate: add "Checked" header if sheet has 7 columns (old format)
            if len(headers) == 7 and "Checked" not in headers:
                print(f"[HotArtists] Migrating sheet: adding 'Checked' column header")
                if sheet.col_count < 8:
                    sheet.resize(cols=8)
                sheet.update_cell(1, 8, "Checked")
                headers.append("Checked")

            # Auto-migrate: add "Profile Pic" header if not present
            if "Profile Pic" not in headers:
                print(f"[HotArtists] Migrating sheet: adding 'Profile Pic' column header")
                # Insert after "Full Name" (index 2) by shifting columns
                # For simplicity, just add at the end and note the mismatch
                new_col = len(headers) + 1
                if sheet.col_count < new_col:
                    sheet.resize(cols=new_col)
                sheet.update_cell(1, new_col, "Profile Pic")
                headers.append("Profile Pic")

            # Auto-migrate: add "Account Type" header if not present
            if "Account Type" not in headers:
                print(f"[HotArtists] Migrating sheet: adding 'Account Type' column header")
                new_col = len(headers) + 1
                if sheet.col_count < new_col:
                    sheet.resize(cols=new_col)
                sheet.update_cell(1, new_col, "Account Type")
                headers.append("Account Type")

            # Find Artist Username column
            try:
                username_col = headers.index("Artist Username")
            except ValueError:
                print(f"[HotArtists] WARNING: 'Artist Username' column not found")
                return set(), sheet

            existing = set()
            for row in all_values[1:]:
                if len(row) > username_col and row[username_col].strip():
                    existing.add(row[username_col].strip().lower())

            print(f"[HotArtists] Found {len(existing)} existing hot artists in sheet")
            return existing, sheet

        except gspread.WorksheetNotFound:
            return set(), None

    def update_hot_artists_sheet(self, ar_accounts: List[str], min_ar_count: int = 2) -> List[Dict]:
        """
        Incrementally update the Hot Artists sheet.
        Append-only: existing rows are never modified or deleted.
        Preserves boss's "Checked" column and all manual edits.
        """
        print(f"\n{'='*60}")
        print("HOT ARTISTS ANALYSIS")
        print(f"{'='*60}")

        # Analyze hot artists from A&R data
        hot_artists = self.analyze_hot_artists(ar_accounts, min_ar_count)

        if not hot_artists:
            print(f"[HotArtists] No artists found followed by {min_ar_count}+ A&Rs")
            return []

        # Get existing hot artists from sheet
        existing_usernames, sheet = self.get_existing_hot_artists()

        # Create sheet if it doesn't exist
        if sheet is None:
            print(f"[HotArtists] Creating 'Hot Artists' worksheet...")
            sheet = self.spreadsheet.add_worksheet(title="Hot Artists", rows=1000, cols=len(self.HOT_ARTISTS_HEADERS))
            sheet.append_row(self.HOT_ARTISTS_HEADERS)

        # Filter to only NEW artists not already in sheet
        new_artists = [
            a for a in hot_artists
            if a['username'].lower() not in existing_usernames
        ]

        print(f"[HotArtists] {len(hot_artists)} total hot artists, {len(existing_usernames)} already in sheet, {len(new_artists)} new to add")

        # Append only new rows
        if new_artists:
            rows = []
            for artist in new_artists:
                rows.append([
                    artist['username'],
                    artist['full_name'],
                    artist.get('profile_pic_url', ''),
                    artist['profile_url'],
                    artist['ar_count'],
                    artist['ar_list_str'],
                    artist['date_first_spotted'],
                    artist['date_last_followed'],
                    '',  # Checked column - empty for new entries
                    ''   # Account Type column - empty for new entries
                ])
            sheet.append_rows(rows)
            print(f"[HotArtists] Appended {len(new_artists)} new hot artists")
        else:
            print(f"[HotArtists] No new hot artists to add")

        # Apply formatting
        total_rows = len(sheet.get_all_values())
        self.format_hot_artists_sheet(sheet, total_rows)

        # Print summary
        print(f"\n{'='*40}")
        print("HOT ARTISTS RESULTS")
        print(f"{'='*40}")
        print(f"  Total in sheet: {len(existing_usernames) + len(new_artists)}")
        print(f"  Newly added: {len(new_artists)}")
        if new_artists:
            for artist in new_artists[:10]:
                print(f"    + @{artist['username']} - followed by {artist['ar_count']} A&Rs: {artist['ar_list_str']}")
            if len(new_artists) > 10:
                print(f"    ... and {len(new_artists) - 10} more")
        print(f"{'='*40}\n")

        return hot_artists

    def format_hot_artists_sheet(self, sheet: gspread.Worksheet, num_rows: int) -> None:
        """Apply special formatting to Hot Artists sheet."""
        try:
            sheet_id = sheet._properties['sheetId']
            num_cols = len(self.HOT_ARTISTS_HEADERS)

            # Format headers
            col_letter = chr(ord('A') + num_cols - 1)
            sheet.format(f"A1:{col_letter}1", {
                'textFormat': {
                    'bold': True,
                    'fontSize': 11,
                    'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}
                },
                'backgroundColor': {
                    'red': 0.8,
                    'green': 0.2,
                    'blue': 0.2
                },
                'horizontalAlignment': 'CENTER',
                'verticalAlignment': 'MIDDLE'
            })
            sheet.freeze(rows=1)

            # Set column widths: Username, Full Name, Profile Pic, Profile URL, # of A&Rs, A&Rs Following, First Spotted, Last Followed, Checked, Account Type
            widths = [150, 180, 80, 280, 80, 250, 160, 160, 120, 130]
            requests = []
            for i, width in enumerate(widths):
                requests.append({
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": i,
                            "endIndex": i + 1
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize"
                    }
                })

            if num_rows > 1:
                # Format data cells
                sheet.format(f"A2:A{num_rows}", {'horizontalAlignment': 'LEFT'})
                sheet.format(f"B2:B{num_rows}", {'horizontalAlignment': 'LEFT'})

                # URL column styling (column D now)
                sheet.format(f"D2:D{num_rows}", {
                    'textFormat': {
                        'foregroundColor': {'red': 0.0, 'green': 0.4, 'blue': 0.8},
                        'underline': True
                    },
                    'horizontalAlignment': 'LEFT'
                })

                # Count column - center and bold (column E now)
                sheet.format(f"E2:E{num_rows}", {
                    'horizontalAlignment': 'CENTER',
                    'textFormat': {'bold': True, 'fontSize': 12}
                })

                # A&Rs list (column F now)
                sheet.format(f"F2:F{num_rows}", {'horizontalAlignment': 'LEFT'})

                # Dates (columns G-H now)
                sheet.format(f"G2:H{num_rows}", {'horizontalAlignment': 'CENTER'})

                # Checked column - left align (column I now)
                sheet.format(f"I2:I{num_rows}", {'horizontalAlignment': 'LEFT'})

                # Account Type column - center align (column J now)
                sheet.format(f"J2:J{num_rows}", {'horizontalAlignment': 'CENTER'})

                # Data validation dropdown for Account Type column (column J, index 9)
                requests.append({
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": num_rows,
                            "startColumnIndex": 9,
                            "endColumnIndex": 10
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [
                                    {"userEnteredValue": "A&R"},
                                    {"userEnteredValue": "Artist"}
                                ]
                            },
                            "showCustomUi": True,
                            "strict": True
                        }
                    }
                })

                # Conditional formatting: Account Type = "A&R" -> light red
                requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": num_rows,
                                "startColumnIndex": 9,
                                "endColumnIndex": 10
                            }],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "A&R"}]
                                },
                                "format": {
                                    "backgroundColor": {
                                        "red": 0.96,
                                        "green": 0.80,
                                        "blue": 0.80
                                    },
                                    "textFormat": {
                                        "bold": True,
                                        "foregroundColor": {"red": 0.7, "green": 0.0, "blue": 0.0}
                                    }
                                }
                            }
                        },
                        "index": 0
                    }
                })

                # Conditional formatting: Account Type = "Artist" -> light green
                requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": num_rows,
                                "startColumnIndex": 9,
                                "endColumnIndex": 10
                            }],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": "Artist"}]
                                },
                                "format": {
                                    "backgroundColor": {
                                        "red": 0.80,
                                        "green": 0.96,
                                        "blue": 0.80
                                    },
                                    "textFormat": {
                                        "bold": True,
                                        "foregroundColor": {"red": 0.0, "green": 0.4, "blue": 0.0}
                                    }
                                }
                            }
                        },
                        "index": 0
                    }
                })

                # Conditional formatting for high counts (columns A-I only, excludes Account Type)
                # 3+ A&Rs = orange background
                requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": num_rows,
                                "startColumnIndex": 0,
                                "endColumnIndex": 9
                            }],
                            "booleanRule": {
                                "condition": {
                                    "type": "CUSTOM_FORMULA",
                                    "values": [{"userEnteredValue": "=$E2>=3"}]
                                },
                                "format": {
                                    "backgroundColor": {
                                        "red": 1.0,
                                        "green": 0.9,
                                        "blue": 0.7
                                    }
                                }
                            }
                        },
                        "index": 0
                    }
                })

                # 4+ A&Rs = red/pink background (very hot!)
                requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": num_rows,
                                "startColumnIndex": 0,
                                "endColumnIndex": 9
                            }],
                            "booleanRule": {
                                "condition": {
                                    "type": "CUSTOM_FORMULA",
                                    "values": [{"userEnteredValue": "=$E2>=4"}]
                                },
                                "format": {
                                    "backgroundColor": {
                                        "red": 1.0,
                                        "green": 0.8,
                                        "blue": 0.8
                                    }
                                }
                            }
                        },
                        "index": 0
                    }
                })

            if requests:
                self.spreadsheet.batch_update({"requests": requests})

            print(f"[HotArtists] Applied formatting to 'Hot Artists' sheet")

        except Exception as e:
            print(f"[HotArtists] Warning: Could not format Hot Artists sheet: {e}")

    # ---------------------------------------------------------------------------
    # Scan Log
    # ---------------------------------------------------------------------------

    def ensure_scan_log_sheet(self):
        """Ensure 'Scan Log' sheet exists with correct headers."""
        return self.get_or_create_worksheet("Scan Log", self.SCAN_LOG_HEADERS)

    def add_scan_log_entry(self, user: str, mode: str, accounts_scanned: int,
                           succeeded: int, failed: int, new_follows: int,
                           failed_accounts: List[str]) -> None:
        """Append a single row to the Scan Log sheet."""
        try:
            sheet = self.ensure_scan_log_sheet()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = [
                timestamp,
                mode,
                accounts_scanned,
                succeeded,
                failed,
                new_follows,
                ", ".join(f"@{a}" for a in failed_accounts) if failed_accounts else "",
            ]
            sheet.append_rows([row])
            print(f"[ScanLog] Entry written: {user}, {mode}, {accounts_scanned} accounts")
        except Exception as e:
            print(f"[ScanLog] Warning: Could not write scan log entry: {e}")

    def load_scan_log(self) -> List[Dict]:
        """Load all rows from the Scan Log sheet."""
        try:
            sheet = self.spreadsheet.worksheet("Scan Log")
            rows = sheet.get_all_values()
            if not rows or len(rows) < 2:
                return []
            headers = rows[0]
            return [dict(zip(headers, row)) for row in rows[1:] if any(v.strip() for v in row)]
        except gspread.WorksheetNotFound:
            return []
        except Exception as e:
            print(f"[ScanLog] Warning: Could not load scan log: {e}")
            return []
