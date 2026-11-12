"""Large synthetic project served by the real API, for the adversarial review."""
import argparse, json, random, sys, time
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server
ROOT = Path("/home/user/PBIBrain")
sys.path.insert(0, str(ROOT))
from backend.api.app import create_app
from backend.graph.repository import GraphRepository
from backend.projects import ProjectService

class Quiet(WSGIRequestHandler):
    def log_message(self, *a): pass

DOMAINS = ["Sales", "Finance", "Supply Chain", "HR", "Marketing", "Customer Service"]
ENT = ["Orders", "Order Lines", "Customers", "Products", "Stores", "Calendar", "Budget", "Forecast", "Inventory", "Shipments", "Returns", "Employees", "Campaigns", "Tickets", "Suppliers", "GL Entries", "Cost Centers", "Currencies", "Territories", "Promotions", "Price Lists", "Contracts", "Invoices", "Payments", "Accounts", "Channels", "Segments", "Warehouses", "Routes", "Carriers"]
COLS = ["Key", "Code", "Name", "Description", "Amount", "Quantity", "Unit Price", "Discount %", "Created Date", "Modified Date", "Status", "Region", "Country", "Category", "Sub Category", "Owner", "Currency Code", "Net Amount (Local Currency, Excluding Tax And Freight)"]
AGG = ["Total", "Average", "YTD", "PY", "YoY %", "MTD", "Rolling 12M", "Budget Variance", "Share of Total", "Rank by"]

def build(models, tables, measures, reports, pages, visuals, seed=7):
    rnd = random.Random(seed)
    out_models, out_reports = [], []
    for m in range(models):
        dom = DOMAINS[m % len(DOMAINS)]
        ver = m // len(DOMAINS)
        mid = f"model-{m}"
        mname = dom + " Analytics" + ("" if ver == 0 else f" v{ver+1}")
        tabs, mids, cids = [], [], []
        for t in range(tables):
            base = ENT[t % len(ENT)] + ("" if t < len(ENT) else f" {t // len(ENT) + 1}")
            tid = f"{mid}-t{t}"
            cols = []
            for c, cn in enumerate(COLS):
                cid = f"{tid}-c{c}"
                cols.append({"id": cid, "name": cn, "dataType": "Double" if "Amount" in cn or cn in ("Quantity", "Unit Price", "Discount %") else "String"})
                cids.append(cid)
            meas = []
            per = measures // tables
            for k in range(per):
                agg = AGG[k % len(AGG)]
                name = f"{agg} {base} Amount" + ("" if k < len(AGG) else f" {k // len(AGG) + 1}")
                xid = f"{tid}-m{k}"
                if k == 0 or not mids:
                    expr = f"SUM('{base}'[Amount])"
                else:
                    dep = rnd.choice(meas)["name"] if meas else None
                    expr = f"CALCULATE([{dep}], DATESYTD('Calendar'[Created Date]))" if dep else f"SUM('{base}'[Amount])"
                    # drift between versions
                    if ver and k % 7 == 0: expr = f"DIVIDE({expr}, 2)"
                meas.append({"id": xid, "name": name, "description": f"{agg} of {base.lower()} amount.", "expression": expr})
                mids.append(xid)
            tabs.append({"id": tid, "name": base, "columns": cols, "measures": meas})
        out_models.append({"id": mid, "name": mname, "tables": tabs})
        for r in range(reports):
            rid = f"{mid}-r{r}"
            secs = []
            for p in range(pages):
                vs = []
                for v in range(visuals):
                    vid = f"{rid}-p{p}-v{v}"
                    vs.append({"id": vid, "name": f"{rnd.choice(AGG)} by {rnd.choice(COLS)}", "title": f"{rnd.choice(AGG)} by {rnd.choice(COLS)}", "visualType": rnd.choice(["columnChart", "card", "tableEx", "lineChart", "slicer", "pivotTable"]),
                               "fields": [{"objectId": rnd.choice(cids), "kind": "column"} for _ in range(rnd.randint(1, 3))],
                               "measures": [{"objectId": rnd.choice(mids)} for _ in range(rnd.randint(1, 3))]})
                secs.append({"id": f"{rid}-p{p}", "name": ["Executive Summary", "Trends", "Detail", "Drillthrough", "Regional Breakdown", "Customer 360", "Product Mix", "Variance Analysis"][p % 8] + ("" if p < 8 else f" {p // 8 + 1}"), "visualContainers": vs})
            out_reports.append({"id": rid, "name": f"{dom} {['Executive Dashboard', 'Operational Report', 'Monthly Business Review', 'Self-Service Explorer'][r % 4]}" + ("" if ver == 0 else f" v{ver+1}"), "modelId": mid, "sections": secs})
    return out_models, out_reports

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8801)
    ap.add_argument("--dir", default="bigdata")
    ap.add_argument("--models", type=int, default=8)
    ap.add_argument("--tables", type=int, default=30)
    ap.add_argument("--measures", type=int, default=300)
    ap.add_argument("--reports", type=int, default=3)
    ap.add_argument("--pages", type=int, default=6)
    ap.add_argument("--visuals", type=int, default=10)
    a = ap.parse_args()
    folder = Path(a.dir).resolve(); folder.mkdir(exist_ok=True)
    models, reports = build(a.models, a.tables, a.measures, a.reports, a.pages, a.visuals)
    srcs = []
    for i, m in enumerate(models):
        s = folder / f"source{i}.json"
        s.write_text(json.dumps({"models": [m], "reports": [r for r in reports if r["modelId"] == m["id"]]}))
        srcs.append(str(s))
    project = ProjectService(folder / "brain.json")
    project.save_config({"version": 1, "name": "Contoso Enterprise BI", "sources": srcs, "database": "brain.lbug", "identity_map": "identity.json"})
    t = time.time()
    if not (folder / "brain.lbug").exists():
        with GraphRepository(folder / "brain.lbug") as repo:
            project.scan(repo)
    print("scan s", round(time.time() - t, 1), flush=True)
    app = create_app(database_path=folder / "brain.lbug", overrides_path=folder / "overrides.json")
    app.project = project
    app.static_dir = Path(__file__).resolve().parent / "dist"
    with make_server("127.0.0.1", a.port, app, handler_class=Quiet) as server:
        print("ready", flush=True)
        server.serve_forever()
main()
