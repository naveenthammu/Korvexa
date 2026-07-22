# Korvexa POS

Korvexa POS is a restaurant operations application with a FastAPI backend,
PostgreSQL, a React/Vite frontend, and Nginx. SQLite is not supported and the
application never creates or alters database tables during startup.

## Application Areas

- POS billing, orders, receipts, discounts, tables, and QR ordering
- Kitchen Display System order lifecycle
- Menu, inventory, purchasing, staff, attendance, payroll, and reporting
- Tenant, branch, user, role, tax, and security administration
- Optional SMTP, Razorpay/RazorpayX, Swiggy, and Zomato integrations

## Project Layout

```text
backend/    FastAPI application, tests, and Alembic migrations
database/   PostgreSQL setup and reset documentation
deploy/     systemd service for the API
frontend/   React/Vite application
nginx/      Nginx site and logrotate configurations
```

## Requirements

- Python 3.13+
- Node.js 22+ and npm
- PostgreSQL 15+
- Nginx for production

## Environment

Copy `.env.example` to `.env` and replace every placeholder. Never upload the
local `.env` file or store production passwords in source control.

Required production values include:

```text
ENVIRONMENT=production
DATABASE_URL=postgresql://korvexa_app:STRONG_URL_ENCODED_PASSWORD@127.0.0.1:5432/korvexa
JWT_SECRET=AT_LEAST_64_RANDOM_CHARACTERS
VITE_API_BASE_URL=http://34.29.31.163
VITE_PUBLIC_APP_URL=http://34.29.31.163
CORS_ORIGINS=http://34.29.31.163
```

Generate a JWT secret on the server:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Vite exposes only variables prefixed with `VITE_`. Database, SMTP, payment,
and delivery-provider secrets remain backend-only.

## Local Development

Apply migrations, then run the existing development services:

```powershell
cd backend
python -m pip install -r requirements.txt
python -m alembic upgrade head
cd ..
```

```powershell
python -m uvicorn app.main:app --app-dir backend --reload
```

```powershell
cd frontend
npm install
npm run dev
```

Local URLs:

```text
Frontend:  http://localhost:5173
API:       http://localhost:8000
API docs:  http://localhost:8000/docs
Readiness: http://localhost:8000/api/v1/ready
```

## Production Server

The checked-in production configuration targets `34.29.31.163` and uses:

```text
Application root: /opt/korvexa
Frontend files:   /opt/korvexa/frontend/dist
Backend listener: 127.0.0.1:8000
Public entrypoint: http://34.29.31.163
```

Only ports 22, 80, and later 443 should be public. PostgreSQL and port 8000
should remain private to the VM.

### 1. Create The Service Account And Directory

```bash
sudo adduser --system --group --home /opt/korvexa korvexa
sudo mkdir -p /opt/korvexa
sudo chown -R korvexa:korvexa /opt/korvexa
sudo chmod 755 /opt/korvexa
```

Upload the project contents to `/opt/korvexa`. Exclude `.env`, `node_modules`,
`.venv`, `dist`, test caches, Python caches, logs, and editor files. Create the
production `.env` directly on the server and protect it:

```bash
cd /opt/korvexa
sudo -u korvexa cp .env.example .env
sudo -u korvexa nano .env
sudo chmod 600 .env
```

### 2. Create PostgreSQL

The setup script prompts for a database-role password and does not store it:

```bash
sudo -u postgres psql -f /opt/korvexa/database/setup.sql
```

Set the same URL-encoded password in `DATABASE_URL`.

### 3. Install And Migrate The Backend

```bash
cd /opt/korvexa/backend
sudo -u korvexa python3 -m venv .venv
sudo -u korvexa .venv/bin/python -m pip install --upgrade pip
sudo -u korvexa .venv/bin/python -m pip install -r requirements.txt
sudo -u korvexa .venv/bin/python -m alembic upgrade head
```

For a new or intentionally cleared installation only, create the baseline menu,
tables, roles, and super administrator:

```bash
cd /opt/korvexa/backend
sudo -u korvexa .venv/bin/python -m scripts.reset_production_data \
  --confirm RESET-KORVEXA-PRODUCTION-DATA \
  --email admin@korvexa.com \
  --password 'REPLACE_WITH_A_STRONG_TEMPORARY_PASSWORD'
```

