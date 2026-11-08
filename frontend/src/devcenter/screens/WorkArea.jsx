// Work area frame of an open session (UI design 4.2): header, banner stack, and the six tabs.
import React, { useEffect, useState } from "react";
import { Copy, Edit3, FolderGit2, LoaderCircle, MoreHorizontal, RefreshCw, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Banner } from "@/components/ui/notice";
import { Menu } from "@/components/ui/menu";
import { EmptyState } from "@/components/ui/result-panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { errorCopy, longCallText, t, tn } from "../copy.js";
import { useAction, useDevCenterState, useResource } from "../useDevCenter.js";
import SourcesTab from "./SourcesTab.jsx";
import PlanTab from "./plan/PlanTab.jsx";
import ImpactTab from "./impact/ImpactTab.jsx";
import AgentTab from "./agent/AgentTab.jsx";
import LogTab from "./log/LogTab.jsx";
import CompareGrid from "../components/CompareGrid.jsx";
import { agentCount, banners, deriveReadiness, planStatus, targetLine } from "./sessionModel.js";

export const TABS = ["compare", "impact", "plan", "agent", "sources", "log"];
export const LOCKED_REASON_ID = "dc-locked-reason";
export const BUSY_REASON_ID = "dc-busy-reason";

// sources_check runs automatically once on each open of a session (UI design 4.2).
const checkedOnOpen = new Set();

