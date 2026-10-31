# Accepted-state changes and Apply only in the in-process JS API

Status: accepted (2026-10-31)

The local HTTP API checks only the host and the origin and has no authentication, so any local process (also an agent shell) can call it. Thus all accepted-state changes (sessions, sources, target, Merge Choices, alignment overrides, removal policies, mappings, rule confirms, accept, reject, Apply, undo) exist only in the pywebview JS API inside the desktop process. HTTP has read endpoints and agent proposal endpoints only, and the MCP adapter uses a fixed endpoint allowlist. A test makes sure that no HTTP route for an accepted-state change exists.

## Considered options

- A secret header on the HTTP API: rejected, because the existing connection ID is on disk and any local process can read it.

## Consequences

- Browser dev mode (Vite) cannot change state. It uses a mock of the JS API.
- An agent with shell access as the same Windows user can still edit project files directly. This is a stated limit, not a guarantee.
