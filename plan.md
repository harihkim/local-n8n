# local-n8n (`lon`) — System Design

> A cross-platform CLI that gives self-hosted n8n an **n8n-Cloud-like experience on your own
> machine**: one command to install prerequisites and run n8n, and an **encrypted, portable
> backup/restore** so your *entire* instance — owner login, settings, workflows, credentials,
> integrations — moves to any device intact.

---

## 1. Context & goals

Self-hosted n8n (Community Edition) is powerful but has rough edges for non-experts:
- On Windows you must set up WSL2 + Docker before n8n will run.
- The first-run **owner login** looks like a cloud sign-up but is actually a *local* account.
- There's no built-in way to reproduce the **exact** instance on a new machine.

**Goal:** a single tool, `lon`, that bootstraps prerequisites, runs/manages n8n via Docker, and
provides faithful encrypted portability — without us hosting any backend.

**Non-goals:** a hosted sync service; multi-tenant orchestration; replacing n8n's own UI.

**Final product goal:** *one command* installs prerequisites and runs n8n.
**MVP goal:** validate the core local lifecycle + encrypted portability loop first — for MVP, prerequisite
installation is **detect-and-guide**; **automatic WSL/Docker provisioning lands post-MVP** (Phase 4).

**MVP scope (to manage the large surface):** ship **Linux/WSL only** — commands `doctor` / `init` /
`up` / `down` / `restart` / `status` / `logs` / `open` / `backup` / `restore` (local-file bundle) — with
Docker via **detect + guided manual install**. `backup`/`restore` are **hard MVP** and already include
recovery-slot creation + the first-run passphrase/recovery-code setup; the standalone **`recovery` /
`passphrase` admin commands** (show/rotate/change/reset) are the **Phase-3d fast-follow** (§13) that lands
right after the core backup→restore loop is green — they do **not** gate the portability proof. **Deferred to
post-MVP:** Windows auto-bootstrap (`wsl --install` + reboot-resume), tunnels (OAuth / inbound webhooks)
**including `init`'s tunnel/domain offer**, remotes, keychain caching, the Postgres profile, and the
`config` / `update` / `remote` / `tunnel` commands. Rationale:
validate the encrypted portability loop — the actual product — before investing in the riskiest,
lowest-value-per-effort provisioning. The decisions below remain the target design; **§13 is the phased
roadmap** (Phase 0 = minimal CLI that generates + runs the compose → Phase 3 = encrypted backup/restore
= MVP) that stages them with per-phase checkpoints.

### Locked design decisions
| Area | Decision |
|---|---|
| CLI runtime | Real CLI runs **inside WSL Ubuntu** on Windows; thin PowerShell bootstrap only on the host. One code path for Win/Linux/macOS. |
| Docker | **Docker Engine in WSL/Linux** (apt). No Docker Desktop / WSL-integration hack. macOS uses **colima** (detect existing Docker Desktop/OrbStack). |
| Install policy | **Detect → explain → prompt → install** with consent; handle WSL reboot-resume. Never silent. |
| Backup fidelity | **Full instance bundle**: the whole `/home/node/.n8n` volume (DB, `config`, binary data) + `.env` + compose + **manifest**; `pg_dump` added in Postgres mode. Logical `export:workflow` optional. |
| Bundle security | **Envelope encryption, multi-slot**: passphrase + **default-on recovery code** (persisted so every backup can include the recovery slot) + optional OS keychain (**often unavailable on WSL** — see §10). |
| Sync | **Encrypted bundle** + **bring-your-own remote** (Git / S3 / folder). No backend. |
| Networking | **(post-MVP)** **ngrok assigned dev domain default** (offered at init *once tunnels land*, skippable, enableable anytime); n8n `--tunnel` zero-config option; cloudflared/own-domain for no-cap + production. |
| State store | **SQLite** registry of instances / backups / remotes / settings — metadata, not duplicated secrets. |

---

## 2. High-level architecture

```
                          ┌──────────────────────────── Windows host ────────────────────────────┐
                          │  bootstrap_win.ps1                                                     │
                          │   • detect/install WSL (+ reboot-resume)                              │
                          │   • install uv + `lon` INSIDE Ubuntu, then hand off                   │
                          └───────────────────────────────┬──────────────────────────────────────┘
                                                          │ (everything below runs in WSL / Linux / macOS)
   ┌───────────────────────────────────────── lon (Typer CLI) ─────────────────────────────────────────┐
   │  app.py  ──dispatch──►  commands: doctor│init│up│down│restart│status│logs│update│open│             │
   │                                          backup│restore│remote│tunnel│config                        │
   │                                                                                                     │
   │  bootstrap/        core/                                  compose/                                  │
   │   platform.py       instance.py  (lifecycle)              template.py + assets/*.tmpl               │
   │   windows.py        backup.py    (full-volume capture)                                              │
   │   docker.py         crypto.py    (envelope/multi-slot)    state.db  (SQLite registry)               │
   │                     remote.py    (git/s3/folder)                                                    │
   │                     tunnel.py    (ngrok/n8n/cloudflared)                                            │
   │                     keychain.py  (optional passphrase cache)                                        │
   └───────────────┬─────────────────────────────┬───────────────────────────────┬─────────────────────┘
                   │ shells out                   │ reads/writes                  │ controls
                   ▼                              ▼                               ▼
           docker / docker compose        ~/.config/local-n8n/            tunnel provider (ngrok…)
                   │                         state.db                              │ public URL
                   ▼                         instances/<name>/{compose,.env}       ▼
           ┌─────────────────┐                                            inbound webhooks / OAuth
           │  n8n container  │  ◄── named volume: /home/node/.n8n (DB + config/binary data)
           └─────────────────┘
```

*(The box shows the full **target** command set; the **MVP subset** is
`doctor`/`init`/`up`/`down`/`restart`/`status`/`logs`/`open`/`backup`/`restore` — the
`recovery`/`passphrase` **admin** commands are the Phase-3d fast-follow, §13.)*

**Layering:** `app.py` (thin CLI) → `core/*` (domain logic) → `bootstrap/*` (host/OS provisioning)
+ `compose/*` (rendering). `core` never imports `app`; OS-specific code is isolated in `bootstrap`.

---

## 3. Components & responsibilities

| Module | Responsibility |
|---|---|
| `app.py` | Typer wiring, global flags (`--instance`, `--verbose`, `--yes`, `--no-install`, `--dry-run`, `--json`), Rich output, error formatting |
| `bootstrap/platform.py` | Detect OS, WSL presence/version, distro, in-WSL vs Windows-native context |
| `bootstrap/windows.py` | `wsl -l -v` checks; `wsl --install -d Ubuntu`; reboot-required detection; idempotent re-run; install uv + `lon` in distro; **hand-off** (invoke `wsl -d Ubuntu -- lon …` forwarding argv verbatim, **streaming stdout/stderr and propagating the WSL exit code** to the host; prompts run inside WSL; reboot-resume state persisted host-side — contract pinned in §13 Phase 4) |
| `bootstrap/docker.py` | Detect Docker Engine; prompt+install via official apt repo (Linux/WSL) or colima (macOS); add user to `docker` group; start service (`service docker start` under WSL) |
| `compose/template.py` | Render `docker-compose.yml` + `.env` from instance config; SQLite default, optional `postgres` profile |
| `core/instance.py` | Lifecycle: up/down/restart/status/logs/update/open; queries `docker` + SQLite |
| `core/backup.py` | Quiesce (stop only n8n; keep Postgres up for `pg_dump`) → capture full `.n8n` volume (helper-container `tar --numeric-owner`) → assemble bundle + manifest → seal (**restore prior run-state in a `finally`**); restore = unseal → verify manifest/version → rehydrate → up |
| `core/crypto.py` | Envelope encryption: random DEK encrypts payload; DEK wrapped per key-slot; header (re)write |
| `core/remote.py` | Push/pull encrypted bundles to git / s3 / folder remotes |
| `core/tunnel.py` | Provider abstraction; bring up public URL; set `WEBHOOK_URL`/`N8N_EDITOR_BASE_URL` + `N8N_PROXY_HOPS=1`, drop `N8N_SECURE_COOKIE=false` on HTTPS; recreate |
| `core/keychain.py` | Optional passphrase caching via `keyring`; graceful fallback when no keychain (headless WSL) |
| `core/state.py` | SQLite schema + DAO (instances, backups, remotes, settings) |

