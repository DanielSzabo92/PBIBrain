// Work area frame of an open session (UI design 4.2): header, banner stack, and the six tabs.
import React, { useEffect } from "react";
import { LoaderCircle, MoreHorizontal, RefreshCw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Banner } from "@/components/ui/notice";
import { Menu } from "@/components/ui/menu";
import { EmptyState } from "@/components/ui/result-panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { errorCopy, longCallText, t, tn } from "../copy.js";
import { useAction, useDevCenterState, useResource } from "../useDevCenter.js";
import SourcesTab from "./SourcesTab.jsx";
import CompareGrid from "../components/CompareGrid.jsx";
import { agentCount, banners, planStatus, targetLine } from "./sessionModel.js";

export const TABS = ["compare", "impact", "plan", "agent", "sources", "log"];
export const LOCKED_REASON_ID = "dc-locked-reason";
export const BUSY_REASON_ID = "dc-busy-reason";

// sources_check runs automatically once on each open of a session (UI design 4.2).
const checkedOnOpen = new Set();

export default function WorkArea({ session, tabState, onTabs, onRetryLock, onClose }) {
  const toast = useToast();
  const busy = useDevCenterState((state) => state.busy);
  const running = useDevCenterState((state) => state.running);
  const plan = useResource("plan");
  const check = useAction("sources_check");
  const readOnly = Boolean(session.read_only);
  const longBusy = busy === "long";
  const changeDisabled = readOnly || longBusy;
  const reasonId = readOnly ? LOCKED_REASON_ID : longBusy ? BUSY_REASON_ID : undefined;
  const status = planStatus(session.plan_status, plan.data, plan.status === "loading" && !plan.data);
  const agent = agentCount(session);
  const blocking = status.blocking ?? 0;
  const stack = banners(session).filter((banner) => !(banner.id === "missing" && tabState.tab === "sources"));
  const busyText = longBusy && running ? longCallText(running) : null;

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

  const bannerActions = {
    locked: <Button variant="outline" size="sm" onClick={onRetryLock} disabled={longBusy}>{t("shared.locked.action")}</Button>,
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
        <div className="dc-work-actions">
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
            groups={[{ items: [{ label: t("work.more.close"), icon: X, onSelect: onClose, disabled: longBusy }] }]}
          />
        </div>
      </header>
      {busyText ? <p id={BUSY_REASON_ID} className="dc-busy-line" role="status"><LoaderCircle className="spin" aria-hidden="true" />{busyText}</p> : null}
      {check.error ? <Banner tone="bad">{errorCopy(check.error).body}</Banner> : null}
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
          {TABS.map((tab) => (
            <TabsTrigger
              key={tab}
              value={tab}
              count={tab === "plan" && blocking > 0 ? blocking : tab === "agent" && agent > 0 ? agent : undefined}
              countTone={tab === "plan" ? "bad" : "info"}
              countLabel={tab === "plan" ? t("work.tab.count.plan") : tab === "agent" ? t("work.tab.count.agent") : undefined}>
              {t(`work.tab.${tab}`)}
            </TabsTrigger>
          ))}
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
            ) : (
              <LaterTab tab={tab} marks={tab === "compare" && tabState.marks} />
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

// The tabs that later U-steps build (U4 to U10). The frame shows the tab and its filter state.
function LaterTab({ tab, marks }) {
  return (
    <EmptyState headingLevel={2} title={t("work.tab.later.title")}>
      {t("work.tab.later.body", { tab: t(`work.tab.${tab}`) })}
      {marks ? ` ${t("work.compare.marks")}` : ""}
    </EmptyState>
  );
}
