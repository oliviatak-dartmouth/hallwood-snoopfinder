"""
Snoopfinder: Web UI
Run with:  streamlit run app.py
"""

import streamlit as st
import os
import sys
import json
import pandas as pd
from datetime import datetime, timedelta
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from src.config_manager import (
    load_config, get_ar_accounts, add_ar_account, remove_ar_account,
    get_cookies, update_cookies, update_cookies_cloud, validate_cookies,
    get_cookie_health, get_apify_token, get_spreadsheet_id,
    get_google_credentials_dict, is_cloud_mode,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Snoopfinder",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "log_output" not in st.session_state:
    st.session_state.log_output = ""
if "tracker_running" not in st.session_state:
    st.session_state.tracker_running = False

# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def get_sheets_manager():
    spreadsheet_id = get_spreadsheet_id()
    if not spreadsheet_id:
        return None
    from src.sheets_manager import GoogleSheetsManager
    creds_dict = get_google_credentials_dict()
    if creds_dict:
        return GoogleSheetsManager(credentials_dict=creds_dict, spreadsheet_id=spreadsheet_id)
    config = load_config()
    creds_file = config.get("credentials_file", "credentials/google_credentials.json")
    if not os.path.exists(creds_file):
        return None
    return GoogleSheetsManager(credentials_file=creds_file, spreadsheet_id=spreadsheet_id)


@st.cache_data(ttl=300)
def load_cookies_from_sheet():
    old_stdout, sys.stdout = sys.stdout, StringIO()
    try:
        sm = get_sheets_manager()
        if not sm:
            return None
        raw = sm.load_cookies_from_sheet()
        if raw:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        return None
    except Exception:
        return None
    finally:
        sys.stdout = old_stdout


def get_active_cookies():
    sheet_cookies = load_cookies_from_sheet()
    if sheet_cookies:
        return sheet_cookies
    try:
        config = load_config()
        local_cookies = get_cookies(config)
        if local_cookies:
            return local_cookies
    except Exception:
        pass
    try:
        raw = st.secrets.get("INSTAGRAM_COOKIES", "")
        if raw:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _clean_df(df):
    if df.empty:
        return df
    return df[df.apply(lambda row: any(str(v).strip() for v in row), axis=1)].reset_index(drop=True)


def _parse_timestamps(df, col="Timestamp"):
    """Parse a Timestamp column into a datetime Series, handling any format Google Sheets might use."""
    # Try case-insensitive column match
    actual_col = next((c for c in df.columns if c.strip().lower() == col.lower()), None)
    if actual_col is None:
        return pd.Series([pd.NaT] * len(df), dtype="datetime64[ns]")
    return pd.to_datetime(df[actual_col], errors="coerce")


def _format_timestamp_col(df, col="Timestamp"):
    """Replace Timestamp column with separate Date and Time columns; add _parsed_ts for sorting/filtering."""
    df = df.copy()
    df["_parsed_ts"] = _parse_timestamps(df, col)
    if col not in df.columns:
        # No Timestamp column — still add _parsed_ts (all NaT) so callers can rely on it
        return df
    df["Date"] = df["_parsed_ts"].dt.strftime("%b %d, %Y").where(df["_parsed_ts"].notna(), "")
    df["Time"] = df["_parsed_ts"].dt.strftime("%I:%M %p").where(df["_parsed_ts"].notna(), "")
    # Insert Date/Time where Timestamp was, drop Timestamp
    other_cols = [c for c in df.columns if c not in (col, "Date", "Time", "_parsed_ts")]
    ts_idx = list(df.columns).index(col)
    before = [c for c in other_cols if list(df.columns).index(c) < ts_idx]
    after = [c for c in other_cols if list(df.columns).index(c) > ts_idx]
    return df[before + ["Date", "Time"] + after + ["_parsed_ts"]]


@st.cache_data(ttl=120)
def load_new_follows_data():
    old_stdout, sys.stdout = sys.stdout, StringIO()
    try:
        sm = get_sheets_manager()
        if not sm:
            return pd.DataFrame()
        try:
            sheet = sm.spreadsheet.worksheet("New Follows")
        except Exception:
            return pd.DataFrame()
        rows = sheet.get_all_values()
        if not rows or len(rows) < 2:
            return pd.DataFrame()
        return _clean_df(pd.DataFrame(rows[1:], columns=rows[0]))
    except Exception:
        return pd.DataFrame()
    finally:
        sys.stdout = old_stdout


@st.cache_data(ttl=120)
def load_hot_artists_data():
    old_stdout, sys.stdout = sys.stdout, StringIO()
    try:
        sm = get_sheets_manager()
        if not sm:
            return pd.DataFrame()
        try:
            sheet = sm.spreadsheet.worksheet("Hot Artists")
        except Exception:
            return pd.DataFrame()
        rows = sheet.get_all_values()
        if not rows or len(rows) < 2:
            return pd.DataFrame()
        return _clean_df(pd.DataFrame(rows[1:], columns=rows[0]))
    except Exception:
        return pd.DataFrame()
    finally:
        sys.stdout = old_stdout


@st.cache_data(ttl=120)
def load_ar_sheet_data(ar_username: str):
    old_stdout, sys.stdout = sys.stdout, StringIO()
    try:
        sm = get_sheets_manager()
        if not sm:
            return pd.DataFrame()
        try:
            sheet = sm.spreadsheet.worksheet(ar_username)
        except Exception:
            return pd.DataFrame()
        rows = sheet.get_all_values()
        if not rows or len(rows) < 2:
            return pd.DataFrame()
        return _clean_df(pd.DataFrame(rows[1:], columns=rows[0]))
    except Exception:
        return pd.DataFrame()
    finally:
        sys.stdout = old_stdout


@st.cache_data(ttl=120)
def load_all_ar_stats(accounts: tuple):
    old_stdout, sys.stdout = sys.stdout, StringIO()
    try:
        sm = get_sheets_manager()
        if not sm:
            return {}
        stats = {}
        for acct in accounts:
            try:
                sheet = sm.spreadsheet.worksheet(acct)
                rows = sheet.get_all_values()
                if rows and len(rows) >= 2:
                    headers = rows[0]
                    status_idx = headers.index("Status") if "Status" in headers else None
                    ts_idx = headers.index("Timestamp") if "Timestamp" in headers else None
                    total = 0
                    new_count = 0
                    latest_ts = ""
                    all_timestamps = set()
                    for row in rows[1:]:
                        if not any(cell.strip() for cell in row):
                            continue
                        total += 1
                        if status_idx is not None and len(row) > status_idx and row[status_idx].strip().upper() == "NEW":
                            new_count += 1
                        if ts_idx is not None and len(row) > ts_idx and row[ts_idx].strip():
                            ts_val = row[ts_idx].strip()
                            all_timestamps.add(ts_val)
                            if not latest_ts or ts_val > latest_ts:
                                latest_ts = ts_val
                    stats[acct] = {"total": total, "new": new_count, "last_run": latest_ts, "scan_timestamps": sorted(all_timestamps, reverse=True)}
                else:
                    stats[acct] = {"total": 0, "new": 0, "last_run": "", "scan_timestamps": []}
            except Exception:
                stats[acct] = {"total": 0, "new": 0, "last_run": "", "scan_timestamps": []}
        return stats
    except Exception:
        return {}
    finally:
        sys.stdout = old_stdout


def _format_last_run(ts_str):
    if not ts_str:
        return "Never"
    try:
        dt = pd.to_datetime(ts_str)
        return dt.strftime("%b %d, %Y at %I:%M %p")
    except Exception:
        return ts_str


def capture_tracker_run(func, *args, **kwargs):
    old_stdout = sys.stdout
    sys.stdout = buffer = StringIO()
    error = None
    result = None
    try:
        result = func(*args, **kwargs)
    except Exception as e:
        error = e
        print(f"\n[ERROR] {e}")
    finally:
        sys.stdout = old_stdout
    return buffer.getvalue(), result, error


def run_health_checks(config: dict) -> list:
    checks = []
    cookies = get_active_cookies()
    cookie_health = get_cookie_health(config, cookies_override=cookies)
    status_map = {"ok": "pass", "warning": "warn"}
    checks.append({"check": "Instagram Cookies", "status": status_map.get(cookie_health["status"], "fail"), "message": cookie_health["message"]})
    token = get_apify_token(config)
    checks.append({"check": "Apify API Token", "status": "pass" if token else "fail",
                    "message": "Token is configured." if token else "No Apify API token found."})
    creds_dict = get_google_credentials_dict()
    creds_file = config.get("credentials_file", "credentials/google_credentials.json")
    has_creds = creds_dict is not None or os.path.exists(creds_file)
    checks.append({"check": "Google Credentials", "status": "pass" if has_creds else "fail",
                    "message": "Configured." if has_creds else "Missing credentials."})
    sheet_id = get_spreadsheet_id()
    checks.append({"check": "Spreadsheet ID", "status": "pass" if sheet_id else "fail",
                    "message": "Configured." if sheet_id else "GOOGLE_SPREADSHEET_ID not set."})
    accounts = get_ar_accounts(config)
    checks.append({"check": "Tracked Accounts", "status": "pass" if accounts else "warn",
                    "message": f"{len(accounts)} account(s) configured." if accounts else "No competitor A&R accounts configured yet."})
    return checks


def _show_tracker_error(error):
    err_str = str(error).lower()
    st.error(f"**Error:** {error}")
    if any(w in err_str for w in ["cookie", "expired", "blocked", "banned", "401", "403", "login", "session", "unauthorized"]):
        st.warning("**What to do:** Cookies are expired or the account is blocked. Go to **Settings > Cookies** and paste fresh cookies. See the **Help** page for step-by-step instructions.")
    elif any(w in err_str for w in ["failed", "aborted", "timed-out"]):
        st.warning("**What to do:** The Apify scan failed. Check the [Apify console](https://console.apify.com/) for details. Usually this means cookies need updating — go to **Settings > Cookies**.")
    elif any(w in err_str for w in ["0 results", "no data"]):
        st.warning("**What to do:** No data came back. This usually means cookies need updating. Go to **Settings > Cookies**.")
    elif any(w in err_str for w in ["timeout", "timed out"]):
        st.warning("**What to do:** The scan timed out. Try scanning fewer accounts at a time using 'Scan specific accounts'.")
    elif "private" in err_str:
        st.warning("**What to do:** This account may be private. Private accounts can't be scanned.")
    else:
        st.warning("**What to do:** Check the Run Log below for details. If the issue persists, try updating cookies in **Settings > Cookies**.")


@st.cache_data(ttl=120)
def _load_tracking_account():
    """Load tracking Instagram account info from Google Sheet."""
    old_stdout, sys.stdout = sys.stdout, StringIO()
    try:
        sm = get_sheets_manager()
        if not sm:
            return {}
        return sm.load_tracking_account()
    except Exception:
        return {}
    finally:
        sys.stdout = old_stdout


STATUS_ICONS = {"pass": "✅", "warn": "⚠️", "fail": "❌"}

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

_RADIO_PAGES = ["New Follows", "Hot Artists", "Competitor A&Rs", "Scan History", "Scan Log", "Settings", "Help"]

if "active_page" not in st.session_state:
    st.session_state.active_page = "New Follows"
# _nav_radio tracks the last radio selection (persists when on Run Tracker page)
if "_nav_radio" not in st.session_state:
    st.session_state._nav_radio = "New Follows"
if "last_scan_results" not in st.session_state:
    st.session_state.last_scan_results = []  # list of {account, success, new_follows, error}

def _on_nav_change():
    st.session_state.active_page = st.session_state._nav_radio

with st.sidebar:
    st.title("Snoopfinder")

    if st.button("Run Tracker", type="primary", use_container_width=True):
        st.session_state.active_page = "Run Tracker"
        st.rerun()

    st.divider()

    # Keep radio showing last selection even when on Run Tracker page
    _nav_display = (st.session_state.active_page
                    if st.session_state.active_page in _RADIO_PAGES
                    else st.session_state._nav_radio)

    st.radio(
        "Navigate",
        _RADIO_PAGES,
        index=_RADIO_PAGES.index(_nav_display),
        key="_nav_radio",
        on_change=_on_nav_change,
        label_visibility="collapsed",
    )

    st.divider()

    st.error("If the tracker fails, update cookies in **Settings > Cookies**.")

    sheet_id = get_spreadsheet_id()
    if sheet_id:
        st.markdown(f"[Open Google Sheet](https://docs.google.com/spreadsheets/d/{sheet_id})")

page = st.session_state.active_page


# ===========================================================================
# PAGE: New Follows (LANDING PAGE)
# ===========================================================================
if page == "New Follows":
    st.header("New Follows")
    st.caption("Accounts that competitor A&Rs have recently started following.")

    config = load_config()
    accounts = get_ar_accounts(config)

    if accounts:
        stats = load_all_ar_stats(tuple(accounts))
        total_tracked = sum(s["total"] for s in stats.values())
        total_new = sum(s["new"] for s in stats.values())
        all_runs = [s["last_run"] for s in stats.values() if s["last_run"]]
        last_run = _format_last_run(max(all_runs) if all_runs else "")

        cols = st.columns(4)
        cols[0].metric("Competitor A&Rs", len(accounts))
        cols[1].metric("Total Follows Tracked", f"{total_tracked:,}")
        cols[2].metric("New Follows", f"{total_new:,}")
        cols[3].metric("Last Scan", last_run)

    st.divider()

    df = load_new_follows_data()

    if df.empty:
        st.info("No new follows detected yet. Go to **Run Tracker** to scan.")
    else:
        # DEBUG — remove once confirmed working
        with st.expander("Debug info (temporary)", expanded=False):
            st.write("Columns:", list(df.columns))
            if not df.empty:
                st.write("First timestamp value:", df.iloc[0, 0] if df.shape[1] > 0 else "n/a")
                st.write("Last timestamp value:", df.iloc[-1, 0] if df.shape[1] > 0 else "n/a")

        display_df = _format_timestamp_col(df)
        # Sort by parsed datetime descending (most recent scan first)
        display_df = display_df.sort_values("_parsed_ts", ascending=False, na_position="last").reset_index(drop=True)

        # Filters row: A&R, search, date
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            ar_filter = st.multiselect(
                "Filter by competitor A&R",
                options=sorted(df["A&R Account"].unique()) if "A&R Account" in df.columns else [],
                default=[],
                placeholder="All",
            )
        with col2:
            search = st.text_input("Search (any field)", placeholder="Username, name, A&R...", key="nf_search")
        with col3:
            date_options = ["All time", "Today", "Last 7 days", "Last 30 days", "Custom range"]
            date_filter = st.selectbox("Date range", date_options, key="nf_date")

        # Custom date range
        custom_start = custom_end = None
        if date_filter == "Custom range":
            d1, d2 = st.columns(2)
            with d1:
                custom_start = st.date_input("From", value=datetime.now().date() - timedelta(days=30), key="nf_from")
            with d2:
                custom_end = st.date_input("To", value=datetime.now().date(), key="nf_to")

        filtered = display_df.copy()

        # Apply A&R filter
        if ar_filter:
            filtered = filtered[filtered["A&R Account"].isin(ar_filter)]

        # Apply search across all columns (except hidden ones)
        if search:
            s = search.lower()
            visible_cols = [c for c in filtered.columns if c != "_parsed_ts"]
            mask = filtered[visible_cols].apply(lambda row: any(s in str(v).lower() for v in row), axis=1)
            filtered = filtered[mask]

        # Apply date filter
        if "_parsed_ts" in filtered.columns and date_filter != "All time":
            now = pd.Timestamp.now()
            if date_filter == "Today":
                filtered = filtered[filtered["_parsed_ts"].dt.date == now.date()]
            elif date_filter == "Last 7 days":
                filtered = filtered[filtered["_parsed_ts"] >= now - timedelta(days=7)]
            elif date_filter == "Last 30 days":
                filtered = filtered[filtered["_parsed_ts"] >= now - timedelta(days=30)]
            elif date_filter == "Custom range" and custom_start and custom_end:
                filtered = filtered[
                    (filtered["_parsed_ts"].dt.date >= custom_start) &
                    (filtered["_parsed_ts"].dt.date <= custom_end)
                ]

        # Drop hidden column before display
        show_df = filtered.drop(columns=["_parsed_ts"], errors="ignore")

        st.caption(f"Showing {len(show_df)} of {len(display_df)} results")

        st.dataframe(
            show_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Profile Pic": st.column_config.ImageColumn("Pic", width="small"),
                "Profile URL": st.column_config.LinkColumn("Profile", display_text="Open"),
                "Date": st.column_config.TextColumn("Date", width="medium"),
                "Time": st.column_config.TextColumn("Time", width="small"),
                "A&R Account": st.column_config.TextColumn("Competitor A&R", width="medium"),
                "New Follow": st.column_config.TextColumn("Followed User", width="medium"),
                "Full Name": st.column_config.TextColumn("Full Name", width="medium"),
            },
            height=600,
        )

    if st.button("Refresh"):
        load_new_follows_data.clear()
        load_all_ar_stats.clear()
        st.rerun()


