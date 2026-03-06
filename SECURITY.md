# Security Policy

## Scope

This policy covers security vulnerabilities in the Anzen SDK, backend server, and dashboard.

Ironically, a security tool has security vulnerabilities too. We take them seriously.

## Reporting a vulnerability

Open a public issue on GitHub.

## What counts as a vulnerability

- Bypass of any detection guard
- Authentication bypass in the backend API
- SQL injection or other injection attacks in the backend
- XSS or other frontend vulnerabilities
- Dependency with a known CVE that affects Anzen

## What does NOT count

- Detection evasion via adversarial prompts — this is expected and the subject of ongoing research, not a vulnerability. Open an issue or PR with new patterns instead.
- Self-XSS
- Theoretical attacks without a proof of concept
