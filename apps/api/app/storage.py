"""Almacenamiento privado de archivos: fuera del frontend, nunca se sobrescribe un archivo existente."""
import hashlib
import re
import uuid
from pathlib import Path

from app.db import REPO_ROOT, setting
from app.errors import invalid

MAX_BYTES = 10 * 1024 * 1024
# Tipo declarado → firma real del contenido (no se confía en la extensión ni en el content-type).
SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n", ".png"),
    "image/jpeg": (b"\xff\xd8\xff", ".jpg"),
    "application/pdf": (b"%PDF-", ".pdf"),
}


def root() -> Path:
    path = Path(setting("STORAGE_DIR", "storage"))
    return path if path.is_absolute() else REPO_ROOT / path


def sniff(content: bytes) -> str:
    """Detecta el tipo por su firma; rechaza lo que no sea PNG, JPEG o PDF."""
    if not content:
        raise invalid("El archivo está vacío.")
    if len(content) > MAX_BYTES:
        raise invalid("El archivo supera el máximo de 10 MB.")
    for mime, (magic, _) in SIGNATURES.items():
        if content.startswith(magic):
            return mime
    raise invalid("Tipo de archivo no permitido. Usa PNG, JPEG o PDF.")


def safe_name(name: str | None, mime: str) -> str:
    base = re.sub(r"[^\w.\- ]+", "_", Path(name or "archivo").name).strip(" .") or "archivo"
    ext = SIGNATURES[mime][1]
    if not base.lower().endswith((ext, ".jpeg") if mime == "image/jpeg" else ext):
        base += ext
    return base[-120:]


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Tipos que solo genera el sistema (nunca se aceptan como subida).
GENERATED_EXT = {XLSX: ".xlsx"}


def save(organization_id, content: bytes, mime: str) -> tuple[str, str]:
    """Guarda el contenido y devuelve (storage_key, sha256)."""
    digest = hashlib.sha256(content).hexdigest()
    ext = SIGNATURES[mime][1] if mime in SIGNATURES else GENERATED_EXT[mime]
    key = f"{organization_id}/{digest[:2]}/{uuid.uuid4().hex}{ext}"
    path = root() / key
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as fh:  # «x»: falla si existiera, nunca sobrescribe.
        fh.write(content)
    return key, digest


def read(storage_key: str) -> bytes:
    path = (root() / storage_key).resolve()
    if root().resolve() not in path.parents:
        raise invalid("Ruta de almacenamiento no válida.")
    if not path.exists():
        from app.errors import ApiError
        raise ApiError(410, "file_missing", "El archivo ya no está en el almacenamiento. Restaura el respaldo de storage/.")
    return path.read_bytes()


def verify(storage_key: str, expected_sha256: str) -> dict:
    """Recalcula la huella del archivo guardado y la compara con la registrada."""
    path = (root() / storage_key).resolve()
    if root().resolve() not in path.parents or not path.exists():
        return {"ok": False, "recorded_sha256": expected_sha256, "actual_sha256": None, "detail": "Archivo no encontrado"}
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"ok": actual == expected_sha256, "recorded_sha256": expected_sha256, "actual_sha256": actual,
            "detail": "Íntegro" if actual == expected_sha256 else "La huella no coincide: el archivo fue alterado"}
