# Command Reference

Global options must be placed before the command:

```bash test
uv run lon --help
```

## Global Options

| Option | Purpose |
| --- | --- |
| `--verbose` | Also print diagnostic details to stderr. |
| `--json` | Emit one JSON object to stdout for finite commands. |
| `--dry-run` | Preview mutating/browser commands without changing instance files, state, Docker, or browsers. |
| `--yes`, `-y` | Assume yes for confirmation prompts where supported. |

Human output goes to stderr. JSON output goes to stdout. Lifecycle commands that may wait on Docker
also stream Docker Compose output to stderr. In an interactive terminal, Docker's live progress display is
preserved; in non-interactive output it falls back to plain streaming.

Every invocation writes a persistent diagnostic log under `$LOCAL_N8N_HOME/logs/`, or
`~/.config/local-n8n/logs/` when `LOCAL_N8N_HOME` is not set. The log records command metadata, progress,
friendly errors, and internal diagnostics. It does not mirror terminal output wholesale, so recovery codes
and typed passphrases are not copied into the log. `--dry-run` may still create a diagnostic log file.

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

## Portability

### `lon backup`

Create an encrypted local `.n8nbundle` for a registered instance.

Options:

- `--instance`, `-i`: instance name. Default: `default`.
- `--output`, `-o`: backup bundle path. Default: `$LOCAL_N8N_HOME/backups/<instance>-<timestamp>.n8nbundle`.
- `--yes`, `-y`: skip the downtime confirmation prompt.

Safe preview:

```bash test
uv run lon --dry-run backup --instance preview
```

`backup` briefly stops n8n if the container is running, captures the Docker volume, writes an encrypted
bundle, records backup metadata in `state.db`, and then starts n8n again if it was running before.

The first backup creates local recovery material and prints a recovery code once. Store that code somewhere
safe; future backups reuse the local wrapped recovery material.

### `lon restore`

Restore an encrypted local `.n8nbundle`.

Options:

- `--replace`: replace an existing instance after first creating a pre-restore safety backup.
- `--port`, `-p`: override the restored n8n port.

Safe preview:

```bash test
uv run lon --dry-run restore /tmp/example.n8nbundle
```

`restore` decrypts the bundle with either the backup passphrase or recovery code, verifies the manifest and
payload checksums, restores the saved n8n volume into a fresh Docker volume, writes the restored `.env` and
Compose file, registers the instance in `state.db`, starts n8n, and waits for the web UI.

Restore does not recreate the original machine's `recovery.wrapped` file. The next `lon backup` for the
restored instance creates fresh local recovery material and prints a new recovery code once.

By default, `restore` refuses to overwrite an existing instance. Use `--replace` only when you intend to
replace that instance; the current implementation first attempts a pre-restore encrypted backup with the
same secret before it stops and replaces the existing instance.

### `lon recovery show`

Show the active backup recovery code after authorizing with the backup passphrase.

Options:

- `--instance`, `-i`: instance name. Default: `default`.

Safe preview:

```bash test
uv run lon --dry-run recovery show
```

`recovery show` reads the local `recovery.wrapped` file for the instance, unlocks it with the backup
passphrase, and prints the recovery code. Use it only when you intentionally need to store or verify the
code; normal backups reuse the wrapped recovery material without printing the code again.

### `lon recovery rotate`

Create a new recovery code for future backups after authorizing with the backup passphrase.

Options:

- `--instance`, `-i`: instance name. Default: `default`.

Safe preview:

```bash test
uv run lon --dry-run recovery rotate
```

`recovery rotate` replaces the local `recovery.wrapped` material and prints the new recovery code once.
Existing bundle files are not rekeyed; they still open with the recovery code that was active when they
were created. Run a fresh backup after rotating if you want a bundle tied to the new recovery code.

### `lon passphrase change`

Change the backup passphrase used to unlock local recovery material for future backups.

Options:

- `--instance`, `-i`: instance name. Default: `default`.

Safe preview:

```bash test
uv run lon --dry-run passphrase change
```

`passphrase change` unlocks the local `recovery.wrapped` file with the current backup passphrase and
rewrites it with the new backup passphrase. Existing bundle files are not rekeyed; each bundle still opens
with the passphrase or recovery code that was active when that bundle was created.

### `lon passphrase reset`

Reset backup passphrase and recovery material for a running, reachable local instance.

Options:

- `--instance`, `-i`: instance name. Default: `default`.

Safe preview:

```bash test
uv run lon --dry-run passphrase reset
```

`passphrase reset` is the escape hatch for a live instance when both the old backup passphrase and recovery
code are lost. It requires the n8n container to be running and the web UI to be reachable, then writes fresh
local `recovery.wrapped` material and prints a new recovery code once. Existing bundle files are not rekeyed
and remain openable only with the passphrase or recovery code that was active when they were created.

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

Run prerequisite diagnostics. By default, `doctor` is read-only.

Options:

- `--port`, `-p`: port to check. Default: `5678`.
- `--fix`: preview or run prerequisite fixes. The first Phase 4 slice supports
  `lon --dry-run doctor --fix` only; real installers are not active yet.

Checks:

- platform
- Docker CLI
- Docker daemon
- Docker backend, including Docker Desktop WSL integration detection
- Docker Compose
- port availability

Help:

```bash test
uv run lon doctor --help
```

Fix preview:

```bash
lon --dry-run doctor --fix
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
