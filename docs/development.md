# Development

## Prerequisites

- Python 3.9+
- Groq API key(s)
- Playwright (for screenshot generation only)

## Setup

```bash
# Clone the repository
git clone <repo-url>
cd country-guide-reconciliation

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Groq API key(s) and optional Slack webhook URL

# Initialize database and start
python app.py
```

The app runs at `http://localhost:8080`.

## Seeding Data

To import the baseline employment guide from Notion:

```bash
python notion_import.py
```

This is a one-time operation. Subsequent updates come through the sync pipeline.

## Running Tests

```bash
python -m pytest tests/
```

## Updating Documentation Screenshots

Screenshots are captured automatically with Playwright:

```bash
python docs/capture_screenshots.py
```

This starts the Flask app, navigates to each key page, and saves screenshots to `docs/assets/screenshots/`. Run this after any UI changes.

## Building Docs

```bash
# Local preview
mkdocs serve

# Deploy to GitHub Pages
mkdocs gh-deploy
```

## Project Configuration

| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` | Groq API key (comma-separated for multi-key rotation) |
| `SLACK_WEBHOOK_URL` | Optional Slack webhook for sync alerts |
| `DATABASE_PATH` | SQLite database path (default: `country_guides.db`) |
