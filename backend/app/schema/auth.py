from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    username: str = Field(..., min_length=3, max_length=30, description="Unique username")
    password: str = Field(..., min_length=6, description="Plaintext password")

    model_config = ConfigDict(str_strip_whitespace=True)


class UserLoginRequest(BaseModel):
    email_or_username: str = Field(..., description="User registered email or username")
    password: str = Field(..., description="User password")

    model_config = ConfigDict(str_strip_whitespace=True)


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
