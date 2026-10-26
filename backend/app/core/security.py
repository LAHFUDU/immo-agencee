import hashlib
import secrets
import string

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# argon2-cffi defaults to Argon2id with RFC 9106 "low memory" parameters.
_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        # Still spend comparable time to avoid user enumeration via timing.
        _hasher.hash(password)
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def validate_password_strength(password: str) -> str | None:
    """Returns an error message (French) or None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères."
    classes = sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )
    if classes < 3:
        return "Le mot de passe doit combiner au moins 3 types : minuscules, majuscules, chiffres, symboles."
    return None


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_temp_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        core = "".join(secrets.choice(alphabet) for _ in range(length - 2))
        pwd = core + secrets.choice("!@#$%&*?") + secrets.choice(string.digits)
        if validate_password_strength(pwd) is None:
            return pwd
