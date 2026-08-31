# Power BI Desktop Bridge CLI research

Research date: 2026-08-31. Sources are Microsoft-owned documentation, Microsoft’s
published npm package, and the published package metadata.

## Finding

`@microsoft/powerbi-desktop-bridge-cli` gives Power BI Brain a direct local
connection to a running Power BI Desktop instance and can open a `.pbip` or
`.pbix` file. It does **not** return semantic-model or report metadata for graph
ingestion. The Brain still needs its file/MCP adapters for TMDL/TMSL and PBIR;
the bridge is the Desktop open/reload/status/screenshot control path.

The package is a public preview. The published package currently reports version
`0.1.2`, requires Node.js 20+, and installs the `powerbi-desktop` executable.
[npm package metadata and README](https://www.npmjs.com/package/@microsoft/powerbi-desktop-bridge-cli)

## Commands and machine output

Install and check the command:

```powershell
npm install -g @microsoft/powerbi-desktop-bridge-cli@latest
powerbi-desktop --version
```

Supported commands:

| Command | Input/output and use |
|---|---|
| `powerbi-desktop open <path.pbip\|path.pbix>` | Launches Desktop with the file, waits for bridge discovery, and emits a JSON envelope with launch details and bridge status. |
| `powerbi-desktop status [--pid <pid>]` | Emits `status` plus `instances[]`; connected instances include `pid`, `currentFilePath`, `hasUnsavedChanges`, `reportDir`, and PBIR `pages[]`. |
| `powerbi-desktop manifest --pid <pid>` | Emits `status`, `pid`, and the Desktop method manifest. |
| `powerbi-desktop reload --pid <pid>` | Reloads the selected Desktop instance’s current PBIP/PBIR file and emits `result.success`; it takes no separate report path. |
| `powerbi-desktop screenshot <page-id> --pid <pid> [--output <png>]` | Captures one PBIR page, writes a PNG, and emits the resolved output path. The page argument is the internal PBIR page ID. |
| `powerbi-desktop screenshot-all --pid <pid> --output-dir <dir>` | Reads PBIR `pages.json`, captures each page serially, and emits `status: "ok"` or `"partial"` plus `screenshots[]` and `failures[]`. |

The CLI writes machine-readable JSON to stdout and progress/diagnostic text to
stderr. Select a PID from `status` before single-instance operations. The
package README documents the command set, JSON stdout contract, PID selection,
and serial-operation rule.
[Published CLI README](https://www.npmjs.com/package/@microsoft/powerbi-desktop-bridge-cli)

`open` is the only command that accepts a PBIP/PBIX path. `reload` and
`screenshot-all` require the selected Desktop instance to expose a PBIP/PBIR
current file; a PBIX-only instance cannot satisfy those operations. The
Microsoft runbook also confirms that `--report` is not a supported selector and
that screenshot IDs are PBIR internal page IDs, not display names.
[Microsoft Desktop verification runbook](https://github.com/microsoft/skills-for-fabric/blob/main/skills/powerbi-report-authoring/references/powerbi-desktop.md)

Important package behavior: the published `0.1.2` CLI implementation invokes
`file.reload/v1` with `reloadModelDefinition: false`. Treat `powerbi-desktop
reload` as a report/PBIR reload; use the Modeling MCP/file workflow and reopen
the PBIP when TMDL/TMSL model changes must be applied.
[Published package](https://registry.npmjs.org/@microsoft/powerbi-desktop-bridge-cli/-/powerbi-desktop-bridge-cli-0.1.2.tgz)

## Connection and safety boundaries

The bridge is a local server inside Power BI Desktop. It uses the Windows named
pipe `pbi-desktop-bridge-{processId}` and JSON-RPC 2.0 with Content-Length
framing. Remote access is not supported, each Desktop window has its own pipe,
and only one operation should run at a time for a PID.
[Microsoft Learn: Desktop Bridge overview](https://learn.microsoft.com/en-us/power-bi/developer/agentic/power-bi-desktop-bridge-overview)

The currently documented bridge methods are:

- `application.state.get/v1`: current file path and unsaved-change flag.
- `report.snapshot.capture/v1`: a Base64-encoded PNG for one PBIR page.
- `file.reload/v1`: reloads the current PBIP/PBIR file, with a
  `reloadModelDefinition` option.
- `bridge.manifest`: discovers the methods and their schemas.

There is no documented metadata-extraction method. Status/manifest are
read-only observations. Reload changes Desktop’s in-memory state and screenshots
write local PNG files; neither is a semantic-model mutation API. Check
`hasUnsavedChanges` before reload because a reload can replace unsaved Desktop
state. The bridge requires the Power BI Desktop preview option **Enable external
tool access to Power BI Desktop through secure local APIs**.
[Microsoft Learn: methods, prerequisites, and transport](https://learn.microsoft.com/en-us/power-bi/developer/agentic/power-bi-desktop-bridge-overview)

## Brain integration route

Use the bridge as a controlled Desktop companion to the existing ingestion
pipeline:

1. `powerbi-desktop open "<report>.pbip"`.
2. Run `powerbi-desktop status`; select the instance whose `currentFilePath`
   matches the target and whose bridge is connected.
3. Ingest the PBIP project’s semantic-model files and PBIR files through Brain
   adapters. Do not expect metadata from the bridge JSON.
4. For report-definition edits, validate PBIR, run
   `powerbi-desktop reload --pid <pid>`, then rerun ingestion and optionally
   capture screenshots.
5. For TMDL/TMSL semantic-model edits, use the Power BI Modeling MCP/file
   workflow and reopen the PBIP if Desktop does not reflect the model change;
   the Microsoft runbook scopes bridge reload primarily to PBIR/report edits.
[Microsoft report-authoring workflow](https://github.com/microsoft/skills-for-fabric/blob/main/skills/powerbi-report-authoring/references/powerbi-desktop.md)

This preserves the Brain boundary: PBIP files/MCP provide source metadata,
normalization produces canonical facts, and the Desktop bridge only controls and
verifies the local Desktop process.

## Local smoke evidence

On 2026-08-31, the installed command returned `0.1.2`. `powerbi-desktop status`
found the open Finance PBIP with `bridgeStatus: "connected"`,
`hasUnsavedChanges: false`, a resolved `.Report` directory, and one PBIR page.
`powerbi-desktop manifest --pid <that status PID>` returned the three operational
methods above plus `bridge.manifest`. This confirms direct PBIP/Desktop
connection on this machine; it does not change the metadata-extraction finding.
