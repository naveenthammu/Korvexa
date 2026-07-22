# Korvexa POS

Korvexa POS is a restaurant operations application built with FastAPI,
PostgreSQL, React/Vite, PM2, and Nginx. SQLite is not supported. Database schema
changes are managed only through Alembic migrations.

## Security First

Never commit or paste real credentials into this repository. In particular, do
not commit:

- `.env` or a production environment export
- SSH private keys or account passwords
- PostgreSQL passwords or connection strings containing real passwords
- JWT, SMTP, Razorpay, RazorpayX, Swiggy, or Zomato secrets
- GitHub personal access tokens
- the initial administrator password

The committed `.env.example` contains names and placeholders only. Production
values belong in the GitHub `production` Environment secrets and in the
protected `/home/pos/Korvexa/.env` file on the server. The `.env` file must have
mode `600` and be owned by `pos`.

If any real secret is accidentally committed, deleting it in a later commit is
not enough. Revoke or rotate the secret immediately, then remove it from Git
history.

## Application Areas

- POS billing, orders, receipts, discounts, tables, and QR ordering
- Kitchen Display System order lifecycle
- Menu, inventory, purchasing, staff, attendance, payroll, and reporting
- Tenant, branch, user, role, tax, and security administration
- Optional SMTP, Razorpay/RazorpayX, Swiggy, and Zomato integrations

## Project Layout

```text
.github/workflows/  Verification and production deployment workflow
backend/            FastAPI application, tests, and Alembic migrations
database/           PostgreSQL creation and reset documentation
deploy/             PM2 process definition and limited sudo policy
frontend/           React/Vite application
nginx/              Nginx site and logrotate configurations
```

## Current Production Profile

The checked-in deployment configuration currently targets:

```text
Server:             34.29.31.163
SSH user:           pos
Application root:   /home/pos/Korvexa
Frontend files:     /home/pos/Korvexa/frontend/dist
Backend listener:   127.0.0.1:8000
Public URL:         http://34.29.31.163
Database:           PostgreSQL 16, database korvexa, role korvexa_app
Runtime:            Python 3.13, Node.js 22, PM2
```

Public endpoints:

```text
Application: http://34.29.31.163/
Readiness:   http://34.29.31.163/api/v1/ready
```

Only ports `22`, `80`, and later `443` should be public. PostgreSQL port `5432`
and API port `8000` must not be exposed to the internet.

## Environment Configuration

The backend and Vite both read the root `.env` file. Vite exposes only names
prefixed with `VITE_`; all service credentials must remain backend-only.

### Core Production Values

These values are required:

```dotenv
ENVIRONMENT=production
DATABASE_URL=postgresql://korvexa_app:URL_ENCODED_DATABASE_PASSWORD@127.0.0.1:5432/korvexa
JWT_SECRET=REPLACE_WITH_AT_LEAST_64_RANDOM_CHARACTERS
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
DATABASE_POOL_RECYCLE_SECONDS=1800
VITE_API_BASE_URL=http://34.29.31.163
VITE_PUBLIC_APP_URL=http://34.29.31.163
CORS_ORIGINS=http://34.29.31.163
```

Generate a JWT secret without storing it in shell history:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

URL-encode a database password before placing it in `DATABASE_URL`:

```bash
python3 -c "from getpass import getpass; from urllib.parse import quote; print(quote(getpass('Database password: '), safe=''))"
```

`CORS_ORIGINS` is a comma-separated allowlist. Production rejects a wildcard
origin. After HTTPS is enabled, replace every public HTTP value with the final
HTTPS domain and rebuild the frontend.

### Where Credentials Come From

| Value | Source | Storage location |
| --- | --- | --- |
| Database role password | Generate during `database/setup.sql` setup | PostgreSQL and `PRODUCTION_ENV_FILE` |
| `JWT_SECRET` | Generate with the Python command above | `PRODUCTION_ENV_FILE` |
| SSH private key | Generate on a trusted administrator computer | GitHub `SSH_PRIVATE_KEY` secret |
| SSH public key | Generated beside the private key | Server `authorized_keys` |
| SSH host key | Read and independently verify from the server | GitHub `SSH_KNOWN_HOSTS` secret |
| Google SMTP App Password | Google Account security settings | `PRODUCTION_ENV_FILE` |
| Razorpay/RazorpayX keys | Provider dashboard after account activation | `PRODUCTION_ENV_FILE` |
| Swiggy/Zomato credentials | Provider POS partner onboarding team | `PRODUCTION_ENV_FILE` |

