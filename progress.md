# local-n8n Progress

## Current phase

Phase 3 backup/restore/admin MVP is released as GitHub prerelease `v0.1.0a3`.

Phase 4 prerequisite automation is in progress: `lon --dry-run doctor --fix` previews Docker prerequisite
fixes, and `lon doctor --fix` can now run supported executable fixes with confirmation. Release
infrastructure now also has a manual PyPI/TestPyPI Trusted Publishing workflow ready for setup; first package
publishing is gated on completing Phase 4 with validated Linux, macOS, and Windows support.

## Implemented

- Created a Python 3.13 `uv` package for `local-n8n`.
- Added the `lon` console script.
- Added `lon up` and `lon down`.
- Render `~/.config/local-n8n/instances/<name>/docker-compose.yml`.
- Generate `~/.config/local-n8n/instances/<name>/.env` once and preserve the existing
  `N8N_ENCRYPTION_KEY` on later runs.
- Set `.env` to mode `0600`.
- Use deterministic Compose project names: `local-n8n-<instance>`.
- Use explicit Docker volume names: `n8n_<instance>_data`.
- Use n8n's official stable Docker image by default: `docker.n8n.io/n8nio/n8n`.
- Added friendly error mapping for missing Docker, daemon-not-running, port-in-use, and generic Compose failures.
- Added HTTP readiness polling so `lon up` prints success only after the n8n web UI responds.
- Added a startup progress message so `lon up` does not look hung while n8n is booting.
- Added a shutdown progress message so `lon down` does not look idle while Docker stops the container.
- Added a SQLite `state.db` registry with WAL mode and `busy_timeout`.
- `lon up` now records/adopts instances in the registry while preserving existing Phase 0 `.env` files.
- Added `lon status`, `lon list`, `lon logs`, `lon start`, `lon stop`, `lon restart`, and `lon open`.
- Added read-only `lon doctor` diagnostics for platform, Docker CLI, Docker daemon, Docker Compose, and port availability.
- Added `--verbose` diagnostics for CLI internals such as selected instance, compose path, Docker commands, and readiness checks.
- Added `--json` for finite commands, emitting a single JSON object to stdout while human output stays on stderr.
- Added `--dry-run` for mutating lifecycle/browser commands so users can preview planned writes and Docker commands.
- Added global `--yes` plumbing for future confirmation prompts.
- Added GitHub Actions CI for lint, format, type checking, and tests.
- Added a tag-triggered GitHub prerelease workflow that builds wheel/source distribution artifacts.
- Set package metadata to the first alpha version: `0.1.0a1`.
- Added MkDocs Material documentation with versioned publishing via `mike`.
- Added documentation drift checks so command docs stay aligned with the current CLI.
- Started Phase 2 with a side-effect-free init planning model in `core/init.py`.
- Stream Docker Compose output for `lon up`, `lon down`, `lon stop`, `lon start`, and `lon restart`
  so long waits such as first-run image pulls show real progress.
- Preserve Docker Compose's live TTY progress display in interactive terminals while keeping plain
  streaming for non-interactive runs.
- Added `lon init` as the guided first-run command: plan, check Docker prerequisites, start/register the
  instance through the existing lifecycle path, optionally open the browser, and explain n8n's local
  `/setup` owner-account step.
- Added WSL Docker backend detection to `lon doctor` / `lon init` prerequisites so Docker Desktop WSL
  integration is accepted as a valid backend and explained clearly.
- Released Phase 2 as GitHub prerelease `v0.1.0a2` with wheel/source artifacts and versioned docs published
  as `latest`.
- Started Phase 3a with a library-only encrypted bundle core in `core/crypto.py`: deterministic bundle
  framing, canonical JSON headers, AES-256-GCM payload encryption, Argon2id passphrase/recovery slots, and
  strict format/authentication errors.
