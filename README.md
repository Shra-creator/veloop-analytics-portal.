# VELOOP Analytics Portal

A Flask-based analytics dashboard for exploring the supplied **simulated** VELOOP user-profile dataset. This version adds database-backed user registration, login, and logout.

## Features
- Account registration with unique username and email
- Login using username or email
- Passwords stored as secure password hashes, never as plain text
- CSRF protection for forms and POST actions
- Login-protected dashboard, analytics pages, API summary, uploads, and CSV export
- Per-account CSV/Excel uploads for analysis (uploads are stored on the app filesystem; see persistence note below)
- Overview dashboard, charts, searchable user explorer, data-quality checks, KPI catalogue, insights, and action backlog
- Health endpoint at `/health`

## Important data disclaimer
The included dataset is fictional/simulated and is for analytical testing only. It is **not actual VELOOP user or business performance**. Reward earnings, wallet movements, withdrawal outcomes, referral conversions, and retention cannot be calculated reliably without verified event and transaction datasets. Do not describe simulated figures as real company statistics.

## Run locally on Windows
1. Extract this project folder.
2. Open PowerShell in the project folder.
3. Create a virtual environment: `py -m venv .venv`
4. Activate it: `.venv\\Scripts\\Activate.ps1`
5. Install dependencies: `pip install -r requirements.txt`
6. Run: `python app.py`
7. Open `http://127.0.0.1:5000/register` and create your account.

For local use, the app creates `data/velop_auth.db` automatically. The local fallback secret key is for development only; set a private `SECRET_KEY` environment variable if using the app beyond local testing.

## Deploy on Render with persistent accounts
**Important:** For persistent user accounts across redeploys/restarts, connect the web service to a PostgreSQL database. The SQLite fallback is suitable for local development and may be lost on an ephemeral hosting filesystem.

1. Push the updated project files to your GitHub repository.
2. In Render, create a PostgreSQL database (if your account/plan offers it) and keep it in the same region as the web service.
3. Open the database details and copy its **Internal Database URL**.
4. Open the `velop-analytics-portal` web service → **Environment**.
5. Add `DATABASE_URL` with the PostgreSQL Internal Database URL as its value. Keep it private; never commit it to GitHub.
6. Confirm `SECRET_KEY` exists as a private environment variable. Use a long, random value; do not share it.
7. Save changes and redeploy the web service.
8. Open `/register` on the live URL, create an account, log out, and log back in to verify it works.

Build command: `pip install -r requirements.txt`

Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`

Health check path: `/health`

## Routes
- `/register` — create an account
- `/login` — log in
- `/logout` — log out (POST action)
- `/` — overview dashboard (login required)
- `/users` — user explorer (login required)
- `/quality` — data quality audit (login required)
- `/kpis` — KPI catalogue (login required)
- `/insights` — insights and data gaps (login required)
- `/backlog` — proposed implementation backlog (login required)
- `/upload` — upload CSV/Excel for analysis (login required)
- `/download` — export current dataset (login required)
- `/api/summary` — summary JSON (login required)
- `/health` — public service health check

## Upload persistence limitation
Uploaded CSV/Excel files are separated by account, but currently stored on the web service's filesystem. On Render's ephemeral filesystem, uploaded datasets can be lost after a restart or redeploy. PostgreSQL persists user accounts; it does **not** automatically persist uploaded files. Durable uploaded-file storage would require a persistent disk or object storage, which is a separate addition.

## Security notes
- Use HTTPS in production.
- Keep `SECRET_KEY` and `DATABASE_URL` private.
- Do not upload confidential company or personal data without permission.
- This is a portfolio/demo analytics portal, not a production VELOOP system.
