# Snoopfinder Setup

Track who A&R accounts are following to detect new artist scouting.

## How It Works

1. You provide a list of A&R Instagram usernames to monitor
2. You manually export each A&R's "Following" list as a CSV
3. The system compares new exports to previous snapshots
4. It detects NEW accounts the A&R started following
5. Results are stored in Google Sheets with a summary of all new follows

**Example output:**
```
** 3 NEW FOLLOWS DETECTED **
Potential artists being scouted:
  @label_ar -> @rising_artist_1
  @label_ar -> @new_producer_xyz
  @other_label_ar -> @indie_band_2024
```

---

## 1. Install Python Dependencies

```bash
cd snoopfinder
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 2. Set Up Google Sheets API

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Select a project" → "New Project"
3. Name it "Snoopfinder"
4. Click "Create"

### Step 2: Enable the Google Sheets API

1. In your project, go to "APIs & Services" → "Library"
2. Search for "Google Sheets API"
3. Click on it and click "Enable"

### Step 3: Create OAuth 2.0 Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. If prompted, configure the OAuth consent screen:
   - Choose "External" (unless you have Google Workspace)
   - Fill in App name: "Snoopfinder"
   - Add your email as User support email and Developer contact
   - Click "Save and Continue" through the remaining steps
   - Under "Test users", add your Google email
4. Back at Credentials, click "Create Credentials" → "OAuth client ID"
5. Choose "Desktop app" as application type
6. Name it "AR Tracker Desktop"
7. Click "Create"
8. Click "Download JSON"
9. Save the file as `credentials/google_credentials.json` in your project

### Step 4: First Run Authentication

```bash
python run.py setup
```

This will:
1. Open your browser for Google authentication
2. Ask you to authorize the app
3. Create a new Google Sheet with tabs for each A&R account
4. Create a "New Follows" summary sheet

After setup, add the spreadsheet ID to your `.env` file:
```
GOOGLE_SPREADSHEET_ID=your_spreadsheet_id_here
```

---

## 3. Configure A&R Accounts to Monitor

Edit `config.yaml` and add the Instagram usernames of A&R accounts you want to track:

```yaml
ar_accounts:
  - "label_ar"
  - "third_label_ar"
  - "other_label_ar"
  - "some_ar_person"
```

These are the accounts whose "Following" lists you'll export and monitor.

---

## 4. How to Export an A&R's "Following" List

Since you need the list of accounts an A&R is **following** (not their followers), here are your options:

### Option A: Browser Extension (Recommended)

Several browser extensions can export Instagram following lists:

1. **IG Export** (Chrome)
   - Install from Chrome Web Store
   - Go to the A&R's profile (e.g., instagram.com/label_ar)
   - Click on their "Following" count
   - Click the extension icon → Export Following
   - Save as CSV

2. **Inssist** (Chrome)
   - Install from Chrome Web Store
   - Navigate to the A&R profile
   - Open "Following" list
   - Use export feature

3. **Export for Instagram** (Chrome/Firefox)
   - Similar workflow to above

### Option B: Manual Scroll + Copy Method

1. Go to the A&R account's profile on Instagram (web)
2. Click on "Following" (not Followers!)
3. Scroll through the entire list to load all accounts
4. Use browser dev tools or copy usernames manually
5. Paste into a spreadsheet
6. Export as CSV with a `username` column

### Option C: Third-Party Tools

- **Phantombuster** - Has Instagram Following Export actor
- **IGExport.io** - Web-based export tool
- **Inflact** - Following list export feature

### Saving Your Export

Save CSV files to `data/exports/` with this naming convention:
```
{ar_username}_following.csv
```

Examples:
```
data/exports/label_ar_following.csv
data/exports/third_label_ar_following.csv
data/exports/other_label_ar_following_20240115.csv  (with date)
```

### CSV Format

Your CSV just needs a `username` column with the accounts they follow:

```csv
username
artist_one
producer_two
songwriter_three
another_artist
```

Optional columns (if your export tool provides them):
```csv
username,full_name
artist_one,Artist One Official
producer_two,John Producer
```

The script auto-detects column names and cleans up @ symbols.

---

## 5. Running the Tracker

### Initial Setup (one time)
```bash
python run.py setup
```

### Track All Configured A&R Accounts
```bash
python run.py track
```

### Track a Specific A&R Account
```bash
python run.py track label_ar
# or with @
python run.py track @third_label_ar
```

### Typical Workflow

1. Export Following lists for each A&R (weekly/bi-weekly)
2. Save CSVs to `data/exports/`
3. Run `python run.py track`
4. Check terminal output for new follows
5. View Google Sheet "New Follows" tab for full history

---

## 6. Understanding the Output

### Terminal Output
```
============================================================
Tracking A&R: @label_ar
============================================================
Currently following: 1,247 accounts
Previously tracked: 1,244 accounts

** 3 NEW FOLLOWS DETECTED **
Potential artists being scouted:
  + @rising_artist_1 (Rising Artist)
  + @new_producer_xyz
  + @indie_band_2024 (Indie Band)
```

### Google Sheets Structure

**Per-A&R tabs** (e.g., "label_ar"):
| Account Followed | Full Name | Profile URL | First Seen | Last Seen | Status |
|-----------------|-----------|-------------|------------|-----------|--------|
| rising_artist_1 | Rising Artist | instagram.com/... | 2024-01-15 | 2024-01-15 | active |

**"New Follows" summary tab:**
| Date Detected | A&R Account | New Follow | Full Name | Profile URL |
|--------------|-------------|------------|-----------|-------------|
| 2024-01-15 | label_ar | rising_artist_1 | Rising Artist | instagram.com/... |
| 2024-01-15 | label_ar | new_producer_xyz | | instagram.com/... |

---

## 7. Switching to Apify (Future Automation)

When you're ready to automate data collection:

1. Sign up at [Apify.com](https://apify.com)
2. Get your API token from Settings → Integrations
3. Add to `.env`:
   ```
   APIFY_API_TOKEN=your_token_here
   ```
4. Change `data_source` in `config.yaml`:
   ```yaml
   data_source: "apify"
   ```

The Apify integration will automatically fetch Following lists without manual exports.

---

## Project Structure

```
snoopfinder/
├── config.yaml           # A&R accounts list + settings
├── requirements.txt      # Python dependencies
├── run.py               # CLI entry point
├── SETUP.md             # This file
├── .env                 # Your secrets (create from .env.example)
├── .gitignore
├── credentials/         # Google API credentials
│   ├── google_credentials.json
│   └── token.json
├── data/
│   └── exports/         # Put your Following CSV exports here
└── src/
    ├── data_sources.py  # CSV + Apify data sources
    ├── sheets_manager.py # Google Sheets integration
    └── tracker.py       # Main tracking logic
```

---

## Troubleshooting

### "No CSV file found for A&R account"
- Check file is in `data/exports/`
- Check filename matches: `{username}_following.csv`
- Username in filename should match config.yaml (without @)

### "Credentials file not found"
Download OAuth JSON from Google Cloud Console and save to `credentials/google_credentials.json`

### "Access blocked" during Google auth
Add your email as a test user in Google Cloud Console → OAuth consent screen

### First run shows all accounts as "new"
This is expected! The first run establishes the baseline. Subsequent runs will only show actual new follows.

### Token expired
Delete `credentials/token.json` and run setup again.
