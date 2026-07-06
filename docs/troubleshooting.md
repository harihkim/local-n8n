# Troubleshooting

## Diagnostic Logs

Every `lon` invocation writes a diagnostic log:

```text
~/.config/local-n8n/logs/lon-<timestamp>-<pid>.log
```

If `LOCAL_N8N_HOME` is set, logs are written under `$LOCAL_N8N_HOME/logs/` instead. Error messages include
the exact log path.

Diagnostic logs record command metadata, progress messages, friendly errors, and internal diagnostics used
by `--verbose`. They do not copy typed passphrases or recovery codes from terminal output.

## Docker Was Not Found

Run:

```bash
lon doctor
```

If Docker CLI is missing, install Docker Desktop for Windows and enable WSL integration for this distro, or
install Docker Engine directly inside WSL/Linux.

## Docker Desktop WSL Integration Is Active

This is a valid setup. Docker Desktop runs its own WSL backend and exposes Docker commands inside your
integrated WSL distro.

If `lon doctor` reports Docker Desktop WSL integration as the active backend, Docker resources are managed by
Docker Desktop rather than by a Docker Engine installed directly inside the current distro.

## Docker Desktop WSL Integration Is Off

If Docker Desktop is installed but `docker` is missing or the daemon is unreachable inside WSL, enable
integration for this distro:

1. Open Docker Desktop on Windows.
2. Go to Settings > Resources > WSL Integration.
3. Enable integration for your WSL distro.
4. Apply the change and re-run:

```bash
lon doctor
```

Alternatively, install Docker Engine directly inside WSL if you do not want to use Docker Desktop.

## Docker Daemon Is Not Running

If `doctor` reports that Docker is installed but unreachable, start Docker Desktop or Docker Engine and retry.

Under WSL with Docker Engine installed directly, this may look like:

```bash
sudo service docker start
```

## Port Is Already in Use

Default n8n port is `5678`. Choose another port:

```bash
lon up --instance manual-check --port 5683
```

Then open:

```text
http://localhost:5683
```

## Browser Shows Connection Failed Right After `lon up`

`lon up` waits for the n8n web UI before printing success. If the browser still fails:

- run `lon status`
- run `lon logs`
- retry the URL after a few seconds
- check whether another process owns the port

## Browser Shows `/setup`

That is normal for a fresh n8n instance. It means n8n is ready for first-run owner setup.

## Browser Shows `n8n is starting up`

That page means the HTTP server is reachable, but the editor is not ready yet. `lon up` and `lon init`
should keep waiting until the setup/login/editor UI is ready.

## Browser Shows `Cannot GET /`

This should not count as ready. `lon` rejects generic `Cannot GET ...` responses in its readiness check.

If you see it manually, run:

```bash
lon logs
lon status
```

## `restart` Fails After `down`

`lon down` removes the container. It keeps the Docker volume, but there is no container left to restart.

Use:

```bash
lon up
```

If you want to stop without removing the container, use:

```bash
lon stop
lon start
```

## Named Instance Confusion

Commands default to the `default` instance.

If you created an instance with:

```bash
lon up --instance manual-check --port 5683
```

then inspect it with:

```bash
lon status --instance manual-check
```

Use `lon list` to discover registered instances.

## Where Files Live

Default config path:

```text
~/.config/local-n8n/
```

Per-instance files:

```text
~/.config/local-n8n/instances/<name>/docker-compose.yml
~/.config/local-n8n/instances/<name>/.env
```

State registry:

```text
~/.config/local-n8n/state.db
```

Override with:

```bash
LOCAL_N8N_HOME=/tmp/local-n8n-test lon up
```
