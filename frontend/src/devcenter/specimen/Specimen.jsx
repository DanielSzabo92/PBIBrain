// Part specimen (UI design 13, step U1). Test page only: main.jsx loads it at /__specimen__
// only when the fake server shim is on the page (DEVCENTER_FAKE=1). It shows each shared
// part in each of its states, for the e2e axe, click, and keyboard specs and for the kit gates.
import * as React from "react"
import { Copy, FileText, MoreHorizontal, Pencil, Search, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Select } from "@/components/ui/select"
import { Combobox } from "@/components/ui/combobox"
import { Menu } from "@/components/ui/menu"
import { FilterButton, FilterChip } from "@/components/ui/filter"
import { SegmentedControl } from "@/components/ui/segmented-control"
import { Switch } from "@/components/ui/switch"
import { ChoiceRadio } from "@/components/ui/choice-radio"
import { StatusBadge } from "@/components/ui/status-badge"
import { Tooltip, TooltipProvider } from "@/components/ui/tooltip"
import { Banner, Notice } from "@/components/ui/notice"
import { ToastProvider, useToast } from "@/components/ui/toast"
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogTrigger, Dialog, DialogClose, DialogContent, DialogTrigger } from "@/components/ui/dialog"
import { SidePane } from "@/components/ui/side-pane"
import { ProgressList, StepIndicator } from "@/components/ui/progress"
import { EmptyState, ResultPanel, Skeleton } from "@/components/ui/result-panel"
import { DataTable } from "@/components/ui/data-table"
import { Input } from "@/components/ui/input"

const THEME_KEY = "pbibrain-theme"

function useSpecimenTheme() {
  const [theme, setTheme] = React.useState(() => (document.documentElement.dataset.theme === "light" ? "light" : "dark"))
  React.useEffect(() => {
    const root = document.documentElement
    root.classList.toggle("dark", theme === "dark")
    if (theme === "light") root.dataset.theme = "light"
    else delete root.dataset.theme
    try { localStorage.setItem(THEME_KEY, theme) } catch { /* Storage can be unavailable. */ }
  }, [theme])
  return [theme, setTheme]
}

function Part({ id, title, children }) {
  return (
    <section className="specimen-part" aria-labelledby={`part-${id}`} data-part={id}>
      <h2 id={`part-${id}`}>{title}</h2>
      <div className="specimen-row">{children}</div>
    </section>
  )
}

function State({ label, children }) {
  return (
    <div className="specimen-state">
      <p className="specimen-state-label">{label}</p>
      {children}
    </div>
  )
}

const SELECT_OPTIONS = [
  { value: "keep", label: "Keep target" },
  { value: "source", label: "Use source", description: "Copies the source definition." },
  { value: "both", label: "Keep both", disabled: true, reason: "The names clash. Rename one object first." },
]

const FOLDERS = [
  { label: "Model folders", options: [{ value: "measures", label: "Measures" }, { value: "finance", label: "Finance" }, { value: "sales", label: "Sales" }] },
  { label: "Other folders", options: [{ value: "archive", label: "Archive", warn: "Not in the target model" }] },
]

const TABLE_ROWS = [
  { id: "net-sales", name: "Net Sales", type: "Measure", status: "ok" },
  { id: "margin", name: "Margin", type: "Measure", status: "warn" },
  { id: "region", name: "Region", type: "Column", status: "bad" },
]

const STATUS_WORDS = { ok: "Valid", warn: "Valid with warnings", bad: "Not valid" }

function ToastDemo() {
  const toast = useToast()
  return <Button variant="outline" onClick={() => toast.show({ tone: "ok", text: "Merge Choice set for 3 rows." })}>Show toast</Button>
}

function ControlledCheckbox(props) {
  const [checked, setChecked] = React.useState(props.defaultChecked ?? false)
  return <Checkbox {...props} checked={checked} onCheckedChange={setChecked} />
}

