-- Run as a PostgreSQL administrator:
-- psql -U postgres -f database/setup.sql

\set ON_ERROR_STOP on

\if :{?app_role}
\else
\set app_role korvexa_app
\endif

\if :{?app_database}
\else
\set app_database korvexa
\endif

\if :{?app_password}
\else
\prompt 'Enter a strong password for the Korvexa database role: ' app_password
\endif

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_role', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_role')\gexec

SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'app_role', :'app_password')\gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'app_database', :'app_role')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'app_database')\gexec

SELECT format('ALTER DATABASE %I OWNER TO %I', :'app_database', :'app_role')\gexec

\connect :app_database

SELECT format('ALTER SCHEMA public OWNER TO %I', :'app_role')\gexec
SELECT format('GRANT ALL ON SCHEMA public TO %I', :'app_role')\gexec
