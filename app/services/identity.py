import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import HubError
from app.models import Token, User, new_id


@dataclass(frozen=True)
class Principal:
    id: str
    tenant_id: str
    username: str
    role: str


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310000).hex()
    return f"{salt}:{digest}"


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class IdentityService:
    def __init__(self, db):
        self.db = db

    def create_user(self, username, password, tenant_id=None, role="admin"):
        if len(password) < 8:
            raise HubError("密码至少 8 位")
        try:
            with self.db.session() as session:
                user = User(
                    username=username, password_hash=password_hash(password), tenant_id=tenant_id or new_id(), role=role
                )
                session.add(user)
                session.flush()
                return Principal(user.id, user.tenant_id, user.username, user.role)
        except IntegrityError as exc:
            raise HubError("用户名已存在", 409) from exc

    def login(self, username, password):
        with self.db.session() as session:
            user = session.scalar(select(User).where(User.username == username))
            if not user or not hmac.compare_digest(
                user.password_hash, password_hash(password, user.password_hash.split(":")[0])
            ):
                raise HubError("用户名或密码错误", 401)
            token = secrets.token_urlsafe(32)
            session.add(Token(digest=digest(token), user_id=user.id, expires_at=int(time.time()) + 86400))
            return token

    def resolve(self, token):
        with self.db.session() as session:
            stored = session.get(Token, digest(token))
            if not stored or (stored.expires_at is not None and stored.expires_at <= int(time.time())):
                raise HubError("登录已失效，请重新登录", 401)
            user = session.get(User, stored.user_id)
            if not user:
                raise HubError("用户不存在", 401)
            return Principal(user.id, user.tenant_id, user.username, user.role)

    def logout(self, token):
        with self.db.session() as session:
            stored = session.get(Token, digest(token))
            if stored:
                session.delete(stored)

    @staticmethod
    def require_editor(principal):
        if principal.role not in {"admin", "editor"}:
            raise HubError("当前账号没有修改知识库的权限", 403)

    @staticmethod
    def require_admin(principal):
        if principal.role != "admin":
            raise HubError("需要管理员权限", 403)