This reset command deletes all application data. Do not run it during a normal
update. Change the administrator password immediately after first login.

### 4. Build The Frontend On The Server

The production build reads `VITE_*` values from `/opt/korvexa/.env`:

```bash
cd /opt/korvexa/frontend
sudo -u korvexa npm ci
sudo -u korvexa npm run build
```

### 5. Install The API Service

```bash
sudo cp /opt/korvexa/deploy/korvexa-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now korvexa-api
sudo systemctl status korvexa-api --no-pager
```

The API runs as the unprivileged `korvexa` user, binds only to localhost, and
restarts automatically after a process failure.

### 6. Install Nginx And Log Rotation

```bash
sudo cp /opt/korvexa/nginx/nginx.conf /etc/nginx/sites-available/korvexa
sudo ln -sfn /etc/nginx/sites-available/korvexa /etc/nginx/sites-enabled/korvexa
sudo rm -f /etc/nginx/sites-enabled/default
sudo cp /opt/korvexa/nginx/korvexa.logrotate /etc/logrotate.d/korvexa-nginx
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl reload nginx
```

Nginx preserves the complete `/api/v1/...` path, serves frontend deep links
through `index.html`, and rotates application access/error logs for 14 days.

## Updating The Server

1. Back up PostgreSQL.
2. Upload the new source while preserving `/opt/korvexa/.env`.
3. Install changed dependencies.
4. Build the frontend.
5. Apply migrations before restarting the API.
6. Validate Nginx and reload it only when its configuration changed.

```bash
sudo -u postgres pg_dump -Fc korvexa > /var/backups/korvexa-$(date +%F-%H%M).dump

cd /opt/korvexa/backend
sudo -u korvexa .venv/bin/python -m pip install -r requirements.txt
sudo -u korvexa .venv/bin/python -m alembic upgrade head

cd /opt/korvexa/frontend
sudo -u korvexa npm ci
sudo -u korvexa npm run build

sudo systemctl restart korvexa-api
sudo nginx -t && sudo systemctl reload nginx
```

Never run the reset command as part of an update.

## Cleanup And Logs

Generated files are excluded by `.gitignore` and should not be uploaded. After
an update, old caches can be removed without touching source or database data:

```bash
sudo find /opt/korvexa -type d \
  \( -name __pycache__ -o -name .pytest_cache -o -name test-results -o -name playwright-report \) \
  -prune -exec rm -rf {} +
sudo find /opt/korvexa -type f \
  \( -name '*.pyc' -o -name '*.log' -o -name '*.tmp' -o -name '*.tsbuildinfo' \) \
  -delete
sudo journalctl --vacuum-time=14d
sudo logrotate /etc/logrotate.d/korvexa-nginx
```

Do not delete the current Nginx or API logs while diagnosing a deployment.
Inspect them with:

```bash
sudo journalctl -u korvexa-api -n 200 --no-pager
sudo tail -n 200 /var/log/nginx/korvexa.error.log
```

## Verification

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://34.29.31.163/api/v1/ready
curl -I http://34.29.31.163/
```

Then sign in, verify Menu is populated, place a temporary order, accept it in
KDS, move it through preparation to served, and remove the temporary order.

Automated checks:

```bash
cd /opt/korvexa/backend
sudo -u korvexa .venv/bin/python -m pytest -q

cd /opt/korvexa/frontend
sudo -u korvexa npm test -- --run
sudo -u korvexa npx tsc --noEmit
```

Backend tests require a separate PostgreSQL schema whose name begins with
`korvexa_test`; they must never target the production schema.

## HTTPS And External Integrations

The IP configuration supports the core application over HTTP. Before public
production use, point a domain to `34.29.31.163`, enable a trusted TLS
certificate, and replace all public URLs and CORS origins with that HTTPS
domain. Password-reset email, Razorpay webhooks, RazorpayX, Swiggy, and Zomato
require public HTTPS URLs and real provider credentials. Keep those placeholders
unchanged until each provider has activated the account.

Provider secrets must exist only in the server `.env`; never place them in the
frontend, README, shell history, or deployment archive.