export default function WorkArea({ session, tabState, onTabs, onRetryLock, onClose, onShowList, onRenameSession, onDuplicateSession, onDeleteSession }) {
  const toast = useToast();
  const busy = useDevCenterState((state) => state.busy);
  const running = useDevCenterState((state) => state.running);
  const plan = useResource("plan");
  const check = useAction("sources_check");
  const readOnly = Boolean(session.read_only);
  const longBusy = busy === "long";
  const changeDisabled = readOnly || longBusy;
  const reasonId = readOnly ? LOCKED_REASON_ID : longBusy ? BUSY_REASON_ID : undefined;
  const status = deriveReadiness({
    session,
    plan,
    checking: (plan.status === "loading" && !plan.data) || session.plan_state === "checking",
  });
  const agent = agentCount(session);
  const blocking = status.blockingCount ?? status.blocking ?? 0;
  const stack = banners(session).filter((banner) => !(banner.id === "missing" && tabState.tab === "sources"));
  const busyText = longBusy && running ? longCallText(running) : null;
  // Step U10: after an apply, undo, or format with the target open in Power BI Desktop.
  const [desktopBanner, setDesktopBanner] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [renameDraft, setRenameDraft] = useState(session.display_name || "");

  useEffect(() => {
    setRenameDraft(session.display_name || "");
  }, [session.display_name]);

  const handleSaveRename = () => {
    const trimmed = renameDraft.trim();
    if (!trimmed) return;
    setRenameOpen(false);
    onRenameSession?.(session.session_id, trimmed);
    toast.show({ tone: "ok", text: "Session renamed" });
  };

  const handleDuplicate = async () => {
    await onDuplicateSession?.(session.session_id);
    toast.show({ tone: "ok", text: "Session duplicated" });
  };

  const handleDelete = async () => {
    setDeleteOpen(false);
    await onDeleteSession?.(session.session_id);
    toast.show({ tone: "ok", text: "Session deleted" });
  };

  const moreItems = [
    ...(onShowList ? [{ label: t("work.more.sessions"), icon: FolderGit2, onSelect: onShowList }] : []),
    { label: t("work.more.rename"), icon: Edit3, onSelect: () => setRenameOpen(true), disabled: changeDisabled },
    { label: t("work.more.duplicate"), icon: Copy, onSelect: handleDuplicate, disabled: longBusy },
    { label: t("work.more.close"), icon: X, onSelect: onClose, disabled: longBusy },
    { label: t("work.more.delete"), icon: Trash2, onSelect: () => setDeleteOpen(true), disabled: changeDisabled },
  ];

  useEffect(() => {
    if (readOnly || checkedOnOpen.has(session.session_id)) return;
    checkedOnOpen.add(session.session_id);
    check.run({});
    // Only a new session ID starts the check.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.session_id]);

  const checkSources = async () => {
    const reply = await check.run({});
    if (reply) toast.show({ tone: reply.mark_count > 0 ? "warn" : "ok", text: reply.mark_count > 0 ? tn("work.check_sources.marks", reply.mark_count) : t("work.check_sources.same") });
  };

  const sessionPath = session.path || (session.session_id ? `.pbibrain/sessions/${session.session_id}/session.json` : "");

  const handleCopyPath = () => {
    if (sessionPath && navigator.clipboard) {
      navigator.clipboard.writeText(sessionPath);
      toast.show({ tone: "ok", text: "Session path copied" });
    }
  };

  const bannerActions = {
    locked: (
      <div className="dc-banner-actions-group flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={onRetryLock} disabled={longBusy}>{t("shared.locked.action")}</Button>
        {sessionPath ? (
          <Button variant="outline" size="sm" onClick={handleCopyPath} title="Copy session path">
            <Copy className="size-3.5" aria-hidden="true" />
            <span>Copy path</span>
          </Button>
        ) : null}
        <Button variant="outline" size="sm" onClick={() => setDeleteOpen(true)} title="Delete session">
          <Trash2 className="size-3.5" aria-hidden="true" />
          <span>Delete session</span>
        </Button>
      </div>
    ),
    missing: <Button variant="outline" size="sm" onClick={() => onTabs({ tab: "sources" })}>{t("work.banner.missing.action")}</Button>,
    changed: <Button variant="outline" size="sm" onClick={() => onTabs({ tab: "compare", marks: true })}>{t("work.banner.changed.action")}</Button>,
  };

  return (
    <div className="dc-work">
      <header className="dc-work-head">
        <div className="dc-work-title">
          <h1 className="dc-title">{session.display_name}</h1>
          <p className="dc-subtitle">{targetLine(session)}</p>
        </div>
        <div className="dc-work-actions" data-ui-actions="">
          <Button variant={status.tone === "plain" ? "outline" : "status"} tone={status.tone === "plain" ? undefined : status.tone} aria-label={`${status.text}. ${t("work.plan.open")}`} onClick={() => onTabs({ tab: "plan" })}>
            {status.checking ? <LoaderCircle className="spin" aria-hidden="true" /> : null}
            {status.text}
          </Button>
          <Button variant="outline" onClick={checkSources} loading={check.pending} loadingText={t("work.check_sources.loading")} disabled={changeDisabled && !check.pending} aria-describedby={check.pending ? undefined : reasonId}>
            <RefreshCw aria-hidden="true" />{t("work.check_sources")}
          </Button>
          <Menu
            align="end"
            label={t("work.more")}
            trigger={<Button variant="outline" size="icon" aria-label={t("work.more")}><MoreHorizontal /></Button>}
            groups={[{ items: moreItems }]}
          />
        </div>
      </header>
      {busyText ? <p id={BUSY_REASON_ID} className="dc-busy-line" role="status"><LoaderCircle className="spin" aria-hidden="true" />{busyText}</p> : null}
      {check.error ? <Banner tone="bad">{errorCopy(check.error).body}</Banner> : null}
      {desktopBanner ? (
        <Banner tone="info" data-banner="desktop" actions={<Button variant="outline" size="sm" onClick={() => setDesktopBanner(false)}>{t("work.banner.desktop.action")}</Button>}>
          {t("work.banner.desktop")}
        </Banner>
      ) : null}
      {stack.length > 0 ? (
        <div className="dc-banners">
          {stack.map((banner) => (
            <Banner key={banner.id} tone={banner.tone} data-banner={banner.id} actions={bannerActions[banner.id]}>
              <span id={banner.id === "locked" ? LOCKED_REASON_ID : undefined}>{banner.text}</span>
            </Banner>
          ))}
        </div>
      ) : null}
      <Tabs value={tabState.tab} onValueChange={(tab) => onTabs({ tab })} className="dc-tabs" activationMode="automatic">
        <TabsList aria-label={t("work.tabs")} className="dc-tab-row">
          {TABS.map((tab) => {
            let count;
            let countTone = "info";
            let countLabel;

            if (tab === "sources" && status.missingSourcesCount > 0) {
              count = status.missingSourcesCount;
              countTone = "bad";
              countLabel = tn("work.plan.missing", status.missingSourcesCount);
            } else if (tab === "compare" && status.unconfirmedCount > 0) {
              count = status.unconfirmedCount;
              countTone = "warn";
              countLabel = tn("work.plan.unconfirmed", status.unconfirmedCount);
            } else if (tab === "impact" && status.blockingImpactCount > 0) {
              count = status.blockingImpactCount;
              countTone = "bad";
              countLabel = t("work.tab.count.impact");
            } else if (tab === "plan" && blocking > 0) {
              count = blocking;
              countTone = "bad";
              countLabel = t("work.tab.count.plan");
            } else if (tab === "agent" && agent > 0) {
              count = agent;
              countTone = "info";
              countLabel = t("work.tab.count.agent");
            }

            return (
              <TabsTrigger
                key={tab}
                value={tab}
                count={count}
                countTone={countTone}
                countLabel={countLabel}>
                {t(`work.tab.${tab}`)}
              </TabsTrigger>
            );
          })}
        </TabsList>
        {TABS.map((tab) => (
          <TabsContent key={tab} value={tab} className="dc-tab-panel">
            {tab === "sources" ? (
              <SourcesTab session={session} changeDisabled={changeDisabled} reasonId={reasonId} />
            ) : tab === "compare" ? (
              <CompareGrid
                session={session}
                tabState={tabState}
                onTabs={onTabs}
                changeDisabled={changeDisabled}
                reasonId={reasonId}
              />
            ) : tab === "impact" ? (
              <ImpactTab session={session} tabState={tabState} onTabs={onTabs} changeDisabled={changeDisabled} reasonId={reasonId} />
            ) : tab === "plan" ? (
              <PlanTab
                session={session}
                changeDisabled={changeDisabled}
                reasonId={reasonId}
                onTabs={onTabs}
                onDesktopBanner={() => setDesktopBanner(true)}
              />
            ) : tab === "agent" ? (
              <AgentTab session={session} changeDisabled={changeDisabled} reasonId={reasonId} onTabs={onTabs} />
            ) : tab === "log" ? (
              <LogTab onTabs={onTabs} />
            ) : (
              <LaterTab
                tab={tab}
                marks={tab === "compare" && tabState.marks}
                impactRowKey={tab === "impact" ? tabState.impactRowKey : null}
                impactItemId={tab === "impact" ? tabState.impactItemId : null}
              />
            )}
          </TabsContent>
        ))}
      </Tabs>
      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent
          title={t("work.rename.title")}
          footer={
            <>
              <Button variant="outline" onClick={() => setRenameOpen(false)}>
                {t("shared.cancel") || "Cancel"}
              </Button>
              <Button onClick={handleSaveRename} disabled={!renameDraft.trim()}>
                {t("work.rename.save")}
              </Button>
            </>
          }
        >
          <label className="dc-field">
            <span>{t("work.rename.label")}</span>
            <Input
              value={renameDraft}
              onChange={(e) => setRenameDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSaveRename(); }}
              autoFocus
            />
          </label>
        </DialogContent>
      </Dialog>
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent
          title={t("work.delete.title")}
          description={t("work.delete.description")}
          footer={
            <>
              <AlertDialogCancel asChild>
                <Button variant="outline">{t("shared.cancel") || "Cancel"}</Button>
              </AlertDialogCancel>
              <AlertDialogAction asChild>
                <Button variant="destructive" onClick={handleDelete}>
                  <Trash2 aria-hidden="true" />
                  {t("work.delete.confirm")}
                </Button>
              </AlertDialogAction>
            </>
          }
        />
      </AlertDialog>
    </div>
  );
}

// The tabs that later U-steps build (U4 to U10). The frame shows the tab and its filter state.
function LaterTab({ tab, marks, impactRowKey, impactItemId }) {
  return (
    <div data-impact-row={impactRowKey || undefined} data-impact-item={impactItemId || undefined}>
      <EmptyState headingLevel={2} title={t("work.tab.later.title")}>
        {t("work.tab.later.body", { tab: t(`work.tab.${tab}`) })}
        {marks ? ` ${t("work.compare.marks")}` : ""}
        {impactRowKey ? ` Impact target: ${impactRowKey}.` : ""}
      </EmptyState>
    </div>
  );
}
