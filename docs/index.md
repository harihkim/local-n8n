# local-n8n

`local-n8n` provides the `lon` CLI for running a local, self-hosted n8n instance with a path toward encrypted, portable backups.

The current release is an alpha. It focuses on the local lifecycle:

- create and start an n8n Docker Compose instance
- initialize a new instance with a guided first-run command
- stop, start, restart, and remove the container while keeping data
- inspect status and logs
- manage named local instances
- run read-only prerequisite checks
- use script-friendly global flags such as `--json` and `--dry-run`

## Install

Install the current GitHub prerelease with `uv`:

```bash
uv tool install git+https://github.com/harihkim/local-n8n.git@v0.1.0a2
```

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
- release versions such as `v0.1.0a2` remain browsable.

For normal use, stay on `latest`.