---

## 4. Tech stack

| Concern | Choice | Why |
|---|---|---|
| CLI framework | **Typer** + **Rich** | type-driven subcommands, clean UX |
| Packaging | **uv** project; pkg `local_n8n`, tool `local-n8n`, entry point **`lon`**; `uv tool install` | fast, isolated |
| Encryption | **`cryptography`** (AES-256-GCM) + **`argon2-cffi`** (Argon2id KDF) | multi-slot envelope, well-supported |
| Keychain | **`keyring`** | abstracts libsecret / macOS Keychain / Win Cred Mgr |
| State DB | stdlib **`sqlite3`** | zero extra deps |
| Docker / tunnels | subprocess to `docker`, `docker compose`, `ngrok`, `cloudflared` | use official tooling, no SDK lock-in |
| Testing / QA | **pytest** + **pytest-mock**, Typer **`CliRunner`**, `tmp_path`/temp SQLite; **ruff** (lint) + **ty** (Astral type checker); **full type hints** | one Astral toolchain (uv/ruff/ty); lint + types gate CI (see §15). **`ty` is pre-1.0 — fall back to `pyright`/`mypy` as the CI gate if it isn't stable enough at build time; the hints are the invariant, the checker is swappable.** |

---

## 5. Filesystem & config layout

```
~/.config/local-n8n/                 # inside WSL on Windows
  state.db                           # SQLite registry + settings (single source of truth)
  instances/
    default/
      docker-compose.yml             # rendered
      .env                           # N8N_ENCRYPTION_KEY (chmod 600), ports, base URL, DB type
      recovery.wrapped               # per-instance recovery secret (after first backup); passphrase-wrapped or in keychain
  backups/                           # local bundle cache (also pushable to remotes)
    default-2026-07-01T12-00.n8nbundle
```
Docker named volume `n8n_<instance>_data` holds n8n's own data (`/home/node/.n8n`, incl. `database.sqlite`).
**Config home** defaults to `~/.config/local-n8n/` and is overridable via **`LOCAL_N8N_HOME`** (every path
above derives from it). Each instance's **Docker Compose project name is `local-n8n-<instance>`**, giving
deterministic container/network names. The **active data volume is a pointer** in `state.db.data_volume`
(initially `n8n_<instance>_data`; atomic restore bumps it to a new generation `n8n_<instance>_data.g<N>`),
and compose renders the volume's `name:` from that pointer. Instance **`<name>` must match `^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$`**
(lowercase letters, digits, hyphens; must start and end alphanumeric — no leading/trailing `-`) since it's
used verbatim in paths, the compose project name, and the volume name; `lon` validates and rejects anything else.

---

## 6. Data model (SQLite, sketch)

```sql
CREATE TABLE instances (
  name TEXT PRIMARY KEY,
  compose_path TEXT NOT NULL,
  data_volume TEXT NOT NULL,          -- ACTIVE generation volume name (pointer; see §16)
  port INTEGER NOT NULL,
  base_url TEXT,                      -- public/tunnel URL if set
  db_type TEXT NOT NULL DEFAULT 'sqlite',
  image_ref TEXT NOT NULL,            -- pinned image as tag@digest
  n8n_version TEXT,
  enc_key_ref TEXT NOT NULL,          -- pointer to .env location (NOT the key itself)
  created_at TEXT, last_started_at TEXT
);
CREATE TABLE backups (
  id INTEGER PRIMARY KEY,
  instance TEXT REFERENCES instances(name),
  created_at TEXT NOT NULL,
  location TEXT NOT NULL,             -- local path
  remote_id INTEGER REFERENCES remotes(id),
  checksum TEXT NOT NULL, size INTEGER, n8n_version TEXT
);
CREATE TABLE remotes (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,                 -- git | s3 | folder
  location TEXT NOT NULL,
  config_json TEXT
);
CREATE TABLE settings ( key TEXT PRIMARY KEY, value TEXT );
-- e.g. default-instance, cache-passphrase, default-port, default-image-tag, tunnel-provider,
--      ngrok-authtoken-ref, backup-retention (keep-N / keep-last-<days>d; default keep-all)
```
**Schema versioning:** the DB carries a version (`PRAGMA user_version`, or a `schema_migrations` table)
and `lon` runs ordered, idempotent migrations on startup. This is separate from `compose_schema` in the
manifest (which versions the rendered compose/`.env` layout) and `bundle_schema`/`format_schema`.

**DB concurrency:** open `state.db` in **WAL mode** with a **`busy_timeout` (≥ 5 s)** so a slow concurrent
read never fails a mutating op with *"database is locked"*; the per-instance lock (§16) still serializes
the operations themselves.

**Secrets policy:** `state.db` stores **references/metadata only**. The `N8N_ENCRYPTION_KEY` lives in
the instance `.env` (chmod 600) and inside encrypted bundles. Sensitive provider tokens are kept in
the OS keychain or `.env`, never in plaintext columns.

### 6.1 Bundle format (envelope header + encrypted manifest)

A `.n8nbundle` has **two layers**. Crypto metadata **cannot** live only in the encrypted manifest —
you must be able to derive the key *before* you can decrypt — so it lives in an **outer, unencrypted
envelope header**. The encrypted payload carries `manifest.json`, which governs **restore semantics**.

**On-disk framing:** `magic (4 bytes "N8NB")` · `header_len (uint32, big-endian)` · `header (canonical
JSON, UTF-8)` · `ciphertext_with_tag (AES-256-GCM ciphertext ‖ 16-byte GCM tag)`. Parse by reading the
magic, then `header_len`, then exactly that many header bytes; everything after is `ciphertext_with_tag`
(last 16 bytes = tag; total length = header `payload.ciphertext_length`). The tag is **appended to the
ciphertext**, not stored in the header — it is the output of authenticating the header-as-AAD, so it
cannot live inside that same header. The parser **rejects** the bundle if the 4-byte file-prefix magic
and the header's `magic` field disagree, or if `format_schema` is unknown.

**Fixed constants (pin before coding):** DEK = **32 bytes**; AES-256-GCM **nonce = 12 bytes**, **tag = 16
bytes**; Argon2id **salt = 16 bytes** per slot with params **`t=3, m=65536 KiB (64 MiB), p=4`**; **per-slot
wrap** = AES-256-GCM of the DEK under the Argon2id-derived KEK → `wrapped_dek = ciphertext(32) ‖ tag(16)`
(48 bytes); binary header fields (`salt`/`nonce`/`wrapped_dek`) are **base64, RFC 4648, padded**;
`header_len` is **uint32 big-endian, max 64 KiB** (reject larger); after the header, **exactly
`payload.ciphertext_length` bytes remain** (ciphertext ‖ 16-byte tag) — **any extra ⇒ reject**.

**Canonical JSON** (the header is AAD-authenticated, so the writer must serialize deterministically):
UTF-8, **keys sorted**, **compact separators** (`,` and `:`, no whitespace), no trailing newline,
**integers only — no floats**. Determinism is required only on the **write** path. **The open path
never re-serializes:** it uses the exact `header_len` bytes read from disk **verbatim** as the AAD, so
unknown/future header fields (or any serializer drift) can never break verification of a valid bundle.

