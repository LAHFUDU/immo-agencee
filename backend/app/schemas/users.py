import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORM


class RoleOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_system: bool
    is_superadmin: bool
    permissions: list[str] = []


class RoleIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    permissions: list[str] = []


class PermissionOut(BaseModel):
    code: str
    module: str
    label: str


class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    job_title: str | None
    role_id: uuid.UUID
    role_name: str
    role_code: str
    is_active: bool
    is_agent: bool
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    job_title: str | None = Field(default=None, max_length=120)
    role_id: uuid.UUID
    is_agent: bool = True
    credential_mode: Literal["invite", "temp_password"] = "invite"


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    job_title: str | None = Field(default=None, max_length=120)
    role_id: uuid.UUID | None = None
    is_agent: bool | None = None
    email: EmailStr | None = None


class CredentialResult(BaseModel):
    """Returned once to the administrator. Never stored in clear text."""

    user: UserOut
    mode: Literal["invite", "temp_password"]
    invite_url: str | None = None
    temp_password: str | None = None
    email_status: str


class ResetRequest(BaseModel):
    credential_mode: Literal["invite", "temp_password"] = "invite"


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role_name: str
    role_code: str
    is_superadmin: bool
    must_change_password: bool
    language: str
    permissions: list[str]
    csrf_token: str


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class AcceptTokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(max_length=256)
