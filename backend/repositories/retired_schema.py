"""One-time removal of retired tables, before any other startup migration."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile


# Child tables first. Never infer ownership from a prefix.
_RETIRED = (
    "tabletop_history", "tabletop_requests", "tabletop_migrations",
    "tabletop_drafts", "tabletop_games", "tabletop_settings",
)


def _verified_backup(path, tables):
    # The caller holds BEGIN IMMEDIATE. A separate reader can copy the latest
    # committed pages (including WAL) while the lock excludes competing writers.
    with NamedTemporaryFile(dir=path.parent, prefix=f"{path.name}.pre-125-",
                            suffix=".pending", delete=False) as file:
        backup = Path(file.name)
    try:
        with closing(sqlite3.connect(path)) as source:
            with closing(sqlite3.connect(backup)) as target:
                source.backup(target)
                target.execute("PRAGMA journal_mode=DELETE")
            with closing(sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True)) as saved:
                if saved.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise sqlite3.DatabaseError("Повреждена резервная копия SQLite.")
                for table in tables:
                    query = f'SELECT count(*) FROM "{table}"'
                    if source.execute(query).fetchone() != saved.execute(query).fetchone():
                        raise sqlite3.DatabaseError(f"Неполная резервная копия таблицы {table}.")
        # Persist the new directory entry before permitting a destructive commit.
        with backup.open("rb+") as file:
            os.fsync(file.fileno())
        backup.replace(backup.with_suffix(".bak"))
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    except BaseException:
        backup.unlink(missing_ok=True)
        raise


def remove_retired_tables(storage):
    with storage.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        tables = [table for table in _RETIRED if table in existing]
        if tables:
            # SQLite DROP can execute ON DELETE CASCADE, even across tables we
            # intend to keep. Fail closed on unexpected cross-schema references.
            for table in existing.difference(tables):
                parents = db.execute('SELECT "table" FROM pragma_foreign_key_list(?)', (table,))
                if any(parent[0].lower() in tables for parent in parents):
                    raise sqlite3.DatabaseError(f"Внешняя ссылка на удаляемую схему в {table}.")
            _verified_backup(storage.path.resolve(), tables)
            for table in tables:
                db.execute(f'DROP TABLE "{table}"')