# ===========================================================================
# PAGE: Hot Artists
# ===========================================================================
elif page == "Hot Artists":
    st.header("Hot Artists")
    st.caption("Artists followed by multiple competitor A&Rs — likely being scouted by several labels.")

    df = load_hot_artists_data()

    if df.empty:
        st.info("No data yet. Go to **Run Tracker** and select **Update Hot Artists**.")
    else:
        display_df = df.copy()
        for date_col in ["Date First Spotted", "Date Last Followed"]:
            if date_col in display_df.columns:
                try:
                    parsed = pd.to_datetime(display_df[date_col], errors="coerce")
                    display_df[date_col] = parsed.dt.strftime("%b %d, %Y").fillna(display_df[date_col])
                except Exception:
                    pass

        col1, col2 = st.columns([1, 1])
        with col1:
            search = st.text_input("Search (any field)", placeholder="Username, name, A&R...", key="hot_search")
        with col2:
            if "# of A&Rs" in display_df.columns:
                try:
                    display_df["# of A&Rs"] = pd.to_numeric(display_df["# of A&Rs"], errors="coerce").fillna(0).astype(int)
                except Exception:
                    pass
                min_ars = st.slider("Minimum # of A&Rs following", min_value=2, max_value=max(5, int(display_df["# of A&Rs"].max()) if len(display_df) else 5), value=3)
            else:
                min_ars = 3

        filtered = display_df.copy()
        if search:
            s = search.lower()
            mask = filtered.apply(lambda row: any(s in str(v).lower() for v in row), axis=1)
            filtered = filtered[mask]
        if "# of A&Rs" in filtered.columns:
            filtered = filtered[filtered["# of A&Rs"] >= min_ars]

        st.caption(f"Showing {len(filtered)} artists")

        col_config = {
            "Profile Pic": st.column_config.ImageColumn("Pic", width="small"),
            "Profile URL": st.column_config.LinkColumn("Profile", display_text="Open"),
            "# of A&Rs": st.column_config.NumberColumn("# of A&Rs", width="small"),
            "A&Rs Following": st.column_config.TextColumn("Which A&Rs", width="large"),
            "Date First Spotted": st.column_config.TextColumn("First Spotted", width="medium"),
            "Date Last Followed": st.column_config.TextColumn("Last Followed", width="medium"),
        }
        if "Account Type" in filtered.columns:
            col_config["Account Type"] = st.column_config.TextColumn("Type", width="small")
        if "Checked" in filtered.columns:
            col_config["Checked"] = st.column_config.TextColumn("Checked", width="small")

        st.dataframe(filtered, use_container_width=True, hide_index=True, column_config=col_config, height=600)

    if st.button("Refresh", key="refresh_hot"):
        load_hot_artists_data.clear()
        st.rerun()


