# local-n8n (`lon`)

`lon` is a CLI for running a local self-hosted n8n instance with encrypted, portable backups.

The current development branch includes the Phase 3 portability loop: guided init, Docker Compose
management, instance state, diagnostics, encrypted backup/restore, and recovery/passphrase admin commands.
It does not automatically install Docker, manage Windows bootstrap, configure tunnels, or publish remotes.

Documentation: https://harihkim.github.io/local-n8n/

## Requirements

- Python 3.13
- `uv`
- Docker Engine available in the development environment

On Windows, develop and run the CLI inside WSL Ubuntu. Automatic WSL/Docker provisioning is post-MVP.

## Install from GitHub

The latest tagged prerelease is `v0.1.0a2`; it contains the local lifecycle work. The Phase 3
backup/restore/admin commands described below are currently on the development branch and will be included
in a later prerelease.

Install the latest tagged prerelease with:

```bash
uv tool install git+https://github.com/harihkim/local-n8n.git@v0.1.0a2
```

For development inside this checkout, keep using `uv run lon ...`.

## Usage

```bash
uv run lon init
uv run lon up
uv run lon stop
uv run lon down
```

The local lifecycle also includes:

```bash
uv run lon status
uv run lon list
uv run lon logs
uv run lon start
uv run lon restart
uv run lon open
uv run lon doctor
```

Lifecycle semantics:

- `lon init`: guided first run; check Docker prerequisites, create/register/start the instance, and explain
  the n8n local owner setup step.
- `lon up`: create or recreate the Compose container and start n8n.
- `lon list`: list registered instances with URL, container status, and volume.
- `lon stop`: stop the existing container but keep it present, so `lon start` can resume it.
- `lon start`: start an existing stopped container; if `lon down` removed it, use `lon up`.
- `lon restart`: restart an existing container; if `lon down` removed it, use `lon up`.
- `lon down`: remove the container/network but keep the Docker data volume.

Encrypted portability:

```bash
uv run lon backup
uv run lon restore /path/to/default-2026-07-05T12-00-00Z.n8nbundle
uv run lon recovery show
uv run lon recovery rotate
uv run lon passphrase change
uv run lon passphrase reset
```

- `lon backup`: briefly stops n8n for a consistent Docker-volume snapshot, writes an encrypted
  `.n8nbundle`, and restarts n8n if it was running.
- First backup prints a recovery code once and writes local `recovery.wrapped` material for future backups.
- `lon restore`: decrypts with either the backup passphrase or recovery code, restores into a fresh Docker
  volume, writes restored instance files, registers state, starts n8n, and waits for readiness.
- Recovery and passphrase admin commands manage local recovery material. Existing bundles are never rekeyed
  by rotate/change/reset; they remain tied to the unlock material active when they were created.

`lon init` writes instance files under `~/.config/local-n8n/instances/default/` unless
`LOCAL_N8N_HOME` is set. It generates `.env` once, stores a fixed `N8N_ENCRYPTION_KEY`, sets the file to
mode `0600`, and does not overwrite that key on later runs.

`lon` records instances and backup metadata in `~/.config/local-n8n/state.db`. Existing Phase 0 instance
files are adopted without overwriting `.env`.

Use `--verbose` before the command for diagnostic output:

```bash
uv run lon --verbose status --instance default
```

Phase 1b global flags:

```bash
uv run lon --json status --instance default
uv run lon --dry-run up --instance preview --port 5688
uv run lon --yes status
```

- `--json` emits a single JSON object to stdout for finite commands; human output remains on stderr.
- `--dry-run` shows the planned action for mutating commands without writing files, changing state, opening
  browsers, or running Docker.
- `--yes` is accepted globally for confirmation prompts where supported.

Development-only reset:

```bash
uv run lon --dry-run dev wipe
uv run lon --dry-run dev wipe --images
uv run lon dev wipe
```

`dev wipe` removes local-n8n containers, volumes, instance files, and state for development clean-slate
testing. For real deletion, it warns and asks you to type `yes`; pressing Enter keeps the default `no`.
Pass `--images` to also remove known local-n8n Docker images, including the current built-in n8n image.
Use `--yes` only for development automation.

## Release process

CI runs lint, format check, `ty`, Pyrefly, tests, and docs build on pushes and pull requests. Pushing a
`v*` tag builds the wheel/source distribution and creates a GitHub prerelease with those artifacts attached.
PyPI publishing is intentionally deferred until the Phase 3 MVP checkpoint is reviewed.

The documentation site is built with MkDocs Material and published with versioned URLs. The default docs
version is `latest`, with `dev` available for unreleased work on `main`.

The default n8n image follows n8n's official stable Docker image:

```text
docker.n8n.io/n8nio/n8n
```

Instances that still have the earlier built-in `1.113.3` image pin recorded in local state are prompted to
move to this stable image reference on the next `lon up` or `lon init`. Press Enter to accept the default
`yes`, or type `n` to keep the existing image. Custom image references are left unchanged.

An explicit `lon update` command and user-selectable image/version settings remain planned follow-ups.