**Tamper protection:** the outer header is **not secret but is authenticated** — it is passed as the
AES-256-GCM **associated data (AAD)** when sealing the payload, so altering KDF params or slot metadata,
or stripping a slot, makes decryption fail. The whole-bundle checksum is recorded in the `backups` table
for integrity/identification. The GCM tag already authenticates the entire encrypted payload, so the
manifest's per-file `sha256` values are **defense-in-depth / post-decrypt identification**, not the
primary integrity mechanism.

**Outer envelope header (plaintext, read first):**

```jsonc
{
  "magic": "N8NB",            // bundle marker
  "format_schema": 1,         // envelope/crypto format version
  "cipher": "aes-256-gcm",
  "kdf": "argon2id",
  "kdf_params": { "t": 3, "m": 65536, "p": 4 },
  "slots": [                  // one per unlock method; any opens the bundle
    { "type": "passphrase", "salt": "…", "nonce": "…", "wrapped_dek": "…" },
    { "type": "recovery",   "salt": "…", "nonce": "…", "wrapped_dek": "…" }
    // optional { "type": "keychain", … }
  ],
  "payload": { "nonce": "…", "ciphertext_length": 12345 }   // bytes of ciphertext_with_tag (incl. 16-byte tag); tag is appended, not stored here
}
```

**Inner `manifest.json` (inside the AES-256-GCM-encrypted payload — restore semantics):**

```jsonc
{
  "bundle_schema": 1,
  "lon_version": "0.1.0",                               // CLI that wrote the bundle
  "created_at": "2026-07-01T12:00:00Z",
  "platform_created_on": "linux-wsl | linux | macos",
  "instance": "default",
  "n8n_version": "2.x.y",                               // example only — whatever stable tag is current
  "image": "docker.n8n.io/n8nio/n8n:2.x.y@sha256:…",    // tag + digest, pinned
  "db_type": "sqlite|postgres",
  "compose_schema": 1,                                  // version of our rendered compose/.env layout
  "features": ["full_volume", "envelope_v1"],           // capabilities the bundle relies on (forward-compat gate)
  "files": {                                            // per-file sha256; no self-reference (manifest not hashed here)
    "n8n_volume.tar": "sha256:…",
    "docker-compose.yml": "sha256:…",
    ".env": "sha256:…",
    "pg_dump.sql": "sha256:…",                          // present only in Postgres mode
    "exports/*": "sha256:…"                             // one entry per exported file, only with --with-exports
  },
  "base_url": "https://name.ngrok-free.dev",
  "tunnel": { "provider": "ngrok|n8n|cloudflared|none", "domain": "…", "authtoken_included": true },
  "restore_policy": "same-version by default; --upgrade allows forward migration"
}
```

**Payload tree (pre-encryption):** `manifest.json`, `n8n_volume.tar` (full `/home/node/.n8n`),
`.env`, `docker-compose.yml`, optional `pg_dump.sql`, optional `exports/` (logical workflow exports).

---

## 7. Command surface (target)

Full **target** surface; rows tagged **(post-MVP)** ship after Phase 3. **MVP subset:** `doctor`, `init`,
`up`/`down`/`restart`, `status`, `logs`, `open`, `backup`, `restore` (hard MVP); the `recovery` and
`passphrase` **admin** commands are the **Phase-3d fast-follow** — `backup`/`restore` themselves already set
the passphrase + emit recovery slots.

| Command | Behavior |
|---|---|
| `lon doctor` | **Read-only** check of OS, WSL (Win), Docker Engine, distro, port availability; **detect Docker Desktop WSL-integration vs Engine-in-WSL conflict** and explain the chosen path; pass/fail + fix hints. Installs happen via `init`/`bootstrap` or the opt-in **`doctor --fix` (post-MVP)** — never bare `doctor` |
| `lon init` | Guided first run: ensure prereqs (**detect + guide**; auto-install is post-MVP) → generate compose+`.env` → generate & store `N8N_ENCRYPTION_KEY` → register instance → **offer tunnel/domain setup (skippable, post-MVP)** → `up` → `open`; explains the browser owner-account step |
| `lon up` / `start` · `down` / `stop` · `restart` | container lifecycle (down keeps the volume) |
| `lon status` | container state, health, URL, version (SQLite + `docker`) |
| `lon logs [-f]` | stream container logs |
| `lon update` | **(post-MVP)** **auto-`backup` first** (skippable with `--no-backup`) since image updates may run DB migrations; then pull newer image, recreate, record version |
| `lon open` | open the editor URL in a browser — tries `wslview` → `powershell.exe Start-Process` (WSL) → `xdg-open` (Linux) → `open` (macOS); **prints the URL when no opener is available** |
| `lon backup [--push <remote>] [--with-exports]` | **full-instance** encrypted bundle (whole `.n8n` volume). **Warns about the brief n8n downtime before quiescing** — backup stops n8n for a consistent snapshot (§12), so it prompts before stopping (proceeds on confirm or `--yes`); matters most once inbound webhooks land (missed events during the window). **First run sets the backup passphrase + shows the recovery code once** and prints the recovery rule verbatim (*keep at least one of {a working instance, an openable bundle}*; §10). Record in SQLite; optional remote push + git-friendly logical exports |
| `lon restore <bundle \| --from-remote> [--replace]` | ensure prereqs (incl. **pulling the pinned image** — needs registry access, §12) → decrypt → rehydrate **full volume** + key + base URL → `up`. **Refuses to overwrite an existing instance unless `--replace`** (which snapshots current state first, sealed with the **existing** instance's unlock material — §16) |
| `lon remote add\|list\|remove` | **(post-MVP)** configure git / s3 / folder remote |
| `lon tunnel start\|stop\|status` | **(post-MVP)** bring up/down public URL (ngrok default / n8n `--tunnel` / cloudflared); wire `WEBHOOK_URL`+`N8N_EDITOR_BASE_URL`+`N8N_PROXY_HOPS` (re-secure cookie on HTTPS); print OAuth redirect URL to register |
| `lon config get\|set` | **(post-MVP)** settings incl. `cache-passphrase`, default port, image tag, base URL, tunnel provider, `ngrok-authtoken` |
| `lon recovery show\|rotate` | `show` reveals the recovery code (**requires authorization — passphrase or keychain**, since `recovery.wrapped` is encrypted); `rotate` generates a new recovery secret and re-wraps the recovery slot + future bundles |
| `lon passphrase change` | set a new backup passphrase (authorize with current passphrase or recovery code); re-wraps the local recovery secret + future bundles' passphrase slot. **Existing bundles are NOT rekeyed** — each still opens only with the passphrase/recovery code current when it was written; there is intentionally **no bulk "rekey old bundles" command** (would require re-reading every bundle). To refresh, run a new `backup` |
| `lon passphrase reset` | **escape hatch** (live instance required): both passphrase **and** recovery code lost → discard old unlock material, set a fresh passphrase + recovery code; **old bundles become permanently unopenable** |

### 7.1 CLI contracts (flags & exit codes — pin before coding)

These global flags are listed in §3; their **contracts** are fixed here so scripts and CI can depend on them.
(`--instance` selects the target instance and `--no-install` — the post-MVP opt-out of prereq auto-install —
are intentionally left uncontracted here; they need no stable machine-facing behavior beyond their obvious effect.)

- **Exit codes.** `0` success; `2` usage error (Typer default for bad args/flags); `1` generic/unexpected
  error. Expected, script-branchable failures get **stable, documented codes**: `10` prerequisite missing
  (Docker/daemon), `11` port in use, `12` instance busy (lock held, §16), `13` instance not found / not
  registered, `14` bundle decrypt/auth failure, `15` version-incompatible restore. (Phase 0 only needs
  `0`/`1`/`2` + `10`/`11`; the rest land with the commands that raise them — never reuse a code for a new meaning.)
- **`--json`.** Emits a **single JSON object to stdout** (human Rich output then goes to stderr / is
  suppressed) with a stable shape: `{ "ok": bool, "command": str, "data": {…}, "error": {"code": int,
  "message": str} | null }`. Failures set `ok:false`, populate `error`, and the **process exit code still
  reflects the failure**. No partial/streaming JSON except `logs -f` (newline-delimited objects).
- **`--dry-run`.** Plan-only: **no** container, volume, filesystem-write, or remote side effects. Prints
  (or, with `--json`, emits) exactly what *would* happen — files to write, `docker` commands to run, pointer
  swaps. Read-only detection (`doctor`/`status`) still runs; mutating ops under `--dry-run` **do not take the
  per-instance lock**. **Secrets are never materialized in dry-run output:** a generated `N8N_ENCRYPTION_KEY`,
  passphrase, recovery code, or provider token is shown **redacted** (`***`) or as a labeled synthetic
  placeholder — dry-run must never print (or generate-and-print) a real key. (`--dry-run` itself arrives with
  the global flags in Phase 1; this rule binds the `.env`-render codepath introduced in Phase 0, so that once
  dry-run wraps it the generated key is redacted.)
- **`--yes`.** Assume "yes" for confirmation prompts (CI/non-interactive). It **never** bypasses a guard
  that has no safe default — `restore` over an existing instance still requires `--replace`, `passphrase
  reset` still requires explicit data-loss confirmation — and it **never** supplies secrets (§16: secrets
  only via prompt/stdin).
- **`--verbose`.** Adds diagnostic logging to **stderr only**; must not alter stdout or the `--json` payload.

---

## 8. docker-compose template (key points)

- Image `docker.n8n.io/n8nio/n8n`; mounted at `/home/node/.n8n`; `restart: unless-stopped`. The volume is
  declared with an **explicit top-level `name:` set to the instance's active data volume** (from
  `state.db.data_volume`; initially `n8n_<name>_data`, later a generation like `n8n_<name>_data.g<N>` after
  atomic restore) so Compose does **not** prefix it with the project name — swaps are a pointer flip +
  re-render (§16).