GitHub does not generate provider credentials. It stores encrypted copies used
during deployment. The server account password is not needed by the workflow.

### Password Reset Email

Add these only after the public HTTPS domain and mail account are ready:

```dotenv
FRONTEND_RESET_URL=https://pos.example.com/reset-password
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_TLS=true
SMTP_SSL=false
SMTP_USERNAME=notifications@example.com
SMTP_PASSWORD=REPLACE_WITH_PROVIDER_APP_PASSWORD
SMTP_FROM=Korvexa <notifications@example.com>
```

For Google SMTP, enable two-step verification on the Google account and create
an App Password. Use the App Password as `SMTP_PASSWORD`; do not use the normal
Google account password. Port `587` normally uses TLS with `SMTP_TLS=true` and
`SMTP_SSL=false`; port `465` normally uses SSL.

`EXPOSE_DEV_RESET_TOKEN=true` is test/development-only and must never be set in
production.

### Payment Integrations

Add live values only after the provider account and HTTPS webhook are active:

```dotenv
PUBLIC_API_BASE_URL=https://pos.example.com
RAZORPAY_KEY_ID=REPLACE_WITH_LIVE_KEY_ID
RAZORPAY_KEY_SECRET=REPLACE_WITH_LIVE_KEY_SECRET
RAZORPAY_WEBHOOK_SECRET=REPLACE_WITH_WEBHOOK_SECRET
RAZORPAYX_KEY_ID=REPLACE_WITH_RAZORPAYX_KEY_ID
RAZORPAYX_KEY_SECRET=REPLACE_WITH_RAZORPAYX_KEY_SECRET
RAZORPAYX_ACCOUNT_NUMBER=REPLACE_WITH_ACCOUNT_NUMBER
RAZORPAYX_WEBHOOK_SECRET=REPLACE_WITH_WEBHOOK_SECRET
```

Webhook paths are:

```text
Razorpay:  /api/v1/integrations/razorpay/webhook
RazorpayX: /api/v1/integrations/razorpayx/webhook
```

The backend also accepts the legacy secret names `RAZORPAY_SECRET` and
`RAZORPAYX_SECRET`, but the names in `.env.example` are preferred. Payment keys
must never use a `VITE_` prefix.

### Swiggy And Zomato Integrations

These values must come from approved partner onboarding. They cannot be
invented or obtained from a consumer restaurant account:

```dotenv
PUBLIC_API_BASE_URL=https://pos.example.com
ZOMATO_API_BASE_URL=https://PROVIDER_ASSIGNED_BASE_URL
ZOMATO_API_TOKEN=REPLACE_WITH_PARTNER_TOKEN
ZOMATO_AUTH_HEADER=Authorization
ZOMATO_AUTH_SCHEME=Bearer
ZOMATO_OUTLET_ID=REPLACE_WITH_OUTLET_ID
ZOMATO_WEBHOOK_SECRET=REPLACE_WITH_WEBHOOK_SECRET
ZOMATO_WEBHOOK_AUTH_HEADER=Authorization
ZOMATO_WEBHOOK_AUTH_SCHEME=Bearer
SWIGGY_API_BASE_URL=https://PROVIDER_ASSIGNED_BASE_URL
SWIGGY_API_TOKEN=REPLACE_WITH_PARTNER_TOKEN
SWIGGY_AUTH_HEADER=Authorization
SWIGGY_AUTH_SCHEME=Bearer
SWIGGY_OUTLET_ID=REPLACE_WITH_OUTLET_ID
SWIGGY_WEBHOOK_SECRET=REPLACE_WITH_WEBHOOK_SECRET
SWIGGY_WEBHOOK_AUTH_HEADER=Authorization
SWIGGY_WEBHOOK_AUTH_SCHEME=Bearer
```

Provider action paths are listed in `.env.example`. Change them only when the
provider's integration team supplies different paths.

