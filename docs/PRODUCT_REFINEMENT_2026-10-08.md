# PBIBrain product refinement — 8 October 2026

The product now keeps context across Search, Graph, Inspector, and Review. Errors have visible recovery actions, review counts agree across screens, and controls follow one restrained visual system.

## Changes

- Flat charcoal surfaces, quieter decoration, clearer input boundaries, readable text in both themes, and a themed graph minimap.
- Consistent page titles, visible search labels, keyboard focus, a skip-to-content link, and layouts checked from 320 to 1440 pixels.
- Settings opens Project first. Unsaved changes have clear save and scan states; configuration failures expose retry.
- Graph preserves filters, layout, center, cached results, and suggestion visibility across Inspector visits. Scan and refresh invalidate its cached data.
- Review preserves filters, sorting, row focus, and scroll position. Failed decisions stay visible with an error. Failed refreshes retain usable reviews and offer retry.
- Overview and sidebar use the backend's canonical pending queue count, including outdated decisions. Existing raw counts remain available to API consumers.
- Scan completion reloads the currently open Review screen. Old review responses cannot overwrite a newer project generation. Review actions pause during scans.
- Graph, graph appearance, and model summary load on demand. The initial JavaScript bundle is about half its previous size.

Power BI source files retain their read-only boundary. No dependencies were added, and no existing project or UI history was replaced.

## Evidence

| Check | Result |
| --- | --- |
| Backend tests | 227 passed |
| Frontend unit tests | 26 passed |
| Chrome workflow tests | 41 passed |
| Responsive layouts and theme contrast | 116 passed; no page errors |
| Frozen native scan and reopen | 4 paths passed; 17 nodes, 23 edges each; source hashes unchanged |
| Frontend, desktop, and installer builds | Exit code 0 |
| Packaged frontend identity | All 21 files match the tested build in desktop bundle and portable ZIP |

Validation logs, screenshots, responsive checks, and package hashes are in [the evidence folder](evidence/product-refinement-2026-10-08/).

Browser checks use Google Chrome against a temporary native graph API fixture. Failure and race regressions inject transport faults. These checks do not establish universal absence of bugs.

Native desktop window behavior and installation on a clean machine remain unverified. The installed application was not replaced.

## Delivery

- [Portable app](C:/Users/Daniel/Desktop/PBIBrain/dist/PBIBrain-Portable-x64.zip)
- [Windows installer](C:/Users/Daniel/Desktop/PBIBrain/dist/installer/PBIBrain-Setup-x64.exe)

Source changes remain uncommitted. Graft was rebuilt after the changes.