- `.env`: fixed CLI-generated `N8N_ENCRYPTION_KEY` (so credentials survive container re-creation),
  configurable `N8N_PORT`. **`N8N_SECURE_COOKIE=false` is set ONLY for plain `http://localhost`** — when
  an HTTPS tunnel/domain is active it is removed so the cookie stays secure. When a tunnel/reverse proxy
  is active, set `WEBHOOK_URL`/`N8N_EDITOR_BASE_URL`/`N8N_HOST`/`N8N_PROTOCOL` **plus `N8N_PROXY_HOPS=1`**.
- Current n8n-recommended envs included by default: `N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true`,
  `N8N_RUNNERS_ENABLED=true`, and timezone via `GENERIC_TIMEZONE` + `TZ` (detected from the host,
  overridable). The image is **pinned to an exact `tag@digest` chosen and frozen at release time** (both
  recorded in the manifest) — resolve and freeze the digest when cutting a release; do not depend on a
  floating "current 2.x". Use the **multi-arch manifest-list digest** (§16), not a host-specific per-arch digest.
  **Version-coupling caveat:** because the pin is frozen per `lon` release and the MVP has **no `update`
  command**, an MVP user stays on the n8n version their `lon` build shipped until they upgrade `lon`
  (the post-MVP `lon update` in Phase 6 adds an in-place path). This is a **documented limitation**, called
  out in the README (§13 Phase 0) — not a bug.
- Default DB = n8n's **SQLite** (fine for single-user local). Optional **`postgres` compose profile** (post-MVP).
  Backup **always captures the full `/home/node/.n8n` volume**; the DB portion additionally branches on
  type (volume file in SQLite mode vs a `pg_dump` in Postgres mode).

**Image-pin release process (repeatable — the digest invariant needs a repeatable step):**
1. Pick the target n8n tag — a **stable, non-floating** release.
2. Resolve its **multi-arch manifest-list digest**: `docker buildx imagetools inspect
   docker.n8n.io/n8nio/n8n:<tag>`; record `<tag>@sha256:<manifest-list-digest>` (§16), **not** a per-arch digest.
3. **Smoke-test that exact pin** with the §14 fast loop (`init` → owner + workflow + credential → `backup` →
   wipe → `restore`) on **both amd64 and arm64** before it ships.
4. Bake the frozen `tag@digest` into the release as the default `default-image-tag`, record it in the
   `CHANGELOG`. Bumping n8n = a new `lon` release that repeats 1–3 (until post-MVP `lon update` automates the
   client side).

---

## 9. Networking & integrations

Integrations split by **direction** — this decides if a public URL is needed:

| Type | Public URL? | Handling |
|---|---|---|
| Outbound **API-key** (OpenAI, REST, DB, mail) | No | works on `localhost`, offline-friendly |
| **OAuth2** sign-in (Google, Slack…) | callback URL the provider accepts | some allow `http://localhost`; others need HTTPS/public → tunnel |
| Inbound **webhook triggers** (Stripe/GitHub/Telegram → n8n) | Yes | external service must reach n8n → tunnel or domain |

> **⚠️ MVP networking limitation (surface prominently in README + `init` copy).** MVP ships **local-only**
> networking (no tunnels until Phase 5). So during MVP: **inbound webhooks and HTTPS-only OAuth callbacks do
> not work**, and only `http://localhost` OAuth providers can complete a sign-in. `backup`/`restore` faithfully
> carry **stored OAuth tokens** across machines (proven in Phase 3), but that is **token persistence, not live
> provider callback continuity** — Google/Slack/webhook flows only "just work" across machines once Phase 5
> lands. Don't let README/CLI copy imply otherwise before then.

**Providers (via `tunnel.py`) — all of this is post-MVP; the MVP ships local-only networking:**
- **ngrok (default real provider):** free plan gives **one assigned dev domain** (auto-allocated, not
  user-chosen) that persists across restarts. Free limits: **20k HTTP/S requests/mo, 1 GB transfer/mo,
  up to 3 online endpoints**; needs an authtoken. Setup **offered at `init`, skippable, enableable anytime**.
  ⚠️ The free tier injects a **browser interstitial** — usually fine for API/webhook traffic, but it can
  interfere with **browser-based OAuth/editor** flows; a paid plan or cloudflared/own-domain removes it.
  *(These free-tier figures reflect ngrok's current pricing and may change — treat as documentation, not a
  hard guarantee; verify at setup.)*
- **cloudflared / own domain (the other real provider):** stable hostname needs a domain you own;
  **no bandwidth cap**; also the production reverse-proxy + HTTPS path.
- **n8n `--tunnel`:** a **dev-only convenience** for a quick local webhook test. Its underlying mechanism
  is provider-managed and **may change between n8n releases**, so it is **not** a stable portability
  feature — `ngrok`/`cloudflared` are the abstractions we depend on.

**Bandwidth note:** only **inbound** webhook/OAuth-callback traffic crosses the tunnel (small JSON);
**outbound** API calls go machine→provider directly and don't count against the ngrok cap.

**Durability:** secrets-at-rest never break on our side (we carry the encryption key, so API-key and
OAuth tokens restore intact). Breakage only comes from the **provider** rotating a key or expiring a
refresh token — fixed by re-auth, outside any backup tool's control.

---

## 10. Security & recovery model

**Two distinct secrets — do not conflate:**
| Secret | Protects | Lives in | If lost |
|---|---|---|---|
| `N8N_ENCRYPTION_KEY` | credentials inside a running instance | instance `.env` + bundles | that instance's creds unreadable |
| Bundle passphrase + recovery code | the portable bundle at rest | user's head / password manager / keychain | only that bundle is locked |

