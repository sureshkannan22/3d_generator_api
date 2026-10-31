from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlmodel import Session, select
from jose import JWTError, jwt

from app.core.database import get_session
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    SECRET_KEY,
    ALGORITHM,
)
from app.models.user_model import User
from app.schemas.user_schema import (
    UserCreate,
    UserResponse,
    Token,
    RefreshTokenRequest,
)

router = APIRouter(prefix="/auth", tags=["Authentication & Users"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


@router.post("/register", response_model=UserResponse)
def register_user(user_data: UserCreate, session: Session = Depends(get_session)):
    # 1. Check if user already exists in the database
    statement = select(User).where(User.email == user_data.email)
    existing_user = session.exec(statement).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # 2. Hash the raw password
    hashed_pwd = hash_password(user_data.password)

    # 3. Create the database user object
    username = (user_data.name or user_data.email.split("@")[0]).strip()
    db_user = User(
        username=username,
        email=user_data.email,
        password_hash=hashed_pwd,
        is_active=True,
    )

    # 4. Save to the database
    session.add(db_user)
    session.commit()
    session.refresh(db_user)

    return db_user


@router.post("/login", response_model=Token)
def login_user(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    # 1. Find user in the database by email (form_data.username acts as email)
    statement = select(User).where(User.email == form_data.username)
    user = session.exec(statement).first()

    # 2. Verify password
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Issue JWT access & refresh tokens containing their email
    access_token = create_access_token(data={"sub": user.email})
    refresh_token = create_refresh_token(data={"sub": user.email})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/refresh", response_model=Token)
def refresh_access_token(
    request: RefreshTokenRequest,
    session: Session = Depends(get_session),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            request.refresh_token, SECRET_KEY, algorithms=[ALGORITHM]
        )
        if payload.get("type") != "refresh":
            raise credentials_exception
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    statement = select(User).where(User.email == email)
    user = session.exec(statement).first()
    if user is None:
        raise credentials_exception

    new_access_token = create_access_token(data={"sub": user.email})
    new_refresh_token = create_refresh_token(data={"sub": user.email})
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    """
    AUTHORIZATION DEPENDENCY:
    Intercepts requests, decodes the token, and fetches the user from the database.
    If anything fails, blocks the request with a 401 Unauthorized error.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Query database to ensure user exists
    statement = select(User).where(User.email == email)
    user = session.exec(statement).first()
    if user is None:
        raise credentials_exception

    return user


@router.post("/logout")
def logout_user(current_user: User = Depends(get_current_user)):
    """
    Logs out the current user.
    Because JWT is stateless, the primary action happens on the client side
    (deleting tokens from secure storage).
    This endpoint verifies the user's token and confirms the logout action.
    """
    return {
        "message": f"User {current_user.email} successfully logged out.",
        "action_required": "Please clear your local access and refresh tokens.",
    }
