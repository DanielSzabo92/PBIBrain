# Frontend overhaul — 29 September 2026

Goal: a compact, dark workspace that explains Power BI objects without exposing internal graph records.

## Design sources

- [Minimalist UI skill](https://github.com/Leonxlnx/taste-skill/blob/main/skills/minimalist-skill/SKILL.md): restrained typography, flat surfaces, semantic accents, clear hierarchy, and purposeful controls. The user's dark theme and compact spacing take precedence over its white canvas and large spacing defaults.
- [metal-fx](https://github.com/Jakubantalik/metal-fx), pinned to 1.0.4: silver treatment for command buttons. Navigation and object rows stay flat. Animation runs on interaction; reduced motion pauses it. Native button borders and focus remain available without WebGL. The package initially hides its host until a GPU frame; the integration explicitly keeps commands visible.
- [border-beam](https://github.com/Jakubantalik/Libraries.dev/tree/main/packages/border-beam), pinned to 1.4.1: a restrained monochrome beam on focused text inputs. No competing container highlight. Reduced motion disables the animation.
- System typography and Radix icons replace the previous Inter/Lucide styling.

## Findings and changes

| Surface | Cause of the problem | Result |
| --- | --- | --- |
| All screens | Blue-tinted surface layers, competing accents, repeated headings | Charcoal surfaces, warm white text, compact navigation, quieter dividers |
| Search | Input ring, browser outline, and enclosing label highlight stacked | One field boundary; keyboard focus remains visible |
| Search results | IDs used as fallback subtitles; raw search-field paths displayed | Names and scope names; plain “In formula” / “In description” explanations |
| Search / Inspector | No object-type filter | Server-side type filter included in search cache keys and pagination |
| Inspector entry | Menu rendered only an empty selection prompt | Browsable measures immediately; type, model, and report filters; object selection and return focus |
| Inspector details | Generic property dumps exposed IDs, ASTs, hashes, and raw source | Explicit list of useful properties; formula, description, direct dependencies, and direct consumers retained |
| Inspector context | Unresolved model/table references leaked their identifiers | Resolved names only; missing scope labels omitted |
| Review evidence | Objects and serialized JSON passed through JSON.stringify | Nested evidence becomes readable explanations; transport metadata is omitted |
| Review rows | Suggestion value led the row; flex centering fought text alignment | Object name first, labeled suggestion second, explanation alongside; left aligned |
| Review counts | Candidate edge and semantic node represented the same suggestion | Merged by candidate identity; accurate queue count; misleading duplicate home/sidebar counts removed |
| Review decisions | Canonical node identity could approve only one side of a suggestion | Original candidate identity updates the related semantic records; persistence verified |
| Review actions | Repeat submissions possible; errors could close an edit | Pending controls disabled; failed decisions remain available; failed edits remain open |
| Review on narrow screens | Evidence hidden by responsive CSS | Evidence stays visible below the object; actions remain reachable |
| Review filter controls | A legacy select width left arrows outside the field border | Select and wrapper widths now match; verified at desktop and mobile sizes |
| Settings | Only group colors; many controls shown immediately | Studio, Coast, Ember, and Slate palettes with six muted type colors; custom controls in a disclosure |
| Settings persistence | JSON key order could make a saved palette appear unselected | Color maps compared by values; custom colors and project sources preserved |
| Project settings | Read-only storage paths and duplicate storage/readiness explanations | Editable project name, meaningful source paths, source management, and scan controls |
| Graph | Inferred objects doubled visual clutter; large grouped layout by default | Source objects first; optional suggestions and ownership grouping |
| Graph size | Initial request allowed 100 objects | Initial slice limited to 30 with explicit truncation notice and Show more |
| Graph exploration | Whole-project layout overwhelmed local relationships | Double-click or Center graph here isolates a neighborhood; distance and return controls retained |
| Graph controls | Six always-visible filters consumed vertical space | Extra filters in a disclosure; active filter count; canvas fits desktop viewport |
| Graph details | IDs, raw metadata, and serialized evidence repeated Inspector problems | Human names, useful properties, DAX, readable evidence, named relationships |
| Accessibility | Decorative rendering could hide a functional button | Button fallback verified with WebGL unavailable; focus, keyboard selection, and reduced motion checked |

The Power BI source files and canonical graph semantics remain read-only. UI names never replace the identifiers used for API requests.

## Validation

Browser acceptance uses actual Google Chrome and the production Vite build, served by the existing isolated HTTP/native-database test server. Its project is scanned, closed, and reopened before testing. Some failure, pagination, and response-order cases deliberately intercept requests; these are fault-injection tests, not independent backend acceptance.

- Node tests cover layouts, transport, evidence parsing, property filtering, and palettes.
- Browser tests cover all six screens, Inspector browsing, decision persistence and failure recovery, color persistence, keyboard and mobile use, graph grouping/focus, and a WebGL-free button fallback.
- A separate temporary model with 180 measures produces 183 source objects. The graph initially shows 30; server-side search finds Scenario 174 outside that slice; focusing it shows its three-object neighborhood.
- Backend Inspector, product API, and graph-presentation contracts are rerun.
- Screenshots are inspected for desktop and 390px layouts.

### Command results

- `npm run build`: passed; Metal FX, Border Beam, and Radix license notices included in the output. Vite retains its bundle-size advisory.
- `npm test`: 21 passed.
- `PLAYWRIGHT_CHANNEL=chrome npx playwright test`: 22 passed. After the final select-width adjustment, the narrow-screen acceptance test passed again and all three desktop filter boundaries were checked.
- `python -m unittest tests.test_phase4_inspector_contract tests.test_product_api tests.test_graph_presentation -q`: 35 passed.
- `git diff --check`: passed.
- `graft build`: refreshed successfully, 145 indexed source files.

- `scripts/build-desktop.ps1 -SkipFrontend -SkipInstaller`: passed. Frozen native scan/reopen passed with 17 nodes and 23 edges.
- All four frontend output files match both the packaged directory and portable ZIP byte-for-byte.
- Outputs: `dist/PBIBrain/PBIBrain.exe` and `dist/PBIBrain-Portable-x64.zip` (48,528,640 bytes).

Installer, clean-machine, and manual native-window acceptance were not run. Browser checks used actual Chrome; the frozen executable check covers native scanning and persistence.