```dotenv
ZOMATO_ACCEPTED_PATH=/online-ordering/v1/order/confirm
ZOMATO_REJECTED_PATH=/online-ordering/v1/order/reject
ZOMATO_READY_PATH=/online-ordering/v1/order/ready
ZOMATO_PICKED_UP_PATH=/online-ordering/v1/order/pickedup
ZOMATO_DELIVERED_PATH=/online-ordering/v1/order/delivered
SWIGGY_ACCEPTED_PATH=/orders/{external_order_id}/accept
SWIGGY_REJECTED_PATH=/orders/{external_order_id}/reject
SWIGGY_READY_PATH=/orders/{external_order_id}/ready
SWIGGY_PICKED_UP_PATH=/orders/{external_order_id}/picked-up
SWIGGY_DELIVERED_PATH=/orders/{external_order_id}/delivered
```

### Test-Only Values

Tests require an isolated PostgreSQL schema. Never point these values at the
production schema:

```dotenv
TEST_DATABASE_URL=postgresql://korvexa_test:TEST_PASSWORD@127.0.0.1:5432/korvexa_test
TEST_DATABASE_SCHEMA=korvexa_test
```

The test safety check accepts only schema names beginning with `korvexa_test`.
GitHub Actions automatically creates an isolated PostgreSQL 16 test service.

## Local Development

Requirements:

- Python 3.13+
- Node.js 22+
- PostgreSQL 15+

Create a local `.env` from the example, create the PostgreSQL database, and
apply migrations:

```powershell
Copy-Item .env.example .env
psql -U postgres -f database/setup.sql
Set-Location backend
python -m pip install -r requirements.txt
python -m alembic upgrade head
Set-Location ..
```

Start the API and frontend in separate terminals:

```powershell
python -m uvicorn app.main:app --app-dir backend --reload
```

```powershell
Set-Location frontend
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

## One-Time Server Setup

The following steps prepare a new Ubuntu 22.04 server. Run them from an SSH
session as `pos`; commands beginning with `sudo` require administrator access.

### 1. Install Operating-System Packages

```bash
sudo apt update
sudo apt install -y ca-certificates curl git nginx rsync postgresql-common
sudo systemctl enable --now nginx
```

Configure the cloud firewall and any host firewall to allow `22`, `80`, and
`443` only. Do not open `5432` or `8000` publicly.

### 2. Install PostgreSQL 16

Add the official PostgreSQL Apt repository and install the versioned packages.
Do not install the unversioned `postgresql` meta-package because it can move to
a newer major version unexpectedly.

```bash
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
sudo apt update
sudo apt install -y postgresql-16 postgresql-client-16
sudo systemctl enable --now postgresql
pg_lsclusters
```

If `pg_lsclusters` shows no PostgreSQL 16 cluster, create one once:

```bash
sudo pg_createcluster 16 main --port=5432 --start
```

Confirm that PostgreSQL listens locally, not on a public interface:

```bash
sudo -u postgres psql -c "SHOW listen_addresses;"
sudo ss -ltnp | grep 5432
```

### 3. Install Python 3.13 With uv

```bash
curl -LsSf https://astral.sh/uv/0.11.30/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.13
uv --version
uv run --python 3.13 python --version
```

### 4. Install Node.js 22 With NVM

```bash
export NVM_DIR="$HOME/.nvm"
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.6/install.sh | bash
. "$NVM_DIR/nvm.sh"
nvm install 22
nvm alias default 22
node --version
npm --version
```

Node.js 22 must be active before installing PM2 or building the frontend.

### 5. Create The Application Directory

For a first installation:

```bash
sudo install -d -o pos -g pos -m 0755 /home/pos/Korvexa
sudo chmod 711 /home/pos
```

Place the repository contents in `/home/pos/Korvexa`. Do not upload `.env`,
`node_modules`, `.venv`, `dist`, caches, or logs from another machine.

Create the environment file directly on the server:

```bash
cd /home/pos/Korvexa
cp .env.example .env
nano .env
chmod 600 .env
```

Confirm that the file is protected without printing its contents:

```bash
stat -c '%U %G %a %n' /home/pos/Korvexa/.env
```

Expected ownership and mode are `pos pos 600`.

### 6. Create The Database

The checked-in setup script prompts for the role password and does not store it
in Git:

```bash
sudo -u postgres psql -f /home/pos/Korvexa/database/setup.sql
```

Use the same password, URL-encoded, in `DATABASE_URL`. Then install backend
dependencies and apply every migration:

```bash
cd /home/pos/Korvexa/backend
$HOME/.local/bin/uv venv --clear --seed --python 3.13 .venv
$HOME/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m alembic current
```

### 7. Create The First Administrator And Baseline Menu

Run this only on a new or intentionally cleared installation. It deletes all
application data while preserving the migration version:

```bash
cd /home/pos/Korvexa/backend
export KORVEXA_SUPERUSER_EMAIL=admin@korvexa.com
read -rsp 'Temporary administrator password: ' KORVEXA_SUPERUSER_PASSWORD
echo
export KORVEXA_SUPERUSER_PASSWORD
.venv/bin/python -m scripts.reset_production_data \
  --confirm RESET-KORVEXA-PRODUCTION-DATA