# ===========================================================================
# PAGE: Competitor A&Rs
# ===========================================================================
elif page == "Competitor A&Rs":
    st.header("Competitor A&Rs")
    st.caption("Full following data for each competitor A&R account you're monitoring.")

    config = load_config()
    accounts = get_ar_accounts(config)

    if not accounts:
        st.info("No competitor A&R accounts added yet. Go to **Settings** to add some.")
        st.stop()

    stats = load_all_ar_stats(tuple(accounts))

    overview_data = []
    for acct in accounts:
        s = stats.get(acct, {"total": 0, "new": 0, "last_run": ""})
        overview_data.append({
            "Account": f"@{acct}",
            "Total Follows": s["total"],
            "New Follows": s["new"],
            "Last Scanned": _format_last_run(s["last_run"]),
        })

    st.dataframe(
        pd.DataFrame(overview_data),
        use_container_width=True,
        hide_index=True,
        height=min(400, 50 + len(overview_data) * 35),
    )

    st.divider()

    selected = st.selectbox("View details for", accounts, format_func=lambda x: f"@{x}")

    if selected:
        df = load_ar_sheet_data(selected)
        if df.empty:
            st.info(f"No data for @{selected} yet. Run the tracker to scan their follows.")
        else:
            if "Username" in df.columns:
                df = df[df["Username"].str.strip() != ""]

            s = stats.get(selected, {"total": 0, "new": 0, "last_run": ""})
            scols = st.columns(4)
            scols[0].metric("Total Follows", len(df))
            new_count = len(df[df["Status"].str.upper() == "NEW"]) if "Status" in df.columns else 0
            scols[1].metric("New Follows", new_count)
            baseline_count = len(df[df["Status"].str.upper() == "BASELINE"]) if "Status" in df.columns else 0
            scols[2].metric("Baseline", baseline_count)
            scols[3].metric("Last Scanned", _format_last_run(s["last_run"]))

            col1, col2 = st.columns([1, 1])
            with col1:
                status_filter = st.selectbox("Filter by status", ["All", "NEW", "BASELINE"], key="ar_status")
            with col2:
                search = st.text_input("Search (any field)", placeholder="Username, name...", key="ar_search")

            display_df = _format_timestamp_col(df)

            filtered = display_df.copy()
            if status_filter != "All" and "Status" in filtered.columns:
                filtered = filtered[filtered["Status"].str.upper() == status_filter]
            if search:
                s = search.lower()
                visible_cols = [c for c in filtered.columns if c != "_parsed_ts"]
                mask = filtered[visible_cols].apply(lambda row: any(s in str(v).lower() for v in row), axis=1)
                filtered = filtered[mask]

            show_df = filtered.drop(columns=["_parsed_ts"], errors="ignore")

            st.caption(f"Showing {len(show_df)} of {len(display_df)} follows for @{selected}")
            st.dataframe(
                show_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Profile Pic": st.column_config.ImageColumn("Pic", width="small"),
                    "Profile URL": st.column_config.LinkColumn("Profile", display_text="Open"),
                    "Date": st.column_config.TextColumn("Date", width="medium"),
                    "Time": st.column_config.TextColumn("Time", width="small"),
                    "Status": st.column_config.TextColumn("Status", width="small"),
                },
                height=600,
            )

    if st.button("Refresh", key="refresh_ar"):
        load_ar_sheet_data.clear()
        load_all_ar_stats.clear()
        st.rerun()


