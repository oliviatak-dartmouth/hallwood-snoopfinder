#!/usr/bin/env python3
"""
Instagram A&R Following Tracker

Usage:
    python3 run.py add <username>        # Add new A&R, fetch following, establish baseline
    python3 run.py detect                             # Detect new follows for ALL accounts
    python3 run.py detect <u1> [u2 ...]              # Detect one or more specific accounts
    python3 run.py detect --except <u1> [u2 ...]     # Detect all EXCEPT specific accounts
    python3 run.py sync                               # Sync config.yaml with spreadsheet
    python3 run.py hotartists            # Incrementally update Hot Artists sheet
    python3 run.py restore <username>    # Restore an A&R sheet from a backup CSV

Typical workflow:
    python3 run.py sync                                    # Pull latest account list into config.yaml
    python3 run.py detect                                       # Run detection for all accounts
    python3 run.py detect label_ar                           # Run detection for one account
    python3 run.py detect label_ar third_label_ar               # Run detection for two accounts
    python3 run.py detect --except label_ar third_label_ar      # Run all except these two
    python3 run.py hotartists                              # Refresh Hot Artists cross-reference

Adding a new account:
    python3 run.py add <username>        # Adds account + auto-updates config.yaml
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.tracker import FollowingTracker


def update_config_ar_accounts(config_path: str, accounts: list) -> None:
    """
    Update the ar_accounts list in config.yaml with the given accounts.
    Preserves all comments and other config keys unchanged.
    """
    with open(config_path, 'r') as f:
        lines = f.readlines()

    new_lines = []
    in_ar_section = False

    for line in lines:
        stripped = line.rstrip()

        if stripped.lstrip().startswith('ar_accounts:') and not stripped.lstrip().startswith('#'):
            in_ar_section = True
            new_lines.append(line)
            # Write the synced account list right after the header
            for account in accounts:
                new_lines.append(f'  - {account}\n')
            continue

        if in_ar_section:
            lstripped = stripped.lstrip()
            if not stripped:
                # Blank line — keep
                new_lines.append(line)
            elif lstripped.startswith('#'):
                # Comment — keep
                new_lines.append(line)
            elif lstripped.startswith('-'):
                # Active entry — skip (replaced by new list above)
                pass
            elif stripped and not stripped[0].isspace():
                # Top-level key reached — exit ar_accounts section
                in_ar_section = False
                new_lines.append(line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    with open(config_path, 'w') as f:
        f.writelines(new_lines)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == 'add':
        if len(sys.argv) < 3:
            print("Usage: python3 run.py add <username>")
            sys.exit(1)
        username = sys.argv[2].lstrip('@')
        tracker = FollowingTracker(clear_summary=False)
        tracker.track_ar_account(username)
        # Auto-sync config.yaml so the new account appears immediately
        accounts = tracker.sync_accounts_from_sheets()
        update_config_ar_accounts('config.yaml', accounts)
        print(f"\n[Config] config.yaml updated — {len(accounts)} account(s) now listed under ar_accounts")

    elif command == 'sync':
        tracker = FollowingTracker(clear_summary=False)
        accounts = tracker.sync_accounts_from_sheets()
        old_accounts = [a for a in tracker.config.get('ar_accounts', []) if a]

        update_config_ar_accounts('config.yaml', accounts)

        added = [a for a in accounts if a not in old_accounts]
        print(f"\n[Sync] config.yaml ar_accounts updated")
        print(f"[Sync] Total accounts tracked: {len(accounts)}")
        if added:
            print(f"[Sync] Newly added to config: {', '.join(added)}")
        else:
            print(f"[Sync] No new accounts (already up to date)")
        print(f"\nAll accounts in config.yaml:")
        for a in accounts:
            print(f"  - {a}")
        print(f"\nTo run detection for all:  python3 run.py detect")
        print(f"To run one account:        python3 run.py detect <username>")

    elif command == 'detect':
        if len(sys.argv) > 2 and sys.argv[2] == '--except':
            exclude = [u.lstrip('@') for u in sys.argv[3:]]
            if not exclude:
                print("Usage: python3 run.py detect --except <username1> [username2 ...]")
                sys.exit(1)
            # Don't clear the whole summary — track_all will clear only the accounts it runs
            tracker = FollowingTracker(clear_summary=False)
            tracker.track_all(exclude=exclude)
        elif len(sys.argv) > 2:
            usernames = [u.lstrip('@') for u in sys.argv[2:]]
            if len(usernames) == 1:
                # Single account — clear only that account's summary rows
                username = usernames[0]
                tracker = FollowingTracker(clear_summary=True, clear_summary_ar=username)
                ar_accounts = [a for a in tracker.config.get('ar_accounts', []) if a]
                if username not in ar_accounts:
                    print(f"Error: @{username} is not in config.yaml ar_accounts.")
                    print(f"Configured accounts: {', '.join(ar_accounts) if ar_accounts else '(none)'}")
                    print(f"Run 'python3 run.py sync' to pull all spreadsheet accounts into config.")
                    print(f"Or to add a new account: python3 run.py add {username}")
                    sys.exit(1)
                tracker.track_ar_account(username)
            else:
                # Multiple specific accounts — validate all, then run each
                tracker = FollowingTracker(clear_summary=False)
                ar_accounts = [a for a in tracker.config.get('ar_accounts', []) if a]
                invalid = [u for u in usernames if u not in ar_accounts]
                if invalid:
                    print(f"Error: not in config.yaml ar_accounts: {', '.join(invalid)}")
                    print(f"Run 'python3 run.py sync' to pull all spreadsheet accounts into config.")
                    sys.exit(1)
                # Clear summary rows for each account we're about to run
                for username in usernames:
                    tracker.sheets.clear_summary_sheet(ar_username=username)
                for username in usernames:
                    tracker.track_ar_account(username)
        else:
            tracker = FollowingTracker(clear_summary=True)
            tracker.track_all()

    elif command == 'hotartists':
        tracker = FollowingTracker(clear_summary=False)
        tracker.update_hot_artists()

    elif command == 'restore':
        if len(sys.argv) < 3:
            print("Usage: python3 run.py restore <username>")
            sys.exit(1)
        username = sys.argv[2].lstrip('@')
        tracker = FollowingTracker(clear_summary=False)

        backups = tracker.sheets.list_backups(username)
        if not backups:
            print(f"No backups found for @{username} in data/backups/")
            sys.exit(1)

        print(f"\nAvailable backups for @{username}:")
        for i, path in enumerate(backups):
            print(f"  [{i + 1}] {os.path.basename(path)}")

        if len(sys.argv) > 3:
            # User passed a backup number as third arg
            try:
                choice = int(sys.argv[3]) - 1
            except ValueError:
                print("Error: backup number must be an integer")
                sys.exit(1)
        else:
            # Default to most recent
            print(f"\nNo backup number specified, using most recent.")
            choice = 0

        if choice < 0 or choice >= len(backups):
            print(f"Error: invalid choice. Pick 1-{len(backups)}")
            sys.exit(1)

        selected = backups[choice]
        print(f"\nRestoring from: {os.path.basename(selected)}")
        confirm = input("Are you sure? This will overwrite the current sheet. (y/n): ").strip().lower()
        if confirm != 'y':
            print("Restore cancelled.")
            sys.exit(0)

        success = tracker.sheets.restore_worksheet_from_csv(username, selected)
        if success:
            print(f"\nRestore complete for @{username}.")
        else:
            print(f"\nRestore failed. Check the error messages above.")
            sys.exit(1)

    elif command == 'help':
        print(__doc__)

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
