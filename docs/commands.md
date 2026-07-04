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
| `--yes`, `-y` | Assume yes for confirmation prompts. Currently reserved for future prompts. |

Human output goes to stderr. JSON output goes to stdout.

## Lifecycle

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
