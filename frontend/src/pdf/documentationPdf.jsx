// The documentation PDF, drawn in the workbench with pdfcn components on Takumi (takumi-pdf, WebAssembly).
// The server builds the content (POST /api/documentation-export with format "document"); this file only lays
// it out. Everything runs locally: the fonts are the app's own bundled Inter and JetBrains Mono, so the
// desktop app needs no network to export.
import { render } from "takumi-pdf";
import interLatin from "@fontsource-variable/inter/files/inter-latin-wght-normal.woff2?url";
import interLatinExt from "@fontsource-variable/inter/files/inter-latin-ext-wght-normal.woff2?url";
import monoLatin from "@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2?url";
import monoLatinExt from "@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-ext-wght-normal.woff2?url";

import { PdfcnThemeProvider } from "@/components/pdf/theme-provider";
import { Heading } from "@/components/pdf/heading/heading";
import { Text } from "@/components/pdf/text/text";
import { DataTable } from "@/components/pdf/data-table/data-table";
import { PdfList } from "@/components/pdf/list/list";
import { Divider } from "@/components/pdf/divider/divider";
import { PageNumber } from "@/components/pdf/page-number/page-number";
import { View } from "@/lib/pdf-primitives";
import { professionalTheme } from "@/lib/pdf-themes/professional";

const SANS = "Inter";
const MONO = "JetBrains Mono";

// Unicode ranges of the two @fontsource subsets (latin, latin-ext), so Hungarian ő/ű and the like print.
const LATIN = [[0x0000, 0x00ff], [0x0131, 0x0131], [0x0152, 0x0153], [0x02bb, 0x02bc], [0x02c6, 0x02c6], [0x02da, 0x02da],
  [0x02dc, 0x02dc], [0x0304, 0x0304], [0x0308, 0x0308], [0x0329, 0x0329], [0x2000, 0x206f], [0x20ac, 0x20ac],
  [0x2122, 0x2122], [0x2191, 0x2191], [0x2193, 0x2193], [0x2212, 0x2212], [0x2215, 0x2215], [0xfeff, 0xfeff], [0xfffd, 0xfffd]];
const LATIN_EXT = [[0x0100, 0x02ba], [0x02bd, 0x02c5], [0x02c7, 0x02cc], [0x02ce, 0x02d7], [0x02dd, 0x02ff], [0x1d00, 0x1dbf],
  [0x1e00, 0x1e9f], [0x1ef2, 0x1eff], [0x2020, 0x2020], [0x20a0, 0x20ab], [0x20ad, 0x20c0], [0x2113, 0x2113],
  [0x2c60, 0x2c7f], [0xa720, 0xa7ff]];

/** pdfcn's professional theme with the app's fonts and a denser scale for reference documentation. */
export const DOCUMENT_THEME = {
  ...professionalTheme,
  name: "pbibrain-documentation",
  colors: { ...professionalTheme.colors, accent: "#2563eb" },
  spacing: { ...professionalTheme.spacing, componentGap: 10, paragraphGap: 6, sectionGap: 18 },
  typography: {
    body: { fontFamily: SANS, fontSize: 9, lineHeight: 1.45 },
    heading: {
      fontFamily: SANS,
      fontSize: { h1: 20, h2: 14, h3: 11.5, h4: 10, h5: 9.5, h6: 9 },
      fontWeight: 700,
      lineHeight: 1.25,
    },
  },
};

/** The fonts the PDF embeds, fetched from the app's own bundle (no network). */
export async function loadDocumentFonts(fetcher = globalThis.fetch) {
  const bytes = async (url) => new Uint8Array(await (await fetcher(url)).arrayBuffer());
  const [sans, sansExt, mono, monoExt] = await Promise.all([interLatin, interLatinExt, monoLatin, monoLatinExt].map(bytes));
  return [
    { name: SANS, data: sans, unicodeRange: LATIN },
    { name: SANS, data: sansExt, unicodeRange: LATIN_EXT },
    { name: MONO, data: mono, unicodeRange: LATIN, generic: "monospace" },
    { name: MONO, data: monoExt, unicodeRange: LATIN_EXT, generic: "monospace" },
  ];
}

