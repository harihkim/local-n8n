# local-n8n (`lon`)

`local-n8n` provides the `lon` CLI for running a local, self-hosted n8n instance with encrypted,
portable backups.

The project is in alpha. The current prerelease focuses on the local lifecycle and encrypted portability:
create an n8n Docker Compose instance, manage it from the terminal, back it up into an encrypted
`.n8nbundle`, and restore it on another machine.

## Documentation

- [Latest docs](https://harihkim.github.io/local-n8n/latest/)
- [Quickstart](https://harihkim.github.io/local-n8n/latest/quickstart/)
- [Command reference](https://harihkim.github.io/local-n8n/latest/commands/)
- [Troubleshooting](https://harihkim.github.io/local-n8n/latest/troubleshooting/)

If GitHub Pages is not enabled yet, the same documentation is available in [`docs/`](docs/).

## Status

Latest prerelease: `v0.1.0a3`

Included today:

- guided first run with `lon init`
- Docker Compose lifecycle commands: `up`, `down`, `stop`, `start`, and `restart`
- instance inspection with `status`, `list`, `logs`, `open`, and `doctor`
- encrypted backup and restore with `.n8nbundle` files
- recovery-code and backup-passphrase admin commands
- JSON, dry-run, yes, verbose, and persistent diagnostic log support

Not included yet:

- automatic Docker or WSL installation
- hosted sync or a managed backend
- tunnel/public webhook setup
- remote backup targets
- PyPI publishing

## Requirements

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/)
- Docker Engine or Docker Desktop with a working `docker compose`

On Windows, run `lon` inside WSL Ubuntu with Docker available to that distro.

## Install

Install the latest GitHub prerelease with `uv`:

```bash
uv tool install git+https://github.com/harihkim/local-n8n.git@v0.1.0a3
```

For development inside this checkout:

```bash
uv run lon --help
```

## Quickstart

Create and start the default local n8n instance:

```bash
lon init
```

Inspect it:

```bash
lon status
lon logs
lon open
```

Stop or remove the container while keeping the Docker data volume:

```bash
lon stop
lon start
lon down
lon up
```

Create an encrypted backup:

```bash
lon backup
```

Restore from a backup bundle:

```bash
lon restore /path/to/default-2026-07-05T12-00-00Z.n8nbundle
```

## Encrypted Backups

`lon backup` briefly stops n8n for a consistent Docker-volume snapshot, writes an encrypted
`.n8nbundle`, and restarts n8n if it was running before.

The first backup asks for a backup passphrase and prints a recovery code once. Future backups reuse local
`recovery.wrapped` material so they do not create a new recovery code unless you rotate or reset recovery
material explicitly.

Useful admin commands:

```bash
lon recovery show
lon recovery rotate
lon passphrase change
lon passphrase reset
```

Existing backup bundles are never rekeyed by rotate/change/reset. Each bundle remains tied to the unlock
material that was active when it was created.

## Files and Logs

By default, `lon` stores local state under:

```text
~/.config/local-n8n/
```

Important paths:

- `instances/<name>/docker-compose.yml`
- `instances/<name>/.env`
- `instances/<name>/recovery.wrapped`
- `state.db`
- `backups/`
- `logs/`

Set `LOCAL_N8N_HOME` to use a different local data directory.

Every `lon` invocation writes a diagnostic log under `~/.config/local-n8n/logs/`, or
`$LOCAL_N8N_HOME/logs/` when that environment variable is set. Error messages include the exact log path.
Logs record command metadata, progress, and friendly errors without copying typed passphrases or recovery
codes from terminal output.

## Script-Friendly Flags

Global flags must be placed before the command:

```bash
lon --json status
lon --dry-run up --instance preview --port 5688
lon --verbose status
lon backup --yes
```

- `--json` emits one JSON object to stdout for finite commands.
- `--dry-run` previews mutating commands without changing instance files, state, Docker, or browsers.
- `--yes` skips supported confirmation prompts. Some commands, such as `backup`, also expose a
  command-local `--yes`.
- `--verbose` also prints diagnostic details to stderr.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

Run checks locally:

```bash
uv run pytest tests
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pyrefly check
uv run mkdocs build --strict
```

Development-only cleanup:

```bash
uv run lon --dry-run dev wipe
uv run lon dev wipe
```

`dev wipe` removes local-n8n containers, volumes, instance files, and state for clean-slate testing. It
asks you to type `yes` before real deletion. Pass `--images` to also remove known local-n8n Docker images.

## Release and Docs

GitHub prereleases are created from `v*` tags. The release workflow runs lint, format check, type checks,
tests, docs build, builds the wheel/source distribution, and attaches those artifacts to a GitHub
prerelease.

Docs are built with MkDocs Material and versioned with `mike`. The public docs site should be served from
the `gh-pages` branch once GitHub Pages is enabled for the public repository.

PyPI publishing is intentionally deferred while early alpha releases are validated through GitHub
prereleases.

## Security Notes

`local-n8n` does not host your data. n8n data lives in your local Docker volume, and backup bundles are
encrypted before being written to disk.

Do not commit generated `.env` files, `state.db`, `recovery.wrapped`, diagnostic logs, or `.n8nbundle`
files. The repository ignores those runtime artifacts by default.

Please report suspected vulnerabilities privately. See [SECURITY.md](SECURITY.md).
