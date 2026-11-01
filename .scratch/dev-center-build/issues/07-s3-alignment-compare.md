# 07: S3 alignment compare

Status: open. Lane: backend. Design step: S3 (docs/DEV_CENTER_TECHNICAL_DESIGN.md section 16).

Depends on (tickets): [03](03-s1-scanner-coverage.md), [04](04-s2-session-store.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

## Lead notes

- S2 row keys for each source are `<type>:<qualified name>` (`backend/devcenter/sources/objects.py`), and `row_confirm`, the marks, and `merge_choices` use them. Define how an aligned compare row key maps to these source keys, and test it.
- S2 follow-ups (small, in this ticket): add a test that `ROW_KEY_KINDS` in `backend/devcenter/session/secrets.py` equals the kinds of `sources/objects.py`; in `store.py` `_remove_stale`, a `PermissionError` on the read or stat of a lock must give a read-only open, not an error.
- Register new JS API methods in `backend/devcenter/jsapi.py` (`AREA_MODULES`) and new reads in `backend/devcenter/http_routes.py`. Put schemas in `backend/devcenter/contracts/` (validator by `$id`).

### Design text: S3. Alignment and compare

- Goal: N-way compare rows with states, marks, and plain-word phrases.
- Code areas: `backend/devcenter/alignment/`, `backend/devcenter/compare/`, `backend/dax/parser.py` (normalization tokens), `backend/diff/snapshots.py` (reuse `compare_properties` where it fits), `backend/api/app.py` (`compare-rows`, `diff`).
- Depends on: S1, S2.
- Acceptance tests:
  - For the merge lab, the full compare row set equals a golden file (states, marks, notes, phrases).
  - lineageTag wins over name: the "Renamed" plus "name clash" case.
  - A duplicate lineageTag is ignored with a warning.
  - Each alignment key of section 4.1 aligns its fixture case.
  - A possible rename appears only with one candidate on each side.
  - Default DAX normalization: each rule of section 4.2 has a pass and a fail case; `[Total]` is not equal to `Sales[Total]`.
  - "Same after rename" in default mode; "Different" in strict mode.
  - Alignment overrides from the session change the rows.
  - Same input twice gives the same row order and IDs.
  - UC20: `GET display-folders?source=<id>` returns the display folder paths of a merge lab source; the object type filter limits them.
  - UC21: `alignment_override` break removes the Merge Choice of the row and returns the new row keys.
  - UC23: `q` filters compare rows by name, case-insensitive.
  - UC24: `total` and `state_counts` equal the counts of the full filtered row set.
  - UC25: `sort` by state, name, type, and table, asc and desc, gives a stable order.
  - UC26: `row_state` is the highest-precedence cell state, and the `state` filter uses it.
  - UC31: `phrases.json` holds each compare phrase ID that the engine uses; the contract test refuses an em or en dash, an emoji, and text over 60 characters.

## Build record

What I built:

- `backend/devcenter/compare/extract.py`: the compare objects of one source. The model part comes from the TOM bridge for TMDL and for TMSL, so both formats give the same values. The report part comes from the PBIR files or from the PBIR-Legacy `report.json`. A cache uses the path and the Source Fingerprint.
- `backend/devcenter/alignment/keys.py` and `align.py`: the alignment keys of section 4.1 and the steps (manual, lineageTag, key, second key, type conflict, moved, possible rename). Tables align first, so the objects of a renamed table use the target table name. A duplicate lineageTag gives a warning and a cell note.
- `backend/devcenter/compare/normalize.py`, `properties.py`, `rows.py`: DAX normalization on the lexer tokens (`dax_tokens` in `backend/dax/parser.py`, also removes `--` comments), the property lists and the phrase IDs, the cell states, `row_state`, filters (`q`, `folder` or `display_folder`, and the others), stable sort (`sort=<field>:<dir>` or `sort` with `order`), `total`, and `state_counts`.
- `backend/devcenter/compare/service.py`, `http_routes.py`, `jsapi_methods.py`: `GET compare-rows`, `GET compare-rows/{row}/diff` (`{row}` is the row ID or the URL-encoded row key), `GET display-folders` (`object_type` or `type`), and the JS API methods `alignment_override` (confirm, break, reject_rename, clear) and `compare_mode_set`.
- Contracts: `http/compare-rows.reply.json`, `http/compare-row-diff.reply.json`, `http/display-folders.reply.json`, the request and reply of the two JS API methods, and `phrases.json` (UC31).
- Row key mapping: a compare row key is the source row key of the target object, else of the first donor object. A donor-only row whose key is in use gets `@<source ID>`. Each cell has `source_key`; a row shows each mark whose source ID and source key are those of one of its cells. `row_confirm` takes these source keys. A mark with no cell goes to `orphan_marks`.
- S2 follow-ups: `OBJECT_KINDS` in `sources/objects.py` and a test that it equals `ROW_KEY_KINDS`; `_remove_stale` gives a read-only open on a `PermissionError` of the lock read or stat. The secret check also reads `target_key`, `donor_key`, and `other_row_key` as row key fields.
- Shared files: `jsapi.py` one line (`AREA_MODULES`); `http_routes.py` one registration import line plus one line in `dispatch` that gives the `{name}` path parts to the handler in the query. `host.py` needed no change. The S3 methods are out of `HOST_PENDING`.
- Golden file: `tests/fixtures/devcenter_compare/merge_lab_rows.json`. Set `PBIBRAIN_UPDATE_GOLDEN=1` to write it again.

Tests:

- `python -m unittest tests.test_devcenter_compare`: 34 tests, OK.
- `python -m unittest discover -s tests`: 470 tests, OK (after the merge of 354f742).
- `npm test` in `frontend/`: 99 pass. `npm run build`: OK.

Open items:

- The functional spec example shows a report measure cell on a model measure row. This build keeps report measures as separate `report_measure` rows (section 4.1 key: home table + name).
- Visual fields do not read through the alignment (no "same after rename" for visual queries).
- `proposal_status` is always null until S10.
