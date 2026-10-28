"""Contraseñas (scrypt de la biblioteca estándar) y tokens de sesión."""
import hashlib
import hmac
import secrets

_N, _R, _P, _DKLEN = 2**14, 8, 1, 32
# Hash ficticio para igualar el tiempo de respuesta cuando el usuario no existe.
_DUMMY = None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    global _DUMMY
    if not stored:
        _DUMMY = _DUMMY or hash_password("x")
        stored, ok = _DUMMY, False
    else:
        ok = True
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(bytes.fromhex(digest)))
    except ValueError:
        return False
    return hmac.compare_digest(actual.hex(), digest) and ok


def new_session_token() -> tuple[str, str]:
    """Devuelve (token para la cookie, SHA-256 que se guarda en la BD)."""
    token = secrets.token_urlsafe(32)
    return token, token_sha256(token)


def token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()