unset KORVEXA_SUPERUSER_PASSWORD
```

Change the temporary administrator password immediately after first login.
Never add the password to this README, `.env`, shell history, or GitHub Actions.
Never run the reset command during a normal deployment.

### 8. Build The Frontend

The Vite configuration reads `VITE_*` values from the root `.env`:

```bash
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
nvm use 22
cd /home/pos/Korvexa/frontend
npm ci --no-audit --no-fund
npm run build
```

### 9. Configure PM2

Install PM2 under Node.js 22 and start the API with the checked-in process file:

```bash
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
nvm use 22
npm install --global pm2
pm2 startOrReload /home/pos/Korvexa/deploy/ecosystem.config.cjs --update-env
pm2 save --force
pm2 startup systemd -u pos --hp /home/pos
```

Run the exact `sudo ...` command printed by `pm2 startup`, then finish with:

```bash
pm2 save --force
sudo systemctl enable --now pm2-pos
systemctl status pm2-pos --no-pager
pm2 status
```

Configure bounded PM2 logs once:

```bash
pm2 install pm2-logrotate
pm2 set pm2-logrotate:max_size 20M
pm2 set pm2-logrotate:retain 14
pm2 set pm2-logrotate:compress true
pm2 set pm2-logrotate:dateFormat YYYY-MM-DD_HH-mm-ss
pm2 save --force
```

### 10. Configure Nginx

```bash
sudo cp /home/pos/Korvexa/nginx/nginx.conf /etc/nginx/sites-available/korvexa
sudo ln -sfn /etc/nginx/sites-available/korvexa /etc/nginx/sites-enabled/korvexa
sudo rm -f /etc/nginx/sites-enabled/default
sudo cp /home/pos/Korvexa/nginx/korvexa.logrotate /etc/logrotate.d/korvexa-nginx
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl reload nginx
```

Nginx serves the frontend, supports React deep links, and proxies `/api/` to
`127.0.0.1:8000` without removing the API path.

### 11. Install Limited Deployment Sudo Access

GitHub Actions needs permission to validate and reload Nginx without an
interactive password. Install the narrow checked-in policy:

```bash
sudo install -o root -g root -m 0440 \
  /home/pos/Korvexa/deploy/korvexa-deploy.sudoers \
  /etc/sudoers.d/korvexa-deploy
sudo visudo -cf /etc/sudoers.d/korvexa-deploy
sudo -l -U pos
```

The policy allows only `/usr/sbin/nginx -t` and
`/usr/bin/systemctl reload nginx`. Do not grant the deployment user unrestricted
passwordless sudo.

## GitHub Actions Deployment

The workflow is `.github/workflows/deploy-production.yml`.

- Every pull request to `main` runs backend and frontend verification.
- Every push to `main` runs verification.
- A push or manual workflow run deploys only when `DEPLOY_ENABLED=true`.
- Deployment uses a dedicated SSH key, not the server account password.
- Source is synchronized while server `.env`, `.venv`, `node_modules`, and
  `dist` are handled safely by the workflow.
- Alembic runs before PM2 reload; Nginx is reloaded only after validation.
- Private and public health checks must pass.

### 1. Create A Dedicated Deployment Key

Create this key on a trusted administrator computer, outside the repository.
Do not reuse a personal key. In Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "$HOME\.ssh" | Out-Null
ssh-keygen -t ed25519 -C "github-actions-korvexa-production" -f "$HOME\.ssh\korvexa_github_actions"
```

