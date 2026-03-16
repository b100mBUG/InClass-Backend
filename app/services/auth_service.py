from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, Token, UserRead
from app.core.security import hash_password, verify_password, create_access_token


def register_user(db: Session, payload: UserCreate) -> UserRead:
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    if payload.role == "student" and payload.student_id:
        if db.query(User).filter(User.student_id == payload.student_id).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Student ID already registered",
            )

    user = User(
        full_name=payload.full_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        student_id=payload.student_id if payload.role == "student" else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserRead.model_validate(user)


def login_user(db: Session, payload: UserLogin) -> Token:
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return Token(access_token=token, user=UserRead.model_validate(user))
