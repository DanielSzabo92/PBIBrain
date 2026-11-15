// Root of the Development Center sidebar item (UI design 2, step U3).
// With no open session it shows the session list. With an open session it shows the work area.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { ChevronRight } from "lucide-react";
import { ToastProvider, useToast } from "@/components/ui/toast";
import { Skeleton } from "@/components/ui/result-panel";
import { Breadcrumb, BreadcrumbList, BreadcrumbItem, BreadcrumbLink, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb";
import { t } from "../copy.js";
import { createDevCenterHttp } from "../httpClient.js";
import { createDevCenterStore } from "../store.js";
import { DevCenterProvider, useAction, useDevCenterState, useDevCenterStore } from "../useDevCenter.js";
import { shared } from "../sharedStore.js";
import SessionList from "./SessionList.jsx";
import CreateSession from "./CreateSession.jsx";
import WorkArea from "./WorkArea.jsx";
import "./screens.css";


// One store for the app window. The open session stays open while the user goes to other sidebar items.
export function devCenterStore() {
  if (!shared.store) shared.store = createDevCenterStore({ http: createDevCenterHttp(), api: () => globalThis.pywebview?.api ?? null });
  return shared.store;
}

// The last tab and the marks filter of each session, in memory only (UI design 2).
const tabMemory = new Map();

/** The session skeleton; after five seconds it says why it may be slow instead of staying silent. */
function SessionLoading() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), 5000);
    return () => clearTimeout(timer);
  }, []);
  return <div className="dc-page">
    <Skeleton label={t("work.loading")} />
    {slow ? <p className="dc-loading-slow" role="status">{t("work.loading.slow")}</p> : null}
  </div>;
}

export default function DevCenter({ onOpenProject }) {
  const [store] = useState(devCenterStore);
  return (
    <DevCenterProvider store={store}>
      <ToastProvider>
        <DevCenterScreens onOpenProject={onOpenProject} />
      </ToastProvider>
    </DevCenterProvider>
  );
}

