// Apply the light theme before first paint to avoid a dark flash: a saved choice wins,
// otherwise the operating system's setting decides.
// Kept external because the desktop host's CSP forbids inline scripts.
try {
  var saved = null;
  try { saved = localStorage.getItem("pbibrain-theme"); } catch (error) { /* Storage can be unavailable. */ }
  var light = saved === "light" || (saved !== "dark" && window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches);
  if (light) {
    document.documentElement.classList.remove("dark");
    document.documentElement.dataset.theme = "light";
  }
} catch (error) { /* Without matchMedia the dark default stays. */ }
