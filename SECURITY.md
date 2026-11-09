# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.5.x | Yes |
| 0.4.x | No |
| 0.3.x | No |
| 0.2.x | No |
| 0.1.x | No |
| Older | No |

Engramkeep is alpha software. Security fixes are applied to the latest release.

## Reporting a vulnerability

Please do **not** open a public issue for a security vulnerability.

Use GitHub's private vulnerability reporting for this repository:

1. Open the repository's **Security** tab.
2. Choose **Advisories** and **Report a vulnerability**.
3. Include a description, affected version, reproduction steps, and impact.

If private reporting is unavailable, open a minimal public issue asking the
maintainers for a private contact channel. Do not include vulnerability
details, credentials, or real memory data in that issue.

## What to include

- Affected version or commit.
- Operating system and Python version.
- A minimal, synthetic reproduction.
- The security impact you observed.
- Any suggested mitigation.

Do not attach a real Engramkeep store, credentials, or personal information.
Use synthetic cards and temporary directories.

## Response

Maintainers will acknowledge a report on a best-effort basis and will share a
remediation plan when possible. This is a volunteer project; no SLA or bug
bounty is offered.

## Scope

In scope:

- path traversal or symlink escape in the core store,
- secret leakage despite the documented redaction behavior,
- unsafe file writes or permission issues,
- command execution or network access introduced by the core,
- vulnerabilities in the MCP server, dashboard, or installer code,
- supply-chain issues in the build or release process.

Out of scope:

- prompt injection that an agent chooses to follow (documented as a residual
  risk; report it if the core itself treats card text as instructions),
- same-user malware or a compromised host,
- secrets that the documented redaction cannot detect,
- missing encryption at rest (documented limitation),
- issues in third-party agents or their configuration formats.

## Safe harbor

We welcome good-faith research. Do not access, modify, or exfiltrate data that
does not belong to you. Do not run denial-of-service tests against public
infrastructure. Test against a local, synthetic store.

## Security design

Read [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for the current model and
[docs/PRIVACY.md](docs/PRIVACY.md) for data handling.
