# Model summary — 2026-09-30

Settings → Model summary selects one semantic model and previews a standalone
`model-context.md`. Copy context uses the clipboard, with selected-preview
fallback when clipboard access fails. Save Markdown downloads the exact UTF-8
file; the Windows desktop host enables pywebview's native Save dialog.

The renderer uses the already-open graph and effective human review decisions.
It leaves the canonical documentation exporter unchanged. It preserves exact
stored expressions, includes hidden objects and linked report usage, separates
endpoint order from filtering direction, and exposes unknown metadata and
unresolved references. Approved table-role interpretations appear in the
overview with their INFERRED class and review status. Shared labels never apply
another object's approval or override. No model call or network service is used.

## Validation

- Summary tests: seven pass, including model isolation, independent shared-label
  decisions, exact Unicode expressions/fences, relationship direction, security
  declarations, partitions, native scan/reopen, TMDL/PBIP ingestion, reviewed
  table roles, and unchanged source files.
- Final full Python regression suite: 226 passed, including all seven summary
  tests and the reviewed-role check.
- Frontend unit suite: 26 passed. Vite production build passed.
- Four browser tests passed: native-backed API preview, exact UTF-8 download,
  Windows clipboard line endings, clipboard fallback, error/retry, late model
  responses, empty projects, and layout at 1440×1000 and 1024×680. Chromium
  rendering evidence: [preview](evidence/model-summary-2026-09-30/browser-preview.png).
- Frozen executable scan/reopen gate passed all four path fixtures.
- [Packaged verification](evidence/model-summary-2026-09-30/verify-packaged.py)
  exercises the rebuilt agent's native LadybugDB HTTP API against a disposable
  TMDL/PBIP fixture, checks identical repeated summaries, and verifies all ten
  source files remain unchanged. [Results](evidence/model-summary-2026-09-30/packaged-results.json).

Browser tests cover copy/download behavior; the native Windows Save dialog was
not manually exercised. Installed copies are unchanged. The updated GUI,
agent executable, and portable ZIP are under `dist/`.

## Example

[Standalone model context](evidence/model-summary-2026-09-30/model-context.md)
comes from a disposable fixture, not the user's model. Source paths refer to
that temporary scan. Export does not reread source files: rescan after edits.
Security details unavailable to the scanner remain unknown; the file cannot
prove runtime results, uniqueness, business correctness, or absence of RLS/OLS.
