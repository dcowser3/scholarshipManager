# Email Demo Troubleshooting

This note captures the local runbook learnings from bringing up the email demo flow.

## What You Actually Need

The frontend is not required to test the email demo workflow.

For email-only testing, start:

- PostgreSQL
- the backend API
- the backend `.env` with the email demo settings

Recommended local flow:

```bash
cd "/Users/deriancowser/Documents/New project"
docker compose up db
```

Then in another shell:

```bash
cd "/Users/deriancowser/Documents/New project/backend"
uv sync
uv run alembic upgrade head
uv run python -m app.scripts.seed
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level debug
```

## Expected Backend Behavior

`uvicorn` should stay in the foreground. It is not supposed to return to the shell prompt while the server is running.

A healthy startup eventually prints logs similar to:

- `Started server process`
- `Waiting for application startup`
- `Application startup complete`
- `Uvicorn running on http://127.0.0.1:8000`

Use this health check to confirm the API is up:

- [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

Expected response:

```json
{"status":"ok"}
```

## Config Needed For The Email Demo

The backend poller starts only when `EMAIL_POLL_ENABLED=true`.

At minimum, `backend/.env` needs values like:

```ini
EMAIL_POLL_ENABLED=true
EMAIL_POLL_INTERVAL_SECONDS=10
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_USER=<demo gmail address>
EMAIL_IMAP_PASSWORD=<gmail app password>
EMAIL_ALLOWED_SENDERS=<comma-separated allowed senders>
EMAIL_SENDER_SPORTS={"coach@school.edu":"Baseball"}
EMAIL_DEMO_RECIPIENT=<recipient email>
EMAIL_FROM_ADDRESS=<demo gmail address>
OPENAI_API_KEY=<openai api key>
```

## Known Gotchas

- `docker compose up frontend` is unnecessary if you only want to verify the email flow.
- Running the backend locally is the most reliable path for the demo because the app reads `backend/.env` directly.
- `--reload` can make troubleshooting noisier because the reloader process and child process behave differently. Start without `--reload` first when diagnosing startup issues.
- Startup may take several seconds because the app imports the document-generation stack used later for attachment creation.

## If Uvicorn Looks Stuck

If `uv run uvicorn ...` appears to do nothing:

1. Wait a few seconds. The process may still be importing dependencies.
2. Check whether the server is actually listening with the health check URL above.
3. Prefer running without `--reload` during debugging.
4. If imports are behaving strangely, rebuild the virtual environment:

```bash
cd "/Users/deriancowser/Documents/New project/backend"
rm -rf .venv
uv sync
find app -type d -name '__pycache__' -prune -exec rm -rf {} +
```

This cleared bad local import state during troubleshooting and allowed the backend to start normally again.

## Quick Email Demo Verification

Once the health check works:

1. Send an email from an address listed in `EMAIL_ALLOWED_SENDERS`.
2. Wait about one poll interval for the confirmation email.
3. Reply `YES`.
4. Confirm the generated attachments arrive at `EMAIL_DEMO_RECIPIENT`.