# ===========================================================================
# PAGE: Scan History
# ===========================================================================
elif page == "Scan History":
    st.header("Scan History")
    st.caption("A log of every scan run, showing when each competitor A&R was last checked.")

    config = load_config()
    accounts = get_ar_accounts(config)

    if not accounts:
        st.info("No accounts configured yet.")
        st.stop()

    stats = load_all_ar_stats(tuple(accounts))

    # Build scan history from all timestamps across all accounts
    scan_events = []
    for acct in accounts:
        s = stats.get(acct, {"scan_timestamps": []})
        for ts_str in s.get("scan_timestamps", []):
            try:
                dt = pd.to_datetime(ts_str)
                scan_events.append({
                    "Account": f"@{acct}",
                    "Scan Date": dt.strftime("%b %d, %Y"),
                    "Scan Time": dt.strftime("%I:%M %p"),
                    "_sort": dt,
                })
            except Exception:
                pass

    if not scan_events:
        st.info("No scans have been run yet. Go to **Run Tracker** to start.")
        st.stop()

    scan_df = pd.DataFrame(scan_events)

    # Deduplicate: group by account + date/time (same scan produces many rows with same timestamp)
    scan_df = scan_df.drop_duplicates(subset=["Account", "Scan Date", "Scan Time"])
    scan_df = scan_df.sort_values("_sort", ascending=False).reset_index(drop=True)

    # Summary stats
    unique_dates = scan_df["Scan Date"].nunique()
    total_scans = len(scan_df)
    latest = scan_df.iloc[0]

    cols = st.columns(3)
    cols[0].metric("Total Scan Events", total_scans)
    cols[1].metric("Unique Scan Days", unique_dates)
    cols[2].metric("Most Recent", f"{latest['Scan Date']} at {latest['Scan Time']}")

    st.divider()

    # Filter by account
    acct_filter = st.multiselect(
        "Filter by account",
        options=sorted(scan_df["Account"].unique()),
        default=[],
        placeholder="All accounts",
        key="sh_filter",
    )

    show_df = scan_df.drop(columns=["_sort"])
    if acct_filter:
        show_df = show_df[show_df["Account"].isin(acct_filter)]

    st.caption(f"Showing {len(show_df)} scan events")
    st.dataframe(show_df, use_container_width=True, hide_index=True, height=500)

    if st.button("Refresh", key="refresh_sh"):
        load_all_ar_stats.clear()
        st.rerun()