When prompted for a passphrase, press Enter twice. This dedicated unattended key
must not have a passphrase because the current workflow has no passphrase input.
Protect the computer and use this key only for this deployment.

On Linux or macOS, use:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -C "github-actions-korvexa-production" -f ~/.ssh/korvexa_github_actions
```

This creates:

```text
korvexa_github_actions      Private key: GitHub secret only; never upload to server or Git
korvexa_github_actions.pub  Public key: install on the server
```

Install the public key from Windows PowerShell:

```powershell
Get-Content "$HOME\.ssh\korvexa_github_actions.pub" |
  ssh pos@34.29.31.163 'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys'
```

Or install it from Linux/macOS:

```bash
ssh-copy-id -i ~/.ssh/korvexa_github_actions.pub pos@34.29.31.163
```

Verify key login before configuring GitHub:

```powershell
ssh -i "$HOME\.ssh\korvexa_github_actions" -o IdentitiesOnly=yes pos@34.29.31.163 "whoami && pwd"
```

Expected output begins with `pos` and `/home/pos`. Do not disable password login
until key login has been tested from a second terminal and recovery console
access is available.

### 2. Verify And Capture The Server Host Key

Run this through the cloud provider's trusted serial console or an already
trusted SSH session:

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

On the trusted Windows computer, capture the public host key:

```powershell
ssh-keyscan -H -t ed25519 34.29.31.163 2>$null |
  Set-Content -Encoding ascii "$HOME\.ssh\korvexa_production_known_hosts"
ssh-keygen -lf "$HOME\.ssh\korvexa_production_known_hosts"
```

Compare both SHA256 fingerprints exactly. Save the `known_hosts` line only after
they match. `ssh-keyscan` alone does not prove the server identity.

### 3. Create The GitHub Production Environment

Open the repository on GitHub:

1. Select **Settings**.
2. Select **Environments**.
3. Select **New environment**.
4. Name it exactly `production`.
5. Optionally add required reviewers and restrict deployments to `main`.

Add these **Environment variables** under `production`:

| Name | Value |
| --- | --- |
| `SSH_HOST` | `34.29.31.163` |
| `SSH_PORT` | `22` |
| `SSH_USER` | `pos` |
| `APP_DIR` | `/home/pos/Korvexa` |
| `PUBLIC_URL` | `http://34.29.31.163` |

Add these **Environment secrets** under `production`:

| Name | Content |
| --- | --- |
| `SSH_PRIVATE_KEY` | Entire dedicated private key, including the `BEGIN` and `END` lines |
| `SSH_KNOWN_HOSTS` | Verified complete line from `korvexa_production_known_hosts` |
| `PRODUCTION_ENV_FILE` | Complete multiline production `.env` content |

Do not add the SSH account password. The workflow does not use it.

The minimum `PRODUCTION_ENV_FILE` content is:

```dotenv
ENVIRONMENT=production
DATABASE_URL=postgresql://korvexa_app:URL_ENCODED_DATABASE_PASSWORD@127.0.0.1:5432/korvexa
JWT_SECRET=REPLACE_WITH_AT_LEAST_64_RANDOM_CHARACTERS
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
DATABASE_POOL_RECYCLE_SECONDS=1800
VITE_API_BASE_URL=http://34.29.31.163
VITE_PUBLIC_APP_URL=http://34.29.31.163
CORS_ORIGINS=http://34.29.31.163
```

Append SMTP, payment, and delivery values only when each provider is activated.
Do not leave fake provider values in production because an integration can
appear partially configured.

To prepare the multiline value manually on Windows, create a protected working
file outside the repository, copy the required names from `.env.example`, and
replace every placeholder:

```powershell
New-Item -ItemType Directory -Force C:\secure | Out-Null
Copy-Item .env.example C:\secure\korvexa.production.env
notepad C:\secure\korvexa.production.env
```

Remove unused optional provider sections before uploading it. Never share this
file by email or chat, and delete the local copy after GitHub and the server have
been verified.

### 4. Enable Deployment

This is a repository-level Actions variable, not an Environment secret:

1. Open **Settings > Secrets and variables > Actions**.
2. Select **Variables**.
3. Add `DEPLOY_ENABLED` with value `true`.

Set it to `false` to stop production deployment while still running all
verification jobs.

### 5. Trigger And Monitor Deployment

Automatic deployment:

```bash
git push origin main
```

Manual trigger:

1. Open **Actions**.
2. Select **Verify and deploy production**.
3. Select **Run workflow**.
4. Choose `main` and confirm.

The deployment succeeds only after both the `Verify application` and
`Deploy over SSH` jobs pass. Afterward, run the checks in the Verification
section below.

### Optional GitHub CLI Setup

The web interface above is the simplest method. Administrators using GitHub CLI
can set non-secret values with:

```powershell
gh variable set SSH_HOST --env production --body "34.29.31.163"
gh variable set SSH_PORT --env production --body "22"
gh variable set SSH_USER --env production --body "pos"
gh variable set APP_DIR --env production --body "/home/pos/Korvexa"
gh variable set PUBLIC_URL --env production --body "http://34.29.31.163"
gh variable set DEPLOY_ENABLED --body "true"
```

Set secrets from files stored outside the repository:

```powershell
Get-Content -Raw "$HOME\.ssh\korvexa_github_actions" |
  gh secret set SSH_PRIVATE_KEY --env production
Get-Content -Raw "$HOME\.ssh\korvexa_production_known_hosts" |
  gh secret set SSH_KNOWN_HOSTS --env production
Get-Content -Raw "C:\secure\korvexa.production.env" |
  gh secret set PRODUCTION_ENV_FILE --env production
```

Delete `C:\secure\korvexa.production.env` securely when it is no longer needed.
Never create it inside the repository.

### Rotate The Deployment SSH Key

1. Generate a new dedicated key with a new filename.
2. Append the new public key to `/home/pos/.ssh/authorized_keys`.
3. Verify login using the new private key.
4. Replace the GitHub `SSH_PRIVATE_KEY` Environment secret.
5. Run the deployment workflow and confirm success.
6. Remove the old public-key line from `authorized_keys`.
7. Delete the old private key from administrator computers and backups.

If the server is rebuilt, also recapture and verify its host key before replacing
`SSH_KNOWN_HOSTS`. Never update that secret merely to bypass a host-key error.

## Manual Production Deployment

Use this process when GitHub Actions is unavailable. Automatic deployment is
preferred because it verifies the application first.

### 1. Back Up PostgreSQL

Create the protected backup directory once:

```bash
sudo install -d -o postgres -g postgres -m 0700 /var/backups/korvexa
```

Create a timestamped custom-format backup:

```bash
BACKUP="/var/backups/korvexa/korvexa-$(date +%F-%H%M%S).dump"
sudo -u postgres pg_dump -Fc -f "$BACKUP" korvexa
sudo ls -lh "$BACKUP"
```

Copy important backups to encrypted storage outside the server and test restore
procedures regularly.

### 2. Synchronize Source

From the repository root on a trusted Linux/macOS machine or Windows WSL/Git
Bash, run the equivalent of the workflow sync:

```bash
rsync -az --delete-delay \
  -e "ssh -i ~/.ssh/korvexa_github_actions -p 22 -o IdentitiesOnly=yes" \
  --exclude='.git/' \
  --exclude='.env' \
  --exclude='backend/.venv/' \
  --exclude='frontend/node_modules/' \
  --exclude='frontend/dist/' \
  --exclude='**/__pycache__/' \
  --exclude='**/.pytest_cache/' \
  --exclude='*.pyc' \
  --exclude='*.log' \
  ./ pos@34.29.31.163:/home/pos/Korvexa/
```

This preserves the production `.env`. Review every path before using `--delete`
against a different server.

If environment values changed, edit `/home/pos/Korvexa/.env` on the server and
restore mode `600`. Keep a protected backup of the previous values until the
deployment is verified.

### 3. Install, Migrate, Build, And Reload

Run on the server:

```bash
set -Eeuo pipefail
export PATH="$HOME/.local/bin:$PATH"
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
nvm use 22

cd /home/pos/Korvexa/backend
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m alembic upgrade head

cd /home/pos/Korvexa/frontend
npm ci --no-audit --no-fund
npm run build

pm2 startOrReload /home/pos/Korvexa/deploy/ecosystem.config.cjs --update-env
pm2 save --force
sudo nginx -t
sudo systemctl reload nginx
```