- Started Phase 3b with `lon backup`: downtime confirmation, passphrase prompt, stop-if-running volume
  capture, encrypted `.n8nbundle` write, recovery material creation/reuse, backup metadata recording, and
  restart-in-`finally` behavior.
- Started Phase 3c with `lon restore`: decrypt/verify bundle payload, refuse existing instances unless
  `--replace`, restore to a fresh generated Docker volume, rehydrate `.env`/Compose, register state, start
  n8n, and wait for readiness.
- Completed Phase 3d admin polish with `lon recovery show`, `lon recovery rotate`,
  `lon passphrase change`, and `lon passphrase reset`: passphrase-authorized recovery-code
  display/rotation, recovery-material rewrapping, and live-instance escape-hatch reset.
- Added development-only `lon dev wipe` to remove local-n8n Docker resources, instance files, and state
  during clean-slate testing, with optional image removal through `--images`.
- Added persistent per-invocation diagnostic logs under `~/.config/local-n8n/logs/` (or
  `$LOCAL_N8N_HOME/logs/`) with command metadata, progress, friendly errors, and internal diagnostics.
- Started Phase 4 with a bootstrap planning layer and `lon doctor --fix`: dry-run previews Docker
  prerequisite fixes, while non-dry-run can execute supported repair commands after confirmation.
- Added supported Linux/WSL Docker Engine installation planning/execution through Docker's official apt
  repository, including Compose and Buildx packages, service startup, and Docker group membership setup.
- Added a Windows bootstrap helper and setup guide that recommend WSL Ubuntu plus Docker Desktop WSL
  integration by default while preserving direct Docker Engine inside WSL as an explicit advanced choice.
- Added a Windows PowerShell `scripts/lon.ps1` launcher so users can run `lon` from PowerShell while the
  launcher executes the real command inside WSL.
- Added `scripts/install-windows-launcher.ps1` to install a user-local `lon` command on Windows, so normal
  PowerShell usage can be `lon init`, `lon doctor`, and other direct CLI commands.
- Added a Windows package-entrypoint bridge: when the installed `lon` command runs on Windows, it delegates
  all commands into WSL, converts obvious Windows paths for WSL, and supports `uv`/`pipx` package installs
  as the primary Windows UX.
- Added a manual PyPI/TestPyPI publishing workflow using PyPI Trusted Publishing; first real publish is
  deferred until Phase 4 completes and Linux, macOS, and Windows prerequisite support is validated.
- Added unit tests for compose rendering, env preservation, CLI behavior, Docker error mapping, readiness polling, state registry, lifecycle parsing, and doctor diagnostics.

## Unexpected issues and fixes

### uv cache path was read-only in the Codex sandbox

`uv` tried to use the normal home-directory cache, but the sandbox made that path read-only.

Fix: during verification only, used:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_PYTHON_INSTALL_DIR=/tmp/uv-python
```

This is not expected to be necessary in a normal WSL shell.

### Python 3.13 was not installed locally

`python3.13` was not present in the environment.

Fix: allowed `uv` to download and manage CPython 3.13 for the project.

### Non-default port smoke test exposed a Compose mapping bug

The first compose template mapped host `${N8N_PORT}` to container `5678`, while `.env` also made n8n listen
on `${N8N_PORT}` inside the container. This worked accidentally for the default port and failed for
`--port 5680`.

Fix: changed the mapping to:

```yaml
- "${N8N_PORT}:${N8N_PORT}"
```

### `lon up` reported success before n8n was actually ready

`docker compose up -d` returns once the container starts, not once the n8n web UI is serving requests.
This caused a short window where the CLI said n8n was running but the browser still showed connection errors.

Fix: added readiness polling against `http://localhost:<port>/` before printing the success message.
Also added a visible startup line before the blocking wait:

```text
Starting n8n and waiting for the web UI...
```

### Commands with possible waits need progress messages

`lon down` can also take a moment while Docker stops the container.

Fix: added a visible shutdown line, then clarified the command after manual testing showed that `down`
removes the container:

