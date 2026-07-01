# local-n8n Progress

## Current phase

Phase 1 branch: lifecycle commands, SQLite state registry, and read-only `doctor`.

## Implemented

- Created a Python 3.13 `uv` package for `local-n8n`.
- Added the `lon` console script.
- Added `lon up` and `lon down`.
- Render `~/.config/local-n8n/instances/<name>/docker-compose.yml`.
- Generate `~/.config/local-n8n/instances/<name>/.env` once and preserve the existing
  `N8N_ENCRYPTION_KEY` on later runs.
- Set `.env` to mode `0600`.
- Use deterministic Compose project names: `local-n8n-<instance>`.
- Use explicit Docker volume names: `n8n_<instance>_data`.
- Pin the Phase 0 n8n image to the verified multi-arch digest:
  `docker.n8n.io/n8nio/n8n:1.113.3@sha256:57f95a26b1b28527053fba6316d9d046395d9b4da9d0da486e838384a38fcf37`.
- Added friendly error mapping for missing Docker, daemon-not-running, port-in-use, and generic Compose failures.
- Added HTTP readiness polling so `lon up` prints success only after the n8n editor responds.
- Added a startup progress message so `lon up` does not look hung while n8n is booting.
- Added a shutdown progress message so `lon down` does not look idle while Docker stops the container.
- Added a SQLite `state.db` registry with WAL mode and `busy_timeout`.
- `lon up` now records/adopts instances in the registry while preserving existing Phase 0 `.env` files.
- Added `lon status`, `lon list`, `lon logs`, `lon start`, `lon stop`, `lon restart`, and `lon open`.
- Added read-only `lon doctor` diagnostics for platform, Docker CLI, Docker daemon, Docker Compose, and port availability.
- Added unit tests for compose rendering, env preservation, CLI behavior, Docker error mapping, readiness polling, state registry, lifecycle parsing, and doctor diagnostics.

## Unexpected issues and fixes

### uv cache path was read-only in the Codex sandbox

`uv` tried to use the normal home-directory cache, but the sandbox made that path read-only.

Fix: during verification only, used:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_PYTHON_INSTALL_DIR=/tmp/uv-python
```

This is not expected to be necessary in a normal WSL shell.

### Python 3.13 was not installed locally

`python3.13` was not present in the environment.

Fix: allowed `uv` to download and manage CPython 3.13 for the project.

### Non-default port smoke test exposed a Compose mapping bug

The first compose template mapped host `${N8N_PORT}` to container `5678`, while `.env` also made n8n listen
on `${N8N_PORT}` inside the container. This worked accidentally for the default port and failed for
`--port 5680`.

Fix: changed the mapping to:

```yaml
- "${N8N_PORT}:${N8N_PORT}"
```

### `lon up` reported success before n8n was actually ready

`docker compose up -d` returns once the container starts, not once the n8n web editor is serving requests.
This caused a short window where the CLI said n8n was running but the browser still showed connection errors.

Fix: added readiness polling against `http://localhost:<port>/` before printing the success message.
Also added a visible startup line before the blocking wait:

```text
Starting n8n and waiting for the editor...
```

### Commands with possible waits need progress messages

`lon down` can also take a moment while Docker stops the container.

Fix: added a visible shutdown line, then clarified the command after manual testing showed that `down`
removes the container:

```text
Removing n8n container and keeping the data volume...
```

Going forward, commands that can block on Docker, network, restore, backup, or external tools should print
a short progress update before the wait begins.

### `down`, `stop`, `start`, and `restart` need distinct semantics

Manual testing showed that `lon down` uses Docker Compose `down`, which removes the container while keeping
the named data volume. Running `restart` after that appeared to hang because there was no container to
restart and the CLI still waited for readiness.

Fixes:

- `lon status` now reports the empty Compose state as `not present` instead of `not created`.
- `lon restart` fails fast when there is no container and tells the user to run `lon up`.
- `lon stop` was added for the common expectation of stopping the container without removing it.
- `lon start` was added to start an existing stopped container.
- Added unit tests at both core and CLI levels for the down/restart/start edge cases.

Follow-up manual testing exposed that `docker compose ps --format json` omits stopped containers unless
`--all` is passed, so a container stopped by `lon stop` looked `not present`. Fixed by using
`docker compose ps --all --format json` for status/list checks and added a regression test.

### Unplanned convenience: instance listing

`plan.md` Phase 1 listed `status/logs/restart/open`, but manual testing with multiple instances made it
clear that users need a discovery command instead of remembering every `--instance` value.

Added:

```bash
lon list
```

It renders registered instances with name, URL, container state, and volume. This feature was not explicitly
called out in `plan.md`; it was added as Phase 1 UX polish.

Follow-up polish: when instances are listed, the CLI now suggests
`lon status --instance <name>` for more detail.

## Verification

- `uv run --python 3.13 pytest tests`
- `uv run --python 3.13 ruff check .`
- `uv run --python 3.13 ruff format --check .`
- `uv run --python 3.13 ty check`
- Real Docker smoke test:
  - `lon up --instance phase0-check --port 5680`
  - verified n8n responded on `http://localhost:5680`
  - `lon down --instance phase0-check`
  - removed the temporary Docker volume

## Phase 1 notes

- Read-only/lifecycle commands adopt an existing Phase 0 instance only when instance files already exist.
  They do not silently create a brand-new registry row.
- `lon up` remains the creation path for Phase 1.
- `lon down` removes the container/network but keeps the volume; `lon stop` keeps the container present.
- `doctor` is intentionally read-only. It reports problems and hints, but does not install or change anything.

## Next phase

Continue Phase 1 hardening: global flags (`--json`, `--dry-run`, `--verbose`, `--yes`) and richer status
output can be layered on top of the registry/lifecycle foundation.