# ===========================================================================
# PAGE: Run Tracker
# ===========================================================================
elif page == "Run Tracker":
    st.header("Run Tracker")
    st.caption("Scan competitor A&R accounts for new follows.")

    config = load_config()
    accounts = get_ar_accounts(config)

    if not accounts:
        st.warning("No competitor A&R accounts configured. Add one below.")

    # Reset stuck tracker state
    if st.session_state.tracker_running:
        st.warning("Tracker appears to be running. If it's stuck, click Reset.")
        if st.button("Reset (stuck?)", type="secondary"):
            st.session_state.tracker_running = False
            st.rerun()

    run_mode = st.radio(
        "What do you want to do?",
        ["Scan specific accounts", "Scan all accounts", "Update Hot Artists"],
        captions=[
            "Pick which accounts to check",
            "Check every competitor A&R for new follows",
            "Refresh the Hot Artists list (artists followed by 3+ A&Rs)",
        ],
    )

    # Pre-populate with retry list if coming from a failed run
    _retry_default = st.session_state.pop("_retry_accounts", None)
    selected_accounts = []
    if run_mode == "Scan specific accounts":
        default_sel = [a for a in (_retry_default or accounts) if a in accounts]
        selected_accounts = st.multiselect("Select accounts", accounts, default=default_sel)

    # --- Add new account inline ---
    with st.expander("Add a new competitor A&R account"):
        new_acct_col, btn_col = st.columns([3, 1])
        new_username_input = new_acct_col.text_input(
            "Instagram username",
            placeholder="label_ar  (@ is optional)",
            label_visibility="collapsed",
            key="rt_new_account",
        )
        if btn_col.button("Add", key="rt_add_account"):
            if new_username_input.strip():
                success, msg = add_ar_account(new_username_input.strip())
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.error("Enter a username.")

    # Reload accounts after potential add
    accounts = get_ar_accounts(load_config())
    if not accounts:
        st.stop()

    if st.button("Run", type="primary", disabled=st.session_state.tracker_running):
        st.session_state.tracker_running = True
        st.session_state.log_output = ""
        st.session_state.last_scan_results = []

        active_cookies = get_active_cookies()
        if active_cookies:
            cfg = load_config()
            if "apify" not in cfg:
                cfg["apify"] = {}
            cfg["apify"]["cookies"] = active_cookies
            try:
                from src.config_manager import save_config
                save_config(cfg)
            except Exception:
                pass

        with st.spinner("Scanning... this may take several minutes per account."):
            try:
                from src.tracker import FollowingTracker

                scan_results = []  # [{account, success, new_follows, error}]
                full_log = ""

                if run_mode == "Update Hot Artists":
                    tracker = FollowingTracker(clear_summary=False)
                    log, result, error = capture_tracker_run(tracker.update_hot_artists)
                    full_log = log
                    scan_results = [{"account": "Hot Artists update", "success": error is None,
                                     "new_follows": 0, "error": str(error) if error else None}]

                elif run_mode == "Scan specific accounts":
                    if not selected_accounts:
                        st.error("Select at least one account.")
                        st.session_state.tracker_running = False
                        st.stop()
                    tracker = FollowingTracker(clear_summary=False)
                    for acct in selected_accounts:
                        tracker.sheets.clear_summary_sheet(ar_username=acct)
                        log, result, err = capture_tracker_run(tracker.track_ar_account, acct)
                        full_log += log
                        new_f = result.get("new_follows", 0) if isinstance(result, dict) else 0
                        scan_results.append({
                            "account": acct,
                            "success": err is None,
                            "new_follows": new_f,
                            "error": str(err) if err else None,
                        })
                    failed = [r for r in scan_results if not r["success"]]
                    error = RuntimeError(f"{len(failed)} account(s) failed") if failed else None

                else:  # Scan all
                    tracker = FollowingTracker(clear_summary=True)
                    log, results_list, error = capture_tracker_run(tracker.track_all)
                    full_log = log
                    if isinstance(results_list, list):
                        for r in results_list:
                            scan_results.append({
                                "account": r.get("ar_account", "?"),
                                "success": r.get("status") != "error",
                                "new_follows": r.get("new_follows", 0),
                                "error": r.get("message") if r.get("status") == "error" else None,
                            })

                st.session_state.log_output = full_log
                st.session_state.last_scan_results = scan_results

                # Write to Scan Log
                try:
                    sm = get_sheets_manager()
                    if sm and scan_results and run_mode != "Update Hot Artists":
                        failed_accts = [r["account"] for r in scan_results if not r["success"]]
                        sm.add_scan_log_entry(
                            user="",
                            mode=run_mode,
                            accounts_scanned=len(scan_results),
                            succeeded=len([r for r in scan_results if r["success"]]),
                            failed=len(failed_accts),
                            new_follows=sum(r["new_follows"] for r in scan_results),
                            failed_accounts=failed_accts,
                        )
                except Exception:
                    pass  # Don't block on log write failure

                load_new_follows_data.clear()
                load_hot_artists_data.clear()
                load_all_ar_stats.clear()
                load_ar_sheet_data.clear()

            except Exception as e:
                st.session_state.log_output = str(e)
                _show_tracker_error(e)
            finally:
                st.session_state.tracker_running = False

    # --- Post-run summary ---
    if st.session_state.last_scan_results:
        results = st.session_state.last_scan_results
        succeeded = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]
        total_new = sum(r["new_follows"] for r in results)

        st.divider()
        if failed:
            st.error(f"**Scan complete with errors** — {len(succeeded)}/{len(results)} accounts succeeded, {len(failed)} failed")
        else:
            st.success(f"**All {len(succeeded)} accounts scanned successfully** — {total_new} new follows found")

        # Per-account breakdown
        sum_cols = st.columns(3)
        sum_cols[0].metric("Scanned", len(results))
        sum_cols[1].metric("Succeeded", len(succeeded))
        sum_cols[2].metric("New Follows Found", total_new)

        if failed:
            st.markdown("**Failed accounts:**")
            for r in failed:
                st.warning(f"@{r['account']} — {r['error']}")
            if st.button("Retry failed accounts", type="primary"):
                st.session_state._retry_accounts = [r["account"] for r in failed]
                st.session_state.last_scan_results = []
                st.rerun()

        with st.expander("Per-account breakdown"):
            for r in results:
                icon = "✅" if r["success"] else "❌"
                detail = f"{r['new_follows']} new follows" if r["success"] else r["error"]
                st.markdown(f"{icon} **@{r['account']}** — {detail}")

    if st.session_state.log_output:
        with st.expander("Run Log", expanded=False):
            st.code(st.session_state.log_output, language="text")


