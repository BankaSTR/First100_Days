"""Optional one-time transfer of a private SQLite backup through hosting variables."""
import base64
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import zlib

MAX_DATABASE_BYTES = 20 * 1024 * 1024


def restore_database(path: Path, environ=None):
    environ = os.environ if environ is None else environ
    encoded = environ.get("BOT_DATABASE_IMPORT", "")
    if not encoded or path.exists():
        return False
    try:
        if len(encoded) > 2 * 1024 * 1024:
            raise ValueError("Snapshot too large")
        compressed = base64.b64decode(encoded, validate=True)
        inflater = zlib.decompressobj()
        data = inflater.decompress(compressed, MAX_DATABASE_BYTES + 1)
        if len(data) > MAX_DATABASE_BYTES or not inflater.eof or inflater.unused_data:
            raise ValueError("Invalid compressed snapshot")
        expected = environ.get("BOT_DATABASE_IMPORT_SHA256", "")
        if not expected or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Snapshot checksum mismatch")
        if not data.startswith(b"SQLite format 3\x00"):
            raise ValueError("Not SQLite")
    except (ValueError, zlib.error):
        raise ValueError("Не удалось проверить перенос базы. Проверьте BOT_DATABASE_IMPORT и BOT_DATABASE_IMPORT_SHA256.") from None
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".database-transfer-", suffix=".sqlite3", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        with closing(sqlite3.connect(temporary.as_uri() + "?mode=ro&immutable=1", uri=True)) as check:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Переносимая база повреждена.")
            tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"members", "applications", "flows", "outbox", "meta"}.issubset(tables):
                raise ValueError("В переносимой базе нет таблиц бота.")
        # Windows rename and POSIX link both refuse to replace an existing file.
        try:
            if os.name == "nt":
                os.rename(temporary, path)
            else:
                os.link(temporary, path)
        except FileExistsError:
            return False
        return True
    finally:
        temporary.unlink(missing_ok=True)
