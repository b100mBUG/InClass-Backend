from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator


class UserBase(BaseModel):
    full_name: str
    email: EmailStr
    role: str
    student_id: Optional[str] = None

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, v):
        if v not in ("lecturer", "student"):
            raise ValueError("role must be 'lecturer' or 'student'")
        return v


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int

    model_config = {"from_attributes": True}


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