# ===========================================================================
# PAGE: Settings
# ===========================================================================
elif page == "Settings":
    st.header("Settings")

    tab_accounts, tab_cookies, tab_ig_account, tab_health = st.tabs(["Competitor A&Rs", "Cookies", "Tracking Account", "System Health"])

    # --- TAB: Competitor A&Rs ---
    with tab_accounts:
        config = load_config()
        accounts = get_ar_accounts(config)

        st.subheader(f"Monitoring {len(accounts)} accounts")
        if accounts:
            for acct in accounts:
                col1, col2 = st.columns([4, 1])
                col1.markdown(f"**@{acct}**")
                if col2.button("Remove", key=f"remove_{acct}"):
                    success, msg = remove_ar_account(acct)
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
        else:
            st.info("No accounts added yet.")

        st.divider()

        st.subheader("Add Competitor A&R")
        st.caption("Enter their Instagram username. After adding, run the tracker to establish a baseline of who they currently follow.")

        new_username = st.text_input("Instagram username", placeholder="e.g. label_ar")
        if st.button("Add Account", type="primary"):
            if new_username:
                success, msg = add_ar_account(new_username)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.error("Enter a username.")

        st.divider()

        st.subheader("Sync from Google Sheet")
        st.caption("Pull the account list from the Google Sheet if accounts were added there directly.")
        if st.button("Sync"):
            try:
                from src.tracker import FollowingTracker
                with st.spinner("Syncing..."):
                    old_stdout, sys.stdout = sys.stdout, StringIO()
                    try:
                        tracker = FollowingTracker(clear_summary=False)
                        synced = tracker.sync_accounts_from_sheets()
                    finally:
                        sys.stdout = old_stdout
                    config["ar_accounts"] = synced
                    from src.config_manager import save_config
                    save_config(config)
                    st.success(f"Synced {len(synced)} accounts.")
                    st.rerun()
            except Exception as e:
                st.error(f"Sync failed: {e}")

    # --- TAB: Cookies ---
    with tab_cookies:
        config = load_config()
        cookies = get_active_cookies()
        health = get_cookie_health(config, cookies_override=cookies)

        st.subheader("Status")
        if health["status"] == "ok":
            st.success(health["message"])
        elif health["status"] == "warning":
            st.warning(health["message"])
        else:
            st.error(health["message"])

        details = health.get("details", {})
        if details:
            cols = st.columns(3)
            cols[0].metric("Expires", details.get("session_expires", "N/A"))
            cols[1].metric("Days Left", details.get("session_days_left", "N/A"))
            cols[2].metric("User ID", details.get("ds_user_id", "N/A"))

        st.divider()

        st.subheader("Update Cookies")
        st.caption("Cookies expire every 30-90 days. If scans stop working, this is the first thing to fix.")

        # Show tracking account credentials inline so they don't have to switch tabs
        ig_info = _load_tracking_account()
        if ig_info.get("username"):
            with st.expander("Tracking account login details", expanded=True):
                st.markdown(f"**Username:** `{ig_info['username']}`")
                if ig_info.get("email"):
                    st.markdown(f"**Email / Phone:** `{ig_info['email']}`")
                if ig_info.get("password"):
                    if st.toggle("Show password", key="show_pw_cookies"):
                        st.code(ig_info["password"], language=None)
                if ig_info.get("notes"):
                    st.caption(ig_info["notes"])
        else:
            st.info("No tracking account saved yet — add login details in the **Tracking Account** tab first.")

        st.markdown("""
**Steps to get fresh cookies:**
1. Open **[instagram.com](https://instagram.com)** in Chrome and log in with the details above
2. Install [Copy Cookies](https://chromewebstore.google.com/detail/copy-cookies/jcbpglbplpblnagieibnemmkiamekcdg) if you haven't already
3. Click the **Copy Cookies** extension icon while on instagram.com
4. Click **"Copy"** in the popup
5. Paste below and click **Save**
""")

        cookies_input = st.text_area(
            "Paste cookies JSON",
            height=150,
            placeholder='[{"name": "sessionid", "value": "...", ...}, ...]',
        )

        if st.button("Save Cookies", type="primary"):
            if cookies_input:
                valid, msg, parsed = validate_cookies(cookies_input)
                if not valid:
                    st.error(msg)
                else:
                    saved_to_sheet = False
                    try:
                        old_stdout, sys.stdout = sys.stdout, StringIO()
                        try:
                            sm = get_sheets_manager()
                            if sm:
                                sm.save_cookies_to_sheet(cookies_input)
                                saved_to_sheet = True
                        finally:
                            sys.stdout = old_stdout
                    except Exception:
                        pass
                    try:
                        update_cookies(cookies_input)
                    except Exception:
                        pass
                    if saved_to_sheet:
                        st.success(f"Cookies saved! ({len(parsed)} cookies)")
                        load_cookies_from_sheet.clear()
                        st.rerun()
                    else:
                        st.error("Could not save cookies. Check Google Sheets connection.")
            else:
                st.error("Paste your cookies first.")

    # --- TAB: Tracking Account ---
    with tab_ig_account:
        st.subheader("Instagram Tracking Account")
        st.caption("The Instagram account used to scan competitor A&Rs. Store the login details here so anyone on the team can grab them when cookies need updating.")

        ig_info = _load_tracking_account()

        # Show current details
        if ig_info.get("username"):
            st.markdown("**Current tracking account:**")
            st.markdown(f"- **Username:** `{ig_info.get('username', '')}`")
            if ig_info.get("email"):
                st.markdown(f"- **Email/Phone:** `{ig_info.get('email', '')}`")
            if ig_info.get("password"):
                with st.expander("Show password"):
                    st.code(ig_info["password"], language=None)
            if ig_info.get("notes"):
                st.info(ig_info["notes"])
            st.success("To update cookies: go to the **Cookies** tab — the login details above will appear there automatically.")
        else:
            st.info("No tracking account details saved yet. Add them below.")

        st.divider()

        # Edit form
        st.subheader("Update Account Details")
        new_ig_user = st.text_input("Instagram username", value=ig_info.get("username", ""), key="ig_user_input")
        new_ig_pass = st.text_input("Instagram password", value=ig_info.get("password", ""), type="password", key="ig_pass_input")
        new_ig_email = st.text_input("Email or phone used to create the account", value=ig_info.get("email", ""), key="ig_email_input")
        new_ig_notes = st.text_area("Notes for the team", value=ig_info.get("notes", ""), height=80, key="ig_notes_input", placeholder="e.g. Created March 2026, don't change the profile pic")

        if st.button("Save Account Details", type="primary", key="ig_save"):
            info_to_save = {
                "username": new_ig_user.strip(),
                "password": new_ig_pass.strip(),
                "email": new_ig_email.strip(),
                "notes": new_ig_notes.strip(),
            }
            try:
                old_stdout, sys.stdout = sys.stdout, StringIO()
                try:
                    sm = get_sheets_manager()
                    if sm and sm.save_tracking_account(info_to_save):
                        _load_tracking_account.clear()
                        st.success("Account details saved!")
                        st.rerun()
                    else:
                        st.error("Could not save. Check Google Sheets connection.")
                finally:
                    sys.stdout = old_stdout
            except Exception as e:
                st.error(f"Error saving: {e}")

        st.divider()
        st.subheader("How to copy cookies")
        st.markdown("""
1. Open **Chrome** and go to **instagram.com**
2. Log in with the tracking account details above
3. Install [Copy Cookies](https://chromewebstore.google.com/detail/copy-cookies/jcbpglbplpblnagieibnemmkiamekcdg) if you haven't already
4. Click the extension icon (puzzle piece icon in Chrome toolbar, then find Copy Cookies)
5. Click **"Copy"** — this copies the cookies to your clipboard
6. Go to the **Cookies** tab in this app and paste them in
""")

        st.divider()
        st.subheader("If the account gets banned or locked")
        st.markdown("""
Instagram sometimes bans tracking accounts. If that happens:

1. **Create a new Instagram account** — use a different email address
2. **Let it age** — browse Instagram normally for a day or two before using it for scanning
3. **Update the details above** with the new username/password/email
4. **Log into the new account** in Chrome and copy cookies
5. **Paste the new cookies** in the **Cookies** tab

**Tips to avoid bans:**
- Don't scan more than once a day
- Don't scan too many accounts in one run
- The tracking account should follow a few random accounts to look like a real person
""")

    # --- TAB: System Health ---
    with tab_health:
        config = load_config()
        checks = run_health_checks(config)

        any_fail = any(c["status"] == "fail" for c in checks)
        any_warn = any(c["status"] == "warn" for c in checks)

        if any_fail:
            st.error("Some checks failed — scans won't work until these are fixed.")
        elif any_warn:
            st.warning("Warnings detected but scans should still work.")
        else:
            st.success("All systems healthy.")

        for c in checks:
            icon = STATUS_ICONS[c["status"]]
            st.markdown(f"{icon} **{c['check']}** — {c['message']}")