```text
Removing n8n container and keeping the data volume...
```

Going forward, commands that can block on Docker, network, restore, backup, or external tools should print
a short progress update before the wait begins.

### `down`, `stop`, `start`, and `restart` need distinct semantics

Manual testing showed that `lon down` uses Docker Compose `down`, which removes the container while keeping
the named data volume. Running `restart` after that appeared to hang because there was no container to
restart and the CLI still waited for readiness.

Fixes:

- `lon status` now reports the empty Compose state as `not present` instead of `not created`.
- `lon restart` fails fast when there is no container and tells the user to run `lon up`.
- `lon stop` was added for the common expectation of stopping the container without removing it.
- `lon start` was added to start an existing stopped container.
- Added unit tests at both core and CLI levels for the down/restart/start edge cases.

Follow-up manual testing exposed that `docker compose ps --format json` omits stopped containers unless
`--all` is passed, so a container stopped by `lon stop` looked `not present`. Fixed by using
`docker compose ps --all --format json` for status/list checks and added a regression test.

### Unplanned convenience: instance listing

The earlier internal Phase 1 plan listed `status/logs/restart/open`, but manual testing with multiple
instances made it clear that users need a discovery command instead of remembering every `--instance`
value.

Added:

```bash
lon list
```

It renders registered instances with name, URL, container state, and volume. This feature was not explicitly
called out in the earlier internal plan; it was added as Phase 1 UX polish.

Follow-up polish: when instances are listed, the CLI now suggests
`lon status --instance <name>` for more detail.

### Docker health was not useful for n8n web UI readiness

`lon status` displayed `Health: -` because the generated Compose service does not define a Docker
healthcheck, so Docker has no health value to report. That field was misleading.

Fixes:

- Replaced `Health` with `Web UI` in `lon status`.
- `Web UI` reports `reachable` / `not reachable` using the same n8n web UI readiness probe as `lon up`.
- Strengthened readiness so a generic HTTP response like `Cannot GET /` is not accepted as ready.
- Treated n8n's first-run `/setup` redirect as ready, because setup/login/editor are all valid n8n web UI states.
- Added `--verbose` debug output to make readiness and Docker command behavior easier to diagnose.

Follow-up manual testing showed one more transient page:

```text
n8n is starting up. Please wait
```

That page contains the string `n8n`, so the earlier readiness heuristic accepted it too early. Fixed by
treating the startup/waiting page as not ready and continuing to poll until setup/login/editor responds.

### Persistent CLI logs are still a separate decision

We need persistent CLI logs eventually, but not in this readiness commit. Proposed path:

```text
$LOCAL_N8N_HOME/logs/lon.log
```

Open design items before implementation: log rotation, retention, and redaction rules. Secrets such as
`N8N_ENCRYPTION_KEY`, future passphrases/recovery codes, provider tokens, and `.env` contents must never
be logged.

### Phase 1b global flags

The earlier internal plan listed `--json`, `--dry-run`, and `--yes` in Phase 1, but the first Phase 1
branch focused on the lifecycle/state/doctor checkpoint.

Implemented in Phase 1b:

- `--json` writes one structured JSON object to stdout for finite commands. Existing Rich/human output remains
  on stderr so scripts can safely parse stdout.
- `--dry-run` short-circuits mutating lifecycle/browser commands before filesystem writes, state changes,
  Docker commands, readiness waits, or browser opening.
- `--yes` is accepted globally and stored in CLI options. It does not change behavior yet because current
  Phase 1 commands do not prompt.

Known limitation: `lon --json logs --follow` is rejected for now instead of emitting newline-delimited JSON.
Plain `lon logs --follow` remains available for text streaming.

### First-run Docker image pulls looked frozen

`lon up` printed that it was starting n8n, but a first run may spend significant time pulling the n8n image
before the web UI wait even begins. That made the command look hung on slower networks or machines.

Fixes:

