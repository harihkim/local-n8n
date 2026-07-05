from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from local_n8n.compose.template import DEFAULT_IMAGE_REF
from local_n8n.core.config import config_home

SCHEMA_VERSION = 2


@dataclass(frozen=True)
class InstanceRecord:
    name: str
    compose_path: Path
    data_volume: str
    port: int
    image_ref: str
    enc_key_ref: Path
    created_at: str
    last_started_at: str | None = None
    base_url: str | None = None
    db_type: str = "sqlite"
    n8n_version: str | None = None


@dataclass(frozen=True)
class BackupRecord:
    instance: str
    created_at: str
    location: Path
    checksum: str
    size: int
    n8n_version: str | None = None
    remote_id: int | None = None
    id: int | None = None


class StateStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._migrate()

    @classmethod
    def open_default(cls) -> Self:
        return cls(config_home() / "state.db")

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def get_instance(self, name: str) -> InstanceRecord | None:
        row = self._conn.execute(
            """
            SELECT name, compose_path, data_volume, port, base_url, db_type, image_ref,
                   n8n_version, enc_key_ref, created_at, last_started_at
            FROM instances
            WHERE name = ?
            """,
            (name,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_instance(row)

    def list_instances(self) -> list[InstanceRecord]:
        rows = self._conn.execute(
            """
            SELECT name, compose_path, data_volume, port, base_url, db_type, image_ref,
                   n8n_version, enc_key_ref, created_at, last_started_at
            FROM instances
            ORDER BY name
            """
        ).fetchall()
        return [_row_to_instance(row) for row in rows]

    def upsert_instance(self, record: InstanceRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO instances (
                name, compose_path, data_volume, port, base_url, db_type, image_ref,
                n8n_version, enc_key_ref, created_at, last_started_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                compose_path = excluded.compose_path,
                data_volume = excluded.data_volume,
                port = excluded.port,
                base_url = excluded.base_url,
                db_type = excluded.db_type,
                image_ref = excluded.image_ref,
                n8n_version = excluded.n8n_version,
                enc_key_ref = excluded.enc_key_ref,
                last_started_at = excluded.last_started_at
            """,
            (
                record.name,
                str(record.compose_path),
                record.data_volume,
                record.port,
                record.base_url,
                record.db_type,
                record.image_ref,
                record.n8n_version,
                str(record.enc_key_ref),
                record.created_at,
                record.last_started_at,
            ),
        )
        self._conn.commit()

    def record_started(self, name: str, started_at: str | None = None) -> None:
        self._conn.execute(
            "UPDATE instances SET last_started_at = ? WHERE name = ?",
            (started_at or utc_now(), name),
        )
        self._conn.commit()

    def record_backup(self, record: BackupRecord) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO backups (
                instance, created_at, location, remote_id, checksum, size, n8n_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.instance,
                record.created_at,
                str(record.location),
                record.remote_id,
                record.checksum,
                record.size,
                record.n8n_version,
            ),
        )
        self._conn.commit()
        backup_id = cursor.lastrowid
        if backup_id is None:
            raise RuntimeError("SQLite did not return a backup id")
        return backup_id

    def list_backups(self, instance: str | None = None) -> list[BackupRecord]:
        if instance is None:
            rows = self._conn.execute(
                """
                SELECT id, instance, created_at, location, remote_id, checksum, size, n8n_version
                FROM backups
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT id, instance, created_at, location, remote_id, checksum, size, n8n_version
                FROM backups
                WHERE instance = ?
                ORDER BY created_at DESC, id DESC
                """,
                (instance,),
            ).fetchall()
        return [_row_to_backup(row) for row in rows]

    def _migrate(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS instances (
              name TEXT PRIMARY KEY,
              compose_path TEXT NOT NULL,
              data_volume TEXT NOT NULL,
              port INTEGER NOT NULL,
              base_url TEXT,
              db_type TEXT NOT NULL DEFAULT 'sqlite',
              image_ref TEXT NOT NULL,
              n8n_version TEXT,
              enc_key_ref TEXT NOT NULL,
              created_at TEXT NOT NULL,
              last_started_at TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backups (
              id INTEGER PRIMARY KEY,
              instance TEXT NOT NULL REFERENCES instances(name),
              created_at TEXT NOT NULL,
              location TEXT NOT NULL,
              remote_id INTEGER,
              checksum TEXT NOT NULL,
              size INTEGER NOT NULL,
              n8n_version TEXT
            )
            """
        )
        self._conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self._conn.commit()


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_instance_record(
    *,
    name: str,
    compose_path: Path,
    data_volume: str,
    port: int,
    enc_key_ref: Path,
    image_ref: str = DEFAULT_IMAGE_REF,
    created_at: str | None = None,
    last_started_at: str | None = None,
) -> InstanceRecord:
    return InstanceRecord(
        name=name,
        compose_path=compose_path,
        data_volume=data_volume,
        port=port,
        image_ref=image_ref,
        enc_key_ref=enc_key_ref,
        created_at=created_at or utc_now(),
        last_started_at=last_started_at,
    )


def _row_to_instance(row: sqlite3.Row) -> InstanceRecord:
    return InstanceRecord(
        name=row["name"],
        compose_path=Path(row["compose_path"]),
        data_volume=row["data_volume"],
        port=row["port"],
        base_url=row["base_url"],
        db_type=row["db_type"],
        image_ref=row["image_ref"],
        n8n_version=row["n8n_version"],
        enc_key_ref=Path(row["enc_key_ref"]),
        created_at=row["created_at"],
        last_started_at=row["last_started_at"],
    )


def _row_to_backup(row: sqlite3.Row) -> BackupRecord:
    return BackupRecord(
        id=row["id"],
        instance=row["instance"],
        created_at=row["created_at"],
        location=Path(row["location"]),
        remote_id=row["remote_id"],
        checksum=row["checksum"],
        size=row["size"],
        n8n_version=row["n8n_version"],
    )
