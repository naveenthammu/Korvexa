from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_nginx_preserves_api_v1_paths_and_supports_spa_deep_links():
    root = Path(__file__).resolve().parents[2]
    config = (root / "nginx" / "nginx.conf").read_text(encoding="utf-8")

    assert "server_name 34.29.31.163;" in config
    assert "root /home/pos/Korvexa/frontend/dist;" in config
    assert "proxy_pass http://127.0.0.1:8000;" in config
    assert "proxy_pass http://127.0.0.1:8000/;" not in config
    assert "try_files $uri $uri/ /index.html;" in config


def test_migration_graph_has_one_unambiguous_head():
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(root / "backend" / "migrations"))
    script = ScriptDirectory.from_config(config)

    revisions = list(script.walk_revisions())
    revision_ids = [revision.revision for revision in revisions]

    assert len(revision_ids) == len(set(revision_ids))
    assert script.get_heads() == ["20260722_0007"]


def test_production_workflow_uses_protected_ssh_deployment():
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github" / "workflows" / "deploy-production.yml").read_text(encoding="utf-8")

    assert "environment:\n      name: production" in workflow
    assert "vars.DEPLOY_ENABLED == 'true'" in workflow
    assert "secrets.SSH_PRIVATE_KEY" in workflow
    assert "secrets.SSH_KNOWN_HOSTS" in workflow
    assert "secrets.PRODUCTION_ENV_FILE" in workflow
    assert "ssh-keyscan" not in workflow
    assert "--exclude='.env'" in workflow
    assert '"$UV" venv --clear --seed --python 3.13 .venv' in workflow
    assert ".venv/bin/python -m alembic upgrade head" in workflow
    assert "npm run build" in workflow
    assert 'pm2 startOrReload "$APP_DIR/deploy/ecosystem.config.cjs" --update-env' in workflow
    assert "pm2 save --force" in workflow
    assert "systemctl restart korvexa-api" not in workflow
    assert '"$PUBLIC_URL/api/v1/ready"' in workflow
