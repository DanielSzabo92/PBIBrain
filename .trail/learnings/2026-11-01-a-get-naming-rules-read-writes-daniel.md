---
title: "A GET naming-rules read writes no file, so the rule file keeps only the rules that the user acted on"
author: Daniel
date: 2026-11-01
branch: claude/dev-center-build-6abbf2
cost: { minutes: 28, tokens: 43816 }
id: l-ba10d9bf
scope: repo
status: active
touches:
  - ".scratch/dev-center-build/issues/08-s4-naming-rules.md"
  - backend/devcenter/naming/service.py
  - backend/devcenter/naming/store.py
  - tests/test_devcenter_naming.py
  - ".scratch/dev-center-build/issues/07-s3-alignment-compare.md"
  - backend/dax/parser.py
  - backend/devcenter/alignment/__init__.py
  - backend/devcenter/alignment/align.py
  - backend/devcenter/alignment/keys.py
  - backend/devcenter/compare/__init__.py
---

## Decided
- `backend/devcenter/naming/`: a read must not write a file, because `GET naming-rules` is an HTTP read. Thus the rule file holds only rules that the user confirmed, rejected, edited, or added. The app detects the other proposed rules again on each read, with stable hash IDs of the signature.
- An edited detected rule keeps the detected rule ID. `offered_rules` hides each detected rule whose ID is already stored, otherwise an edit and then a reject offered the old rule again.
- The detection limits (5 objects, 80%) are in the `settings` object of the rule file, because `config/brain.json` refuses unknown keys.
- `POST name-propose` and `POST plan-validate` are POST reads (`READ_POSTS` in `backend/devcenter/http_routes.py`), because section 14.1 lists them as reads. They change no revision and no file.

## Watch out
- The TOM bridge also reads a `model.bim` path and fills the default values, so TMDL and TMSL sources compare as equal with no default logic of our own. One bridge read takes about 1 s, so the compare cache keys on the path and the Source Fingerprint.
- `_valid_rule` in `naming/store.py` does not check the scope and check values; a hand-edited bad value still gives a KeyError in `rule_text`.
