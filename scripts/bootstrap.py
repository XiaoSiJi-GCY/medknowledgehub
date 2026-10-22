import secrets

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.core.config import ROOT
from app.models import Token, User
from app.runtime import Runtime
from app.services.identity import digest


def main():
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(cfg, "head")
    runtime = Runtime()
    try:
        settings = runtime.settings
        if not settings.admin_password.get_secret_value() or not settings.service_token.get_secret_value():
            raise ValueError("请先在本机 .env 设置 ADMIN_PASSWORD 和 SERVICE_TOKEN")
        with runtime.db.session() as session:
            admin = session.scalar(select(User).where(User.username == settings.admin_username))
        if not admin:
            admin = runtime.identity.create_user(settings.admin_username, settings.admin_password.get_secret_value())
        with runtime.db.session() as session:
            service = session.scalar(select(User).where(User.username == settings.admin_username + "-service"))
        if not service:
            service = runtime.identity.create_user(
                settings.admin_username + "-service", secrets.token_urlsafe(32), admin.tenant_id, "viewer"
            )
        with runtime.db.session() as session:
            session.merge(
                Token(digest=digest(settings.service_token.get_secret_value()), user_id=service.id, expires_at=None)
            )
        runtime.vectors.ensure()
        runtime.graph_index.ensure()
        print("Initialized PostgreSQL schema, Milvus indexes, Neo4j constraints and service identity.")
        print("Administrator:", settings.admin_username, "(password is in local .env; not printed)")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