Do not run `reset_production_data` during an update.

### 4. Verify Before Closing The Session

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/v1/ready
curl -fsS http://34.29.31.163/api/v1/ready
curl -fsSI http://34.29.31.163/
pm2 status
```

## Database Backup And Restore

Restoring replaces current production data. Confirm the backup path and take a
fresh backup before proceeding.

```bash
pm2 stop korvexa-api
sudo -u postgres psql -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'korvexa' AND pid <> pg_backend_pid();"
sudo -u postgres dropdb --if-exists korvexa
sudo -u postgres createdb --owner=korvexa_app korvexa
sudo -u postgres pg_restore \
  --exit-on-error --no-owner --role=korvexa_app \
  --dbname=korvexa /var/backups/korvexa/REPLACE_WITH_BACKUP.dump

cd /home/pos/Korvexa/backend
.venv/bin/python -m alembic upgrade head
pm2 startOrReload /home/pos/Korvexa/deploy/ecosystem.config.cjs --update-env
pm2 save --force
curl -fsS http://127.0.0.1:8000/api/v1/ready
```

Migration downgrades are not a general rollback strategy. To roll back an
application release, re-run a previously successful GitHub Actions workflow for
the required commit. If that release is incompatible with the current schema,
restore the matching database backup first.

## Verification

### Service Checks

```bash
pm2 status
systemctl is-active pm2-pos nginx postgresql
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://34.29.31.163/api/v1/ready
curl -fsSI http://34.29.31.163/
curl -fsSI http://34.29.31.163/dashboard
```

### Functional Smoke Test

After every production release:

1. Sign in as an administrator without saving the password in the browser.
2. Confirm the active tenant and branch load.
3. Confirm Menu, Tables, Staff, Inventory, Admin, and Reports load values.
4. Create a temporary dine-in order and confirm billing totals and balance.
5. Submit the order and accept it in KDS.
6. Move it through preparing, ready, and served states.
7. Request a discount and confirm the notification appears for the approver.
8. Print or preview a receipt and check alignment.
9. Test QR ordering using a non-production-value temporary order.
10. Remove or void all temporary smoke-test data according to business policy.

Payment and delivery-provider tests should be performed only after those
providers are activated and using their approved test/live procedure.

### Automated Tests

GitHub Actions runs these on every pull request and push:

```bash
cd backend
python -m pytest -q

cd ../frontend
npm test -- --run
npm exec tsc -- --noEmit
```

Do not run backend tests with the production schema. Use the isolated
`korvexa_test` database/schema or rely on GitHub Actions.

## Operations And Logs

Common PM2 operations:

```bash
pm2 status
pm2 describe korvexa-api
pm2 logs korvexa-api --lines 200 --nostream
pm2 restart korvexa-api --update-env
pm2 save --force
```

Nginx and PostgreSQL logs:

```bash
sudo tail -n 200 /var/log/nginx/korvexa.error.log
sudo journalctl -u nginx -u postgresql --since '1 hour ago' --no-pager
```

Remove generated caches without touching source, environment files, build
output, or database data:

```bash
find /home/pos/Korvexa -type d \
  \( -name __pycache__ -o -name .pytest_cache -o -name test-results -o -name playwright-report \) \
  -prune -exec rm -rf {} +
find /home/pos/Korvexa -type f \
  \( -name '*.pyc' -o -name '*.tmp' -o -name '*.tsbuildinfo' \) \
  -delete