- Added a streaming command runner for Docker Compose lifecycle commands.
- `lon up`, `lon down`, `lon stop`, `lon start`, and `lon restart` now forward Docker Compose output while
  those commands run.
- Human progress and Docker output are written to stderr. Stdout remains reserved for machine-readable JSON,
  so `lon --json ...` can still be scripted safely.
- Added regression tests for the streaming runner and for lifecycle commands choosing the streaming path.

Follow-up manual testing showed that plain pipe streaming made Docker print every progress refresh as a new
line instead of updating the same terminal rows. Fixed by using a pseudo-terminal for streaming commands
when stderr is interactive, so Docker Compose can use its normal live progress renderer. Non-interactive
commands still use plain pipe streaming.

### Stale n8n image pin was the wrong default

The first implementation pinned `docker.n8n.io/n8nio/n8n:1.113.3@sha256:...` for reproducibility, but did
not add the freshness machinery that must come with pinning. Manual review showed the default image had
fallen behind current n8n releases, which is especially risky for an automation tool with frequent security
and bug-fix releases.

Fixes:

- changed the generated Compose default to n8n's official stable image reference:
  `docker.n8n.io/n8nio/n8n`
- ask before migrating existing registry rows that still use the old built-in `1.113.3` image pin to the
  stable image reference on the next `lon up` or `lon init`; Enter accepts the update, `n` cancels it, and
  custom image references are left unchanged
- updated tests and docs to match the stable-image default
- kept future backup/restore design separate: bundles should still record the exact resolved image used for
  portability, but normal local lifecycle should not ship with a stale hardcoded pin
- promoted `lon update` and user-selectable image/version settings as a near-term design item instead of
  treating them as far-off polish

### CI and GitHub prereleases

Added `.github/workflows/ci.yml` so pushes and pull requests run:

- `ruff check .`
- `ruff format --check .`
- `ty check`
- `pyrefly check`
- `pytest tests`

Type checking is intentionally configured, not just invoked: ty checks `src` and `tests` with all configured
rules treated as errors, while Pyrefly uses the `strict` preset, warning-or-higher failure, Python 3.13, and
the `src` import path.

Added `.github/workflows/release.yml` for tag-triggered prereleases. Pushing a tag like `v0.1.0a1` runs the
same checks, builds the wheel and source distribution with `uv build --sdist --wheel`, and creates a GitHub
prerelease with the artifacts attached. At that point, PyPI publishing was intentionally deferred until after
the core backup/restore MVP loop stabilized.

### Versioned documentation site

Added a documentation site using MkDocs Material. The site is designed to behave like mature framework docs:

- `latest` is the default and points at the newest released docs.
- `dev` tracks unreleased documentation from `main`.
- release versions such as `v0.1.0a1` remain available.

Added `mike` for versioned publishing to the `gh-pages` branch and a docs workflow for future deploys.

Added docs drift tests:

- every registered Typer command must appear in `docs/commands.md`
- global options must be documented
- important command options must be documented
- fenced `bash test` examples in docs must execute successfully in `CliRunner`

### Phase 2 slice 1: init planning model

Started Phase 2 without changing CLI behavior yet. Added a core planner that classifies init state as:

- `new`: no registry row or instance files yet
- `adoptable`: existing Phase 0-style files are present but not registered
- `initialized`: the instance already exists in `state.db`

The planner chooses the effective port, records whether an existing `.env` will be preserved, detects when
a requested port is ignored because the registry already owns the instance, and returns the ordered init
steps that the future `lon init` command will execute.

### Phase 2 slice 2: `lon init` CLI

Added the executable `lon init` command around the planner. The command:

- checks Docker prerequisites before starting
- reuses `up_instance` so compose rendering, registry adoption, Docker streaming, readiness waits, and
  existing friendly error mapping stay centralized
- optionally opens the browser with `--open` / `--no-open`
- prints the first-run owner setup hint for n8n's `/setup` redirect
- supports `--dry-run` and `--json`

