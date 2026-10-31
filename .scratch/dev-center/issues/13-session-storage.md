# How does the app store a merge session?

Type: grilling
Status: resolved
Blocked by: 07

## Question

File format and location of a session. What does it store (sources and their snapshots, alignment, merge choices, agent proposals and reasons, log)? How does the app find that a source changed after the session started? How does a session move between PCs through git without secrets?

## Context

- From "What are the match and compare rules?": the session must store the compare mode (default or strict), the alignments that the user confirmed or broke by hand, and the rename proposals that the user rejected.
- From "How does the Change Plan engine work?": the session stores the removal policy for each removed object, the accepted or mapped prerequisites, and a stable session ID. The session does not store the plan as the source of truth: the engine computes it again. New lineageTags come from the session ID and the row key (UUIDv5), so the session ID must never change.
- From "Which impact data does the backend give to the UI?": the session does not store impact results, because the engine computes them again. The session stores the results of item actions: "include in rewrite" selections, Need mappings, dropped added objects, removed fields, and the selected carry-over offers.
- From "How does the app find and store naming rules?": the rules are not in the session. They are in `<project root>/.pbibrain/naming-rules/<model folder name>.json` (local target) or in `%APPDATA%/PBIBrain/naming-rules/<workspace ID>/<model ID>.json` (cloud target with no local project). The session stores the rule file path and a hash of the rule set that it used.
- From "What are the exact agent tools?": the session stores a `revision` number that changes on each state change. It stores agent proposals (kind, target, payload, confidence, reason, base revision, status) apart from accepted state, and agent questions with options and answers. The log stores the MCP client name for agent entries, and links user accept and reject entries to the proposal.

## Answer

Resolved on 2026-10-31. The user (through the orchestrator session) accepted all 14 proposed defaults, with one addition to decision 14.

### Facts found first

- A project is a folder with `.pbibrain/brain.json` (sources as relative paths, graph database, identity map). `.pbibrain/` also holds `connection.json` (server URL and a `session_id` that is a desktop connection generation, not a Merge Session ID) and the naming rules.
- `backend/snapshots/manifest.py` already has `source_manifest` (path, sha256 hash, and size for each file, `.pbibrain` excluded), canonical JSON, `content_hash`, and `capture_snapshot` with the git `HEAD` commit.
- Cloud model: TOM `Database.LastSchemaUpdate` shows a schema change after a pull (XMLA research). Cloud report: the Fabric API gives no ETag, thus the app hashes the definition parts.

### Decisions

1. **Location.** A session belongs to the open project: `<project root>/.pbibrain/sessions/<session ID>/`. A session with a cloud-only target (no local project) goes to `%APPDATA%/PBIBrain/sessions/<session ID>/`. It does not move through git. To share it, the user pulls the model to a local PBIP first (the default flow).
2. **Files and format.** The session folder has two files. `session.json` holds the current state as canonical JSON (sorted keys, 2-space indent, LF), so git diffs stay small. `log.jsonl` is append-only, with one entry on each line. The app saves atomically (temp file, then rename) on each state change.
3. **What `session.json` stores.** `schema_version`, session ID (UUID), display name, created and updated time (UTC), `revision`, sources, target, compare mode, alignment overrides only (user-confirmed matches, broken matches, rejected renames), Merge Choices keyed by row key, removal policies, prerequisite and Need mappings, item action results ("include in rewrite", dropped added objects, removed fields), selected Offers, naming rule file path and hash, agent proposals, and agent questions with answers. It does not store the computed alignment, the plan, the impact, or the graph. The engine computes them again.
4. **Source references.** Local source: POSIX path relative to the project root, kind, and role (target or donor). Cloud source: tenant ID, workspace ID, item ID, display names, and access type. The session holds no absolute paths, no user names or account e-mail addresses, and no tokens.
5. **Source Fingerprint at session start.** Local source: the file manifest (path, hash, size), plus the git commit if the folder is in git. Cloud model: `LastSchemaUpdate` plus a hash of the canonical model export. Cloud report: a hash of the definition parts. The session holds no copy of source content.
6. **Row fingerprints.** For each aligned row, the session keeps one hash for each source object. The hash covers the compared property set (the fixed property list of the compare rules, default mode). When a Source Fingerprint changes, the app scans again and compares the row hashes. A changed hash marks the row "source changed". An object that is gone marks the row "source object missing". A new object gives a new row with the mark "new since start".
7. **When the app checks sources.** When it opens a session, when the user selects "Check sources", and always before Apply (blocking). A file watcher is not in the first version.
8. **Effect of a source change on choices.** The Merge Choice on a marked row stays, but the row shows "needs review". Apply stays blocked until the user confirms each marked row. The confirm stores the new row hash. Until then, the agent tools return `source_changed` for proposals on a marked row.
9. **After the app's own Apply.** The app writes the new target fingerprint and row hashes from its write record. Thus its own change does not show as "source changed".
10. **Log entries.** Each `log.jsonl` line: time (UTC), author (user or agent), MCP client name for agent entries, action, target (row ID or Impact item ID), value before and after, reason, proposal ID link, and revision after the change. No hash chain: there is one user, and git history is the second record.
11. **Git sharing.** The app writes `.pbibrain/.gitignore`. It excludes the runtime files: `connection.json`, the graph database, locks, backups, and temp files. `sessions/`, `naming-rules/`, and `brain.json` go to git. Before each save, the app runs a secret check (no token-like strings, no absolute user paths) and refuses the save on a hit. A source outside the project root keeps a relative path with `..`. On a PC that does not have it, it shows as "missing", and the user can link it again.
12. **One open session, many sessions.** A project can have many sessions. The app opens one at a time. A lock file in the session folder (git-ignored, with the process ID) makes a second open read-only.
13. **Versions and broken files.** `schema_version` is an integer. The app migrates an older file forward when it opens it, and keeps a backup of the old file. It refuses a newer version with a clear message. It refuses a file with git conflict markers or invalid JSON, and tells the user to fix the merge in git.
14. **Word clash.** The `session_id` key in `connection.json` is the desktop connection generation. The design renames it to `connection_id` (also in `/desktop/session` and the `X-PBIBrain-Session` check in `backend/agent.py` and `backend/desktop/host.py`). Addition from the user: the app must still read the old `session_id` key in existing `connection.json` files, and write it as `connection_id` on the next save, so that existing projects continue to work.

### Glossary

Added "Source Fingerprint" to `CONTEXT.md`.

### ADR

None. No decision here is hard to reverse and surprising at the same time.
