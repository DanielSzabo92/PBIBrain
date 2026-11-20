// Root of the Development Center sidebar item (UI design 2, step U3).
// With no open session it shows the session list. With an open session it shows the work area.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { ToastProvider, useToast } from "@/components/ui/toast";
import { Skeleton } from "@/components/ui/result-panel";
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

export default function DevCenter({ onOpenProject, onProjectChanged, transport }) {
  const [store] = useState(devCenterStore);
  return (
    <DevCenterProvider store={store}>
      <ToastProvider>
        <DevCenterScreens onOpenProject={onOpenProject} onProjectChanged={onProjectChanged} transport={transport} />
      </ToastProvider>
    </DevCenterProvider>
  );
}

function DevCenterScreens({ onOpenProject, onProjectChanged, transport }) {
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
  const renameAction = useAction("session_rename");
  const deleteAction = useAction("session_delete");
  const duplicateAction = useAction("session_duplicate");

  const handleRename = async (id, newName) => {
    const trimmed = String(newName || "").trim();
    if (!trimmed) return;
    const reply = await renameAction.run({ session_id: id, display_name: trimmed });
    if (reply) {
      await store.load("sessions");
      if (session && session.session_id === id) {
        await store.load("session");
      }
    } else {
      toast.show({ tone: "err", text: "Could not rename session" });
    }
  };

  const handleDuplicate = async (id) => {
    const all = store.getState().resources?.sessions?.data?.sessions || [];
    const target = all.find((s) => s.session_id === id) || session;
    const baseName = target?.display_name || "Session";
    const duplicateName = `${baseName} (copy)`;
    const created = await duplicateAction.run({ session_id: id, display_name: duplicateName });
    if (created) {
      await store.load("sessions");
      if (created.session_id) {
        await openAction.run({ session_id: created.session_id });
        await store.load("session");
        setView("work");
      }
    } else {
      toast.show({ tone: "err", text: "Could not duplicate session" });
    }
  };

  const handleDelete = async (id) => {
    const reply = await deleteAction.run({ session_id: id });
    if (reply) {
      await store.load("sessions");
      if (session && session.session_id === id) {
        setView("list");
      }
    } else {
      toast.show({ tone: "err", text: "Could not delete session" });
    }
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

  // The first view: GET sessions tells if a session is open (its revision is null when none is), and only
  // then GET session reads it. Asking for the session with none open answers 409, which the browser logs.
  useEffect(() => {
    let active = true;
    store.load("sessions").then((list) => (list && !Number.isInteger(list.revision) ? null : store.load("session"))).then((data) => {
      if (active) setView((current) => current ?? (data ? "work" : "list"));
    });
    return () => {
      active = false;
    };
  }, [store]);

  // A session that closes (session_close, session_not_open) shows the list, except when CreateSession rolls back a failed draft.
  useEffect(() => {
    if (view === "work" && hadSession.current && !session && !reopening.current) setView("list");
    hadSession.current = Boolean(session);
  }, [session, view]);

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

  return (
    <div className="dc-root">
      {view === "list" ? (
        <SessionList
          banner={listBanner}
          onDismissBanner={() => listBanner && store.dismissNotice(listBanner.id)}
          onNew={() => setView("create")}
          onOpened={() => { if (listBanner) store.dismissNotice(listBanner.id); showWork(); }}
          onOpenProject={onOpenProject}
          onRenameSession={handleRename}
          onDuplicateSession={handleDuplicate}
          onDeleteSession={handleDelete}
        />
      ) : null}
      {view === "create" ? (
        <CreateSession
          transport={transport}
          onCancel={showList}
          onDone={() => { changeTabs({ tab: "compare", marks: false }); showWork(); }}
        />
      ) : null}
      {view === "work" ? (
        session ? (
          <WorkArea
            session={session}
            tabState={tabState}
            onTabs={changeTabs}
            onRetryLock={retryLock}
            onClose={closeSession}
            onShowList={showList}
            onRenameSession={handleRename}
            onDuplicateSession={handleDuplicate}
            onDeleteSession={handleDelete}
            onProjectChanged={onProjectChanged}
          />
        ) : (
          <SessionLoading />
        )
      ) : null}
    </div>
  );
}
