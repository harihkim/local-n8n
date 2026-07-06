# Contributing

Thanks for taking a look at `local-n8n`.

The project is currently in alpha, so small, focused issues and pull requests are easiest to review.

## Local Setup

```bash
uv sync
uv run lon --help
```

## Checks

Run the same checks used by CI:

```bash
uv run pytest tests
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pyrefly check
uv run mkdocs build --strict
```

## Pull Requests

- Keep changes focused.
- Add or update tests for behavior changes.
- Update docs when command behavior, install flow, backup/restore behavior, or troubleshooting changes.
- Do not commit generated local runtime files such as `.env`, `state.db`, `.n8nbundle`, `recovery.wrapped`,
  `logs/`, `backups/`, or `instances/`.

## Security

Please report suspected vulnerabilities privately. See [SECURITY.md](SECURITY.md).
