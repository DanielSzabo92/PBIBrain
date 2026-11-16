# Power BI Brain

*A DownDraughtLab product.*

Semantic graph of your Power BI / Fabric models and reports — a desktop workbench and an MCP server for AI agents.

- **Reads:** PBIP, TMDL, PBIR, cloud semantic models and reports
- **Builds:** one graph of models, tables, columns, measures, calculation groups, DAX functions, M sources, report pages and visuals
- **Serves:** a workbench (desktop or browser), a CLI, and an MCP server

---

## Start

| Option | How |
|---|---|
| Windows installer | Install, open **PBIBrain**, pick the folder with the `.pbip`, **Scan**. See [`docs/DESKTOP.md`](docs/DESKTOP.md). |
| From source (Windows) | `start.bat` |
| From source (Linux / macOS) | `./start.sh` |

- Source start: creates `.venv`, installs, builds the UI, opens `http://127.0.0.1:8000/`
- No project? Empty Overview → **Open sample project**
- Requires: Python 3.11+, Node.js 20+ (source only). The graph is SQLite via Python's built-in `sqlite3` — no database, DLL or environment variable to set up
- Merge model verification also builds the TOM bridge: .NET 8 SDK, `dotnet build -c Release backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj`

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
