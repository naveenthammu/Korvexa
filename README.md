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
deploy/     PM2 process definition and deployment sudo policy
frontend/   React/Vite application
nginx/      Nginx site and logrotate configurations
```

## Requirements

- Python 3.13+
- Node.js 22+ and npm
- PostgreSQL 15+
- Nginx for production
- PM2 for the production API process

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
Application root: /home/pos/Korvexa
Frontend files:   /home/pos/Korvexa/frontend/dist
Backend listener: 127.0.0.1:8000
Public entrypoint: http://34.29.31.163
```

Only ports 22, 80, and later 443 should be public. PostgreSQL and port 8000
should remain private to the VM.

### 1. Prepare The Application Directory

```bash
sudo chown -R pos:pos /home/pos/Korvexa
sudo chmod 711 /home/pos
```

Upload the project contents to `/home/pos/Korvexa`. Exclude `.env`, `node_modules`,
`.venv`, `dist`, test caches, Python caches, logs, and editor files. Create the
production `.env` directly on the server and protect it:

```bash
cd /home/pos/Korvexa
cp .env.example .env
nano .env
chmod 600 .env
```

### 2. Create PostgreSQL

The setup script prompts for a database-role password and does not store it:

```bash
sudo -u postgres psql -f /home/pos/Korvexa/database/setup.sql
```

Set the same URL-encoded password in `DATABASE_URL`.

### 3. Install And Migrate The Backend

```bash
curl -LsSf https://astral.sh/uv/0.11.30/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.13

cd /home/pos/Korvexa/backend
uv venv --clear --seed --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m alembic upgrade head
```

For a new or intentionally cleared installation only, create the baseline menu,
tables, roles, and super administrator:

```bash
cd /home/pos/Korvexa/backend
.venv/bin/python -m scripts.reset_production_data \
  --confirm RESET-KORVEXA-PRODUCTION-DATA \
  --email admin@korvexa.com \
  --password 'REPLACE_WITH_A_STRONG_TEMPORARY_PASSWORD'
```

This reset command deletes all application data. Do not run it during a normal
update. Change the administrator password immediately after first login.

### 4. Build The Frontend On The Server

The production build reads `VITE_*` values from `/home/pos/Korvexa/.env`:

```bash
export NVM_DIR="$HOME/.nvm"
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.6/install.sh | bash
. "$NVM_DIR/nvm.sh"
nvm install 22
nvm alias default 22

cd /home/pos/Korvexa/frontend
npm ci
npm run build
```

### 5. Configure PM2

```bash
npm install --global pm2
pm2 startOrReload /home/pos/Korvexa/deploy/ecosystem.config.cjs --update-env
pm2 save --force
sudo env PATH="$PATH" pm2 startup systemd -u pos --hp /home/pos
```

Run the final command printed by `pm2 startup`, then run `pm2 save --force`
again. The API runs as `pos`, binds only to localhost, and restarts after a
process failure or server reboot.

Configure bounded PM2 logs once:

```bash
pm2 install pm2-logrotate
pm2 set pm2-logrotate:max_size 20M
pm2 set pm2-logrotate:retain 14
pm2 set pm2-logrotate:compress true
pm2 save --force
```

### 6. Install Nginx And Log Rotation

```bash
sudo cp /home/pos/Korvexa/nginx/nginx.conf /etc/nginx/sites-available/korvexa
sudo ln -sfn /etc/nginx/sites-available/korvexa /etc/nginx/sites-enabled/korvexa
sudo rm -f /etc/nginx/sites-enabled/default
sudo cp /home/pos/Korvexa/nginx/korvexa.logrotate /etc/logrotate.d/korvexa-nginx
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl reload nginx
```

Nginx preserves the complete `/api/v1/...` path, serves frontend deep links
through `index.html`, and rotates application access/error logs for 14 days.

## GitHub Actions Deployment

The workflow at `.github/workflows/deploy-production.yml` verifies every pull
request and push to `main`. Production deployment runs only when the repository
variable `DEPLOY_ENABLED` is exactly `true`. It does not use a server password.

Create a GitHub Environment named `production` with these variables:

```text
SSH_HOST=34.29.31.163
SSH_PORT=22
SSH_USER=pos
APP_DIR=/home/pos/Korvexa
PUBLIC_URL=http://34.29.31.163
```

Add these encrypted environment secrets:

```text
SSH_PRIVATE_KEY       Dedicated Ed25519 private key for the pos account
SSH_KNOWN_HOSTS       Trusted SSH host-key line for 34.29.31.163
PRODUCTION_ENV_FILE   Complete multiline production .env content
```

Verify the server host-key fingerprint before saving `SSH_KNOWN_HOSTS`:

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Install the limited workflow permissions once on the server:

```bash
sudo install -o root -g root -m 0440 \
  /home/pos/Korvexa/deploy/korvexa-deploy.sudoers \
  /etc/sudoers.d/korvexa-deploy
sudo visudo -cf /etc/sudoers.d/korvexa-deploy
```

The policy permits only Nginx validation and reload. PM2 runs as `pos` and does
not need sudo. The policy does not grant arbitrary passwordless sudo access.

Start automatic deployment by setting the repository Actions variable:

```text
DEPLOY_ENABLED=true
```

Then use **Actions > Verify and deploy production > Run workflow**, or push a
commit to `main`. The workflow synchronizes source while preserving `.env`,
virtual environments, dependencies, and build output; uploads the protected
environment file; applies Alembic migrations; builds the frontend; reloads the
API through PM2; reloads Nginx; and verifies private and public readiness
endpoints.

## Updating The Server

1. Back up PostgreSQL.
2. Upload the new source while preserving `/home/pos/Korvexa/.env`.
3. Install changed dependencies.
4. Build the frontend.
5. Apply migrations before restarting the API.
6. Validate Nginx and reload it only when its configuration changed.

```bash
sudo -u postgres pg_dump -Fc korvexa > /var/backups/korvexa-$(date +%F-%H%M).dump

cd /home/pos/Korvexa/backend
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m alembic upgrade head

cd /home/pos/Korvexa/frontend
npm ci
npm run build

pm2 startOrReload /home/pos/Korvexa/deploy/ecosystem.config.cjs --update-env
pm2 save --force
sudo nginx -t && sudo systemctl reload nginx
```

Never run the reset command as part of an update.

## Cleanup And Logs

Generated files are excluded by `.gitignore` and should not be uploaded. After
an update, old caches can be removed without touching source or database data:

```bash
sudo find /home/pos/Korvexa -type d \
  \( -name __pycache__ -o -name .pytest_cache -o -name test-results -o -name playwright-report \) \
  -prune -exec rm -rf {} +
sudo find /home/pos/Korvexa -type f \
  \( -name '*.pyc' -o -name '*.log' -o -name '*.tmp' -o -name '*.tsbuildinfo' \) \
  -delete
sudo journalctl --vacuum-time=14d
sudo logrotate /etc/logrotate.d/korvexa-nginx
```

Do not delete the current Nginx or API logs while diagnosing a deployment.
Inspect them with:

```bash
pm2 logs korvexa-api --lines 200 --nostream
sudo tail -n 200 /var/log/nginx/korvexa.error.log
```

## Verification

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://34.29.31.163/api/v1/ready
curl -I http://34.29.31.163/
pm2 status
```

Then sign in, verify Menu is populated, place a temporary order, accept it in
KDS, move it through preparation to served, and remove the temporary order.

Automated checks:

```bash
cd /home/pos/Korvexa/backend
.venv/bin/python -m pytest -q

cd /home/pos/Korvexa/frontend
npm test -- --run
npx tsc --noEmit
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