**Envelope encryption (`crypto.py`):**
1. Random 256-bit **DEK** encrypts the payload tar (AES-256-GCM).
2. DEK is **wrapped once per key-slot**, each slot a KEK:
   - **passphrase** (Argon2id) — everyday unlock,
   - **recovery code** (default-on, shown once when backups are first enabled) — recover a forgotten passphrase,
   - **(optional) OS keychain** — unattended backups on a desktop.
3. These per-slot `{type, salt, nonce, wrapped_dek}` records — plus cipher/KDF params and the payload
   **nonce** (the GCM **tag is appended to the ciphertext**, not stored here) — live in the **outer,
   unencrypted envelope header** (§6.1), since they're needed *before* decryption. **Any** slot opens the
   bundle. The encrypted manifest governs restore semantics only.
4. Forgot passphrase → unlock via recovery code → **re-wrap** a new passphrase slot (no
   re-encryption of the payload).

**Recovery-secret lifecycle (decision):** the recovery code maps to a stable per-instance **recovery
secret** generated the **first time you run `lon backup`**. It is persisted locally **wrapped by the passphrase** (or in the OS
keychain where available), so **every** `lon backup` can add a recovery slot without re-prompting.
`lon recovery show` re-derives the human-readable code; `lon recovery rotate` generates a new secret
and re-wraps the local copy + future bundles. Bundles stay openable by the recovery code that was
current when they were made; **likewise `lon passphrase change` never rekeys existing bundles** — it
re-wraps only the local secret + future bundles, so old bundles still need their original passphrase (or
the recovery code current at their creation). There is intentionally no bulk "rekey old bundles" command.
(Recovery-code **format** — entropy, encoding, checksum, KDF input — is specified in §16.)

**Escape hatch — lost passphrase AND recovery code, but the live instance exists:** run **`lon passphrase
reset`**. Because `recovery.wrapped` is sealed under the *old* (lost) passphrase it cannot be unwrapped, so
reset **discards** the old `recovery.wrapped` + slot material and generates a **fresh passphrase + recovery
code** from the live instance. Old bundles stay **permanently locked** (expected — their unlock secrets are
gone); new backups use the new pair. Requires a registered, live instance.

**Tunnel portability (decision + threat model):** tunnel provider + assigned domain are written to the
**manifest**, and the provider token (e.g. ngrok authtoken) *may* be included **inside the encrypted
bundle** so a restore reproduces the same webhook/OAuth URL. Because a bundle is often **synced to
Git/S3/a shared folder**, embedding a live provider token widens its blast radius if the passphrase leaks.
So embedding is **opt-in with an explicit prompt** at backup time (default: **do not embed**); when omitted
(or via `--no-tunnel-secret`), restore prompts to re-link the tunnel. The token, when embedded, is only ever
inside the AES-GCM payload — never in the manifest's plaintext-visible fields or `state.db`.

**Keychain on WSL (caveat):** because the CLI runs *inside* WSL, Python `keyring` sees the Linux/WSL
Secret Service — usually **absent** on a headless distro — **not** Windows Credential Manager. So
keychain caching is **off by default on WSL** and falls back to the passphrase/recovery prompt. A
Windows bridge (shim to Credential Manager) is optional and **post-MVP**.

**Why no vendor recovery:** this is self-hosted — n8n has no account, copy, or key on their side, and
we deliberately don't escrow keys (escrow = backdoor). **But a forgotten passphrase rarely matters:**
the *live instance is independent of the bundle*, so you just run `lon backup` again with a new
passphrase. True data loss needs **passphrase + recovery code + the live instance** all gone at once.
Rule surfaced to users **verbatim** — in `lon backup` first-run output and the README (not just this
design doc): *keep at least one of {a working instance, an openable bundle} and you're never stuck.*

---

## 11. Key sequences

**`lon init` (fresh machine)**
```
doctor → [missing prereqs] prompt → install WSL? (Win, reboot-resume) → install Docker Engine
   (this auto-install is the Phase-4 target; the MVP guides WSL/Docker setup manually)
 → render compose+.env, gen N8N_ENCRYPTION_KEY → register instance in SQLite
 → offer tunnel/domain (ngrok) [post-MVP; skippable] → docker compose up -d → open browser
 → user creates LOCAL owner account in n8n UI (cannot be bypassed; explained by CLI)
```

**`lon backup`**
```
[first backup only: prompt to set passphrase → generate & show recovery code once]
record prior run-state  →  quiesce for a consistent snapshot:
   SQLite mode  : stop the n8n container, then copy the .n8n volume
   Postgres mode: stop ONLY the n8n container (keep DB up), pg_dump the running DB, copy the .n8n volume
 → capture: full /home/node/.n8n volume (DB, config, binaryData) + .env (encryption key) + compose
   + manifest.json   [+ pg_dump.sql if Postgres]   [+ exports/ if --with-exports]
 → tar  →  crypto.seal (random DEK; wrap with passphrase + recovery + optional keychain slots;
   bind the outer header as AEAD associated data)  →  write magic + header_len + header + ciphertext‖tag → <name>.n8nbundle
 → record in SQLite (bundle checksum)  →  optional remote.push
 →  **finally: restore prior run-state**  ← restart n8n only if it was running before; never auto-start a stopped instance
```

**`lon restore <bundle>` (new device)**
```
ensure prereqs → crypto.open (passphrase|recovery|keychain) → read manifest → version check
 → if instance already exists: abort unless --replace (then snapshot current state first)
 → restore .n8n volume (+ pg_restore) + write .env (carried key + base_url) + tunnel config
 → register → pull pinned image tag@digest → up
 → identical owner login, settings, workflows, credentials, binary data, base URL
```

**Volume copy mechanism (real-Docker detail):** capture/restore the named volume via a **short-lived
helper container** (e.g. `alpine`) that `tar`s with **`--numeric-owner`** to preserve `uid:gid` (n8n runs
as `node` = 1000:1000). Restore extracts into a **fresh** volume the same way, then ensures `.n8n/config`
is **0600** to satisfy `N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS`. Do not rely on host bind-mount ownership.

---

## 12. Error handling & edge cases

- **WSL reboot loop:** detect "reboot required"; print clear next step; bootstrap is **idempotent**
  and continues on re-run (no silent auto-resume).
- **Docker group not yet effective:** after adding user to `docker`, instruct re-login or run via
  `newgrp`/`sudo` for the current session.
