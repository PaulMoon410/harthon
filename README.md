# Python App on Render

A simple Flask application ready to deploy on Render.

## Features

- Flask web framework
- Health check endpoint
- Status endpoint
- Production-ready with Gunicorn

## Endpoints

- `GET /` - Welcome message
- `GET /health` - Health check
- `GET /api/status` - App status

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
export FLASK_APP=app.py
flask run
```

## Deploy to Render

1. Push this repository to GitHub
2. Go to [render.com](https://render.com)
3. Click "New" → "Web Service"
4. Connect your GitHub repository
5. Render will automatically detect the app and deploy it

The `render.yaml` file configures the deployment with a free PostgreSQL database.