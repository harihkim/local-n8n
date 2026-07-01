**IDEA**
<p>let's create a cli to manage n8n using python, uv. should support windows, linux and macos. in windows, we are gonna recommand wsl ubuntu and as it as default option. we have to install wsl if not installed. we check if docker is installed, if not install it. and then turn on wsl integration. then use docker-compose.yml to build and run n8n. the user can stop, start it using our cli. a quality of life improvement, we add a sqlite db to store n8n credentials, workflows, 3rd party integration info etc.</p>

---

**STATUS — this is the original seed idea; superseded by [plan.md](plan.md), which is the source of truth.**
Where this idea and `plan.md` differ, **`plan.md` wins.** Key corrections made during planning:

- **SQLite stores metadata/registry only — NOT n8n credentials/workflows/integration secrets.** n8n already
  encrypts those in its own DB; a second copy would store secrets twice. Portability is instead handled by the
  **encrypted backup bundle** (the full `/home/node/.n8n` volume + encryption key + manifest). See plan.md §6 / §6.1.
- **Docker = Docker Engine installed inside WSL (apt)** — *not* Docker Desktop + "turn on WSL integration".
  See plan.md §1 (Docker decision) and the Desktop-vs-Engine conflict handling in §12.
- **Prereq install is detect-and-guide for the MVP; automatic WSL/Docker provisioning is post-MVP (Phase 4).**
  See plan.md §1 + §13.