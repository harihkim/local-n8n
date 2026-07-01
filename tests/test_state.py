from __future__ import annotations

from pathlib import Path

from local_n8n.core.state import StateStore, new_instance_record


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
