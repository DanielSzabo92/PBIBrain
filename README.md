# Power BI Brain

*A DownDraughtLab product.*

PBIBrain reads your Power BI project files and builds one searchable map of everything in them: models, tables, columns, measures, DAX, Power Query sources, report pages and visuals, and how they depend on each other. You use that map to understand a model, see what breaks if you change something, compare and merge models, export documentation, and give AI agents accurate answers about your reports.

It never changes your Power BI files on its own. The only thing that writes to them is **Merge models → Apply**, after you confirm, with a backup and undo.

---

## How the parts fit together

```text
 Your files                    PBIBrain                                 You and your tools
 ──────────                    ────────                                 ──────────────────
 .pbip / TMDL / PBIR  ──scan──▶  graph (.pbibrain/brain.sqlite)  ──▶  Workbench (desktop app or browser)
 model.bim, .json                 one node per object,                 CLI  (brain …)
 Power BI service items           one link per dependency        ──▶  MCP server for AI agents
                                                                  ──▶  Documentation export (PDF / Markdown)
                                         ▲
                                         └── Merge models: compare → choose → guard check → apply (desktop app only)
```

| Part | What it is | When you use it |
|---|---|---|
| **Project** | A folder with a `.pbibrain/` subfolder: the list of sources (`brain.json`), the graph, your review decisions | Always — everything belongs to one project |
| **Sources** | The Power BI items the project reads: `.pbip` projects, model folders (TMDL), `model.bim`, report folders (PBIR), cloud models and reports | Add them in **Settings**, then **Scan** |
| **Scan** | Reads every source and rebuilds the graph. Read-only. Two copies of the same model (e.g. `Sales v1` and `Sales v2`) are kept side by side as versions | After you add sources or edit the Power BI files |
| **Workbench** | The app: Overview, Search, Graph, Inspector, Review queue, Merge models, Settings, AI chat | Day-to-day exploring |
| **Review queue** | Things PBIBrain guessed (for example "this measure is the same KPI as that one"). You accept or reject them; facts read from files are never changed | When you want those guesses to count |
| **Merge models** | Combine several models and reports into one target model: compare, choose objects, check rules, apply with backup and undo | When consolidating models. Desktop app only — see below |
| **MCP server / `agent-setup`** | Lets Claude Code, Copilot, Codex, Cursor etc. ask the graph questions and propose (not apply) changes | When you work with an AI coding agent |
| **Documentation export** | A PDF or Markdown document for developers and customers: model diagram with storage modes, relationships, tables, measures with DAX, report pages and fields, data sources | Handing a model over, or reviewing it |

### Desktop app or browser?

The same workbench runs in two ways. Both read the same project folder.

| | Desktop app | Browser tab |
|---|---|---|
| How to start | Windows installer → **PBIBrain**, or `pbibrain` from source | `start.bat` / `./start.sh` → opens `http://127.0.0.1:8000/` |
| Explore, search, graph, review, chat, export docs | Yes | Yes |
| File and folder pickers | Yes | No — type or paste paths in **Settings** |
| **Merge models** (create session, add sources, apply) | Yes | No — shows a notice. A browser tab is not allowed to change Power BI files ([why](docs/SECURITY_BOUNDARIES.md)) |
| Cloud items (Power BI service sign-in) | Yes | No |

---

## Getting started

### 1. Install and open

| Option | How |
|---|---|
| Windows installer (recommended) | Install, then open **PBIBrain** from Start. Nothing else to install. See [`docs/DESKTOP.md`](docs/DESKTOP.md). |
| Desktop app from source | `python -m pip install -e ".[mcp,chat,cloud,desktop]"`, build the UI once (`cd frontend && npm install && npm run build`), then run `pbibrain` |
| Browser, from source (Windows) | `start.bat` |
| Browser, from source (Linux / macOS) | `./start.sh` |

- `start.bat` / `start.sh` create `.venv`, install, build the UI, start the server and open the browser
- Requires (source only): Python 3.11+, Node.js 20+. The graph is SQLite through Python's built-in `sqlite3` — no database to install
- Merge models also checks changes with the TOM bridge: .NET 8 SDK, `dotnet build -c Release backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj`

### 2. Open a project

- Desktop app: pick the folder that holds your `.pbip` file. PBIBrain creates `.pbibrain/` in it.
- Browser: the server uses the project in `config/brain.json` (or `--config <path>`).
- Just looking? On the empty Overview choose **Open sample project**.