sudo journalctl --vacuum-time=14d
sudo logrotate /etc/logrotate.d/korvexa-nginx
```

Do not delete logs while diagnosing a failed deployment. `node_modules`,
frontend `dist`, and backend `.venv` are generated on the server and excluded
from Git.

## Troubleshooting

### Vite Reports `Unexpected reserved word`

The server is using an old Node.js version. Activate Node.js 22 before running
npm or PM2:

```bash
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
nvm use 22
node --version
```

### Workflow Reports `rsync: command not found`

Install rsync on the server:

```bash
sudo apt update
sudo apt install -y rsync
```

### Deployment Job Is Skipped

Confirm the repository Actions variable is named exactly `DEPLOY_ENABLED` and
its value is lowercase `true`. Pull requests verify but never deploy.

### SSH Host-Key Verification Fails

Do not disable host-key checking. Compare the server's Ed25519 fingerprint
through a trusted console, recapture the key, and update `SSH_KNOWN_HOSTS` only
after the fingerprints match. A changed key can indicate a rebuilt server or an
attack.

### PM2 Startup Service Fails

Confirm PM2 was installed under Node.js 22, then rebuild the saved process list:

```bash
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
nvm use 22
pm2 save --force
pm2 kill
sudo systemctl reset-failed pm2-pos
sudo systemctl start pm2-pos
systemctl status pm2-pos --no-pager
```

### Nginx Returns `403 Forbidden`

Nginx must be able to traverse `/home/pos` and read the built frontend:

```bash
sudo chmod 711 /home/pos
chmod -R u=rwX,go=rX /home/pos/Korvexa/frontend/dist
sudo nginx -t
sudo systemctl reload nginx
```

### Nginx Returns `502 Bad Gateway`

```bash
pm2 status
pm2 logs korvexa-api --lines 200 --nostream
curl -v http://127.0.0.1:8000/health
```

Check `.env` ownership, the database connection, migrations, and the backend
virtual environment before restarting PM2.

### Readiness Reports A Database Failure

```bash
sudo systemctl status postgresql --no-pager
sudo -u postgres psql -d korvexa -c 'select current_database(), current_user;'
cd /home/pos/Korvexa/backend
.venv/bin/python -m alembic current
```

Verify `DATABASE_URL` privately. Do not paste it into issue trackers or logs.

### Environment Changes Do Not Appear

Backend values require a PM2 reload with `--update-env`. `VITE_*` values are
compiled into the frontend and require a new `npm run build`:

```bash
pm2 startOrReload /home/pos/Korvexa/deploy/ecosystem.config.cjs --update-env
cd /home/pos/Korvexa/frontend
npm run build
sudo systemctl reload nginx
```

## Credential Rotation Checklist

- Change the `pos` account password with `passwd`; never record it in GitHub.
- Rotate the administrator password in the application.
- Rotate the deployment SSH key using the zero-downtime procedure above.
- Rotate the database role password with `ALTER ROLE`, update
  `PRODUCTION_ENV_FILE`, and immediately redeploy.
- Rotate `JWT_SECRET` only with an approved maintenance plan because all active
  login sessions become invalid.
- Rotate SMTP, payment, and delivery-provider keys in both the provider portal
  and `PRODUCTION_ENV_FILE`.
- Revoke any exposed GitHub token in GitHub settings and create a least-privilege
  replacement only if one is actually needed.
- Review `/home/pos/.ssh/authorized_keys` and GitHub Environment access
  regularly.

## HTTPS And Production Integrations

The current IP configuration serves the core application over HTTP. Before
public production use:

1. Point a controlled domain to `34.29.31.163`.
2. Set that domain as `server_name` in `nginx/nginx.conf` and deploy it.
3. Install Certbot and issue a trusted TLS certificate:

   ```bash
   sudo apt update
   sudo apt install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d pos.example.com
   sudo certbot renew --dry-run
   ```

4. Confirm that Certbot configured HTTP-to-HTTPS redirection.
5. Replace `PUBLIC_URL`, all `VITE_*` URLs, `CORS_ORIGINS`,
   `PUBLIC_API_BASE_URL`, and `FRONTEND_RESET_URL` with the HTTPS domain.
6. Redeploy so the frontend is rebuilt.
7. Register the exact HTTPS webhook URLs with each provider.

Password-reset email, Razorpay webhooks, RazorpayX, Swiggy, and Zomato should
not be treated as production-ready until HTTPS and real provider credentials are
configured and verified end to end.

## Reference Documentation

- GitHub Environments: https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
- GitHub Actions secrets: https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions
- PostgreSQL Apt repository: https://www.postgresql.org/download/linux/ubuntu/
- uv installation: https://docs.astral.sh/uv/getting-started/installation/
- NVM: https://github.com/nvm-sh/nvm
- PM2 startup: https://pm2.keymetrics.io/docs/usage/startup/
