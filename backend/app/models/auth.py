import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Table, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamps, UUIDPk, utcnow
from app.models.enums import TokenPurpose, enum_column

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Permission(UUIDPk, Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)


class Role(UUIDPk, Timestamps, Base):
    __tablename__ = "roles"
    code: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # System roles cannot be deleted; the super admin role is also immutable and implicitly has every permission.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    permissions: Mapped[list[Permission]] = relationship(secondary=role_permissions, lazy="selectin")


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    job_title: Mapped[str | None] = mapped_column(String(120))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_agent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="fr", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    role: Mapped[Role] = relationship(lazy="joined")

    __table_args__ = (Index("uq_users_email_lower", func.lower(email), unique=True),)

    @property
    def is_superadmin(self) -> bool:
        return bool(self.role and self.role.is_superadmin)

    def permission_codes(self) -> set[str]:
        from app.core.permissions import ALL_PERMISSION_CODES

        if self.is_superadmin:
            return set(ALL_PERMISSION_CODES)
        return {p.code for p in self.role.permissions}


class UserSession(Base):
    """Server-side session. The cookie carries a random token; only its SHA-256 is stored."""

    __tablename__ = "user_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[User] = relationship(lazy="joined")


class AuthToken(Base):
    """Single-use invitation / password reset token (hash stored only)."""

    __tablename__ = "auth_tokens"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose: Mapped[TokenPurpose] = mapped_column(enum_column(TokenPurpose, "token_purpose"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class RateLimitEvent(Base):
    """Shared (multi-worker safe) rate limiting store."""

    __tablename__ = "rate_limit_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (Index("ix_rate_limit_events_key_created", "key", "created_at"),)
