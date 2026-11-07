---
title: "Documentation PDF is drawn by a small built-in writer with the standard fonts, from one scoped content model shared with the Markdown export"
author: Claude
date: 2026-11-07
branch: claude/sharp-franklin-uyn9fo
cost: { minutes: 18, tokens: 254773 }
id: l-64fa6af1
scope: repo
status: active
src: agent
touches:
  - backend/pdf_writer.py
  - backend/documentation_pdf.py
  - backend/api/app.py
  - tests/test_documentation_pdf.py
  - backend/cli/main.py
---

## Decided
- PDF export (issue #15) uses our own small PDF writer, not reportlab or WebView2 print-to-PDF. No new dependency keeps the Windows package self-contained, and we control every byte: no random /ID, fixed zlib level, sorted content, so the same scan and scope give the same file except the generated_at timestamp (CreationDate, footer, title page).
- One content model (Block list from build_document) feeds both renderers: PDF (TOC with link annotations, outlines, page numbers, box diagrams) and scoped Markdown (diagrams as Mermaid). The old `export-markdown` / render_markdown stays unchanged for the CLI and its tests.
- The app export goes through the running server (POST /api/documentation-export, reply JSON with content_base64), so it works while the app is open; the desktop window already has ALLOW_DOWNLOADS, so a blob download saves the file. Everything chosen in the UI is sent as null, meaning "all", so a later scan's new objects are included.
- The lineage summary diagram is Sources › Models › Reports at model level (a source links to the model whose query reads it). It does not flow through shared expressions to tables, so it does not repeat the ruled-out Lineage-lane problem.

## Watch out
- The standard PDF fonts are WinAnsi only. Hungarian ő/ű map to ö/ü, other unsupported letters to their NFKD base or '?'. The Markdown keeps exact text; the PDF title page says so.
- The TOC page count is computed before layout from the heading count; the capacity formula and the drawing loop must use the same start y (_TOC_START/_TOC_NEXT), or a blank page appears.

In the code: backend/pdf_writer.py, backend/documentation_pdf.py (build_document, render_pdf, render_document_markdown, export_documentation), backend/api/app.py (documentation-export), backend/cli/main.py (export-docs), frontend/src/components/DocumentationExport.jsx, frontend/src/documentationExport.js, tests/test_documentation_pdf.py.
