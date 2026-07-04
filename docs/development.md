# Development

Development currently targets Linux or WSL with Python 3.13 and `uv`.

## Setup

```bash
git clone https://github.com/harihkim/local-n8n.git
cd local-n8n
uv run --python 3.13 lon --help
```

## Checks

Run the same checks CI runs:

```bash
uv run --python 3.13 ruff check .
uv run --python 3.13 ruff format --check .
uv run --python 3.13 ty check
uv run --python 3.13 pytest tests
uv run --python 3.13 mkdocs build --strict
```

## Docs Drift Checks

The test suite includes documentation checks that verify:

- every current CLI command is documented in `docs/commands.md`
- global options are documented
- key command options are documented
- fenced `bash test` examples in docs still run

Use `bash test` only for safe commands that do not start Docker or open a browser.

Use plain `bash` for examples intended for humans but not CI.

## Branch and PR Flow

Use small branches and pull requests:

```bash
git switch -c docs-site-versioned
```

Before merging, wait for CI and docs checks to pass.

## Local Docs Preview

```bash
uv run --python 3.13 mkdocs serve
```

The local preview usually runs at:

```text
http://127.0.0.1:8000/
```