Design note: `init` checks Docker prerequisites but does not pre-bind-test the target port. A rerun or
adoption case can legitimately have the port occupied by the same local-n8n instance, so real conflicts are
left to Docker Compose and the existing `PortInUseError` mapping.

Persistent CLI file logging is still intentionally separate. Current backend-style handling includes typed
errors, exit codes, user-facing hints, `--verbose` diagnostics, JSON error envelopes, and tests for expected
failure modes. File logging should land as its own hardening change with redaction, rotation, and retention
rules.

### Unplanned development reset command

Manual testing repeatedly needed a clean local slate across containers, volumes, instance files, and state.
Added a deliberately sharp development command:

```bash
lon dev wipe
lon dev wipe --images
```

Safety decisions:

- command lives under `dev`, not normal lifecycle
- real deletion prompts with a warning and requires typing `yes`; blank input keeps the default `no`
- `--yes` or global `--yes` skips the prompt for development automation
- Docker image deletion is opt-in through `--images`; it includes the current built-in n8n image even if
  state/instance files were already wiped
- global `--dry-run` previews without requiring confirmation
- JSON output is available through the existing global `--json`
- local deletion is limited to instance files and SQLite state under `$LOCAL_N8N_HOME`

This feature was not explicitly in the earlier internal plan; it was added as developer-experience support
while building Phase 2.

Manual testing exposed the important two-step reset case: running `lon dev wipe` first removes local state,
so a later `lon dev wipe --images` must still know which built-in n8n image to remove. Added core and CLI
regression tests for that state-gone image cleanup path, plus CLI coverage that `--images` still prompts
with default `no` unless the user types `yes` or passes `--yes`.

### Phase 3a crypto core

Added the first Phase 3 slice as a library-only module, with no CLI, Docker, filesystem persistence, or
backup orchestration yet. `core/crypto.py` implements the planned `.n8nbundle` envelope framing:

- `N8NB` magic prefix, 4-byte big-endian header length, canonical JSON header, and AES-GCM
  `ciphertext || tag` payload
- fixed constants from the plan: 32-byte DEK, 12-byte nonces, 16-byte salts/tags, Argon2id
  `t=3, m=65536 KiB, p=4`
- passphrase and recovery slots, either of which can unwrap the DEK and open the bundle
- exact payload-length checks so trailing bytes are rejected
- open path authenticates the exact header bytes as AES-GCM AAD and never re-serializes the header
- deterministic random injection for tests only

Added unit tests for passphrase/recovery round-trip, wrong secret, header tamper, bad magic, header-magic
mismatch, unknown format schema, trailing bytes, empty payload rejection, and a deterministic known-answer
SHA-256 vector.

### Phase 3b backup create path

Added the first backup command path without restore yet:

- `lon backup` asks before downtime unless `--yes` or global `--yes` is used
- the CLI prompts for a backup passphrase and confirms it
- the first backup creates `recovery.wrapped` and prints the recovery code once
- later backups reuse the wrapped recovery material using the backup passphrase
- if n8n is running, backup stops only the n8n service, captures the volume, then starts n8n again in a
  `finally` block and waits for the web UI
- the encrypted bundle payload is a tar archive containing `manifest.json`, `volume.tar`,
  `docker-compose.yml`, and `.env`
- `state.db` now includes a `backups` table and records bundle path, checksum, size, timestamp, and version
  metadata after successful writes

Restore now consumes this payload format directly. The full real Docker backup→wipe→restore portability
smoke test is still pending.

Manual smoke test:

- created isolated instance `backup-smoke` under `LOCAL_N8N_HOME=/tmp/local-n8n-phase3-smoke`
- ran two real encrypted backups against Docker volume `n8n_backup-smoke_data`
- verified first backup created a recovery code and second backup reused `recovery.wrapped`
- opened the second bundle with the recovery code and confirmed the `N8NB` magic/header path works
- confirmed n8n restarted and `lon status` reported `running` / `reachable`
- cleaned up the smoke-test container, volume, local state, and temporary bundles

