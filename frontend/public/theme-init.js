// Apply a saved light theme before first paint to avoid a dark flash.
// Kept external because the desktop host's CSP forbids inline scripts.
try {
  if (localStorage.getItem("pbibrain-theme") === "light") {
    document.documentElement.classList.remove("dark");
    document.documentElement.dataset.theme = "light";
  }
} catch (error) { /* Storage can be unavailable. */ }
