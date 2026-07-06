from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from local_n8n.app import app
from local_n8n.compose.template import DEFAULT_IMAGE_REF, LEGACY_DEFAULT_IMAGE_REFS
from local_n8n.core.backup import BackupResult, RestoreResult
from local_n8n.core.dev import DevWipePlan, DevWipeResult, DevWipeTarget
from local_n8n.core.doctor import DoctorCheck
from local_n8n.core.init import InitResult, plan_init
from local_n8n.core.runner import CommandResult
from local_n8n.core.state import StateStore, new_instance_record

runner = CliRunner()
ComposeRunner = Callable[[list[str], Path], CommandResult]


def _patch_compose_runners(monkeypatch: pytest.MonkeyPatch, fake_run: ComposeRunner) -> None:
    monkeypatch.setattr("local_n8n.core.instance.run", fake_run)
    monkeypatch.setattr("local_n8n.core.instance.run_streaming", fake_run)


def _latest_log(home: Path) -> Path:
    logs = sorted((home / "logs").glob("lon-*.log"))
    assert logs
    return logs[-1]


def test_cli_up_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_web_ui_ready", lambda url: True)

    result = runner.invoke(app, ["up"])

    assert result.exit_code == 0
    assert "Ensuring local-n8n instance files" in result.stderr
    assert "Starting Docker container" in result.stderr
    assert "Waiting for n8n web UI" in result.stderr
    assert "n8n is running" in result.stderr


def test_cli_up_friendly_error_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        raise FileNotFoundError("docker")

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_web_ui_ready", lambda url: True)

    result = runner.invoke(app, ["up"])

    assert result.exit_code == 10
    assert "Docker was not found" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_down_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    _patch_compose_runners(monkeypatch, fake_run)

    result = runner.invoke(app, ["down"])

    assert result.exit_code == 0
    assert "Running Docker Compose down" in result.stderr
    assert "n8n container removed" in result.stderr


def test_cli_stop_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    _patch_compose_runners(monkeypatch, fake_run)

    result = runner.invoke(app, ["stop"])

    assert result.exit_code == 0
    assert "Running Docker Compose stop" in result.stderr
    assert "Container kept" in result.stderr


def test_cli_start_fails_fast_when_container_is_not_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        if "ps" in args:
            return CommandResult(args=args, returncode=0, stdout="", stderr="")
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_web_ui_ready", lambda url: True)

    result = runner.invoke(app, ["start"])

    assert result.exit_code == 1
    assert "no container to start" in result.stderr
    assert "Run `lon up --instance default`" in result.stderr


def test_cli_restart_fails_fast_when_container_is_not_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        if "ps" in args:
            return CommandResult(args=args, returncode=0, stdout="", stderr="")
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_web_ui_ready", lambda url: True)

    result = runner.invoke(app, ["restart"])

    assert result.exit_code == 1
    assert "no container to restart" in result.stderr
    assert "Run `lon up --instance default`" in result.stderr


def test_cli_status_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout='[{"State":"running"}]', stderr="")

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.is_web_ui_ready", lambda url: True)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Checking n8n status" in result.stderr
    assert "running" in result.stderr
    assert "reachable" in result.stderr


def test_cli_verbose_prints_diagnostics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout='[{"State":"running"}]', stderr="")

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.is_web_ui_ready", lambda url: True)

    result = runner.invoke(app, ["--verbose", "status"])

    assert result.exit_code == 0
    assert "debug: verbose diagnostics enabled" in result.stderr


def test_cli_writes_persistent_diagnostic_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout='[{"State":"running"}]', stderr="")

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.is_web_ui_ready", lambda url: True)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    log_text = _latest_log(tmp_path).read_text(encoding="utf-8")
    assert "diagnostic log started" in log_text
    assert "progress: Checking n8n status" in log_text
    assert "status instance=default" in log_text


