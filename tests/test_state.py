from __future__ import annotations

from pathlib import Path

from local_n8n.core.state import BackupRecord, StateStore, new_instance_record


def test_state_store_crud_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    with StateStore(db_path) as state:
        record = new_instance_record(
            name="default",
            compose_path=tmp_path / "instances/default/docker-compose.yml",
            data_volume="n8n_default_data",
            port=5678,
            enc_key_ref=tmp_path / "instances/default/.env",
            created_at="2026-07-01T00:00:00Z",
        )

        state.upsert_instance(record)
        state.record_started("default", "2026-07-01T00:01:00Z")

        loaded = state.get_instance("default")

    assert loaded is not None
    assert loaded.name == "default"
    assert loaded.port == 5678
    assert loaded.data_volume == "n8n_default_data"
    assert loaded.last_started_at == "2026-07-01T00:01:00Z"


def test_state_store_lists_instances_by_name(tmp_path: Path) -> None:
    with StateStore(tmp_path / "state.db") as state:
        for name in ["beta", "alpha"]:
            state.upsert_instance(
                new_instance_record(
                    name=name,
                    compose_path=tmp_path / name / "docker-compose.yml",
                    data_volume=f"n8n_{name}_data",
                    port=5678,
                    enc_key_ref=tmp_path / name / ".env",
                    created_at="2026-07-01T00:00:00Z",
                )
            )

        names = [record.name for record in state.list_instances()]

    assert names == ["alpha", "beta"]


def test_state_store_records_backups(tmp_path: Path) -> None:
    with StateStore(tmp_path / "state.db") as state:
        state.upsert_instance(
            new_instance_record(
                name="default",
                compose_path=tmp_path / "instances/default/docker-compose.yml",
                data_volume="n8n_default_data",
                port=5678,
                enc_key_ref=tmp_path / "instances/default/.env",
                created_at="2026-07-01T00:00:00Z",
            )
        )

        backup_id = state.record_backup(
            BackupRecord(
                instance="default",
                created_at="2026-07-01T00:02:00Z",
                location=tmp_path / "backups/default.n8nbundle",
                checksum="abc123",
                size=42,
                n8n_version="1.2.3",
            )
        )

        backups = state.list_backups("default")

    assert backup_id == 1
    assert len(backups) == 1
    assert backups[0].id == 1
    assert backups[0].instance == "default"
    assert backups[0].checksum == "abc123"
    assert backups[0].size == 42
    assert backups[0].n8n_version == "1.2.3"
