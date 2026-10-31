// Gate build entry (step U1): renders the part specimen with no app and no shim, so that the
// kit gates can open one static file with inline CSS and an inline classic script.
import React from "../../../../frontend/node_modules/react/index.js";
import { createRoot } from "../../../../frontend/node_modules/react-dom/client.js";
import Specimen from "../../../../frontend/src/devcenter/specimen/Specimen.jsx";
import "../../../../frontend/src/theme.css";
import "../../../../frontend/src/app.css";
import "../../../../frontend/src/devcenter/devcenter.css";
import "../../../../frontend/src/devcenter/specimen/specimen.css";

createRoot(document.getElementById("root")).render(React.createElement(Specimen));