function DialogDemos() {
  const [progressOpen, setProgressOpen] = React.useState(false)
  return (
    <>
      <State label="Dialog">
        <Dialog>
          <DialogTrigger asChild><Button id="specimen-open-dialog" variant="outline">Rename object</Button></DialogTrigger>
          <DialogContent title="Rename object" description="Type the new name of the measure." footer={<><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><DialogClose asChild><Button>Save name</Button></DialogClose></>}>
            <label className="specimen-field">New name<Input defaultValue="Net Sales" /></label>
          </DialogContent>
        </Dialog>
      </State>
      <State label="AlertDialog, destructive">
        <AlertDialog>
          <AlertDialogTrigger asChild><Button id="specimen-open-alert" variant="destructive"><Trash2 />Delete rule</Button></AlertDialogTrigger>
          <AlertDialogContent title="Delete the naming rule?" description="The rule goes out of this session. You cannot undo this action." footer={<><AlertDialogCancel asChild><Button variant="outline">Cancel</Button></AlertDialogCancel><AlertDialogAction asChild><Button variant="destructive">Delete rule</Button></AlertDialogAction></>} />
        </AlertDialog>
      </State>
      <State label="Dialog, progress mode">
        <Dialog open={progressOpen} onOpenChange={setProgressOpen}>
          <DialogTrigger asChild><Button variant="outline">Apply plan</Button></DialogTrigger>
          <DialogContent progress title="Apply the plan" description="Do not close the app while the plan applies." footer={<Button onClick={() => setProgressOpen(false)}>Finish demo</Button>}>
            <ProgressList label="Apply steps" lines={[{ text: "Make a backup", state: "done" }, { text: "Write the model", state: "running" }, { text: "Check the result", state: "pending" }]} footer="Step 2 of 3. 0:04 elapsed." />
          </DialogContent>
        </Dialog>
      </State>
    </>
  )
}

function SidePaneDemo() {
  const [openRow, setOpenRow] = React.useState(null)
  const rows = TABLE_ROWS
  const index = rows.findIndex((row) => row.id === openRow)
  return (
    <div className="specimen-pane-layout">
      <ul className="specimen-pane-rows" aria-label="Rows">
        {rows.map((row) => (
          <li key={row.id}><Button id={`specimen-open-${row.id}`} variant="ghost" aria-pressed={row.id === openRow} onClick={() => setOpenRow(row.id)}>Open {row.name}</Button></li>
        ))}
      </ul>
      <SidePane
        open={index >= 0}
        title={index >= 0 ? rows[index].name : ""}
        onClose={() => setOpenRow(null)}
        canPrevious={index > 0}
        canNext={index >= 0 && index < rows.length - 1}
        onPrevious={() => setOpenRow(rows[Math.max(index - 1, 0)].id)}
        onNext={() => setOpenRow(rows[Math.min(index + 1, rows.length - 1)].id)}>
        <p>Type: {index >= 0 ? rows[index].type : ""}</p>
        <Button variant="outline">Set Merge Choice</Button>
      </SidePane>
    </div>
  )
}