### Phase 3c restore path

Added the first restore command path:

- `lon restore <bundle>` prompts for either the backup passphrase or recovery code
- the bundle payload is decrypted through `core.crypto.open_bundle`
- `manifest.json` schema and per-file `sha256`/size metadata are verified before restore
- existing instances are refused by default
- `--replace` first attempts a pre-restore encrypted safety backup using the provided secret, then runs
  Compose `down` for the existing instance
- restore creates a fresh generation-style Docker volume name such as `n8n_default_data.g<timestamp>`
- `.env` is restored with `0600` permissions; `--port` can override `N8N_PORT`
- Compose is rendered for the restored image and fresh volume, then `docker compose up -d` starts n8n and
  readiness polling waits for the web UI

Manual Docker smoke test:

- created isolated instance `phase3c-smoke` under
  `LOCAL_N8N_HOME=/tmp/local-n8n-phase3c-smoke-codex`
- started n8n on port `5687`
- wrote marker file `/home/node/.n8n/codex-smoke/marker.txt` inside the Docker volume
- created encrypted backup `/tmp/local-n8n-phase3c-smoke-codex/phase3c-smoke.n8nbundle`
- verified the first backup created a recovery code
- ran `lon dev wipe --yes` to remove the original container, local state, and volume
- restored from the bundle with the backup passphrase
- verified `lon status --instance phase3c-smoke` reported `running` / `reachable`
- verified the marker file restored with contents `phase3c-smoke-marker`
- cleaned up the restored container, generated volume, local state, and instance files

Observed restore polish item: Docker Compose warns that the generated restore volume already exists but was
not created by Compose. Restore succeeds, but this may be worth quieting or documenting before release.

Follow-up hardening: `--replace` now snapshots the previous instance files/state before replacement. If the
new restore fails after the existing instance has been taken down, restore rolls back the previous Compose
file, `.env`, state pointer, and running state, then removes the partially restored generation volume.

Recovery material decision: restore defers local `recovery.wrapped` creation until the next backup. Restore
only receives one unlock secret, so it cannot generally recreate the same local recovery material: a
passphrase unlock does not reveal the recovery code, and a recovery-code unlock does not provide the
passphrase needed to wrap future local recovery material. The next backup creates a fresh recovery
generation and prints the new recovery code once.

### Phase 3d recovery admin

Added the first Phase 3d admin commands:

- `lon recovery show` prompts for the backup passphrase
- it unlocks the instance's local `recovery.wrapped` file through the passphrase slot
- it prints the active recovery code only on explicit request
- `lon recovery rotate` prompts for the backup passphrase
- it verifies the existing recovery material before replacing it
- it writes fresh local `recovery.wrapped` material and prints the new recovery code once
- future backups reuse the rotated recovery code, while existing bundles remain tied to the recovery code
  active when they were created
- `lon passphrase change` prompts for the current backup passphrase, then a new passphrase with confirmation
- it rewraps the existing recovery code under the new passphrase without changing the recovery code
- future backups can reuse the same recovery code with the new passphrase; existing bundle files are not
  rekeyed
- `lon passphrase reset` confirms that existing bundles are not rekeyed, requires a running/reachable
  instance, then writes fresh recovery material and prints the new recovery code once
- `--dry-run` previews the prompt/unlock/display/reset steps without reading or printing the secret
- `--json` reports admin outcomes without including passphrases or recovery codes in JSON

Phase 3d admin commands are now implemented. The remaining MVP work is final checkpoint polish and release
readiness review.

### Phase 3 MVP checkpoint review

Started the Phase 3 checkpoint review:

- updated README and docs landing page so they no longer describe encrypted backup/restore as future work
- added backup/restore and recovery-admin flow to the quickstart
- added a Phase 3 manual testing checklist covering backup, restore, recovery show/rotate, passphrase
  change/reset, and restored recovery-material behavior
