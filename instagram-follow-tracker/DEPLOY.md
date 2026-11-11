# Deploying the A&R Tracker to Streamlit Cloud

This guide walks you through deploying the app so your whole team can use it from a browser link.

## Step 1: Push to GitHub (Private Repo)

```bash
# Initialize git if not already done
git init
git add -A
git commit -m "Initial commit"

# Create a private repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/instagram-follow-tracker.git
git branch -M main
git push -u origin main
```

Make sure the repo is **private** (it contains config files).

## Step 2: Create a Streamlit Cloud Account

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with your GitHub account
3. Click **"New app"**
4. Select your repo, branch `main`, and file `app.py`

## Step 3: Add Secrets

In the Streamlit Cloud dashboard, go to your app → **Settings** → **Secrets**.

Paste the following (fill in your actual values):

```toml
GOOGLE_SPREADSHEET_ID = "1Ewlz1oxpnzUi578q6SNsxlIJJ9QFiTFsmPtIniN1b1o"
APIFY_API_TOKEN = "YOUR_APIFY_TOKEN"

[google_credentials]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "...@...iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."
```

To get the `[google_credentials]` values: open your `credentials/google_credentials.json` file and copy each field into the TOML format above.

## Step 4: Deploy

Click **"Deploy"**. Your app will be live at a URL like:
```
https://your-app-name.streamlit.app
```

Share this link with your team. That's it — they just open the link in a browser.

## How Cookies Work on the Cloud

- Cookies are stored in the Google Sheet (a hidden `_Config` tab) so they persist
- Any team member can update cookies via the **Cookie Settings** page
- No need to touch code, config files, or the Streamlit dashboard for cookie updates
- When cookies expire, anyone on the team can log into the Instagram tracking account in Chrome, copy cookies, and paste them in the app

## Maintenance

| Task | Who | How |
|------|-----|-----|
| Update expired cookies | Any team member | Cookie Settings page in the app |
| Add/remove A&R accounts | Any team member | Manage Accounts page in the app |
| Update Apify token | Admin only | Streamlit Cloud dashboard → Secrets |
| Update Google credentials | Admin only | Streamlit Cloud dashboard → Secrets |
