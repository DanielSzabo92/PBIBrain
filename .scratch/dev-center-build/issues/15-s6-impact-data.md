# 15: S6 impact data

Status: open. Lane: backend. Design step: S6 (docs/DEV_CENTER_TECHNICAL_DESIGN.md section 16).

Depends on (tickets): [07](07-s3-alignment-compare.md), [11](11-s5-change-plan.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

### Design text: S6. Impact data

- Goal: Impact items, Needs, Offers, wireframes, completeness.
- Code areas: `backend/devcenter/impact/`, `backend/impact/analyzer.py`, `backend/api/app.py` (`impact`, `removal`, `wireframe`).
- Depends on: S3 (row seeds), S5 (plan seeds).
- Acceptance tests:
  - For fixture plans, the Impact item set equals a golden file (severity, certainty, reason ID, path, blocking, actions).
  - Item IDs are stable across runs.
  - A possible item never blocks.
  - The Needs walk is transitive and translates through the alignment.
  - Other reports of the target model carry "not changed by this plan".
  - Cascade preview lists the effect for each dependent; Repoint gives same-kind candidates with type warnings.
  - Wireframe data for the merge lab target equals a golden file; statuses follow the priority order.
  - Offers list donor pages, visuals, and filters; a bookmark shows as information only.
  - The completeness block lists not-checked types, unresolved bindings, and bookmarks.
  - Budget test (section 17, risk R6): plan and impact under 5 s on the generated large set.
  - UC28: bulk `impact_action_apply` with `item_ids` changes all items in one revision step, or none, and lists the items that it could not change.
  - UC29: each `GET impact` filter gives the expected items; `total` and the facet counts equal the full result before paging.
  - UC30: `GET impact/{item}/paths` pages all paths of a fixture item; each step has object ID, name, type, and edge phrase.
  - UC31: each impact reason ID and edge phrase ID that the engine uses is in `phrases.json`.
