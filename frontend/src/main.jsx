import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import GuardReview from "./components/GuardReview.jsx";
import "./theme.css";
import "./app.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {window.location.pathname === "/guard" ? <GuardReview /> : <App />}
  </React.StrictMode>,
);