function TableBlock({ block }) {
  const total = (block.widths || []).reduce((sum, value) => sum + value, 0);
  const columns = block.headers.map((header, index) => ({
    key: `c${index}`,
    header,
    width: total ? `${((block.widths[index] / total) * 100).toFixed(2)}%` : undefined,
  }));
  const data = block.rows.map((row) => Object.fromEntries(row.map((cell, index) => [`c${index}`, cell])));
  return <DataTable columns={columns} data={data} variant="line" size="compact" style={{ marginBottom: 10 }} />;
}

function CodeBlock({ text }) {
  return (
    <View wrap style={{ backgroundColor: "#f4f4f5", borderRadius: 3, padding: 6, marginBottom: 8 }}>
      <Text noMargin style={{ fontFamily: MONO, fontSize: 7.5, lineHeight: 1.4, whiteSpace: "pre-wrap" }}>{text}</Text>
    </View>
  );
}

/** The lineage diagram as a list of flows ("dbo.FactSales › SalesA"): the tables after it give the detail. */
function FlowList({ block }) {
  const names = Object.fromEntries(block.boxes.map((box) => [box.key, box.lines[0]]));
  const items = block.links.filter((link) => names[link.source] && names[link.target])
    .map((link) => ({ text: `${names[link.source]} › ${names[link.target]}` }));
  if (!items.length) return null;
  return <PdfList items={items} style={{ marginBottom: 8 }} />;
}

function Blocks({ blocks }) {
  const out = [];
  blocks.forEach((block, index) => {
    const key = `b${index}`;
    const previous = blocks[index - 1];
    if (block.kind === "heading") {
      // Each top-level part starts a page; the first one follows the title block.
      const style = block.level === 1 && index > 0 ? { breakBefore: "page" } : undefined;
      out.push(<Heading key={key} level={Math.min(block.level + 1, 6)} style={style}>{block.text}</Heading>);
    } else if (block.kind === "paragraph") {
      out.push(<Text key={key}>{block.text}</Text>);
    } else if (block.kind === "note") {
      // The colour legend belongs to the drawn lineage diagram, which the PDF writes as a list.
      if (previous?.kind === "diagram") return;
      out.push(<Text key={key} variant="xs" color="mutedForeground">{block.text}</Text>);
    } else if (block.kind === "table") {
      out.push(<TableBlock key={key} block={block} />);
    } else if (block.kind === "code") {
      out.push(<CodeBlock key={key} text={block.text} />);
    } else if (block.kind === "diagram") {
      out.push(<FlowList key={key} block={block} />);
    }
  });
  return out;
}

function DocumentBody({ document }) {
  return (
    <View style={{ fontFamily: SANS }}>
      <Heading level={1} noMargin>{document.title}</Heading>
      <Text variant="xs" color="mutedForeground">{`Generated ${document.generated_at} from the Power BI project files.`}</Text>
      <Divider />
      <Blocks blocks={document.blocks} />
    </View>
  );
}

/** The document tree for one export. */
export function DocumentationPdf({ document }) {
  return (
    <PdfcnThemeProvider theme={DOCUMENT_THEME}>
      <DocumentBody document={document} />
    </PdfcnThemeProvider>
  );
}

/** PDF bytes for the content model the server returned. */
export async function renderDocumentationPdf(document, { fonts } = {}) {
  return render(<DocumentationPdf document={document} />, {
    size: "a4",
    margin: { top: 48, right: 44, bottom: "auto", left: 44 },
    fonts: fonts ?? (await loadDocumentFonts()),
    fontFamilies: [SANS, MONO],
    lang: "en",
    outline: true,
    // Letters the bundled fonts lack (for example CJK) print as a box instead of stopping the export.
    uncoveredText: "placeholder",
    metadata: { title: document.title, creator: "PBIBrain" },
    footer: (
      <View style={{ display: "flex", flexDirection: "row", justifyContent: "space-between", paddingLeft: 44, paddingRight: 44, fontFamily: SANS }}>
        <View style={{ flexGrow: 1, flexShrink: 1 }}>
          <Text variant="xs" color="mutedForeground" noMargin>{document.title}</Text>
        </View>
        {/* PageNumber fills its parent's width; a fixed box keeps the title on one line. Takumi trims spaces at
            the edges of text runs, so no-break spaces keep "Page 2 of 5" apart. */}
        <View style={{ width: 90, flexShrink: 0 }}>
          <PageNumber size="xs" align="right" format={"Page\u00a0{page}\u00a0of\u00a0{total}"} />
        </View>
      </View>
    ),
  });
}
