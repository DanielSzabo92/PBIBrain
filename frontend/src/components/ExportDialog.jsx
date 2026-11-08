import React, { lazy, Suspense, useState } from "react";
import { FileCode, FileDown } from "lucide-react";
import { Dialog, DialogContent } from "./ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";

const DocumentationExport = lazy(() => import("./DocumentationExport"));
const ModelSummary = lazy(() => import("./ModelSummary"));

export default function ExportDialog({
  open,
  onOpenChange,
  defaultTab = "documentation",
  overview,
  transport,
  scanning,
}) {
  const [tab, setTab] = useState(defaultTab);

  // Sync tab when defaultTab changes on open
  React.useEffect(() => {
    if (open) setTab(defaultTab);
  }, [open, defaultTab]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Export"
        description="Export project documentation or extract model context and formulas for AI tools."
        className="export-dialog"
      >
        <Tabs value={tab} onValueChange={setTab} className="export-tabs">
          <TabsList aria-label="Export options">
            <TabsTrigger value="documentation">
              <FileDown className="size-4" aria-hidden="true" />
              Documentation export
            </TabsTrigger>
            <TabsTrigger value="summary">
              <FileCode className="size-4" aria-hidden="true" />
              Model summary / agent context
            </TabsTrigger>
          </TabsList>
          <TabsContent value="documentation" className="export-tab-content">
            <Suspense fallback={<div className="view-loading">Loading documentation…</div>}>
              <DocumentationExport overview={overview} transport={transport} scanning={scanning} />
            </Suspense>
          </TabsContent>
          <TabsContent value="summary" className="export-tab-content">
            <Suspense fallback={<div className="view-loading">Loading summary…</div>}>
              <ModelSummary overview={overview} transport={transport} scanning={scanning} />
            </Suspense>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
