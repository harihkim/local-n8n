# local-n8n

`local-n8n` provides the `lon` CLI for running a local, self-hosted n8n instance with encrypted, portable backups.

The current release is an alpha. It focuses on the local lifecycle and encrypted portability:

- create and start an n8n Docker Compose instance
- initialize a new instance with a guided first-run command
- stop, start, restart, and remove the container while keeping data
- inspect status and logs
- manage named local instances
- run read-only prerequisite checks
- use script-friendly global flags such as `--json` and `--dry-run`
- create encrypted `.n8nbundle` backups
- restore an instance from an encrypted bundle
- manage recovery codes and backup passphrases

## Install

The latest tagged prerelease is `v0.1.0a3`; it contains the Phase 3 backup/restore/admin MVP.

Install the latest tagged prerelease with `uv`:

```bash
uv tool install git+https://github.com/harihkim/local-n8n.git@v0.1.0a3
```

PyPI publishing is prepared but not active for end users until Phase 4 is complete and Linux, macOS, and
Windows prerequisite support has been validated.

For development inside a checkout, use:

```bash test
uv run lon --help
```

## Start Here

New users should begin with the [Quickstart](quickstart.md).

If you are scripting against the CLI, read the [Command Reference](commands.md). If something feels off, check [Troubleshooting](troubleshooting.md).

## Versioned Docs

The documentation site is versioned:

- `latest` is the default and follows the newest released docs.
- `dev` follows unreleased work on `main`.
- release versions such as `v0.1.0a3` remain browsable.

For normal use, stay on `latest`.