### 3. Add sources and scan

**Settings** (`Ctrl+,`) → **Add source files** (or drop files on the window, or type paths) → **Scan** (`Ctrl+F5`). The scan runs in the background; you can cancel it. Rescan whenever you change the Power BI files — PBIBrain does not watch them.

### 4. Explore

| I want to… | Go to |
|---|---|
| See what is in the project and what differs between models | **Overview** (`Ctrl+1`) |
| Find a measure, column or visual by name | **Search** (`Ctrl+2`) or `Ctrl+K` |
| See where a field comes from and which visuals use it | **Graph** (`Ctrl+3`) → Lineage / Field usage |
| Read one measure's DAX, its dependencies and the visuals that show it | **Inspector** (`Ctrl+4`) |
| Know what breaks if I change or delete something | **Graph** → select it (trace on select), or `brain impact <id>` |
| Ask a question in plain language | **AI chat** (`Ctrl+J`) — set up a provider in Settings first |
| Hand the model to someone | **File → Export documentation…** (PDF or Markdown) |

### 5. Merge models (desktop app)

1. **Merge models** (`Ctrl+6`) → **New merge session**.
2. Add the source models and reports, pick the target (a copy of one source, or an existing PBIP), name the session.
3. **Compare**: every table, column, measure and relationship lined up across the sources — identical, different, or only in one.
4. Choose what goes into the target. Change guards block unsafe edits (broken DAX references, lost report fields).
5. **Plan** → **Apply**. A backup is taken first; **Undo apply** restores it.

Close Power BI Desktop on the target before applying: Desktop does not reload files changed on disk and may overwrite them.

### 6. Connect an AI agent (optional)

`brain --config <project>/.pbibrain/brain.json agent-setup` — then your editor's agent can search the graph, check impact and send merge proposals that wait for you in the app. Details below and in [`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md).

---

## Workbench

| View | Key | What it does |
|---|---|---|
| Overview | `Ctrl+1` | Project health, scan status, identical / drifted / renamed / unique objects across models |
| Search | `Ctrl+2` | Search all objects, preview beside results |
| Graph | `Ctrl+3` | Containers, lineage, field usage; path list, trace on select |
| Inspector | `Ctrl+4` | One object: DAX, dependencies, report bindings, evidence |
| Review queue | `Ctrl+5` | Accept / reject inferred items, bulk select, undo |
| Merge models | `Ctrl+6` | Compare models, pick changes, check guards, apply, undo |
| Settings | `Ctrl+,` | Project, sources, theme, chat providers |

| Also | Key |
|---|---|
| Command palette | `Ctrl+K` |
| AI chat | `Ctrl+J` |
| Scan sources | `Ctrl+F5` |
| Side bar | `Ctrl+B` |
| Light / dark | `Ctrl+Shift+L` |
| All shortcuts | `F1` |

Other:
- Scan runs in the background, with Cancel
- Recent projects on the start screen and in the title bar
- Drop source files on the window to add them
- Export docs as PDF or Markdown

---

## AI chat (`Ctrl+J`)

| Provider | Needs |
|---|---|
| Anthropic | API key |
| OpenAI-compatible | URL (+ key) |
| Local (Ollama, LM Studio) | URL |
| Claude Code, GitHub Copilot, Codex, Antigravity | That CLI, signed in |

- Pick provider, model and effort in the chat; favourite models in Settings
- Answers come from the graph; object names in answers are links
- Agent reads and proposes — never applies. See [`docs/SECURITY_BOUNDARIES.md`](docs/SECURITY_BOUNDARIES.md)

---

## MCP server

```powershell
brain --config C:\Reports\brain.json mcp
```

20 tools:

| Group | Tools |
|---|---|
| Read (11) | `brain_dependencies`, `brain_overview`, `brain_search`, `brain_object`, `brain_context`, `brain_impact`, `brain_graph`, `brain_commonality`, `brain_compare`, `brain_guide`, `brain_pending_changes` |
| Merge (9) | `session_get`, `compare_rows_list`, `impact_get`, `naming_rules_get`, `name_propose`, `question_ask`, `plan_validate`, `proposal_check`, `proposal_submit` |

- App open → live answers; app closed → `.pbibrain/agent-snapshot.json`
- Every reply fits a size budget
- Proposals wait for you in the app

### Connect an editor

