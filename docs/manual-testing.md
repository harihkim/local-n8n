# Manual Testing

Use this checklist when validating a release candidate locally.

## Baseline

```bash
uv run lon --help
uv run lon doctor
uv run lon --dry-run init --instance preview --port 5688 --no-open
```

Expected:

- help lists all current commands
- `doctor` reports platform, Docker CLI, Docker daemon, Docker Compose, and port state
- `init` dry-run explains planned writes/start/open behavior without side effects

## Default Instance

```bash
uv run lon init --no-open
uv run lon status
uv run lon open
```

Expected:

- `init` prints prerequisite/startup progress
- success is printed only after the n8n web UI is reachable
- `status` shows `Container` and `Web UI`
- first-run n8n may redirect to `/setup`

Clean up:

```bash
uv run lon down
```

## Named Instance

```bash
uv run lon init --instance manual-check --port 5683 --no-open
uv run lon status --instance manual-check
uv run lon list
```

Expected:

- `manual-check` uses `http://localhost:5683`
- `lon list` shows the instance name and container state
- `lon status` without `--instance manual-check` still checks `default`

Clean up:

```bash
uv run lon down --instance manual-check
```

## Stop, Start, Down

```bash
uv run lon up --instance lifecycle-check --port 5684
uv run lon stop --instance lifecycle-check
uv run lon status --instance lifecycle-check
uv run lon start --instance lifecycle-check
uv run lon down --instance lifecycle-check
uv run lon restart --instance lifecycle-check
```

Expected:

- after `stop`, `status` shows the container as stopped/exited
- after `down`, `status` shows the container as not present
- `restart` after `down` fails fast and suggests `lon up`

## Global Flags

Safe dry-run:

```bash test
uv run lon --dry-run up --instance preview --port 5688
```

JSON dry-run:

```bash test
uv run lon --json --dry-run up --instance preview --port 5688
```

Verbose status:

```bash
uv run lon --verbose status
```

Expected:

- dry-run does not write instance files, state, or run Docker
- JSON output is a single object on stdout
- verbose diagnostics go to stderr

## Development Wipe

Preview only:

```bash test
uv run lon --dry-run dev wipe
uv run lon --dry-run dev wipe --images
```

Expected:

- dry-run does not remove Docker resources or local files
- real deletion warns and asks you to type `yes`
- pressing Enter keeps the default `no` choice and deletes nothing
