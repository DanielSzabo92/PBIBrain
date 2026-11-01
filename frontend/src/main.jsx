import React, { lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import GuardReview from "./components/GuardReview.jsx";
import "./theme.css";
import "./app.css";
import "./devcenter/devcenter.css";

// The part specimen is a test page. It shows only when the fake server shim is on the page
// (DEVCENTER_FAKE=1), because only the fake server sends the method lists of the shim.
const Specimen = lazy(() => import("./devcenter/specimen/index.js"));
const specimen = window.location.pathname === "/__specimen__" && Boolean(window.__DEVCENTER_FAKE_METHODS__);

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {specimen ? <Suspense fallback={null}><Specimen /></Suspense> : window.location.pathname === "/guard" ? <GuardReview /> : <App />}
  </React.StrictMode>,
);
