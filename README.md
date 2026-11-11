# Snoopfinder

**Competitive intelligence for music A&R.** Snoopfinder watches which Instagram accounts rival label scouts (A&Rs) start following, flags every new follow, and surfaces the artists that several scouts are circling at once. I built it during a summer internship in the music industry to see which up-and-coming artists competing labels were interested in.

**Stack:** Python, Streamlit, Apify (Instagram scraping), Google Sheets API (gspread), pandas, PyYAML

## What it does

- **Scrapes the "following" list** of each tracked account through an Apify actor, then stores a snapshot.
- **Detects new follows** by comparing each fresh snapshot with the previous one.
- **Finds "hot artists":** accounts followed by two or more tracked profiles, which is a stronger signal than a single follow.
- **Writes results to Google Sheets**, one tab per tracked account plus summary tabs, so a team can read them without touching code.
- **Streamlit dashboard** with pages for New Follows, Hot Artists, Scan History, Scan Log and Settings, including a cookie-health check and a way to add accounts and run scans from the UI.
- **Command-line interface** for scheduled or scripted runs.

## Project layout

```
app.py                 Streamlit dashboard
run.py                 CLI entry point (add, detect, sync, hotartists, restore)
src/
  tracker.py           Core detection logic (snapshot diffing)
  data_sources.py      Apify and CSV data sources
  sheets_manager.py    Google Sheets read/write layer
  config_manager.py    Config, secrets and cookie validation
config.example.yaml    Template config (copy to config.yaml)
.env.example           Template environment file
```

## Setup

```bash
git clone https://github.com/<your-username>/snoopfinder.git
cd snoopfinder
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp config.example.yaml config.yaml
cp .env.example .env
```

Then:

1. Put your Apify token in `.env` as `APIFY_API_TOKEN`.
2. Create Google Sheets API credentials and save them to `credentials/` (step-by-step in [SETUP.md](SETUP.md)).
3. Add the Instagram usernames you want to monitor under `ar_accounts` in `config.yaml`.
4. Add session cookies for a dedicated burner Instagram account (never your personal one) on the app's Settings page.

## Usage

```bash
python3 run.py add <username>            # add an account and take a baseline snapshot
python3 run.py detect                    # detect new follows for all accounts
python3 run.py detect <u1> <u2>          # detect for specific accounts
python3 run.py hotartists                # refresh the cross-reference sheet
streamlit run app.py                     # launch the dashboard
```

To deploy the dashboard on Streamlit Community Cloud, see [DEPLOY.md](DEPLOY.md).

## Security notes

- `config.yaml`, `.env` and `credentials/` are gitignored. Keep real tokens and cookies out of version control.
- Use a throwaway Instagram account for scraping, and respect Instagram's terms of service and applicable privacy laws. Only monitor public information.
- This repository ships no real data. Example usernames are placeholders.
