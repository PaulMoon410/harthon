# Python App on Render

A simple Flask application ready to deploy on Render with a live dashboard.

## Features

- Flask web framework
- Health check endpoint
- Status endpoint
- Live dashboard with real-time status polling
- Interactive Python console and session API
- Production-ready with Gunicorn

## Endpoints

- `GET /` - Redirect to the Python console
- `GET /health` - Health check
- `GET /api/status` - App status (JSON)
- `GET /dashboard` - Live terminal-style dashboard (HTML)
- `GET /console` - Interactive Python console (HTML)
- `POST /api/sessions` - Start a Python session
- `POST /api/sessions/<session_id>/execute` - Execute Python in a session
- `DELETE /api/sessions/<session_id>` - Close a session

## Interactive Python

Set `PYTHON_API_KEY` to a long, random ASCII secret of at least 32 characters
in Render's Environment settings. For example, generate one locally with
`python3 -c 'import secrets; print(secrets.token_urlsafe(32))'` and enter it
directly in Render. Do not commit or share the key. If the key is missing or
too short, the execution API refuses requests.

Open `/console`, enter the key, and start a session. For an API client, send the
key in the `Authorization: Bearer <key>` header:

1. `POST /api/sessions` returns `{"session_id": "..."}`.
2. `POST /api/sessions/<session_id>/execute` with JSON
   `{"code": "x = 2\nx + 3"}` returns `{"ok": true, "output": "5\n"}`.
   Python exceptions return `ok: false` and a traceback in `output`.
3. `DELETE /api/sessions/<session_id>` closes the session.

Commands share variables within a session. Each request is limited to 20
seconds; a timeout terminates the session. Interactive `input()` is not
supported. At most 10 sessions can exist; sessions idle for 30 minutes are
expired on access or when creating a session. Sessions are held in memory and
are lost on a restart or redeploy. Run exactly one Gunicorn worker and one
Render instance: sessions are not shared across workers or instances.

**Security:** Python code runs with the service's privileges, including access
to its environment variables, files, network, and API key. This is not a
sandbox. Give the key only to fully trusted clients; all key holders share the
same level of access. Use HTTPS and rotate the key if exposed. Do not use this
service for untrusted code.

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
export FLASK_APP=app.py
flask run
```

Set `PYTHON_API_KEY` in your local shell before starting the app to use the
console and API.

## Deploy to Render

1. Push this repository to GitHub
2. Go to [render.com](https://render.com)
3. Click "New" → "Web Service"
4. Connect your GitHub repository
5. Render will automatically detect the app and deploy it

The `render.yaml` file configures the deployment with a free PostgreSQL database.

## Live Dashboard

Visit `/dashboard` on your deployed URL to see a live updating terminal-style display that polls `/api/status` every 2 seconds.