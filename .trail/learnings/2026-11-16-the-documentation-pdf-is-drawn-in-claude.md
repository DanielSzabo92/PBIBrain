---
title: "The documentation PDF is drawn in the workbench with pdfcn on Takumi, from content blocks the server sends as JSON"
author: Claude
date: 2026-11-16
branch: claude/nice-pasteur-ppkrv8
cost: { minutes: 14, tokens: 127653 }
id: l-942c9d89
scope: repo
status: active
src: agent
touches:
  - README.md
  - backend/documentation_pdf.py
  - backend/pdf_writer.py
  - backend/projects.py
  - frontend/src/desktop.js
  - frontend/src/devcenter/copy.js
  - frontend/src/devcenter/screens/DevCenter.jsx
  - frontend/src/devcenter/screens/SessionList.jsx
  - frontend/src/transport.js
  - frontend/test/chat.test.js
---

## Decided
- The owner chose pdfcn (shadcn registry, Takumi base) for the documentation PDF. The server still builds the content (build_document); format "document" returns its blocks as JSON, and the workbench lays them out with pdfcn components and renders with takumi-pdf (WebAssembly) in the page. The renderer is a lazy chunk, loaded only on export.
- The model diagram was removed from the export (owner: "horrible, remove it for now"). The lineage diagram stays as Mermaid in Markdown and becomes a "A › B" list in the PDF.
- Fonts are the app's bundled @fontsource Inter and JetBrains Mono woff2 (latin + latin-ext with unicodeRange), so the desktop app exports offline. uncoveredText "placeholder" prints a box for letters they lack instead of failing.

## Watch out
- takumi-pdf uses top-level await: the Vite build target is es2022.
- pdfcn components do not import React: Vite uses the automatic JSX runtime (esbuild jsx "automatic"); the classic runtime fails with "React is not defined" only when the export runs.
- Takumi trims spaces at the edges of text runs: PageNumber's format uses no-break spaces, or the footer reads "Page1of5". PageNumber's container is width 100%, so it sits in a fixed-width box beside the footer title.
- PdfList items are { text } objects, not strings (strings print empty bullets).
- The CLI `export-docs --format pdf` still uses the old built-in Python PDF writer (backend/pdf_writer.py): there is no browser in the CLI or the packaged agent.
- The screen type-scale lint skips the pdf folders: the PDF sets print sizes in points.

In the code: frontend/src/pdf/documentationPdf.jsx, frontend/src/components/pdf/ and frontend/src/lib/pdf-* (installed with `npx shadcn@latest add @pdfcn/takumi/<name>`, registry in components.json), frontend/src/components/DocumentationExport.jsx, frontend/vite.config.js, backend/documentation_pdf.py (document_payload, FORMATS), backend/api/app.py documentation-export, frontend/e2e/documentationExport.spec.js.
