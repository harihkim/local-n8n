# Quickstart

This guide assumes Linux or WSL with Python 3.13, `uv`, and Docker Engine available.

Automatic WSL and Docker provisioning is planned for a later phase. For now, `lon doctor` detects and explains prerequisite problems.

## 1. Install

```bash
uv tool install git+https://github.com/harihkim/local-n8n.git@v0.1.0a1
```

Inside the repository checkout, use:

```bash test
uv run lon --help
```

## 2. Check Prerequisites

```bash
lon doctor
```

`doctor` is read-only. It checks platform, Docker CLI, Docker daemon, Docker Compose, and port availability.

## 3. Start n8n

```bash
lon up
```

This creates the default instance under:

```text
~/.config/local-n8n/instances/default/
```

It writes:

- `docker-compose.yml`
- `.env` with `N8N_ENCRYPTION_KEY`

The `.env` file is created once and preserved on later runs.

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

## Named Instances

Use `--instance` to create separate local instances:

```bash
lon up --instance manual-check --port 5683
lon status --instance manual-check
lon down --instance manual-check
```

Instance names must use lowercase letters, digits, and hyphens. They must start and end with a letter or digit.
