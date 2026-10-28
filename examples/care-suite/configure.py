"""Migrate shared settings; preserve database configuration and never print secrets."""
from pathlib import Path
import os
import secrets
from dotenv import dotenv_values, set_key
ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent


def configure():
    destination = Path(os.getenv("CARE_SUITE_ENV_FILE", ROOT / ".env"))
    templates = dict(dotenv_values(ROOT / ".env.example", interpolate=False))
    existing = {}
    for project in ("carepilot", "medknowledgehub"):
        existing.update({k: v for k, v in dotenv_values(BASE / project / ".env", interpolate=False).items() if v is not None})
    existing.update({k: v for k, v in dotenv_values(destination, interpolate=False).items() if v is not None})
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_text((ROOT / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
    for key, default in templates.items():
        value = existing.get(key, default or "")
        if key == "SERVICE_TOKEN" and not value:
            value = secrets.token_urlsafe(32)
        if key == "KNOWLEDGE_BACKEND":
            value = "medknowledgehub"
        set_key(destination, key, str(value), quote_mode="always", encoding="utf-8")
    for project in ("carepilot", "medknowledgehub"):
        local = BASE / project / ".env"
        if not local.exists():
            continue
        backup = local.with_name(".env.before-suite")
        if not backup.exists():
            backup.write_bytes(local.read_bytes())
        lines = [line for line in local.read_text(encoding="utf-8").splitlines()
                 if line.partition("=")[0].strip() not in templates]
        local.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Shared settings saved; project database settings preserved. No credentials printed.")
    return destination


if __name__ == "__main__":
    configure()
