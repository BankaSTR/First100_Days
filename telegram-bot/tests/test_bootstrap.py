import base64
import hashlib
from pathlib import Path
import tempfile
import unittest
import zlib

from bootstrap import restore_database
from store import Store


class BootstrapTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = self.root / "source.sqlite3"
        store = Store(source)
        store.execute("INSERT INTO members(id,name,created_at) VALUES (7,'Existing profile',1)")
        store.execute("INSERT INTO meta(key,value) VALUES ('offset','1234')")
        store.close()
        self.data = source.read_bytes()
        self.env = {"BOT_DATABASE_IMPORT": base64.b64encode(zlib.compress(self.data)).decode(), "BOT_DATABASE_IMPORT_SHA256": hashlib.sha256(self.data).hexdigest()}
        self.target = self.root / "persistent" / "bot.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def test_restores_exact_backup_with_profiles_and_offset(self):
        self.assertTrue(restore_database(self.target, self.env))
        self.assertEqual(self.target.read_bytes(), self.data)
        store = Store(self.target)
        try:
            self.assertEqual(store.offset(), 1234)
            self.assertEqual(store.one("SELECT name FROM members WHERE id=7")[0], "Existing profile")
        finally:
            store.close()
        self.assertEqual(list(self.target.parent.glob('.database-transfer-*')), [])

    def test_never_overwrites_existing_database_even_with_invalid_import(self):
        self.target.parent.mkdir()
        self.target.write_bytes(b"existing")
        self.assertFalse(restore_database(self.target, {"BOT_DATABASE_IMPORT": "invalid"}))
        self.assertEqual(self.target.read_bytes(), b"existing")

    def test_missing_snapshot_does_nothing(self):
        self.assertFalse(restore_database(self.target, {}))
        self.assertFalse(self.target.exists())

    def test_bad_checksum_does_not_create_database(self):
        with self.assertRaises(ValueError):
            restore_database(self.target, self.env | {"BOT_DATABASE_IMPORT_SHA256": "wrong"})
        self.assertFalse(self.target.exists())

    def test_bad_compression_and_base64_are_rejected(self):
        for encoded in ('not-base64', base64.b64encode(b'not-zlib').decode()):
            with self.subTest(encoded=encoded), self.assertRaises(ValueError):
                restore_database(self.target, self.env | {"BOT_DATABASE_IMPORT": encoded})
        self.assertFalse(self.target.exists())

    def test_non_sqlite_snapshot_is_rejected(self):
        data = b'not-a-database'
        with self.assertRaises(ValueError):
            restore_database(self.target, {"BOT_DATABASE_IMPORT": base64.b64encode(zlib.compress(data)).decode(), "BOT_DATABASE_IMPORT_SHA256": hashlib.sha256(data).hexdigest()})
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
