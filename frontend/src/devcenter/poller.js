// Poll rules (UI design section 10, "Refresh").
// GET session: every 5 s while a session is open, the window is visible, and no call runs; one poll on window focus.
// GET apply/progress: every 500 ms, only while apply, format_only_apply, or undo_apply runs.

export const SESSION_POLL_MS = 5000;
export const PROGRESS_POLL_MS = 500;
export const PROGRESS_METHODS = Object.freeze(["apply", "format_only_apply", "undo_apply"]);

export const systemClock = Object.freeze({
  now: () => Date.now(),
  setTimeout: (fn, ms) => globalThis.setTimeout(fn, ms),
  clearTimeout: (handle) => globalThis.clearTimeout(handle),
});

export function documentVisible() {
  const doc = globalThis.document;
  return !doc || doc.visibilityState !== "hidden";
}

// tick() can return a promise. The poller does not start a second tick while one runs.
export function createPoller({
  clock = systemClock,
  intervalMs = SESSION_POLL_MS,
  isActive = () => true,
  isVisible = documentVisible,
  isBusy = () => false,
  tick,
} = {}) {
  if (typeof tick !== "function") throw new TypeError("createPoller needs a tick function.");
  let timer = null;
  let started = false;
  let ticking = false;

  function canPoll() {
    return started && isActive() && !isBusy();
  }

  // The tick shows its own error. A failed poll does not stop the poll.
  function runTick() {
    if (ticking) return Promise.resolve(false);
    let result;
    try {
      result = tick();
    } catch {
      return Promise.resolve(true);
    }
    if (!result || typeof result.then !== "function") return Promise.resolve(true);
    ticking = true;
    return Promise.resolve(result)
      .catch(() => {})
      .then(() => {
        ticking = false;
        return true;
      });
  }

  function schedule() {
    if (timer !== null) clock.clearTimeout(timer);
    timer = started ? clock.setTimeout(fire, intervalMs) : null;
  }

  function fire() {
    timer = null;
    if (canPoll() && isVisible()) runTick();
    schedule();
  }

  return {
    start() {
      if (started) return;
      started = true;
      schedule();
    },
    stop() {
      started = false;
      if (timer !== null) clock.clearTimeout(timer);
      timer = null;
    },
    // One poll at once on window focus, then a full interval to the next poll.
    focus() {
      if (!canPoll()) return Promise.resolve(false);
      schedule();
      return runTick();
    },
    // A change from hidden to visible counts as a focus.
    visibilityChanged() {
      return isVisible() ? this.focus() : Promise.resolve(false);
    },
    isRunning: () => started,
  };
}