function DevCenterScreens({ onOpenProject }) {
  const store = useDevCenterStore();
  const session = useDevCenterState((state) => state.session);
  const notices = useDevCenterState((state) => state.notices);
  const toast = useToast();
  const [view, setView] = useState(() => (store.getState().session ? "work" : null));
  const [tabState, setTabState] = useState(() => tabMemory.get(store.getState().session?.session_id) ?? { tab: "compare", marks: false });
  const hadSession = useRef(Boolean(session));
  const reopening = useRef(false);
  const sessionId = session?.session_id ?? null;
  const closeAction = useAction("session_close");
  const openAction = useAction("session_open");

  const [sessionOverrides, setSessionOverrides] = useState(() => {
    try {
      const saved = localStorage.getItem("pbibrain_session_overrides");
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  });

  const [deletedSessions, setDeletedSessions] = useState(() => {
    try {
      const saved = localStorage.getItem("pbibrain_deleted_sessions");
      return saved ? new Set(JSON.parse(saved)) : new Set();
    } catch {
      return new Set();
    }
  });

  const handleRename = (id, newName) => {
    setSessionOverrides((prev) => {
      const next = { ...prev, [id]: { ...(prev[id] || {}), display_name: newName } };
      try { localStorage.setItem("pbibrain_session_overrides", JSON.stringify(next)); } catch {}
      return next;
    });
    if (session && session.session_id === id) {
      session.display_name = newName;
    }
  };

  const handleDuplicate = async (id) => {
    const all = store.getState().resources?.sessions?.data?.sessions || [];
    const target = all.find((s) => s.session_id === id) || session;
    const baseName = sessionOverrides[id]?.display_name || target?.display_name || "Session";
    const duplicateName = `${baseName} (copy)`;
    try {
      const created = await store.run("session_create", { display_name: duplicateName });
      if (created) {
        await store.load("sessions");
        await store.load("session");
        setView("work");
      }
    } catch (err) {
      toast.show({ tone: "warn", text: err.message || "Could not duplicate session" });
    }
  };

  const handleDelete = async (id) => {
    setDeletedSessions((prev) => {
      const next = new Set([...prev, id]);
      try { localStorage.setItem("pbibrain_deleted_sessions", JSON.stringify([...next])); } catch {}
      return next;
    });
    if (session && session.session_id === id) {
      await closeAction.run({});
    }
    await store.load("sessions");
    setView("list");
  };

  const closeSession = () => closeAction.run({});

  // "Try again" on the locked banner: open the session again, so that PBIBrain asks for the lock again.
  const retryLock = async () => {
    const id = store.getState().session?.session_id;
    if (!id) return;
    reopening.current = true;
    try {
      if (await closeAction.run({})) {
        if (await openAction.run({ session_id: id })) await store.load("session");
      }
    } finally {
      reopening.current = false;
      setView(store.getState().session ? "work" : "list");
    }
  };

  // The first view: GET session tells if a session is open. session_not_open gives the list.
  useEffect(() => {
    let active = true;
    store.load("session").then((data) => {
      if (active) setView((current) => current ?? (data ? "work" : "list"));
    });
    return () => {
      active = false;
    };
  }, [store]);

  // A session that closes (session_close, session_not_open) shows the list.
  useEffect(() => {
    if (hadSession.current && !session && !reopening.current) setView("list");
    hadSession.current = Boolean(session);
  }, [session]);

  useEffect(() => {
    setTabState(tabMemory.get(sessionId) ?? { tab: "compare", marks: false });
  }, [sessionId]);

  // Read the session ID at call time: the create flow calls this after its session opened.
  const changeTabs = useCallback((patch) => {
    setTabState((current) => {
      const next = { ...current, ...patch };
      const id = store.getState().session?.session_id;
      if (id) tabMemory.set(id, next);
      return next;
    });
  }, [store]);

  // Toasts and moves from the store: stale_revision gives shared.stale; source_changed opens Compare with the marks filter.
  useEffect(() => {
    for (const notice of notices) {
      if (notice.kind === "toast") {
        toast.show({ tone: notice.code === "stale_revision" ? "warn" : "ok", text: t(notice.key) });
        store.dismissNotice(notice.id);
      } else if (notice.kind === "navigate") {
        changeTabs({ tab: notice.tab, marks: Boolean(notice.filters?.marks) });
        store.dismissNotice(notice.id);
      }
    }
  }, [notices, store, toast, changeTabs]);

  const listBanner = notices.find((notice) => notice.kind === "banner" && notice.place === "list") ?? null;
  const showList = () => setView("list");
  const showWork = () => setView("work");

  if (view === null) return <SessionLoading />;

  const activeSession = session ? (sessionOverrides[sessionId] ? { ...session, ...sessionOverrides[sessionId] } : session) : null;

  const crumbs = [{ label: t("list.breadcrumb"), onClick: view === "list" ? null : showList }];
  if (view === "work" && activeSession) {
    crumbs.push({ label: activeSession.display_name, onClick: null });
    crumbs.push({ label: t(`work.tab.${tabState.tab}`), onClick: null });
  } else if (view === "create") {
    crumbs.push({ label: t("create.title"), onClick: null });
  }

  return (
    <div className="dc-root">
      {/* With one part the path only repeats the view title above it. */}
      <Breadcrumb className={crumbs.length > 1 ? "dc-breadcrumb" : "dc-breadcrumb sr-only"} aria-label={t("work.breadcrumb")}>
        <BreadcrumbList>
          {crumbs.map((crumb, index) => (
            <React.Fragment key={crumb.label + index}>
              {index > 0 ? <BreadcrumbSeparator /> : null}
              <BreadcrumbItem>
                {crumb.onClick ? (
                  <BreadcrumbLink asChild>
                    <button type="button" className="dc-link" onClick={crumb.onClick}>{crumb.label}</button>
                  </BreadcrumbLink>
                ) : (
                  <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                )}
              </BreadcrumbItem>
            </React.Fragment>
          ))}
        </BreadcrumbList>
      </Breadcrumb>
      {view === "list" ? (
        <SessionList
          banner={listBanner}
          onDismissBanner={() => listBanner && store.dismissNotice(listBanner.id)}
          onNew={() => setView("create")}
          onOpened={() => { if (listBanner) store.dismissNotice(listBanner.id); showWork(); }}
          onOpenProject={onOpenProject}
          sessionOverrides={sessionOverrides}
          deletedSessions={deletedSessions}
          onRenameSession={handleRename}
          onDuplicateSession={handleDuplicate}
          onDeleteSession={handleDelete}
        />
      ) : null}
      {view === "create" ? (
        <CreateSession
          onCancel={showList}
          onDone={() => { changeTabs({ tab: "compare", marks: false }); showWork(); }}
          onOpenPartial={() => { changeTabs({ tab: "sources", marks: false }); showWork(); }}
        />
      ) : null}
      {view === "work" ? (
        activeSession ? (
          <WorkArea
            session={activeSession}
            tabState={tabState}
            onTabs={changeTabs}
            onRetryLock={retryLock}
            onClose={closeSession}
            onShowList={showList}
            onRenameSession={handleRename}
            onDuplicateSession={handleDuplicate}
            onDeleteSession={handleDelete}
          />
        ) : (
          <SessionLoading />
        )
      ) : null}
    </div>
  );
}