- clarified that PyPI publishing was waiting for Phase 3 checkpoint review rather than the older generic
  backup/restore stability milestone
- quieted Docker Compose's restore warning for pre-created generation volumes by rendering restored volumes
  as externally managed Compose volumes

Remaining release-readiness gaps:

- decide release version/tag strategy for the Phase 3 prerelease after review

Manual release-candidate smoke pass:

- baseline help and dry-run commands passed
- `lon doctor --port 5689` passed on WSL with Docker Desktop integration
- initial default-instance smoke attempt exposed a manual-testing hazard: `LOCAL_N8N_HOME` isolates files and
  state, but Docker volume names are global and `default` maps to `n8n_default_data`
- reran lifecycle smoke with unique instance `rc-smoke-codex` on port `5690`
- verified `init`, `status`, `list`, `stop`, `start`, `down`, and the expected `restart` failure after
  `down`
- wrote a marker file into the Docker volume, created an encrypted backup, and verified first recovery-code
  creation
- verified `recovery show`, `recovery rotate`, `passphrase change`, and live-instance `passphrase reset`
- wiped the original volume, restored from the original bundle with the original passphrase, and verified
  `status` reported `running` / `reachable`
- verified restored marker contents `rc-smoke-marker`
- verified restored instances do not immediately recreate `recovery.wrapped`
- cleaned up the unique smoke-test container, networks, generated volumes, local instance files, and state

## Verification

- `uv run --python 3.13 pytest tests`
- `uv run --python 3.13 ruff check .`
- `uv run --python 3.13 ruff format --check .`
- `uv run --python 3.13 ty check`
- `uv run --python 3.13 pyrefly check`
- Real Docker smoke test:
  - `lon up --instance phase0-check --port 5680`
  - verified n8n responded on `http://localhost:5680`
  - `lon down --instance phase0-check`
  - removed the temporary Docker volume

## Phase 1 notes

- Read-only/lifecycle commands adopt an existing Phase 0 instance only when instance files already exist.
  They do not silently create a brand-new registry row.
- `lon up` remains the creation path for Phase 1.
- `lon down` removes the container/network but keeps the volume; `lon stop` keeps the container present.
- `doctor` is intentionally read-only. It reports problems and hints, but does not install or change anything.

## Phase 4: Prerequisite Automation

- First slice landed the safe command contract: `lon --dry-run doctor --fix` previews Docker prerequisite
  fixes without changing the machine.
- Second slice made `lon doctor --fix` executable for supported Docker repair steps, still consent-gated
  and still leaving full Docker installation as a manual action.
- Third slice adds supported Linux/WSL Docker Engine installation through Docker's official apt repository.
- Fourth slice adds Windows host bootstrap guidance/script for WSL Ubuntu, with Docker Desktop WSL integration
  as the recommended default and direct Docker Engine inside WSL as an explicit advanced choice.
- Windows UX follow-up adds a PowerShell launcher so normal operation can stay in Windows PowerShell instead
  of asking users to type routine commands in an Ubuntu shell.
- Windows UX follow-up now installs a user-local `lon.cmd` shim so users can type plain `lon init` from
  PowerShell while the command still executes safely inside WSL.
- Windows package-entrypoint follow-up makes `uv tool install local-n8n` / `pipx install local-n8n` the
  intended package UX: plain `lon ...` runs from PowerShell and delegates to WSL automatically.
- Windows manual validation passed from WSL Ubuntu with Docker Desktop integration active: `docker info`
  reported `Operating System: Docker Desktop` / `Name: docker-desktop`, `docker compose version` reported
  `v5.1.4`, and `uv run lon doctor` passed Platform, Docker CLI, Docker daemon, Docker backend, Docker
  Compose, and Port 5678 checks.
- Next Phase 4 slices: macOS/Colima guidance or automation, then three-platform validation.
- Other near-term follow-up candidates: `lon update` and user config for `default-image-ref`.
