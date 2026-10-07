from pydantic import BaseModel


class SignupRequest(BaseModel):
    username: str
    email: str
    phone: str | None = None
    password: str
    password_confirm: str


class VerifyRequest(BaseModel):
    email: str
    code: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ResearchHistoryItem(BaseModel):
    id: int
    question: str
    report: str
    sources: list[str]
    duration_seconds: int
    created_at: str