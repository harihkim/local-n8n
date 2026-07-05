# Release Process

`local-n8n` currently publishes GitHub prereleases, not PyPI packages.

PyPI publishing is deferred while early alpha releases are validated through GitHub prereleases.

## Package Release

From a clean `main`:

```bash
git tag -a v0.1.0a3 -m "v0.1.0a3"
git push origin v0.1.0a3
```

The release workflow runs checks, builds:

- wheel
- source distribution

and creates a GitHub prerelease with those artifacts attached.

## Install From a Release

```bash
uv tool install git+https://github.com/harihkim/local-n8n.git@v0.1.0a3
```

## Docs Release

Docs are published with `mike`.

The default docs version is `latest`, which points at the newest released docs.

Useful commands:

```bash
uv run --python 3.13 mike deploy --push --update-aliases v0.1.0a3 latest
uv run --python 3.13 mike set-default --push latest
```

Development docs can be published separately:

```bash
uv run --python 3.13 mike deploy --push dev
```

Expected public URL:

```text
https://harihkim.github.io/local-n8n/
```