export default function Specimen() {
  const [theme, setTheme] = useSpecimenTheme()
  const [tab, setTab] = React.useState("compare")
  const [view, setView] = React.useState("grid")
  const [strictness, setStrictness] = React.useState("default")
  const [choice, setChoice] = React.useState("keep")
  const [switchOn, setSwitchOn] = React.useState(false)
  const [selectValue, setSelectValue] = React.useState("keep")
  const [folder, setFolder] = React.useState("")
  const [filter, setFilter] = React.useState(["measure"])
  const [checked, setChecked] = React.useState(["margin"])
  const [menuResult, setMenuResult] = React.useState("No action yet")

  React.useEffect(() => { document.title = "Part specimen" }, [])

  return (
    <TooltipProvider>
      <ToastProvider>
        <main className="specimen" aria-labelledby="specimen-title">
          <header className="specimen-header">
            <h1 id="specimen-title">Part specimen</h1>
            <Switch label="Light theme" checked={theme === "light"} onCheckedChange={(on) => setTheme(on ? "light" : "dark")} />
          </header>

          <Part id="button" title="Button">
            <State label="Primary"><Button>Create session</Button></State>
            <State label="Outline"><Button variant="outline">Check sources</Button></State>
            <State label="Secondary"><Button variant="secondary">Show filters</Button></State>
            <State label="Ghost"><Button variant="ghost">Clear selection</Button></State>
            <State label="Destructive"><Button variant="destructive"><Trash2 />Remove object</Button></State>
            <State label="Destructive outline"><Button variant="destructive-outline">Remove rule</Button></State>
            <State label="Status ok"><Button variant="status" tone="ok">Confirm row</Button></State>
            <State label="Status warn"><Button variant="status" tone="warn">Review warnings</Button></State>
            <State label="Status bad"><Button variant="status" tone="bad">Show conflicts</Button></State>
            <State label="Disabled"><Button disabled>Apply plan</Button></State>
            <State label="Loading"><Button loading loadingText="Checking sources">Check sources</Button></State>
            <State label="Icon"><Button variant="ghost" size="icon" aria-label="Copy name"><Copy /></Button></State>
          </Part>

          <Part id="tabs" title="Tabs">
            <Tabs value={tab} onValueChange={setTab}>
              <TabsList aria-label="Work area">
                <TabsTrigger value="compare" count={12} countLabel="rows">Compare</TabsTrigger>
                <TabsTrigger value="impact" count={3} countTone="bad" countLabel="breaks">Impact</TabsTrigger>
                <TabsTrigger value="plan">Plan</TabsTrigger>
                <TabsTrigger value="log" disabled>Log</TabsTrigger>
              </TabsList>
              <TabsContent value="compare"><p>The compare grid shows here.</p></TabsContent>
              <TabsContent value="impact"><p>The impact list shows here.</p></TabsContent>
              <TabsContent value="plan"><p>The plan shows here.</p></TabsContent>
              <TabsContent value="log"><p>The log shows here.</p></TabsContent>
            </Tabs>
          </Part>

          <Part id="checkbox" title="Checkbox">
            <State label="Unchecked"><label className="specimen-inline"><ControlledCheckbox size="target" />Include hidden objects</label></State>
            <State label="Checked"><label className="specimen-inline"><ControlledCheckbox size="target" defaultChecked />Show changed rows</label></State>
            <State label="Mixed"><label className="specimen-inline"><Checkbox size="target" checked="indeterminate" />Select page</label></State>
            <State label="Error"><label className="specimen-inline"><Checkbox size="target" aria-invalid="true" aria-describedby="approve-hint" />Approve the risk</label><p id="approve-hint" className="specimen-error">Approve the risk to apply.</p></State>
            <State label="Disabled"><label className="specimen-inline"><Checkbox size="target" disabled />Locked row</label></State>
            <State label="Small"><label className="specimen-inline"><ControlledCheckbox />Relationship labels</label></State>
          </Part>

          <Part id="select" title="Select">
            <State label="Default"><Select label="Merge Choice" value={selectValue} onValueChange={setSelectValue} options={SELECT_OPTIONS} /></State>
            <State label="Placeholder"><Select label="Removal policy" options={SELECT_OPTIONS} placeholder="Select a policy" /></State>
            <State label="Disabled"><Select label="Locked choice" value="keep" options={SELECT_OPTIONS} disabled hint="The session is locked." /></State>
            <State label="Loading"><Select label="Target model" options={[]} loading placeholder="Select a model" /></State>
            <State label="Error"><Select label="Sort order" options={SELECT_OPTIONS} placeholder="Select an order" error="Select a sort order." /></State>
          </Part>

          <Part id="combobox" title="Combobox">
            <State label="Default"><Combobox label="Display folder" value={folder} onValueChange={(next) => setFolder(next)} groups={FOLDERS} placeholder="Type a folder" createLabel={(text) => `Use new folder "${text}"`} /></State>
            <State label="Disabled"><Combobox label="Locked folder" value="Measures" groups={FOLDERS} disabled /></State>
            <State label="Loading"><Combobox label="Folder from source" groups={[]} loading loadingText="Loading folders" /></State>
            <State label="List error"><Combobox label="Folder from target" groups={[]} listError="Cannot load the folder list. You can type a folder." /></State>
            <State label="Field error"><Combobox label="Folder name" groups={FOLDERS} error="Type a folder name." /></State>
          </Part>

          <Part id="menu" title="Menu">
            <State label="Row menu">
              <Menu
                label="Row actions"
                trigger={<Button variant="outline" aria-label="Row actions"><MoreHorizontal /></Button>}
                groups={[
                  { label: "Row", items: [{ label: "Rename", icon: Pencil, onSelect: () => setMenuResult("Rename") }, { label: "Copy name", icon: Copy, onSelect: () => setMenuResult("Copy name") }, { label: "Show code", icon: FileText, disabled: true }] },
                  { label: "View", items: [{ label: "Show hidden objects", checked: true }] },
                  { items: [{ label: "Remove from plan", icon: Trash2, destructive: true, onSelect: () => setMenuResult("Remove from plan") }] },
                ]} />
              <p className="specimen-note" role="status">Last action: {menuResult}</p>
            </State>
          </Part>

          <Part id="filter" title="FilterButton and FilterChip">
            <State label="No value"><FilterButton label="State" options={[{ value: "same", label: "Same", count: 40 }, { value: "different", label: "Different", count: 7 }]} selected={[]} /></State>
            <State label="Active"><FilterButton label="Type" options={[{ value: "measure", label: "Measure", count: 24 }, { value: "column", label: "Column", count: 61 }]} selected={filter} onSelectedChange={setFilter} /></State>
            <State label="Loading"><FilterButton label="Folder" options={[{ value: "a", label: "Finance" }]} selected={[]} loading /></State>
            <State label="Error"><FilterButton label="Table" options={[]} selected={[]} error="Cannot load the values. Try again." onRetry={() => {}} /></State>
            <State label="Disabled"><FilterButton label="Owner" options={[]} selected={[]} disabled /></State>
            <State label="Chip"><FilterChip label="Type: Measure" onRemove={() => {}} /></State>
          </Part>

          <Part id="segmented" title="SegmentedControl">
            <State label="Toggle mode"><SegmentedControl aria-label="View" value={view} onValueChange={setView} options={[{ value: "grid", label: "Grid" }, { value: "graph", label: "Graph" }, { value: "wireframe", label: "Wireframe" }]} /></State>
            <State label="Radio mode"><SegmentedControl mode="radio" aria-label="Match mode" value={strictness} onValueChange={setStrictness} options={[{ value: "default", label: "Default" }, { value: "strict", label: "Strict" }]} /></State>
            <State label="Disabled"><SegmentedControl aria-label="Locked view" value="grid" disabled options={[{ value: "grid", label: "Grid" }, { value: "graph", label: "Graph" }]} /></State>
          </Part>

          <Part id="switch" title="Switch">
            <State label="Off and on"><Switch label="Use the / key to go to search" description="When this is off, the / key types a slash." checked={switchOn} onCheckedChange={setSwitchOn} /></State>
            <State label="On"><Switch label="Show changed rows only" defaultChecked /></State>
            <State label="Disabled"><Switch label="Locked setting" disabled /></State>
          </Part>

          <Part id="choice" title="ChoiceRadio group">
            <State label="Default">
              <ChoiceRadio
                legend="Merge Choice"
                value={choice}
                onValueChange={setChoice}
                items={[
                  { value: "keep", label: "Keep target", badge: <StatusBadge tone="plain" label="Default" /> },
                  { value: "source", label: "Use source", children: <label className="specimen-field">New name<Input defaultValue="Net Sales" /></label> },
                  { value: "both", label: "Keep both", disabled: true, reason: "The names clash. Rename one object first." },
                ]} />
            </State>
            <State label="Loading"><ChoiceRadio legend="Removal policy" value="keep" loading items={[{ value: "keep", label: "Keep in target" }, { value: "remove", label: "Remove from target" }]} /></State>
          </Part>

          <Part id="status" title="StatusBadge and Tooltip">
            <State label="Tones">
              <div className="specimen-wrap" data-status-list>
                <StatusBadge tone="ok" label="Valid" />
                <StatusBadge tone="warn" label="High" />
                <StatusBadge tone="bad" label="Critical" />
                <StatusBadge tone="info" label="Proposed" />
                <StatusBadge tone="plain" label="Not checked" />
                <StatusBadge tone="proposal" label="Agent proposal" />
              </div>
            </State>
            <State label="Tooltip trigger">
              <Tooltip content="The match is not certain. Check the row.">
                <StatusBadge tone="plain" help label="Possible" description="The match is not certain. Check the row." />
              </Tooltip>
            </State>
            <State label="Tooltip on a button">
              <Tooltip content="Search names (/)">
                <Button variant="outline" size="icon" aria-label="Search names" aria-keyshortcuts="/"><Search /></Button>
              </Tooltip>
            </State>
          </Part>

          <Part id="notice" title="Notice and Banner">
            <div className="specimen-stack">
              <Notice tone="info" title="Sources changed">Check the sources again to see the new rows.</Notice>
              <Notice tone="warn" title="2 rows need a decision" actions={<Button variant="outline" size="sm">Show rows</Button>}>Set a Merge Choice for each row.</Notice>
              <Notice tone="bad" title="Cannot read the target model" actions={<Button variant="outline" size="sm">Try again</Button>}>The file is open in another program.</Notice>
              <Notice tone="ok" title="Plan is valid">You can apply the plan.</Notice>
              <Notice tone="brand" title="The agent proposed 3 changes">Open the Agent tab to see them.</Notice>
              <Banner tone="warn" title="This session is locked">An apply is in progress in another window.</Banner>
            </div>
          </Part>

          <Part id="toast" title="Toast">
            <State label="Polite toast"><ToastDemo /></State>
          </Part>

          <Part id="dialog" title="Dialog and AlertDialog">
            <DialogDemos />
          </Part>

          <Part id="sidepane" title="SidePane">
            <SidePaneDemo />
          </Part>

          <Part id="steps" title="StepIndicator and ProgressList">
            <StepIndicator label="Create session steps" steps={[{ label: "Sources", state: "done" }, { label: "Target", state: "current" }, { label: "Check", state: "todo" }, { label: "Names", state: "error" }]} />
            <ProgressList label="Check steps" lines={[{ text: "Read the source model", state: "done" }, { text: "Read the target model", state: "running" }, { text: "Match the objects", state: "pending" }, { text: "Read the report", state: "failed", fix: "Close the report in Power BI Desktop, then try again." }]} footer="Step 2 of 4. 0:09 elapsed." />
          </Part>

          <Part id="result" title="ResultPanel">
            <div className="specimen-stack">
              <ResultPanel tone="success" title="Plan applied" actions={<Button variant="outline" size="sm">Show change report</Button>} onClose={() => {}}>12 changes are in the target project.</ResultPanel>
              <ResultPanel tone="differences" title="Plan applied with differences" actions={<Button variant="outline" size="sm">Show differences</Button>}>2 checks show a different result.</ResultPanel>
              <ResultPanel tone="failure" title="Apply failed" actions={<Button variant="outline" size="sm">Undo apply</Button>}>The target project did not change. Close Power BI Desktop and try again.</ResultPanel>
            </div>
          </Part>

          <Part id="empty" title="EmptyState and Skeleton">
            <State label="Empty"><EmptyState title="No sessions" action={<Button>Create session</Button>}>Create a session to compare two projects.</EmptyState></State>
            <State label="Error"><EmptyState variant="error" title="Cannot load the sessions" action={<Button variant="outline">Try again</Button>}>The session folder is not available.</EmptyState></State>
            <State label="Loading"><Skeleton lines={4} label="Loading rows" /></State>
          </Part>

          <Part id="table" title="DataTable">
            <DataTable
              caption="Objects with a change"
              rows={TABLE_ROWS}
              checked={checked}
              onCheckedChange={setChecked}
              rowLabel={(row) => row.name}
              columns={[
                { key: "name", header: "Name", rowHeader: true },
                { key: "type", header: "Type" },
                { key: "status", header: "Status", render: (row) => <StatusBadge tone={row.status} label={STATUS_WORDS[row.status]} /> },
              ]}
              renderDetail={(row) => <p>{row.name} has a change in its expression.</p>}
              renderActions={(row) => <Button variant="ghost" size="sm" aria-label={`Open ${row.name}`}>Open</Button>} />
          </Part>
        </main>
      </ToastProvider>
    </TooltipProvider>
  )
}
