import importlib.util
from pathlib import Path
from dotenv import dotenv_values


def test_migration_preserves_database_paths_and_user_shared_edits(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "configure.py"
    spec = importlib.util.spec_from_file_location("suite_configure", script)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    root = tmp_path / "care-suite"; root.mkdir()
    module.ROOT = root; module.BASE = tmp_path
    monkeypatch.delenv("CARE_SUITE_ENV_FILE", raising=False)
    (root / ".env.example").write_text("MODEL_NAME=default-model\nOPENAI_API_KEY=\nSERVICE_TOKEN=\nKNOWLEDGE_BACKEND=medknowledgehub\n",encoding="utf-8")
    for project in ["carepilot", "medknowledgehub"]:
        folder = tmp_path / project; folder.mkdir()
        (folder / ".env").write_text(f"MODEL_NAME={project}\nOPENAI_API_KEY={project}-key\nLOCAL_PATH=data/{project}.sqlite3\nOTHER_PATH=data/second.sqlite3\n",encoding="utf-8")
    module.configure()
    shared = dotenv_values(root / ".env")
    assert shared["MODEL_NAME"] == "medknowledgehub" and shared["SERVICE_TOKEN"]
    for project in ["carepilot", "medknowledgehub"]:
        values = dotenv_values(tmp_path / project / ".env")
        assert values == {"LOCAL_PATH": f"data/{project}.sqlite3", "OTHER_PATH": "data/second.sqlite3"}
        assert (tmp_path / project / ".env.before-suite").exists()
    from dotenv import set_key
    set_key(root / ".env", "MODEL_NAME", "edited-model")
    module.configure()
    assert dotenv_values(root / ".env")["MODEL_NAME"] == "edited-model"
    assert dotenv_values(root / ".env")["SERVICE_TOKEN"] == shared["SERVICE_TOKEN"]
