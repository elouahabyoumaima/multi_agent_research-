import os
from datetime import datetime, timedelta

import bcrypt
from dotenv import load_dotenv
from jose import JWTError, jwt

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 heures


def hash_password(password: str) -> str:
    """Hash un mot de passe en clair avec bcrypt."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifie qu'un mot de passe en clair correspond au hash stocke."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(username: str) -> str:
    """Cree un JWT signe contenant le username et une date d'expiration."""
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """Decode un JWT et renvoie le username, ou None si invalide/expire."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None
import random
from datetime import datetime


def generate_verification_code() -> str:
    """Genere un code a 6 chiffres pour la verification email."""
    return str(random.randint(100000, 999999))


def is_code_expired(expiry: datetime | None) -> bool:
    """Verifie si le code de verification a expire."""
    if expiry is None:
        return True
    return datetime.utcnow() > expiry