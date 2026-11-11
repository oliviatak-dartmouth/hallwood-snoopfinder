"""
Instagram Follow Tracker: public demo.

This demo uses entirely made-up sample data. It has no connection to Instagram,
Apify or Google Sheets, needs no secrets, and cannot run real scans. The real
dashboard lives in app.py.
"""

import random
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Follow Tracker Demo", page_icon="📈", layout="wide")

# ----------------------------------------------------------------------------
# Synthetic data (seeded so the demo looks the same on every load)
# ----------------------------------------------------------------------------
SCOUTS = ["label_ar_one", "label_ar_two", "label_ar_three", "label_ar_four", "label_ar_five"]
ARTISTS = [
    ("nova_demo", "Nova Demo", "Pop"),
    ("kairo_sample", "Kairo Sample", "Hip-hop"),
    ("mira_mock", "Mira Mock", "R&B"),
    ("the_test_tapes", "The Test Tapes", "Indie"),
    ("juno_example", "Juno Example", "Pop"),
    ("sable_fake", "Sable Fake", "Alt"),
    ("rowan_placeholder", "Rowan Placeholder", "Singer-songwriter"),
    ("echo_demo_club", "Echo Demo Club", "Electronic"),
    ("lark_sample", "Lark Sample", "Folk"),
    ("vesper_mock", "Vesper Mock", "R&B"),
    ("dune_example", "Dune Example", "Hip-hop"),
    ("ivy_testcase", "Ivy Testcase", "Pop"),
]


@st.cache_data
def make_data():
    rng = random.Random(7)
    now = datetime(2026, 11, 11, 9, 0)
    rows = []
    for artist in ARTISTS:
        n_scouts = rng.choice([1, 1, 1, 2, 2, 3, 4])
        for scout in rng.sample(SCOUTS, n_scouts):
            ts = now - timedelta(days=rng.randint(0, 20), hours=rng.randint(0, 23))
            rows.append(
                {
                    "Timestamp": ts,
                    "Scout": scout,
                    "Followed": artist[0],
                    "Name": artist[1],
                    "Genre": artist[2],
                    "Followers": rng.choice([800, 1500, 4200, 9800, 15000, 32000, 61000]),
                }
            )
    follows = pd.DataFrame(rows).sort_values("Timestamp", ascending=False).reset_index(drop=True)

    hot = (
        follows.groupby(["Followed", "Name", "Genre", "Followers"])
        .agg(Scouts=("Scout", "nunique"), Who=("Scout", lambda s: ", ".join(sorted(set(s)))))
        .reset_index()
        .query("Scouts >= 2")
        .sort_values(["Scouts", "Followers"], ascending=False)
        .reset_index(drop=True)
    )

    scans = []
    for i in range(14):
        day = now - timedelta(days=i)
        scans.append(
            {
                "Date": day.date(),
                "Accounts scanned": len(SCOUTS),
                "New follows found": rng.randint(0, 6),
                "Status": "OK" if rng.random() > 0.1 else "Retry needed",
            }
        )
    scan_history = pd.DataFrame(scans)
    return follows, hot, scan_history


follows, hot, scan_history = make_data()

# ----------------------------------------------------------------------------
# Layout
# ----------------------------------------------------------------------------
with st.sidebar:
    st.title("Follow Tracker")
    st.caption("Public demo with sample data")
    page = st.radio(
        "Page",
        ["New Follows", "Hot Artists", "Tracked Accounts", "Scan History", "About"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("Source code: github.com/oliviatak-dartmouth/instagram-follow-tracker")

st.info(
    "This is a demo. All accounts and numbers below are made up. "
    "The real tool connects to Instagram through Apify and writes to Google Sheets."
)

if page == "New Follows":
    st.header("New Follows")
    c1, c2, c3 = st.columns(3)
    c1.metric("New follows (last 21 days)", len(follows))
    c2.metric("Scouts tracked", len(SCOUTS))
    c3.metric("Unique artists", follows["Followed"].nunique())

    scout_filter = st.multiselect("Filter by scout", SCOUTS, default=SCOUTS)
    genre_filter = st.multiselect("Filter by genre", sorted({a[2] for a in ARTISTS}))
    view = follows[follows["Scout"].isin(scout_filter)]
    if genre_filter:
        view = view[view["Genre"].isin(genre_filter)]
    st.dataframe(
        view.assign(Timestamp=view["Timestamp"].dt.strftime("%Y-%m-%d %H:%M")),
        width="stretch",
        hide_index=True,
    )

elif page == "Hot Artists":
    st.header("Hot Artists")
    st.write(
        "Artists followed by two or more tracked scouts. Several scouts following "
        "the same artist is a stronger signal than a single follow."
    )
    st.dataframe(hot, width="stretch", hide_index=True)
    st.bar_chart(hot.set_index("Name")["Scouts"])

elif page == "Tracked Accounts":
    st.header("Tracked Accounts")
    counts = follows.groupby("Scout").size().reindex(SCOUTS, fill_value=0)
    st.bar_chart(counts)
    for scout in SCOUTS:
        with st.expander(f"@{scout}"):
            sub = follows[follows["Scout"] == scout][["Timestamp", "Followed", "Genre", "Followers"]]
            st.dataframe(
                sub.assign(Timestamp=sub["Timestamp"].dt.strftime("%Y-%m-%d")),
                width="stretch",
                hide_index=True,
            )

elif page == "Scan History":
    st.header("Scan History")
    st.dataframe(scan_history, width="stretch", hide_index=True)
    st.line_chart(scan_history.set_index("Date")["New follows found"])
    st.button("Run scan (disabled in demo)", disabled=True)

else:
    st.header("About")
    st.markdown(
        """
**What it does**

- Takes a list of Instagram accounts to monitor.
- Scrapes each account's following list on a schedule using an Apify actor.
- Compares each new snapshot with the last one to detect new follows.
- Cross-references accounts to find artists that several tracked profiles follow.
- Stores results in Google Sheets so a team can read them without touching code.

**Stack:** Python, Streamlit, Apify, Google Sheets API (gspread), pandas.

This page is a public demo. It runs on synthetic data and has no access to
Instagram or any private data.
        """
    )