# ===========================================================================
# PAGE: Scan Log
# ===========================================================================
elif page == "Scan Log":
    st.header("Scan Log")
    st.caption("A record of every tracker run — who ran it, which accounts were scanned, and what happened.")

    @st.cache_data(ttl=60)
    def load_scan_log_data():
        old_stdout, sys.stdout = sys.stdout, StringIO()
        try:
            sm = get_sheets_manager()
            if not sm:
                return []
            return sm.load_scan_log()
        except Exception:
            return []
        finally:
            sys.stdout = old_stdout

    log_rows = load_scan_log_data()

    if not log_rows:
        st.info("No scan history yet. Run the tracker to start logging.")
    else:
        log_df = pd.DataFrame(log_rows)

        # Parse timestamps for sorting
        if "Timestamp" in log_df.columns:
            log_df["_ts"] = pd.to_datetime(log_df["Timestamp"], errors="coerce")
            log_df = log_df.sort_values("_ts", ascending=False, na_position="last").reset_index(drop=True)
            log_df = log_df.drop(columns=["_ts"])

        # Summary metrics
        total_runs = len(log_df)
        total_new = pd.to_numeric(log_df["New Follows Found"], errors="coerce").sum() if "New Follows Found" in log_df.columns else 0
        total_failed = pd.to_numeric(log_df["Failed"], errors="coerce").sum() if "Failed" in log_df.columns else 0

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Runs", total_runs)
        m2.metric("New Follows Found (all time)", int(total_new))
        m3.metric("Total Failed Accounts", int(total_failed))

        st.divider()

        # Filter by mode only
        mode_filter = []
        if "Mode" in log_df.columns:
            mode_filter = st.multiselect("Filter by mode", sorted(log_df["Mode"].dropna().unique()), placeholder="All modes")

        show_log = log_df.copy()
        if mode_filter:
            show_log = show_log[show_log["Mode"].isin(mode_filter)]

        st.caption(f"Showing {len(show_log)} of {total_runs} runs")
        st.dataframe(show_log, use_container_width=True, hide_index=True, height=500)

    if st.button("Refresh", key="sl_refresh"):
        load_scan_log_data.clear()
        st.rerun()


