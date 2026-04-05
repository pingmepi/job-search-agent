# Google OAuth Setup (Drive + Calendar)

How to set up Google Drive and Calendar integration for the job search agent.

## Prerequisites

- Google account
- Google Cloud Console access

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Note the project name

## Step 2: Enable APIs

In the Google Cloud Console:

1. Go to **APIs & Services > Library**
2. Search for and enable:
   - **Google Drive API**
   - **Google Calendar API**

## Step 3: Create OAuth Credentials

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth client ID**
3. If prompted, configure the OAuth consent screen:
   - User Type: **External** (or Internal if using Google Workspace)
   - App name: `Job Search Agent`
   - Add your email as a test user
4. Application type: **Desktop app**
5. Name: `Job Search Agent Desktop`
6. Click **Create**
7. Download the JSON file

## Step 4: Place Credentials File

```bash
# From the project root
mkdir -p credentials
# Move the downloaded JSON file
mv ~/Downloads/client_secret_*.json credentials/google_oauth.json
```

## Step 5: Authenticate Locally

This step requires a browser — it must be done on your local machine, not on Railway.

```bash
python main.py auth-google
```

This will:
1. Open your browser for Google authorization (Drive + Calendar scopes in one prompt)
2. Save the token to `credentials/google_token.pickle`

## Step 6: Deploy to Railway

Railway containers are stateless — the pickle file doesn't persist across deploys. Use a base64-encoded env var instead.

### Encode the token

```bash
# On macOS/Linux
base64 < credentials/google_token.pickle | tr -d '\n'
```

### Set Railway env vars

In your Railway project settings, add:

| Variable | Value |
|----------|-------|
| `GOOGLE_CREDENTIALS_PATH` | `credentials/google_oauth.json` |
| `GOOGLE_TOKEN_B64` | *(paste base64 token)* |
| `TELEGRAM_ENABLE_DRIVE_UPLOAD` | `true` |
| `TELEGRAM_ENABLE_CALENDAR_EVENTS` | `true` |

The app will automatically decode the base64 token to a pickle file on startup.

## Step 7: Verify

Send a job description to the Telegram bot. After processing, check:
- **Google Drive**: Look for `Jobs/{Company}/{Role}/` folder with resume PDF
- **Google Calendar**: Look for "Applied: ..." and "Follow-up: ..." events

## Token Refresh

Tokens auto-refresh using the embedded refresh token. If refresh fails (e.g., token revoked):

1. Re-run `python main.py auth-google` locally
2. Re-encode and update `GOOGLE_TOKEN_B64` in Railway

## Troubleshooting

**"Google credentials not found"**
- Ensure `credentials/google_oauth.json` exists (local) or `GOOGLE_CREDENTIALS_PATH` is set (Railway)

**"No valid token ... interactive mode is disabled"**
- Token expired and can't auto-refresh. Re-run `python main.py auth-google` locally and redeploy tokens.

**"Token expired and refresh failed"**
- The refresh token was revoked. Re-authenticate with `python main.py auth-google`.

**Pipeline completes but Drive/Calendar steps show errors**
- Check the `pack.errors` in the Telegram response for specific Google API error messages.
- Transient errors (429, 500, 503) are retried 3 times automatically.
