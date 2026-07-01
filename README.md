# local-n8n (`lon`)

`lon` is a CLI for running a local self-hosted n8n instance with a path toward encrypted, portable backups.

Phase 0 is intentionally small: it renders a Docker Compose project and starts/stops n8n. It does not
install Docker, create a registry database, manage Windows bootstrap, configure tunnels, or create encrypted
backups yet.

## Requirements

- Python 3.13
- `uv`
- Docker Engine available in the development environment

On Windows, develop and run the CLI inside WSL Ubuntu. Automatic WSL/Docker provisioning is post-MVP.

## Usage

```bash
uv run lon up
uv run lon stop
uv run lon down
```

Phase 1 also includes:

```bash
uv run lon status
uv run lon logs
uv run lon start
uv run lon restart
uv run lon open
uv run lon doctor
```

Lifecycle semantics:

- `lon up`: create or recreate the Compose container and start n8n.
- `lon stop`: stop the existing container but keep it present, so `lon start` can resume it.
- `lon start`: start an existing stopped container; if `lon down` removed it, use `lon up`.
- `lon restart`: restart an existing container; if `lon down` removed it, use `lon up`.
- `lon down`: remove the container/network but keep the Docker data volume.

`lon up` writes instance files under `~/.config/local-n8n/instances/default/` unless
`LOCAL_N8N_HOME` is set. It generates `.env` once, stores a fixed `N8N_ENCRYPTION_KEY`, sets the file to
mode `0600`, and does not overwrite that key on later runs.

Phase 1 records instances in `~/.config/local-n8n/state.db`. Existing Phase 0 instance files are adopted
without overwriting `.env`.

The Phase 0 default n8n image is pinned in code for this CLI release. Because Phase 0 has no `lon update`
command, moving to a newer n8n image requires a newer `lon` build or an explicit code/config change.