# ===========================================================================
# PAGE: Help
# ===========================================================================
elif page == "Help":
    st.header("Help")

    st.subheader("What is this?")
    st.markdown("""
This tool tracks who **competitor A&R accounts** follow on Instagram.
When a rival A&R starts following a new artist, it could mean they're scouting them for a deal.
This gives your team a heads-up on who competitors are looking at.
""")

    st.subheader("Quick start")
    st.markdown("""
1. **Settings > Competitor A&Rs** — add the Instagram usernames of rival A&Rs you want to monitor
2. **Run Tracker > Scan all accounts** — the first scan saves their current follows as a baseline
3. **Run again later** (next day, next week) — new follows since the last scan get flagged
4. **New Follows** — see who competitors recently followed
5. **Hot Artists** — see artists followed by 3+ competitor A&Rs (strongest signal)
""")

    st.subheader("Key concepts")
    st.markdown("""
- **Baseline** = everyone a competitor A&R was following when we first scanned them
- **New Follow** = someone they started following *after* the baseline was set — these are the interesting ones
- **Hot Artist** = an artist followed by 3+ competitor A&Rs — multiple A&Rs showing interest is a strong signal
- **Scan History** = a log of every time we scanned each competitor A&R account
""")

    st.subheader("Cookies & authentication")
    st.markdown("""
The tracker uses Instagram cookies to access following lists. Cookies expire every 30-90 days.

- **Check cookie status** in the sidebar — green means you're good
- **When cookies expire**, go to **Settings > Cookies** and paste fresh ones
- **Login details** for the tracking Instagram account are in **Settings > Tracking Account**
- **If the account gets banned**, create a new Instagram account and paste its cookies — see **Settings > Tracking Account** for full instructions
""")

    st.subheader("Common issues")

    with st.expander("Scans returning errors or 0 results"):
        st.markdown("""
This almost always means cookies have expired. Go to **Settings > Cookies** and paste fresh ones.

If the tracking Instagram account got banned, see **Settings > Tracking Account** for instructions on creating a new one.
""")

    with st.expander("Scans taking too long"):
        st.markdown("""
A&Rs who follow thousands of people take longer to scan (5-10 min each).
Use **Scan specific accounts** on the Run Tracker page to do a few at a time.
""")

    with st.expander("First scan shows no new follows"):
        st.markdown("That's normal — the first scan only sets the baseline. New follows will show up on the next scan.")

    st.divider()
    st.subheader("Access control")
    st.markdown("""
Access control is managed through Streamlit Cloud's sharing settings. Go to your app's settings on Streamlit Cloud to configure who can access it.
""")
