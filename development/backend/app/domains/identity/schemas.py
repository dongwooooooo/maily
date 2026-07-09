import uuid

from pydantic import BaseModel


class GoogleProfile(BaseModel):
    google_subject: str
    email: str
    display_name: str | None = None


class GoogleLoginResult(BaseModel):
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    is_new_user: bool


class RequestContext(BaseModel):
    user_id: uuid.UUID
    workspace_id: uuid.UUID
