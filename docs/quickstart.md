# Quickstart

This guide assumes Linux or WSL with Python 3.13 and `uv` available.

`lon doctor` detects prerequisite problems. `lon --dry-run doctor --fix` previews supported Docker repair
steps, and `lon doctor --fix` can run supported Linux/WSL fixes after confirmation.

On Windows, start with the [Windows setup guide](windows.md), then run `lon` from PowerShell through the
WSL launcher.

## 1. Install

```bash
uv tool install git+https://github.com/harihkim/local-n8n.git@v0.1.0a3
```

Inside the repository checkout, use:

```bash test
uv run lon --help
```

## 2. Check Prerequisites

```bash
lon doctor
```

`doctor` is read-only. It checks platform, Docker CLI, Docker daemon, Docker backend, Docker Compose, and
port availability. Inside WSL, it also reports when Docker Desktop WSL integration is the active backend.

To preview supported fixes:

```bash
lon --dry-run doctor --fix
```

## 3. Initialize and Start n8n

```bash
lon init
```

This creates the default instance under:

```text
~/.config/local-n8n/instances/default/
```

It writes:

- `docker-compose.yml`
- `.env` with `N8N_ENCRYPTION_KEY`

The `.env` file is created once and preserved on later runs.

`init` starts n8n, opens the browser when possible, and explains the local owner setup step.
The generated Compose file uses n8n's official stable Docker image, `docker.n8n.io/n8nio/n8n`.

## 4. Open n8n

```bash
lon open
```

Or open the URL printed by `lon up`, usually:

```text
http://localhost:5678
```

On first run, n8n may redirect to `/setup`. That is expected.

## 5. Stop or Remove the Container

Stop keeps the container available for `start`:

```bash
lon stop
lon start
```

Down removes the container/network but keeps the Docker volume:

```bash
lon down
lon up
```

## 6. Create an Encrypted Backup

```bash
lon backup
```

`backup` briefly stops n8n for a consistent snapshot, writes an encrypted `.n8nbundle`, and starts n8n again
if it was running before. The first backup asks for a backup passphrase and prints a recovery code once.
Store that recovery code somewhere safe.

## 7. Restore a Backup

```bash
lon restore /path/to/default-2026-07-05T12-00-00Z.n8nbundle
```

`restore` opens the bundle with either the backup passphrase or recovery code, restores the Docker volume
into a fresh generation volume, writes the instance files, registers state, starts n8n, and waits for the web
UI.

By default, restore refuses to overwrite an existing instance. Use `--replace` only when you intentionally
want to replace that instance after a pre-restore safety backup.

Recovery admin commands are available when needed:

```bash
lon recovery show
lon recovery rotate
lon passphrase change
lon passphrase reset
```

## Named Instances

Use `--instance` to create separate local instances:

```bash
lon init --instance manual-check --port 5683
lon status --instance manual-check
lon down --instance manual-check
```

Instance names must use lowercase letters, digits, and hyphens. They must start and end with a letter or digit.
