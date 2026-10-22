"""Create a local .env with independent credentials; never print secrets."""

import secrets

from app.core.config import ROOT


def main():
    destination = ROOT / ".env"
    if destination.exists():
        print(".env already exists; preserved.")
        return
    content = (ROOT / ".env.example").read_text(encoding="utf-8")
    content = content.replace("change-me", secrets.token_urlsafe(18)).replace(
        "change-this-password", secrets.token_urlsafe(18)
    )
    content = content.replace("ADMIN_PASSWORD=\n", "ADMIN_PASSWORD=" + secrets.token_urlsafe(18) + "\n")
    content = content.replace("SERVICE_TOKEN=\n", "SERVICE_TOKEN=" + secrets.token_urlsafe(32) + "\n")
    destination.write_text(content, encoding="utf-8")
    print("Created local .env. Configure OPENAI_API_KEY before ingestion and answering.")


if __name__ == "__main__":
    main()
