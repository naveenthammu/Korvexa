from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_nginx_preserves_api_v1_paths_and_supports_spa_deep_links():
    root = Path(__file__).resolve().parents[2]
    config = (root / "nginx" / "nginx.conf").read_text(encoding="utf-8")

    assert "server_name 34.29.31.163;" in config
    assert "root /opt/korvexa/frontend/dist;" in config
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