def test_cli_json_status_writes_single_stdout_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout='[{"State":"running"}]', stderr="")

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.is_web_ui_ready", lambda url: True)

    result = runner.invoke(app, ["--json", "status"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["command"] == "status"
    assert payload["container"] == "running"
    assert payload["web_ui"] == "reachable"
    assert "Checking n8n status" in result.stderr


def test_cli_json_error_writes_error_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    result = runner.invoke(app, ["--json", "status"])

    assert result.exit_code == 13
    payload = json.loads(result.stdout)
    assert payload == {
        "error": {
            "exit_code": 13,
            "hint": "Run `lon up` first to create it.",
            "message": "Instance 'default' is not registered.",
        },
        "ok": False,
    }
    assert "Error:" in result.stderr
    assert "Diagnostic log:" in result.stderr
    log_text = _latest_log(tmp_path).read_text(encoding="utf-8")
    assert "Instance 'default' is not registered." in log_text
    assert "Run `lon up` first to create it." in log_text


def test_cli_init_dry_run_outputs_plan_without_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    result = runner.invoke(
        app,
        ["--dry-run", "init", "--instance", "preview", "--port", "5688", "--no-open"],
    )

    assert result.exit_code == 0
    assert "Dry run. No changes made." in result.stderr
    assert "would check: Docker prerequisites" in result.stderr
    assert "would write" in result.stderr
    assert "would open the n8n web UI" not in result.stderr
    assert not (tmp_path / "instances").exists()
    assert not (tmp_path / "state.db").exists()


def test_cli_json_dry_run_init_outputs_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    result = runner.invoke(app, ["--json", "--dry-run", "init", "--instance", "preview"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["command"] == "init"
    assert payload["instance"] == "preview"
    assert payload["would"]["check_prerequisites"] is True
    assert payload["would"]["start"] is True


def test_cli_init_success_prints_owner_setup_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_init_instance(
        instance_name: str,
        port: int | None,
        open_browser: bool,
        progress: Callable[[str], None],
        image_update_confirm: Callable[[str, str], bool] | None,
    ) -> InitResult:
        assert instance_name == "preview"
        assert port == 5688
        assert not open_browser
        assert image_update_confirm is not None
        progress("fake init progress")
        return InitResult(
            plan=plan_init(instance_name=instance_name, port=port, open_browser=open_browser),
            started=True,
            opened=False,
        )

    monkeypatch.setattr("local_n8n.app.init_instance", fake_init_instance)

    result = runner.invoke(app, ["init", "--instance", "preview", "--port", "5688", "--no-open"])

    assert result.exit_code == 0
    assert "fake init progress" in result.stderr
    assert "local-n8n is ready" in result.stderr
    assert "http://localhost:5688" in result.stderr
    assert "redirects to /setup" in result.stderr


def test_cli_backup_dry_run_outputs_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    result = runner.invoke(app, ["--dry-run", "backup", "--instance", "preview"])

    assert result.exit_code == 0
    assert "Dry run. No changes made." in result.stderr
    assert "would ask before stopping n8n" in result.stderr
    assert "would write bundle" in result.stderr


def test_cli_backup_cancels_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    result = runner.invoke(app, ["backup"], input="\n")

    assert result.exit_code == 1
    assert "Backup cancelled" in result.stderr


def test_cli_backup_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_backup_instance(
        instance_name: str,
        *,
        passphrase: str,
        output_path: Path | None,
        progress: Callable[[str], None],
    ) -> BackupResult:
        assert instance_name == "default"
        assert passphrase == "backup-passphrase"
        assert output_path == tmp_path / "manual.n8nbundle"
        progress("fake backup progress")
        return BackupResult(
            instance="default",
            bundle_path=tmp_path / "manual.n8nbundle",
            checksum="abc123",
            size=42,
            recovery_code="recovery-code",
            restarted=True,
        )

    monkeypatch.setattr("local_n8n.app._prompt_backup_passphrase", lambda: "backup-passphrase")
    monkeypatch.setattr("local_n8n.app.backup_instance", fake_backup_instance)

    result = runner.invoke(
        app,
        ["backup", "--yes", "--output", str(tmp_path / "manual.n8nbundle")],
    )

    assert result.exit_code == 0
    assert "fake backup progress" in result.stderr
    assert "Encrypted backup created" in result.stderr
    assert "Recovery code created" in result.stderr
    assert "recovery-code" in result.stderr
    log_text = _latest_log(tmp_path).read_text(encoding="utf-8")
    assert "progress: fake backup progress" in log_text
    assert "recovery-code" not in log_text


def test_cli_restore_dry_run_outputs_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    result = runner.invoke(app, ["--dry-run", "restore", str(tmp_path / "backup.n8nbundle")])

    assert result.exit_code == 0
    assert "Dry run. No changes made." in result.stderr
    assert "would decrypt bundle and verify manifest" in result.stderr
    assert "would restore Docker volume" in result.stderr


def test_cli_restore_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_restore_instance(
        bundle_path: Path,
        *,
        secret: str,
        replace: bool,
        port: int | None,
        progress: Callable[[str], None],
    ) -> RestoreResult:
        assert bundle_path == tmp_path / "backup.n8nbundle"
        assert secret == "restore-secret"
        assert replace
        assert port == 5691
        progress("fake restore progress")
        return RestoreResult(
            instance="default",
            url="http://localhost:5691",
            compose_path=tmp_path / "instances/default/docker-compose.yml",
            env_path=tmp_path / "instances/default/.env",
            volume_name="n8n_default_data.g1",
            replaced=True,
            pre_restore_backup=tmp_path / "pre-restore.n8nbundle",
        )

    monkeypatch.setattr("local_n8n.app._prompt_restore_secret", lambda: "restore-secret")
    monkeypatch.setattr("local_n8n.app.restore_instance", fake_restore_instance)

    result = runner.invoke(
        app,
        ["restore", str(tmp_path / "backup.n8nbundle"), "--replace", "--port", "5691"],
    )

    assert result.exit_code == 0
    assert "fake restore progress" in result.stderr
    assert "Restored n8n" in result.stderr
    assert "pre-restore backup" in result.stderr


def test_cli_recovery_show_dry_run_outputs_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    result = runner.invoke(app, ["--dry-run", "recovery", "show", "--instance", "default"])

    assert result.exit_code == 0
    assert "Dry run. No changes made." in result.stderr
    assert "would prompt for backup passphrase" in result.stderr
    assert "would print the recovery code" in result.stderr


def test_cli_recovery_show_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_reveal_recovery_code(instance_name: str, *, passphrase: str) -> str:
        assert instance_name == "default"
        assert passphrase == "backup-passphrase"
        return "recovery-code"

    monkeypatch.setattr(
        "local_n8n.app._prompt_existing_backup_passphrase", lambda: "backup-passphrase"
    )
    monkeypatch.setattr("local_n8n.app.reveal_recovery_code", fake_reveal_recovery_code)

    result = runner.invoke(app, ["recovery", "show"])

    assert result.exit_code == 0
    assert "Recovery code:" in result.stderr
    assert "recovery-code" in result.stderr


def test_cli_recovery_rotate_dry_run_outputs_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    result = runner.invoke(app, ["--dry-run", "recovery", "rotate", "--instance", "default"])

    assert result.exit_code == 0
    assert "Dry run. No changes made." in result.stderr
    assert "would unlock existing recovery material" in result.stderr
    assert "would print the new recovery code" in result.stderr


def test_cli_recovery_rotate_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_rotate_recovery_code(instance_name: str, *, passphrase: str) -> str:
        assert instance_name == "default"
        assert passphrase == "backup-passphrase"
        return "new-recovery-code"

    monkeypatch.setattr(
        "local_n8n.app._prompt_existing_backup_passphrase", lambda: "backup-passphrase"
    )
    monkeypatch.setattr("local_n8n.app.rotate_recovery_code", fake_rotate_recovery_code)

    result = runner.invoke(app, ["recovery", "rotate"])

    assert result.exit_code == 0
    assert "New recovery code created" in result.stderr
    assert "new-recovery-code" in result.stderr


def test_cli_passphrase_change_dry_run_outputs_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    result = runner.invoke(app, ["--dry-run", "passphrase", "change", "--instance", "default"])

    assert result.exit_code == 0
    assert "Dry run. No changes made." in result.stderr
    assert "would prompt for current backup passphrase" in result.stderr
    assert "would prompt for new backup passphrase" in result.stderr
    assert "would not rekey existing backup bundles" in result.stderr


def test_cli_passphrase_change_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_change_backup_passphrase(
        instance_name: str,
        *,
        current_passphrase: str,
        new_passphrase: str,
    ) -> None:
        assert instance_name == "default"
        assert current_passphrase == "old-passphrase"
        assert new_passphrase == "new-passphrase"

    monkeypatch.setattr(
        "local_n8n.app._prompt_existing_backup_passphrase", lambda: "old-passphrase"
    )
    monkeypatch.setattr("local_n8n.app._prompt_new_backup_passphrase", lambda: "new-passphrase")
    monkeypatch.setattr("local_n8n.app.change_backup_passphrase", fake_change_backup_passphrase)

    result = runner.invoke(app, ["passphrase", "change"])

    assert result.exit_code == 0
    assert "Backup passphrase changed." in result.stderr
    assert "Existing backup bundles were not rekeyed." in result.stderr


def test_cli_passphrase_reset_dry_run_outputs_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    result = runner.invoke(app, ["--dry-run", "passphrase", "reset", "--instance", "default"])

    assert result.exit_code == 0
    assert "Dry run. No changes made." in result.stderr
    assert "would require a running, reachable n8n instance" in result.stderr
    assert "would print the new recovery code once" in result.stderr


def test_cli_passphrase_reset_cancelled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    result = runner.invoke(app, ["passphrase", "reset"], input="n\n")

    assert result.exit_code == 1
    assert "Passphrase reset cancelled." in result.stderr


def test_cli_passphrase_reset_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fake_reset_backup_passphrase(
        instance_name: str,
        *,
        new_passphrase: str,
        progress: Callable[[str], None],
    ) -> str:
        assert instance_name == "default"
        assert new_passphrase == "new-passphrase"
        progress("fake reset progress")
        return "fresh-recovery-code"

    monkeypatch.setattr("local_n8n.app._prompt_new_backup_passphrase", lambda: "new-passphrase")
    monkeypatch.setattr("local_n8n.app.reset_backup_passphrase", fake_reset_backup_passphrase)

    result = runner.invoke(app, ["--yes", "passphrase", "reset"])

    assert result.exit_code == 0
    assert "fake reset progress" in result.stderr
    assert "Backup passphrase reset" in result.stderr
    assert "fresh-recovery-code" in result.stderr


def test_cli_up_prompts_for_legacy_image_update_with_yes_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    legacy_image_ref = LEGACY_DEFAULT_IMAGE_REFS[0]
    with StateStore(tmp_path / "state.db") as state:
        state.upsert_instance(
            new_instance_record(
                name="default",
                compose_path=instance_dir / "docker-compose.yml",
                data_volume="n8n_default_data",
                port=5678,
                image_ref=legacy_image_ref,
                enc_key_ref=instance_dir / ".env",
                created_at="2026-07-01T00:00:00Z",
            )
        )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.wait_for_web_ui_ready", lambda url: True)

    result = runner.invoke(app, ["up"], input="\n")

    assert result.exit_code == 0
    assert "n8n image update available" in result.stderr
    assert "Update n8n image now? (Y/n)" in result.stderr
    assert "n8n is running" in result.stderr
    with StateStore(tmp_path / "state.db") as state:
        record = state.get_instance("default")
    assert record is not None
    assert record.image_ref == DEFAULT_IMAGE_REF


def test_cli_up_can_decline_legacy_image_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    legacy_image_ref = LEGACY_DEFAULT_IMAGE_REFS[0]
    with StateStore(tmp_path / "state.db") as state:
        state.upsert_instance(
            new_instance_record(
                name="default",
                compose_path=instance_dir / "docker-compose.yml",
                data_volume="n8n_default_data",
                port=5678,
                image_ref=legacy_image_ref,
                enc_key_ref=instance_dir / ".env",
                created_at="2026-07-01T00:00:00Z",
            )
        )

    def fail_run(args: list[str], cwd: Path) -> CommandResult:
        raise AssertionError("up should not run Docker after declined image update")

    _patch_compose_runners(monkeypatch, fail_run)

    result = runner.invoke(app, ["up"], input="n\n")

    assert result.exit_code == 1
    assert "n8n image update cancelled" in result.stderr
    with StateStore(tmp_path / "state.db") as state:
        record = state.get_instance("default")
    assert record is not None
    assert record.image_ref == legacy_image_ref


def test_cli_dev_wipe_defaults_to_no_without_typed_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fail_wipe(*args: object, **kwargs: object) -> None:
        raise AssertionError("wipe_dev should not run without typed yes")

    monkeypatch.setattr("local_n8n.app.wipe_dev", fail_wipe)

    result = runner.invoke(app, ["dev", "wipe"], input="\n")

    assert result.exit_code == 1
    assert "Development wipe warning" in result.stderr
    assert "Type yes to continue" in result.stderr
    assert "Development wipe cancelled" in result.stderr


def test_cli_dev_wipe_with_images_defaults_to_no_without_typed_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fail_wipe(*args: object, **kwargs: object) -> None:
        raise AssertionError("wipe_dev should not run without typed yes")

    monkeypatch.setattr("local_n8n.app.wipe_dev", fail_wipe)

    result = runner.invoke(app, ["dev", "wipe", "--images"], input="\n")

    assert result.exit_code == 1
    assert "Development wipe warning" in result.stderr
    assert "It will also delete known local-n8n Docker images" in result.stderr
    assert "Type yes to continue" in result.stderr
    assert "Development wipe cancelled" in result.stderr


def test_cli_dev_wipe_dry_run_does_not_require_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    (tmp_path / "instances" / "preview").mkdir(parents=True)

    result = runner.invoke(app, ["--dry-run", "dev", "wipe"])

    assert result.exit_code == 0
    assert "Development wipe preview" in result.stderr
    assert "would remove project: local-n8n-preview" in result.stderr
    assert (tmp_path / "instances" / "preview").exists()


def test_cli_dev_wipe_dry_run_with_images_lists_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    (tmp_path / "instances" / "preview").mkdir(parents=True)

    result = runner.invoke(app, ["--dry-run", "dev", "wipe", "--images"])

    assert result.exit_code == 0
    assert "would remove image" in result.stderr
    assert DEFAULT_IMAGE_REF in result.stderr


def test_cli_dev_wipe_dry_run_with_images_lists_default_image_without_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    result = runner.invoke(app, ["--dry-run", "dev", "wipe", "--images"])

    assert result.exit_code == 0
    assert "would remove image" in result.stderr
    assert "Nothing local-n8n related found" not in result.stderr


def test_cli_dev_wipe_typed_yes_runs_wipe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    target = DevWipeTarget(
        name="preview",
        project_name="local-n8n-preview",
        compose_path=tmp_path / "instances" / "preview" / "docker-compose.yml",
        volume_name="n8n_preview_data",
    )
    plan = DevWipePlan(
        config_home=tmp_path,
        targets=(target,),
        volume_names=("n8n_preview_data",),
        image_refs=(),
        local_paths=(tmp_path / "instances", tmp_path / "state.db"),
    )

    monkeypatch.setattr("local_n8n.app.plan_dev_wipe", lambda include_images=False: plan)

    def fake_wipe(
        plan: DevWipePlan,
        progress: Callable[[str], None] | None = None,
    ) -> DevWipeResult:
        if progress is not None:
            progress("fake wipe progress")
        return DevWipeResult(
            plan=plan,
            docker_commands=(("docker", "compose", "down"),),
            deleted_paths=(tmp_path / "instances",),
        )

    monkeypatch.setattr("local_n8n.app.wipe_dev", fake_wipe)

    result = runner.invoke(app, ["dev", "wipe"], input="yes\n")

    assert result.exit_code == 0
    assert "Development wipe confirmed" in result.stderr
    assert "fake wipe progress" in result.stderr
    assert "local-n8n development data wiped" in result.stderr


def test_cli_dev_wipe_yes_with_images_runs_wipe_without_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    plan = DevWipePlan(
        config_home=tmp_path,
        targets=(),
        volume_names=(),
        image_refs=("example.test/n8n:custom@sha256:abc",),
        local_paths=(),
    )
    include_images_values: list[bool] = []

    def fake_plan(include_images: bool = False) -> DevWipePlan:
        include_images_values.append(include_images)
        return plan

    def fake_wipe(
        plan: DevWipePlan,
        progress: Callable[[str], None] | None = None,
    ) -> DevWipeResult:
        return DevWipeResult(
            plan=plan,
            docker_commands=(("docker", "image", "rm"),),
            deleted_paths=(),
        )

    monkeypatch.setattr("local_n8n.app.plan_dev_wipe", fake_plan)
    monkeypatch.setattr("local_n8n.app.wipe_dev", fake_wipe)

    result = runner.invoke(app, ["dev", "wipe", "--yes", "--images"])

    assert result.exit_code == 0
    assert include_images_values == [True]
    assert "Development wipe warning" not in result.stderr
    assert "images: 1" in result.stderr


def test_cli_dev_wipe_yes_with_images_after_state_gone_removes_default_image_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    captured: list[list[str]] = []

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        captured.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.dev.run", fake_run)
    monkeypatch.setattr("local_n8n.core.dev.run_streaming", fake_run)

    result = runner.invoke(app, ["dev", "wipe", "--yes", "--images"])

    assert result.exit_code == 0
    assert "images: 1" in result.stderr
    assert ["docker", "image", "rm", "--force", DEFAULT_IMAGE_REF] in captured


def test_cli_dry_run_up_does_not_call_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    def fail_up(instance_name: str, port: int | None = None) -> None:
        raise AssertionError("up_instance should not be called during dry-run")

    monkeypatch.setattr("local_n8n.app.up_instance", fail_up)

    result = runner.invoke(app, ["--dry-run", "up", "--instance", "preview", "--port", "5688"])

    assert result.exit_code == 0
    assert "Dry run. No changes made." in result.stderr
    assert "would run: docker compose" in result.stderr
    assert not (tmp_path / "instances").exists()
    assert not (tmp_path / "state.db").exists()


def test_cli_json_dry_run_up_outputs_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    result = runner.invoke(app, ["--json", "--dry-run", "up", "--instance", "preview"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["command"] == "up"
    assert payload["instance"] == "preview"
    assert payload["would"]["wait_for_web_ui"] is True
    assert payload["would"]["docker_commands"][0][-2:] == ["up", "-d"]


def test_cli_yes_global_flag_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    instance_dir = tmp_path / "instances" / "default"
    instance_dir.mkdir(parents=True)
    (instance_dir / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout='[{"State":"running"}]', stderr="")

    _patch_compose_runners(monkeypatch, fake_run)
    monkeypatch.setattr("local_n8n.core.instance.is_web_ui_ready", lambda url: True)

    result = runner.invoke(app, ["--yes", "status"])

    assert result.exit_code == 0
    assert "Checking n8n status" in result.stderr


def test_cli_list_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))
    with StateStore(tmp_path / "state.db") as state:
        state.upsert_instance(
            new_instance_record(
                name="manual-check",
                compose_path=tmp_path / "instances" / "manual-check" / "docker-compose.yml",
                data_volume="n8n_manual-check_data",
                port=5683,
                enc_key_ref=tmp_path / "instances" / "manual-check" / ".env",
                created_at="2026-07-01T00:00:00Z",
            )
        )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        return CommandResult(args=args, returncode=0, stdout='[{"State":"running"}]', stderr="")

    _patch_compose_runners(monkeypatch, fake_run)

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "manual-check" in result.stderr
    assert "running" in result.stderr
    assert "Use `lon status --instance <name>` for details." in result.stderr


def test_cli_list_empty_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_N8N_HOME", str(tmp_path))

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "No local-n8n instances yet" in result.stderr
    assert "Use `lon status --instance <name>`" not in result.stderr


def test_cli_doctor_failure_exits_with_check_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("local_n8n.core.doctor.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "local_n8n.core.doctor._port_check",
        lambda port: DoctorCheck("Port 0", True, "available"),
    )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        raise FileNotFoundError("docker")

    monkeypatch.setattr("local_n8n.core.doctor.run", fake_run)

    result = runner.invoke(app, ["doctor", "--port", "0"])

    assert result.exit_code == 10
    assert "Docker CLI" in result.stderr


def test_cli_doctor_fix_dry_run_previews_prereq_fixes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("local_n8n.core.doctor.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "local_n8n.core.doctor._port_check",
        lambda port: DoctorCheck("Port 0", True, "available"),
    )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        raise FileNotFoundError("docker")

    monkeypatch.setattr("local_n8n.core.doctor.run", fake_run)

    result = runner.invoke(app, ["--dry-run", "doctor", "--fix", "--port", "0"])

    assert result.exit_code == 0
    assert "Dry run. No changes made." in result.stderr
    assert "would plan: install-docker" in result.stderr
    assert "Docker CLI is not installed." in result.stderr


def test_cli_doctor_fix_without_confirmation_cancels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("local_n8n.core.doctor.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "local_n8n.core.doctor._port_check",
        lambda port: DoctorCheck("Port 0", True, "available"),
    )

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        raise FileNotFoundError("docker")

    monkeypatch.setattr("local_n8n.core.doctor.run", fake_run)

    result = runner.invoke(app, ["doctor", "--fix", "--port", "0"], input="\n")

    assert result.exit_code == 1
    assert "Apply prerequisite fixes? (y/N)" in result.stderr
    assert "Prerequisite fixes cancelled." in result.stderr


def test_cli_doctor_fix_yes_runs_executable_prereq_fix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("local_n8n.core.doctor.shutil.which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        "local_n8n.core.doctor._port_check",
        lambda port: DoctorCheck("Port 0", True, "available"),
    )
    monkeypatch.setattr("local_n8n.core.doctor._is_wsl", lambda: True)

    def fake_run(args: list[str], cwd: Path) -> CommandResult:
        if args == ["docker", "info"]:
            return CommandResult(args=args, returncode=1, stdout="", stderr="daemon unavailable")
        if args == ["docker", "info", "--format", "{{json .}}"]:
            return CommandResult(args=args, returncode=1, stdout="", stderr="daemon unavailable")
        if args == ["docker", "compose", "version"]:
            return CommandResult(
                args=args, returncode=0, stdout="Docker Compose version v5.1.4", stderr=""
            )
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    commands: list[list[str]] = []

    def fake_runner(args: list[str], cwd: Path) -> CommandResult:
        commands.append(args)
        return CommandResult(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("local_n8n.core.doctor.run", fake_run)
    monkeypatch.setattr("local_n8n.bootstrap.docker.run_streaming", fake_runner)

    result = runner.invoke(app, ["--yes", "doctor", "--fix", "--port", "0"])

    assert result.exit_code == 0
    assert commands == [["sudo", "service", "docker", "start"]]
    assert "Applying prerequisite fixes" in result.stderr
    assert "Prerequisite fix step finished" in result.stderr
