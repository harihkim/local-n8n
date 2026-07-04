# Command Reference

Global options must be placed before the command:

```bash test
uv run lon --help
```

## Global Options

| Option | Purpose |
| --- | --- |
| `--verbose` | Print diagnostic details to stderr. |
| `--json` | Emit one JSON object to stdout for finite commands. |
| `--dry-run` | Preview mutating/browser commands without side effects. |
| `--yes`, `-y` | Assume yes for confirmation prompts where supported. |

Human output goes to stderr. JSON output goes to stdout. Lifecycle commands that may wait on Docker
also stream Docker Compose output to stderr. In an interactive terminal, Docker's live progress display is
preserved; in non-interactive output it falls back to plain streaming.

## Lifecycle

### `lon init`

Plan, initialize, start, and optionally open a local n8n instance. This is the guided first-run entry
point for new users.

Options:

- `--instance`, `-i`: instance name. Default: `default`.
- `--port`, `-p`: host port for n8n.
- `--open` / `--no-open`: open the n8n web UI after startup. Default: `--open`.

Examples:

```bash
lon init
lon init --instance manual-check --port 5683 --no-open
```

Safe preview:

```bash test
uv run lon --dry-run init --instance preview --port 5688 --no-open
```

JSON preview:

```bash test
uv run lon --json --dry-run init --instance preview --port 5688 --no-open
```

On first run, n8n may redirect to `/setup`; create the local owner account there.

### `lon up`

Render instance files if needed, create or recreate the Compose container, start n8n, and wait until the n8n web UI is reachable.

Options:

- `--instance`, `-i`: instance name. Default: `default`.
- `--port`, `-p`: host port for n8n.

Examples:

```bash
lon up
lon up --instance manual-check --port 5683
```

Safe preview:

```bash test
uv run lon --dry-run up --instance preview --port 5688
```

If local state still has the old built-in `1.113.3` image pin, `lon up` prompts before moving that instance
to n8n's stable image reference. Press Enter to accept the default `yes`, or type `n` to keep the existing
image. Custom image references are not changed.

JSON preview:

```bash test
uv run lon --json --dry-run up --instance preview --port 5688
```

### `lon down`

Remove the n8n container and network while keeping the Docker data volume.

Options:

- `--instance`, `-i`: instance name. Default: `default`.

Use `lon up` to create and start the container again.

### `lon stop`

Stop the existing n8n container while keeping the container and Docker volume.

Options:

- `--instance`, `-i`: instance name. Default: `default`.

Use `lon start` to resume the stopped container.

### `lon start`

Start an existing stopped n8n container and wait for the web UI.

Options:

- `--instance`, `-i`: instance name. Default: `default`.

If `lon down` removed the container, use `lon up` instead.

### `lon restart`

Restart an existing n8n container and wait for the web UI.

Options:

- `--instance`, `-i`: instance name. Default: `default`.

If the container is not present, `restart` fails fast and suggests `lon up`.

## Inspection

### `lon status`

Show URL, container state, web UI reachability, Docker volume, and Compose file path for one instance.

Options:

- `--instance`, `-i`: instance name. Default: `default`.

Examples:

```bash
lon status
lon --json status --instance manual-check
```

Help:

```bash test
uv run lon status --help
```

### `lon list`

List registered instances with name, URL, container state, and volume.

Examples:

```bash
lon list
lon --json list
```

### `lon logs`

Show n8n container logs.

Options:

- `--instance`, `-i`: instance name. Default: `default`.
- `--follow`, `-f`: follow log output.
- `--tail`: number of log lines to show. Default: `100`.

Examples:

```bash
lon logs
lon logs --tail 50
lon logs --follow
```

Current limitation: `lon --json logs --follow` is rejected because streaming JSON needs a separate newline-delimited output contract.

### `lon open`

Open the n8n web UI URL in a browser if possible.

Options:

- `--instance`, `-i`: instance name. Default: `default`.

On WSL, `lon open` tries `wslview` and then `powershell.exe Start-Process`. On Linux it tries `xdg-open`; on macOS it tries `open`.

If no opener is available, it prints the URL.

## Diagnostics

### `lon doctor`

Run read-only prerequisite diagnostics.

Options:

- `--port`, `-p`: port to check. Default: `5678`.

Checks:

- platform
- Docker CLI
- Docker daemon
- Docker Compose
- port availability

Help:

```bash test
uv run lon doctor --help
```

## Development

### `lon dev wipe`

Development-only destructive reset. Removes local-n8n Docker resources and local instance state for the
current `$LOCAL_N8N_HOME`.

This is not a normal user cleanup command. It is intended for local development when you want a clean slate.

Options:

- `--yes`, `-y`: skip the typed confirmation prompt.
- `--images`: also remove known local-n8n Docker images, including the current built-in n8n image.

Safe preview:

```bash test
uv run lon --dry-run dev wipe
uv run lon --dry-run dev wipe --images
```

Run for real:

```bash
lon dev wipe
lon dev wipe --images
```

For real deletion, the command warns and asks you to type `yes`. Press Enter or type anything else to keep
the default `no` choice. Use `--yes` only for development automation.

It removes:

- `local-n8n-*` Compose projects/containers/networks found through registered instances or instance dirs
- Docker volumes referenced by local-n8n state or instance naming
- known local-n8n Docker images when `--images` is passed
- `$LOCAL_N8N_HOME/instances`
- `$LOCAL_N8N_HOME/state.db` and SQLite sidecar files
