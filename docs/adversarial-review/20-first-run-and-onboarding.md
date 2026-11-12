# 20 · First run: an empty shell with seven views that all say "nothing here"

**Severity:** P2 · **Criteria:** easy and obvious, accomplishes its goals

## Evidence

![First run](evidence/first-run.png)

A new project opens on:

- "Add your project sources" card with one button, beside a **Validation summary** card that already says "No schema or dependency issues detected." for a project with no data, and a disabled "Scan now".
- The focus box around the h1 (15, item 1).
- A status bar reading "0 models · 0 reports · 0 objects · 0 relationships · Last scan time unknown · Scan now".
- All seven navigation items enabled; Graph says "No matching objects" (nothing was searched), Review and Inspector show their normal chrome with nothing in it.
- `start.sh` opens the browser after a fixed 1.5 s sleep; on a cold start the page can load before the server listens.
- There is no sample project, so nobody can see what the product does without first owning a PBIP project.
- The README promises "1-Click Launch" but requires Python 3.11+ and Node 20+ and builds the UI on first run.

## Solution

1. **A dedicated first-run screen** replacing the shell content (sidebar dimmed until there is data):
   - Drop zone: "Drop a .pbip project or folder here" + **Browse…** + "Connect a workspace".
   - **Open sample project** — ship the merge-lab fixture (`tools/build_merge_lab.py` output) as a bundled demo so every view has content in one click.
2. **Scan immediately after adding** with a determinate progress view: per source, a phase label (Reading model › Parsing DAX › Linking reports) and live object counts. When it ends, land on the Overview with a one-line result ("13,731 objects from 8 sources in 21 s").
3. **Guided next step, not a tour:** after the first scan the Overview's attention ledger lists up to three actions (review suggestions, 2 unused measures, open the graph). No stepper, no coach marks.
4. **Empty states say the truth:** Graph → "No sources scanned yet" + Add sources; never "No matching objects" without a query. Remove the validation card until a scan exists. Hide status-bar counts at zero.
5. **Launch:** add a cheap `GET /api/health` (there is none today) and poll it before opening the browser in `start.sh` / `start.bat`; print one clear line with the URL. Offer the packaged desktop build (`packaging/`) as the primary download in the README; keep the script route under "From source".
6. **Recent projects** on the first-run screen and in the title-bar switcher.

## Acceptance

- From a fresh install, a user reaches a populated graph in ≤ 2 clicks (sample) or ≤ 3 (own project).
- No view shows a zero-count or "no issues" claim before the first scan.
