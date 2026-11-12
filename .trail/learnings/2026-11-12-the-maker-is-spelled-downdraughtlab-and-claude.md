---
title: The maker is spelled DownDraughtLab and shown only as a credit; repo cleanup kept history-only material out of the tree
author: Claude
date: 2026-11-12
branch: claude/ticket-code-cleanup-670qia
cost: { minutes: 6, tokens: 15464 }
id: l-55535e41
scope: repo
status: active
src: agent
touches:
  - ".gitattributes"
---

## Decided
- PBIBrain stays the product name; DownDraughtLab is the maker. Spelling follows the repo's commit author: "DownDraughtLab" (capital D twice). Every visible credit reads from one module, so a rename is one edit there.
- The LICENSE copyright holder was deliberately left as "Daniel": changing it is the owner's legal call, and `tests/test_publication_contract.py` pins it.
- Scratch, audit evidence, UI-audit screenshots and dated review docs were removed from the tree; docs that cited them now say "in git history".

## Tried and ruled out
- Auto-removing every unused import with ruff including package `__init__.py` files: those imports are the packages' public API. Only non-`__init__` modules were fixed.

## Watch out
- In a cloud container without the .NET TOM bridge, 3 Python tests fail on the untouched code too (cloud deploy refusal, mark-date-table bulk edit, model.bim → TMDL convert), and 15 of 16 graph Playwright tests fail the same way before and after. Compare against a baseline before blaming a change.
- Several frontend tests read source text (e.g. `issue45`, `issue48`, `issue49`): removing a file or an `export` keyword can fail them even when behaviour is unchanged.

In the code: frontend/src/brand.js (PRODUCT_NAME, MAKER_NAME, PRODUCT_CREDIT); packaging/PBIBrain.iss AppPublisher; backend/text_keys.py and backend/devcenter/common.py hold helpers that used to be copy-pasted.