- **Docker Desktop vs Engine-in-WSL conflict:** if Docker Desktop's WSL integration is enabled for the
  distro **and** a native Engine runs inside WSL, the two `docker` contexts can clash. `doctor` detects
  both, names which is active, and recommends using exactly one (default Engine-in-WSL; otherwise use
  Desktop's and skip our Engine install).
- **`doctor --fix` (opt-in installs):** bare `doctor` is **read-only** and only diagnoses; **`doctor --fix`**
  is the explicit, consent-gated path that performs the recommended installs (Docker Engine / colima,
  service start, `docker`-group add). It lands with Phase-4 automation and shares the same install routines
  as `init`/`bootstrap` — there is no silent install anywhere.
- **Restore over an existing instance:** `restore` **refuses to overwrite** a registered instance unless
  `--replace` is passed (which snapshots the current state first, then replaces) — prevents clobbering a
  live instance by accident. Atomicity + rollback: see **§16 (restore transaction)**.
- **Concurrent operations:** mutating ops (`backup`/`restore`/`up`/`down`/`restart`/`update`) take a
  **per-instance lock** (§16) so they can't run over each other; read-only `status`/`logs` don't lock.
- **Port in use / multi-instance:** `doctor`/`init` detect a busy port; `init` **auto-selects the next
  free `N8N_PORT`** for a new instance (rather than defaulting every instance to `5678` and colliding),
  and still offers a manual override.
- **Backup quiesce & restart:** `backup` stops **only the n8n app container** for a consistent snapshot
  (Postgres stays up so `pg_dump` runs). A **`finally`** restores the **prior run-state** — if n8n was
  running it is restarted; if it was already stopped it stays stopped — so a failed/aborted backup never
  changes whether the instance is running.
- **Disk space & backup retention:** full-volume tars (plus binary data) can be large, so `backup`
  **pre-checks free space** and fails early with a clear message rather than mid-write. The `backups/`
  cache and old volume generations don't accumulate forever: both are **pruned per the `backup-retention`
  setting** (keep-N / keep-last-Nd; default keep-all). Generation cleanup + orphan-volume sweep: see §16.
- **Encryption-key mismatch on restore:** prevented by always carrying the key in the bundle; if a
  user force-imports into a foreign-key instance, surface a clear error.
- **Version compatibility:** the bundle **pins the image tag + digest**; restore uses the **same n8n
  version by default** (the bundle's pinned image). Restoring an **older** DB into a **newer** image runs
  **forward migrations** — allowed only with **`--upgrade`**, which targets the **current `lon` release's
  pinned `tag@digest`** (not an arbitrary user-supplied version); restoring into an **older** image is
  **refused** (n8n has no down-migrations). `bundle_schema` in the manifest guards our own format changes.
- **Offline / registry-unavailable restore:** the bundle carries the full `.n8n` volume + `.env` + compose
  + manifest but **not the n8n image itself**, so `restore` must **pull the pinned `tag@digest` from the
  registry** — it is therefore **not fully offline** and fails clearly (exit `10`) if the registry or that
  digest is unavailable. Mitigations: pre-pull the image on the target, or the **optional image export**
  (`docker save` the pinned image alongside the bundle, restored via `docker load`) — **planned post-MVP**,
  off by default (it bloats the bundle by the image size). Restore's prereq check surfaces this before doing
  any work. So "moves to any device intact" assumes the target can obtain the pinned image.
- **ID collisions on logical import:** warn that same-ID workflows/credentials overwrite (full-volume
  restore avoids this entirely).
- **No keychain (headless WSL):** `cache-passphrase` silently falls back to prompting.
- **Tunnel limits hit (ngrok):** detect 429/limit, advise cloudflared/own-domain upgrade.

---

## 13. Roadmap, milestones & checkpoints

Each phase is **independently demoable** and ends at a checkpoint you verify before moving on.
**Phases 0–3 are the MVP** (Linux/WSL); **Phases 4–6 are post-MVP**. Every phase reuses the artifact
from the one before it — the compose `lon` renders in Phase 0 is the same one later phases extend.

### Phase 0 — Minimal `lon`: generate the compose + run it (with error handling)
- **Goal:** the smallest CLI that **writes** `docker-compose.yml` + `.env` and brings n8n up — failing
  gracefully, never with a raw stack trace.
- **Scope guard:** Phase 0 is deliberately tiny — **no** crypto, no registry/SQLite, no `init`, no Windows
  bootstrap, no tunnels. Those belong to later phases; keeping them out is what makes Phase 0 shippable in
  one sitting. If a task needs any of them, it's not Phase 0.
- **Build:** uv + **Typer + Rich** skeleton (Rich for output/error formatting) with `lon up` + `lon down`;
  `compose/template.py` renders `docker-compose.yml` + `.env` (generated `N8N_ENCRYPTION_KEY`, `N8N_PORT`,
  `N8N_SECURE_COOKIE=false`, recommended envs from §8, named volume); shell out to `docker compose up -d` /
  `down`. **Fully type-hinted; `ruff` + `ty` clean.** Ship a short **README** stating the *final*
  one-command promise but **labeling prereq auto-install as post-MVP** (MVP = detect-and-guide) and
  **noting the pinned-n8n-version limitation** (MVP has no `lon update`; moving to a newer n8n needs a
  newer `lon` build — §8).
  **Exception handling** for: Docker missing / daemon not running, port already in use, compose
  render/file-write IO errors, and non-zero `docker compose` exit — each mapped to a clear, actionable
  message + non-zero exit code.
- **Contract:** config home = `~/.config/local-n8n/`, overridable via **`LOCAL_N8N_HOME`** (all paths derive
  from it). Writes `instances/<name>/{docker-compose.yml,.env}` (`.env` chmod 600); default instance `default`
  (`--instance` to change). **Compose project name = `local-n8n-<name>`** (via `-p`) → deterministic
  container/network; volume `n8n_<name>_data` (**generation 1** — the `state.db.data_volume` pointer +
  generational restore arrive with the Phase-1 registry / §16). In Phase 0 (no `init` yet) **`lon up` renders the files
  if absent** then `up -d`, **idempotently — never overwriting an existing `.env`/key**; from Phase 2 on, `up`
  requires an instance registered by `init` and errors clearly otherwise. `down` keeps the volume.
- **Checkpoint ✅:** `lon up` writes compose+`.env` and starts n8n at `http://localhost:5678` (create
  owner + workflow; `lon down` then `lon up` → **data persists**). With Docker stopped or the port taken,
  `lon up` exits non-zero with a **readable error**, not a traceback.
- **Tests:** unit — `compose/template` render (compose/`.env` content, key generated, §8 envs present);
  error mapping via Typer `CliRunner` with a **mocked `docker compose` runner** (Docker-missing /
  daemon-down / port-in-use / non-zero exit → friendly message + non-zero code). No real Docker.
- **Ref:** §3, §8.

### Phase 1 — Full lifecycle + state registry + `doctor`
- **Goal:** complete the day-to-day commands and start tracking instances.
- **Build:** add `lon status/logs/restart/open` + global flags (`--yes`/`--json`/`--dry-run`/`--verbose`),
  Rich-rendered status/tables; `core/state.py` (SQLite registry) + `core/instance.py`; read-only `doctor`
  (OS / Docker / port). **Adopt** any pre-existing Phase-0 instance into the registry **without overwriting
  its `.env`** (preserve the encryption key); after this, `up` **consults/records via the registry
  (auto-adopting a Phase-0 instance)** — the hard "must be registered, else error" requirement lands in
  **Phase 2** once `init` is the entry point for creating a new instance.
- **Checkpoint ✅:** `status/logs/open/restart` work; the instance is recorded in `state.db`;
  `doctor` reports OS / Docker / port availability.
- **Tests:** unit — `state.py` DAO CRUD on a temp SQLite; `instance.py` status/log parsing from mocked
  `docker` output; `doctor` detection with mocked platform/Docker; CLI command tests (`CliRunner`).
- **Ref:** §2, §3, §5, §6, §7.

### Phase 2 — `lon init` guided first run (Linux/WSL)
- **Goal:** one command from nothing to a running, registered instance.
- **Build:** `init` (detect + **guided manual** Docker install, generate & store `N8N_ENCRYPTION_KEY`,
  register, `up`, `open`, explain the browser owner step); `doctor` adds the **Docker Desktop vs
  Engine-in-WSL** conflict check.
- **Checkpoint ✅:** on a fresh Linux/WSL shell, `lon init` yields a working instance; re-running is
  idempotent; the conflict check fires when Docker Desktop integration is enabled.
- **Tests:** unit — `init` flow with mocked prereq detection + install prompts; **idempotency** (second
  run no-ops); Docker Desktop-vs-Engine-in-WSL conflict detection from fixture inputs.
- **Ref:** §7, §11 (init), §12.

### Phase 3 — Encrypted backup / restore  ← the actual product  (slices: 3a → 3b → 3c core loop, then 3d admin)
Reproduce the entire instance on any machine from one encrypted file. The MVP-critical path is **3a→3b→3c**
(prove backup→wipe→restore); **3d** (the standalone `recovery`/`passphrase` **admin** commands) is the
**designated fast-follow** — it lands right after the core loop is green and does **not** gate the
portability proof, since `backup`/`restore` already create recovery slots + set the first-run passphrase in
3b/3c. Split so each slice is independently testable; don't advance until its checkpoint is green. **This is
the largest phase — decompose 3a–3d into a dedicated task board of small implementation tickets** (crypto
framing, each slot type, quiesce/`finally`, volume tar, manifest/hashes, `--replace` guard, version policy,
permission fix-up, …) rather than four big commits.

**3a — Crypto core (`core/crypto.py` — library only, no CLI, no persistence):** envelope + multi-slot,
framing, AAD, canonical JSON, the fixed constants (§6.1); slot wrap/unwrap for passphrase + recovery KEKs.
- **Checkpoint ✅:** seal/open round-trip; passphrase **and** recovery both open; wrong passphrase fails;
  header tamper fails (AAD); framing rejects bad magic / unknown `format_schema` / trailing bytes.
- **Tests:** unit — all the above + known-answer vectors, RNG injected. No Docker, no filesystem state.

**3b — Backup create (`core/backup.py` create path):** quiesce (stop only n8n; Postgres up for `pg_dump`),
helper-container volume `tar --numeric-owner`, manifest + per-file hashes, seal, record in SQLite,
**restart in `finally`**. First run sets the passphrase + **persists recovery material** (`recovery.wrapped`)
+ shows the recovery code once. (Recovery/passphrase **admin** commands are deferred to 3d.)
- **Checkpoint ✅:** `lon backup` on a live instance emits a `.n8nbundle`; the instance restarts (or stays
  down if it was down); manifest + per-file hashes validate.
- **Tests:** unit — manifest/hash build, quiesce+`finally` ordering (mocked docker), recovery-material
  persistence (via the 3a library). Integration (gated) — real backup.

**3c — Restore (`core/backup.py` restore path):** unseal, manifest/version check, **`--replace`** guard,
volume restore into a fresh volume (`--numeric-owner`, `config` → 0600), rehydrate `.env`/base URL, `up`.
- **Checkpoint ✅:** workflow + API-key cred + an **OAuth2 cred** (localhost-redirect provider or pre-seeded
  tokens — verify **stored tokens survive restore**, not live re-auth, which is Phase 5) + a **binary-data**
  node → `backup` → wipe volume → `restore` → all return intact; `restore` on a second box; `--replace`
  refuses/handles an existing instance. (= §14 fast loop.)
- **Tests:** unit — version-policy branches, `--replace` guard, permission fix-up (mocked). Integration
  (gated) — full `backup`→wipe→`restore` loop on real Docker.

> **— MVP complete: the instance is portable and self-contained (backup→restore proven at 3c). 3d below is
> admin fast-follow / polish; everything from Phase 4 on is post-MVP. —**

**3d — MVP fast-follow / admin polish (recovery/passphrase admin, after the loop is proven):** `lon recovery show/rotate`,
`lon passphrase change`, `lon passphrase reset` — all operate on the `recovery.wrapped` material from 3b.
- **Checkpoint ✅:** `recovery show` (authorized) prints the code; `rotate` re-wraps; `passphrase change`
  sets a new passphrase; `passphrase reset` on a live instance mints a fresh pair, leaving old bundles locked.
- **Tests:** unit — authorization gate, re-wrap correctness, `reset` discards old material (via 3a library).
- **Ref:** §6.1, §10, §11 (backup/restore), §14, §16.

> **— End of MVP (core loop 3a–3c + admin fast-follow 3d). Everything below is post-MVP. —**

### Phase 4 — Prereq automation (Docker + Windows)
- **Goal:** remove the manual provisioning steps from Phases 2–3.
- **Build:** `bootstrap/docker.py` (apt Engine install, `docker` group, service start); `bootstrap_win.ps1`
  (`wsl --install`, reboot-resume, install uv + `lon` in distro, hand-off); macOS colima.
  **Hand-off is the riskiest piece here** — pin its contract: the PS1 shim invokes `wsl -d <distro> -- lon <argv>`,
  **forwards arguments verbatim, streams stdout/stderr live, and exits with the WSL process's exit code**;
  interactive prompts execute **inside** WSL (the shim stays non-interactive); reboot-resume state (which step to
  continue from) is persisted **host-side** (registry `RunOnce` or a state file), since the reboot kills the shim.
- **Checkpoint ✅:** Windows without WSL → `bootstrap_win.ps1` → reboot prompt → re-run continues →
  `lon` runs inside WSL → `init` works; on macOS, `doctor` *reports* colima missing and `init` (or
  `doctor --fix`) installs it — bare `doctor` never installs.
- **Tests:** unit — parse `wsl -l -v` + reboot-required from fixtures; distro→install-command selection
  (mocked); reboot-resume idempotency simulated. `bootstrap_win.ps1` linted (PSScriptAnalyzer) + a
  `--dry-run` smoke check; real WSL install verified manually / in a VM (gated).
- **Ref:** §2, §3 (`bootstrap/*`), §12 (reboot loop).

### Phase 5 — Networking & tunnels
- **Goal:** OAuth sign-in + inbound webhooks without a manually configured domain.
- **Pre-req:** before building, **re-verify the §9 ngrok free-tier assumptions** (request/transfer caps,
  assigned-dev-domain policy, browser interstitial, authtoken flow) against current provider docs — these
  drift, and the plan treats them as documentation, not a guarantee.
- **Build:** `core/tunnel.py` (ngrok default, cloudflared), wire `WEBHOOK_URL`/`N8N_EDITOR_BASE_URL` +
  `N8N_PROXY_HOPS=1` and re-secure the cookie on HTTPS, embed tunnel config in the bundle; n8n `--tunnel`
  as a dev-only convenience.
- **Checkpoint ✅:** `lon tunnel start` → external `curl` reaches a webhook; an OAuth credential authorizes;
  `restore` reuses the base URL from the manifest.
- **Tests:** unit — provider abstraction with mocked ngrok/cloudflared processes; base-URL env wiring;
  manifest tunnel-config round-trip. Integration (gated, needs ngrok authtoken) — real tunnel + external `curl`.
- **Ref:** §9, §10 (tunnel portability).

### Phase 6 — Sync & convenience
- **Goal:** the cloud-like polish.
- **Build:** `core/remote.py` (git/s3/folder push/pull); `core/keychain.py` (opt-in cache, WSL fallback);
  Postgres compose profile + `pg_dump`/`pg_restore` path; `lon update` (auto-backup first).
- **Checkpoint ✅:** `backup --push` then `restore --from-remote` on a clean box; keychain caching skips the
  prompt on a desktop; `lon update` runs an n8n migration after an automatic backup; a Postgres instance
  backs up and restores.
- **Tests:** unit — `remote` push/pull against a local folder + mocked git/s3; `keychain` wrapper with a
  fake keyring backend + WSL fallback; `pg_dump`/`pg_restore` path mocked; `update` ordering (backup runs
  before pull). Integration (gated) — Postgres backup/restore; `--push`/`--from-remote` round-trip.
- **Ref:** §3, §6, §8 (postgres), §12.

**Definition of done per phase:** fully type-hinted code, **`ruff` + `ty` clean**, **its unit tests green
(plus gated integration tests where noted)**, the checkpoint passes, and the README/section updated.
Don't start a phase until the previous checkpoint is green.

---

## 14. Verification

These are the concrete tests behind the §13 phase checkpoints — the **Linux fast loop** and **Crypto**
items gate Phase 3 (MVP); the rest gate Phases 4–6.

- **Linux (fast loop):** `doctor` → `init` → create owner + a workflow + **an API-key credential, an
  OAuth2 credential, and a node that writes binary data** → `backup` → `down` + wipe volume → `restore`
  → assert **owner login, workflow, both credentials (incl. OAuth tokens), and the binary data** all
  return intact. The OAuth2 credential uses a **localhost-redirect provider or pre-seeded tokens** — this
  checks **token persistence through restore**, not live re-authorization (that's Phase 5). Repeat
  `restore` on a second box to prove device portability.
- **Windows:** run `bootstrap_win.ps1` without WSL → install + reboot prompt → re-run continues →
  CLI lands in WSL → `init` works → restore a Linux-built bundle.
- **macOS:** `doctor` reports colima missing; `init` (or `doctor --fix`) installs it → `up`/`backup`/`restore`.
- **Crypto:** envelope round-trip; wrong passphrase fails but **recovery code still opens** it;
  re-wrap new passphrase works; bundle bytes not plaintext-greppable for a known credential value;
  **flipping any byte in the outer header (KDF params/slot) fails authentication (AAD).**
- **Keychain:** `cache-passphrase` on → second `backup` no prompt on desktop; headless WSL falls back.
- **Tunnel:** skip at `init` → local-only; later `lon tunnel start` → ngrok dev domain set, sample
  webhook receives external `curl`; restore reuses base URL from bundle metadata.

---

## 15. Testing strategy

- **Two layers:** fast **unit** tests (default, hermetic — no Docker, no network) cover rendering,
  state, crypto, parsers, and error mapping; **integration** tests (pytest marker `integration`, opt-in)
  run the real Docker-backed `backup`→`restore` loop and live tunnels.
- **One mock seam:** every external call (`docker`, `wsl`, `ngrok`, `cloudflared`, `git`) goes through a
  thin `run()` wrapper, so unit tests mock a single boundary and never spawn real processes.
- **Crypto rigor (Phase 3):** round-trip + known-answer vectors; wrong passphrase fails and recovery
  opens; any header byte-flip fails AAD auth; framing rejects bad magic / unknown `format_schema`;
  bundle bytes aren't plaintext-greppable for a known secret; RNG injected for determinism.
- **CLI tests:** Typer `CliRunner` asserts exit codes + friendly messages for each handled error.
- **Type hints everywhere:** all functions/dataclasses fully annotated; **`ty`** (Astral's type checker)
  runs in CI and must pass — no untyped defs in `core/*`. `ty` is **pre-1.0**; if it isn't stable enough
  when a phase is built, **`pyright`/`mypy` is the fallback CI gate** — the hints are the invariant, the
  specific checker is swappable.
- **CI:** every push runs `ruff` (lint), **`ty`** (types), and `pytest -m "not integration"`; integration
  runs nightly / on-demand (needs Docker, optional ngrok authtoken). `bootstrap_win.ps1` gets
  PSScriptAnalyzer + a `--dry-run` smoke check.
- **Coverage gate:** `core/*` (crypto, backup, state) held high (≥ 85%); bootstrap/tunnel lower, since
  they're exercised mainly by gated integration tests.
- **Per-phase gate:** a phase isn't done until its unit tests are green (see each phase's **Tests** line
  in §13); integration tests gate the phases that touch Docker/network.

---

## 16. Implementation invariants (pin before coding)

Hard rules every phase must uphold; unit tests assert them.

- **Per-instance lock.** `backup`/`restore`/`up`/`down`/`restart`/`update` take an **exclusive per-instance
  lock** (lockfile `instances/<name>/.lock` via `flock`/`O_EXCL`, storing holder PID + op). A second mutating
  op fails fast with *"instance busy: <op> in progress"*; read-only `status`/`logs` don't lock. Stale locks
  (dead PID) are reclaimed.
- **Atomic restore / rollback (versioned-volume model).** The **active data volume is a pointer**
  (`state.db.data_volume`); compose renders the volume's `name:` from it, and volumes are generational
  (`n8n_<name>_data`, `…g2`, `…g3`, …), so the live volume is **never mutated in place**:
  1. Extract + validate the bundle into a **temp staging dir**, then load it into a **new generation
     volume** `n8n_<name>_data.g<N+1>` (helper-container `tar --numeric-owner`, `config`→0600).
  2. `--replace`: first snapshot the current instance as a **normal encrypted bundle** into `backups/`
     (same crypto path, recorded in `state.db`) — rollback material is encrypted, not loose files. **The
     snapshot is sealed with the *existing* instance's unlock material** (its passphrase + `recovery.wrapped`),
     **never** the incoming bundle's — it's rollback for *this* instance, so it must open with what the user
     already holds for it. If the instance has **never** been backed up, run the first-backup
     passphrase/recovery setup (§11 backup) before the snapshot proceeds.
  3. **Swap** only after validation: stop the container, set `state.db.data_volume = …g<N+1>`, re-render
     compose, `up`. The swap is a single committed pointer change.
  4. **On any failure:** discard the staging dir + new-generation volume; `data_volume` still points at the
     old generation, so the live instance is untouched (rollback). Success removes the old generation
     unless `--keep-old`. A **startup orphan sweep** also removes any `n8n_<name>_data.g<N>` volume **not**
     referenced by `state.db.data_volume` (left by a crash mid-restore), and `backups/` is pruned per the
     **`backup-retention`** setting.
- **Multi-arch image digest.** Pin the **multi-arch manifest-list digest** (from `docker buildx imagetools
  inspect` / the registry manifest list), **not** a host-specific per-arch `RepoDigest` — otherwise an
  amd64-built bundle won't pull on Apple-Silicon/arm64 and restores diverge. Manifest `image` =
  `<tag>@sha256:<manifest-list-digest>`.
- **Recovery-code spec.** Recovery secret = **160 bits CSPRNG (20 bytes)**. Human code = **Crockford Base32**,
  uppercase, hyphen-grouped in blocks of 5, with a **trailing Crockford check symbol** that catches **most
  single-character errors** (a single check symbol does not catch every transposition).
  Normalize before use: uppercase, strip spaces/hyphens, apply Crockford aliasing (I/L→1, O→0), verify
  checksum. The **decoded 20 raw bytes** (not the display string) are the Argon2id input (with the slot's
  16-byte salt) for the recovery-slot KEK.
- **`N8N_ENCRYPTION_KEY` format.** Generate **32 random bytes from a CSPRNG, base64-encoded** (n8n accepts
  an arbitrary string; we pin this so it's deterministic and documented). Written to the instance `.env`
  (chmod 600) and carried in every bundle — **never regenerated** for an existing instance.
- **Secrets never on argv, never in output.** The passphrase and recovery code are read **only** via
  interactive prompt or stdin — **never a CLI flag or env-arg** — keeping them out of shell history and `ps`
  (applies to `backup`, `restore`, `recovery`, `passphrase`). Symmetrically, **generated secrets are never
  emitted to stdout/`--json`/logs**: the `N8N_ENCRYPTION_KEY` is written only to the chmod-600 `.env` (and
  into encrypted bundles), and `--dry-run`/`--verbose` output redacts it (§7.1). The recovery code is the
  **sole deliberate exception** — shown once at first `backup` / `recovery show`, by explicit design.
- **Exact crypto framing (restated).** File = `magic("N8NB", 4B)` · `header_len(uint32 BE, ≤64 KiB)` ·
  `canonical-JSON header` · `ciphertext ‖ GCM tag(16B)`. The **raw on-disk header bytes** (exactly
  `header_len` of them — never a re-serialization) are the AES-256-GCM **AAD**; the **tag is
  appended to the ciphertext, never stored in the header**; after the header, **exactly
  `payload.ciphertext_length` bytes remain** (trailing bytes ⇒ reject). Canonical JSON = UTF-8, sorted keys,
  compact separators, no floats (§6.1).
