"""Auth schemas."""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str = "123456"


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class UserInfo(BaseModel):
    id: int
    username: str
    role: str
