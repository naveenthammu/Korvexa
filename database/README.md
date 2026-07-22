# Database

Korvexa requires PostgreSQL. SQLite and runtime table creation are not supported.

## Create The Database

Run the setup script as a PostgreSQL administrator. It prompts for a database-role password instead of storing one in source control.

```powershell
psql -U postgres -f database/setup.sql
```

Set the resulting connection in the root `.env`, then apply every migration:

```powershell
cd backend
python -m alembic upgrade head
cd ..
```

The application checks the migrated schema through `/ready` and does not create or alter tables during startup.

## Reset And Seed

The reset command truncates all application data while preserving `alembic_version`. It requires an exact confirmation phrase and explicit administrator credentials.

```powershell
cd backend
python -m scripts.reset_production_data `
  --confirm RESET-KORVEXA-PRODUCTION-DATA `
  --email admin@korvexa.com `
  --password "replace-with-a-strong-password"
```

The baseline contains one tenant, one branch, one super administrator, seven menu categories, a balanced restaurant menu, and twelve available tables.

## Tests

Backend tests use an isolated PostgreSQL schema named `korvexa_test`. Override `TEST_DATABASE_URL` and `TEST_DATABASE_SCHEMA` in CI; the safety check refuses schemas that do not start with `korvexa_test`.