| Editor | Setup |
|---|---|
| Claude Code, GitHub Copilot (VS Code), Codex, Antigravity | `brain --config <brain.json> agent-setup` |
| Claude Desktop, Cursor | Add the JSON below |

`agent-setup` writes the MCP config plus editor hooks: PBIBrain tools allowed, files / terminal / web / other servers denied. See [`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md).

```json
{
  "mcpServers": {
    "pbibrain": { "command": "brain", "args": ["--config", "C:\\path\\to\\brain.json", "mcp"] }
  }
}
```

---

## Merge models

- Matches objects by `lineageTag`, name, normalised DAX
- Change guards block unsafe edits — [`docs/CHANGE_GUARD_CONTRACT.md`](docs/CHANGE_GUARD_CONTRACT.md)
- Targets: local PBIP (TMDL) or Fabric / Power BI Service (XMLA, Fabric REST)
- Backup before apply, one-click undo

---

## Lineage

- DAX: ANTLR4 parser — variables, dependencies, `CALCULATE` / `KEEPFILTERS`, `USERELATIONSHIP`
- M: static source tracing (`Sql.Database`, `Lakehouse.Contents`, `File.Contents`, dataflows, SharePoint…) — no code run, no credentials

---

## Project file (`brain.json`)

Stored in `<project>/.pbibrain/` with the graph and scan state.

```json
{
  "version": 1,
  "name": "Finance & Sales",
  "sources": ["C:\\Reports\\Finance\\Finance.pbip", "C:\\Reports\\Sales\\Sales.pbip"],
  "cloud_sources": [
    { "kind": "cloud_model", "workspace_id": "…", "item_id": "…", "name": "Corporate Model" }
  ],
  "database": "brain.sqlite",
  "identity_map": "identity-map.json"
}
```

Relative paths resolve from the folder of `brain.json`. What `.pbibrain/` holds:

| File | Holds |
|---|---|
| `brain.sqlite` (+ `-wal`, `-shm`) | The graph — one SQLite database, one transaction per scan |
| `identity-map.json` | Stable object IDs across renames and rescans |
| `overrides.json` | Your review decisions, kept apart from scanned facts |
| `agent-snapshot.json` | Graph copy MCP reads while the app is closed |
| `INDEX.md`, `.graph/`, `.cache/` | Trail cards exported for coding agents |

Older projects say `"database": "brain.lbug"`; that file is no longer read. Change it to `brain.sqlite` and rescan, or delete `.pbibrain` and reopen the folder.

---

## CLI

All commands take `--config <brain.json>`.

| Command | Does |
|---|---|
| `serve` | Workbench + local API |
| `mcp` | MCP server (stdio) |
| `agent-setup` | Configure editor agents |
| `project-scan` | Scan all sources |
| `scan <path>` (alias `build`) | Scan one `.pbip` / model |
| `status` | Node and edge counts |
| `search <q>` | Find objects |
| `retrieve <q>` | Ranked, paged search for agents |
| `object <id>` | One object |
| `context <id>` | Evidence subgraph |
| `impact <id>` | Downstream impact |
| `compare --before --after` | Compare two snapshots |
| `export-docs` | PDF / Markdown docs |
| `export-markdown` | Markdown dump of the graph |
| `config` | Show resolved config |

Also installed: `pbibrain` (desktop), `brain-agent`, `pbi-guard`.

---

## Trust classes

| Class | Means |
|---|---|
| `FACT` | Extracted from files |
| `INFERRED` | Interpreted from evidence |
| `OBSERVED` | Seen together in reports — not proof |
| Human decision | Your accept / reject / edit — never overwrites facts |

---

## Security

- Power BI access: read-only (writes only through Merge apply)
- Server: loopback only (`127.0.0.1`)
- Credentials: never stored in the graph or logs

---

## Layout

```text
backend/        Python: scanner, graph (SQLite), DAX parser, API, chat, MCP, merge
change_guard/   Change guard contracts and checks
frontend/       Vite + React workbench
packaging/      Windows installer
docs/           Specs, ADRs, guides
tests/          Python tests
```

---

## Develop

```powershell
python -m pip install -e ".[mcp,chat,cloud,desktop]"
python -m unittest discover -s tests
cd frontend; npm install; npm test; npm run build; npx playwright test
```

UI dev server: `cd frontend && npm run dev`

---

Source: [github.com/DanielSzabo92/PBIBrain](https://github.com/DanielSzabo92/PBIBrain) · MIT — see [LICENSE](LICENSE).
