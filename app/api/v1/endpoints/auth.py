from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.user import UserCreate, UserRead, UserLogin, Token
from app.services.auth_service import register_user, login_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserRead, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    """Register a new lecturer or student."""
    return register_user(db, payload)


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Authenticate and receive a JWT token.
    - **username**: your email address
    - **password**: your password
    """
    # OAuth2PasswordRequestForm uses 'username' field — we treat it as email
    payload = UserLogin(email=form_data.username, password=form_data.password)
    return login_user(db, payload)
