# Release Process

`local-n8n` publishes GitHub prereleases and is prepared for PyPI/TestPyPI trusted publishing.

PyPI publishing is intentionally manual until the Trusted Publisher configuration is set up and a release
candidate has been validated.

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

## PyPI Publishing

GitHub Packages does not provide a PyPI-compatible Python package registry, so Python package publishing
uses PyPI/TestPyPI.

The package name `local-n8n` currently appears available on both PyPI and TestPyPI.

Before publishing for the first time:

1. Create or sign in to the target package index account.
2. Configure a Trusted Publisher for this repository and workflow:
   - repository owner: `harihkim`
   - repository name: `local-n8n`
   - workflow filename: `publish-pypi.yml`
   - environment: `testpypi` for TestPyPI, `pypi` for PyPI
3. Run the `Publish Python Package` workflow manually.
4. Publish to `testpypi` first.
5. After the TestPyPI install smoke passes, publish to `pypi`.

TestPyPI install smoke:

```bash
uv tool install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ local-n8n
lon --help
```

PyPI install smoke:

```bash
uv tool install local-n8n
lon --help
```

## Install From a Release

```bash
uv tool install git+https://github.com/harihkim/local-n8n.git@v0.1.0a3
```

After the first PyPI publish, users can install with:

```bash
uv tool install local-n8n
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

## Public Repository Readiness

The `gh-pages` branch can be updated while the repository is private, but the public GitHub Pages URL may
remain unavailable until the repository is public or Pages is supported by the repository's GitHub plan.

Before making the repository public:

- confirm no local secrets, recovery codes, generated bundles, `.env` files, or private logs are committed
- keep internal planning notes out of the public repository; publish durable decisions through README and docs
- confirm release artifacts and install instructions point at the intended public repository
- enable GitHub Pages from the `gh-pages` branch
- verify `https://harihkim.github.io/local-n8n/` and the `latest` docs alias return HTTP 200
- keep early releases marked as prereleases until public feedback validates the alpha flow
