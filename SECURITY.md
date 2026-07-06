# Security Policy

`local-n8n` is an alpha project for running local n8n instances and creating encrypted backup bundles.

## Reporting a Vulnerability

Please do not open a public issue for suspected vulnerabilities.

Report security concerns privately through GitHub Security Advisories for this repository. Include:

- the affected command or workflow
- steps to reproduce
- expected and actual behavior
- whether local secrets, `.env` contents, recovery material, backup bundles, or diagnostic logs may be exposed

## Sensitive Local Files

Do not share these files publicly:

- `.env`
- `state.db`
- `recovery.wrapped`
- `.n8nbundle` backup files
- diagnostic logs from `~/.config/local-n8n/logs/`

Diagnostic logs are designed not to copy typed passphrases or recovery codes from terminal output, but they
may still contain local paths, command names, instance names, and error details.
