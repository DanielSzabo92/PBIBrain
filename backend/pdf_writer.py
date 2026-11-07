"""A small, dependency-free PDF writer for the documentation export (issue #15).

Only what the export needs: the standard Helvetica and Courier fonts (WinAnsi), wrapped text,
tables with a repeated header row, code blocks that split across pages, box-and-line diagrams,
a table of contents with page links, and bookmarks (outlines).

Output is deterministic: the same input and the same ``created`` timestamp give the same bytes.
There is no random /ID, and streams are compressed at a fixed zlib level.
"""

from __future__ import annotations

import unicodedata
import zlib
from dataclasses import dataclass, field
from typing import Iterable, Sequence

PAGE_WIDTH = 595.0  # A4 portrait, in points
PAGE_HEIGHT = 842.0
MARGIN = 48.0
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN
TOP = PAGE_HEIGHT - MARGIN
BOTTOM = MARGIN + 18.0  # room for the footer

# Standard 14 font metrics (Adobe AFM), characters 32..126, in 1/1000 em.
_HELVETICA = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]
_HELVETICA_BOLD = [
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
]
FONTS = {"regular": "F1", "bold": "F2", "mono": "F3", "italic": "F4"}
_BASE_FONTS = (("F1", "Helvetica"), ("F2", "Helvetica-Bold"), ("F3", "Courier"), ("F4", "Helvetica-Oblique"))
# Letters Western European fonts lack, mapped to the nearest glyph they have (Hungarian ő/ű and friends).
_NEAREST = {"ő": "ö", "Ő": "Ö", "ű": "ü", "Ű": "Ü", "\u2212": "-", "\u2192": "->", "\u2190": "<-", "\u2194": "<->"}


def pdf_text(value: object) -> str:
    """Text the WinAnsi fonts can show: unsupported letters fall back to their nearest glyph or '?'."""

    out = []
    for char in str(value):
        if char in ("\t",):
            out.append("    ")
            continue
        if char in _NEAREST:
            out.append(_NEAREST[char])
            continue
        try:
            char.encode("cp1252")
            out.append(char)
        except UnicodeEncodeError:
            base = unicodedata.normalize("NFKD", char)[:1]
            out.append(base if base and base.isascii() and base.isprintable() else "?")
    return "".join(out)


def text_width(text: str, font: str, size: float) -> float:
    if font == "mono":
        return 600 * len(text) * size / 1000
    table = _HELVETICA_BOLD if font == "bold" else _HELVETICA
    total = 0
    for char in text:
        code = ord(char)
        if 32 <= code <= 126:
            total += table[code - 32]
        else:
            base = unicodedata.normalize("NFKD", char)[:1]
            total += table[ord(base) - 32] if base and 32 <= ord(base) <= 126 else 556
    return total * size / 1000


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    """Wrap on spaces; break words longer than the width. Explicit newlines are kept."""

    lines: list[str] = []
    for paragraph in pdf_text(text).split("\n"):
        if font == "mono":
            # Code keeps its spaces; long lines break at the width.
            per_line = max(1, int(width / (0.6 * size)))
            if not paragraph:
                lines.append("")
            while paragraph:
                lines.append(paragraph[:per_line])
                paragraph = paragraph[per_line:]
            continue
        current = ""
        for word in paragraph.split(" "):
            candidate = f"{current} {word}" if current else word
            if text_width(candidate, font, size) <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = ""
            while text_width(word, font, size) > width and len(word) > 1:
                cut = len(word)
                while cut > 1 and text_width(word[:cut], font, size) > width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        lines.append(current)
    return lines


def _escape(text: str) -> bytes:
    raw = text.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)").replace(b"\r", b"")


def _num(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text if text not in ("-0", "") else "0"


@dataclass
class Bookmark:
    title: str
    level: int
    page: int
    y: float
    children: list["Bookmark"] = field(default_factory=list)


@dataclass(frozen=True)
class DiagramBox:
    key: str
    lines: tuple[str, ...]
    x: float
    y: float  # top-down: larger y is lower on the page
    w: float
    h: float
    kind: str = "fact"


@dataclass(frozen=True)
class DiagramLink:
    source: str
    target: str
    label: str = ""
    dashed: bool = False


@dataclass
class _Page:
    ops: list[bytes] = field(default_factory=list)
    links: list[tuple[tuple[float, float, float, float], int, float]] = field(default_factory=list)


class PdfDocument:
    """Pages with a moving cursor. ``y`` is the top of the free space on the current page."""

    def __init__(self, *, title: str, footer: str, created: str) -> None:
        self.title = title
        self.footer = footer
        self.created = created  # PDF date string, e.g. D:20261107120000Z
        self.pages: list[_Page] = []
        self.bookmarks: list[Bookmark] = []
        self.y = TOP
        self.new_page()

    # Pages and cursor ---------------------------------------------------------------------------
    @property
    def page_index(self) -> int:
        return len(self.pages) - 1

    def new_page(self) -> None:
        self.pages.append(_Page())
        self.y = TOP

    def ensure(self, height: float) -> None:
        if self.y - height < BOTTOM and self.y < TOP:
            self.new_page()

    def space(self, height: float) -> None:
        self.y -= height

    # Drawing primitives -------------------------------------------------------------------------
    def _op(self, data: str | bytes, page: int | None = None) -> None:
        target = self.pages[self.page_index if page is None else page]
        target.ops.append(data.encode("latin-1") if isinstance(data, str) else data)

    def text(self, x: float, y: float, text: str, *, font: str = "regular", size: float = 10,
             color: tuple[float, float, float] = (0, 0, 0), page: int | None = None) -> None:
        r, g, b = color
        self._op(f"BT {_num(r)} {_num(g)} {_num(b)} rg /{FONTS[font]} {_num(size)} Tf {_num(x)} {_num(y)} Td (".encode("latin-1")
                 + _escape(pdf_text(text)) + b") Tj ET", page)

    def rect(self, x: float, y: float, w: float, h: float, *, fill: tuple[float, float, float] | None = None,
             stroke: tuple[float, float, float] | None = None, width: float = 0.6) -> None:
        parts = []
        if fill:
            parts.append(f"{_num(fill[0])} {_num(fill[1])} {_num(fill[2])} rg")
        if stroke:
            parts.append(f"{_num(stroke[0])} {_num(stroke[1])} {_num(stroke[2])} RG {_num(width)} w")
        paint = "B" if fill and stroke else "f" if fill else "S"
        self._op(" ".join([*parts, f"{_num(x)} {_num(y)} {_num(w)} {_num(h)} re {paint}"]))

    def line(self, x1: float, y1: float, x2: float, y2: float, *, color: tuple[float, float, float] = (0.4, 0.4, 0.4),
             width: float = 0.8, dashed: bool = False) -> None:
        dash = "[3 2] 0 d" if dashed else "[] 0 d"
        self._op(f"{_num(color[0])} {_num(color[1])} {_num(color[2])} RG {_num(width)} w {dash} "
                 f"{_num(x1)} {_num(y1)} m {_num(x2)} {_num(y2)} l S [] 0 d")

    def link(self, box: tuple[float, float, float, float], page: int, y: float, *, on_page: int | None = None) -> None:
        self.pages[self.page_index if on_page is None else on_page].links.append((box, page, y))

    # Flow blocks --------------------------------------------------------------------------------
    def heading(self, text: str, level: int) -> Bookmark:
        size = {1: 18, 2: 13.5, 3: 11}.get(level, 11)
        if level == 1 and (self.y < TOP or self.pages[self.page_index].ops):
            self.new_page()
        lines = wrap(text, "bold", size, CONTENT_WIDTH)
        self.ensure(len(lines) * size * 1.25 + 40)
        self.space(6 if level > 1 else 0)
        mark = Bookmark(pdf_text(text), level, self.page_index, self.y + 4)
        for line in lines:
            self.space(size * 1.2)
            self.text(MARGIN, self.y, line, font="bold", size=size, color=(0.1, 0.18, 0.32))
        if level == 1:
            self.space(6)
            self.line(MARGIN, self.y, MARGIN + CONTENT_WIDTH, self.y, color=(0.75, 0.8, 0.88), width=1)
        self.space(8)
        if level <= 2:
            self._add_bookmark(mark)
        return mark

    def _add_bookmark(self, mark: Bookmark) -> None:
        if mark.level == 1 or not self.bookmarks:
            self.bookmarks.append(mark)
        else:
            self.bookmarks[-1].children.append(mark)

    def paragraph(self, text: str, *, font: str = "regular", size: float = 9.5,
                  color: tuple[float, float, float] = (0.12, 0.12, 0.12), indent: float = 0) -> None:
        for line in wrap(text, font, size, CONTENT_WIDTH - indent):
            self.ensure(size * 1.35)
            self.space(size * 1.35)
            self.text(MARGIN + indent, self.y, line, font=font, size=size, color=color)
        self.space(5)

    def code(self, text: str, *, size: float = 8) -> None:
        lines = wrap(text, "mono", size, CONTENT_WIDTH - 12) or [""]
        step = size * 1.3
        index = 0
        while index < len(lines):
            self.ensure(step * min(3, len(lines) - index) + 8)
            room = max(1, int((self.y - BOTTOM - 8) / step))
            chunk = lines[index:index + room]
            height = len(chunk) * step + 8
            self.rect(MARGIN, self.y - height, CONTENT_WIDTH, height, fill=(0.95, 0.96, 0.98), stroke=(0.85, 0.87, 0.9))
            y = self.y - 4
            for line in chunk:
                y -= step
                self.text(MARGIN + 6, y + 2, line, font="mono", size=size, color=(0.1, 0.1, 0.1))
            self.space(height)
            index += len(chunk)
        self.space(7)

    def table(self, headers: Sequence[str], rows: Iterable[Sequence[object]], *, widths: Sequence[float] | None = None,
              size: float = 7.5, max_cell_lines: int = 12) -> None:
        headers = [pdf_text(item) for item in headers]
        body = [[pdf_text("" if cell is None else cell) for cell in row] for row in rows]
        count = len(headers)
        if widths is None:
            weights = []
            for column in range(count):
                longest = max([text_width(headers[column], "bold", size)]
                              + [min(text_width(row[column], "regular", size), 220) for row in body[:200]])
                weights.append(max(longest, 30))
        else:
            weights = list(widths)
        total = sum(weights) or 1
        cols = [CONTENT_WIDTH * weight / total for weight in weights]
        pad = 3.0
        step = size * 1.25

        def cell_lines(values: Sequence[str], font: str) -> list[list[str]]:
            out = []
            for value, width in zip(values, cols):
                lines = wrap(value, font, size, width - 2 * pad)
                if len(lines) > max_cell_lines:
                    lines = lines[:max_cell_lines - 1] + ["... (shortened; see the Markdown export)"]
                out.append(lines)
            return out

        head = cell_lines(headers, "bold")
        head_height = max(len(item) for item in head) * step + 2 * pad

        def draw_row(lines: list[list[str]], font: str, fill: tuple[float, float, float] | None) -> None:
            height = max(len(item) for item in lines) * step + 2 * pad
            if fill:
                self.rect(MARGIN, self.y - height, CONTENT_WIDTH, height, fill=fill)
            x = MARGIN
            for column, cell in enumerate(lines):
                y = self.y - pad
                for line in cell:
                    y -= step
                    self.text(x + pad, y + 1.5, line, font=font, size=size, color=(0.1, 0.1, 0.1))
                x += cols[column]
            self.space(height)
            self.line(MARGIN, self.y, MARGIN + CONTENT_WIDTH, self.y, color=(0.86, 0.88, 0.91), width=0.4)

        self.ensure(head_height + step * 2 + 2 * pad)
        draw_row(head, "bold", (0.9, 0.93, 0.97))
        for index, row in enumerate(body):
            lines = cell_lines(row, "regular")
            height = max(len(item) for item in lines) * step + 2 * pad
            if self.y - height < BOTTOM:
                self.new_page()
                draw_row(head, "bold", (0.9, 0.93, 0.97))
            draw_row(lines, "regular", (0.98, 0.98, 0.99) if index % 2 else None)
        self.space(9)

    def diagram(self, boxes: Sequence[DiagramBox], links: Sequence[DiagramLink], *, max_height: float = TOP - BOTTOM - 20) -> None:
        """Boxes in free units, scaled to fit the content width and ``max_height``. Lines run centre to box edge."""

        if not boxes:
            return
        left = min(box.x for box in boxes)
        bottom = min(box.y for box in boxes)
        width = max(box.x + box.w for box in boxes) - left
        height = max(box.y + box.h for box in boxes) - bottom
        scale = min(CONTENT_WIDTH / max(width, 1), max_height / max(height, 1), 1.0)
        drawn = height * scale + 8
        if self.y - drawn < BOTTOM:
            self.new_page()
        top = self.y
        origin_x = MARGIN + (CONTENT_WIDTH - width * scale) / 2

        def place(box: DiagramBox) -> tuple[float, float, float, float]:
            return (origin_x + (box.x - left) * scale, top - (box.y - bottom + box.h) * scale, box.w * scale, box.h * scale)

        frames = {box.key: place(box) for box in boxes}

        def edge_point(frame: tuple[float, float, float, float], tx: float, ty: float) -> tuple[float, float]:
            x, y, w, h = frame
            cx, cy = x + w / 2, y + h / 2
            dx, dy = tx - cx, ty - cy
            if dx == 0 and dy == 0:
                return cx, cy
            factor = min((w / 2) / abs(dx) if dx else float("inf"), (h / 2) / abs(dy) if dy else float("inf"))
            return cx + dx * factor, cy + dy * factor

        for item in links:
            if item.source not in frames or item.target not in frames or item.source == item.target:
                continue
            a, b = frames[item.source], frames[item.target]
            ac = (a[0] + a[2] / 2, a[1] + a[3] / 2)
            bc = (b[0] + b[2] / 2, b[1] + b[3] / 2)
            x1, y1 = edge_point(a, *bc)
            x2, y2 = edge_point(b, *ac)
            self.line(x1, y1, x2, y2, color=(0.45, 0.5, 0.58), width=0.8, dashed=item.dashed)
            if item.label:
                size = max(5.0, 7 * min(1.0, scale * 1.4))
                label = pdf_text(item.label)
                lw = text_width(label, "regular", size)
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                self.rect(mx - lw / 2 - 1.5, my - size / 2 - 1, lw + 3, size + 2, fill=(1, 1, 1))
                self.text(mx - lw / 2, my - size / 2 + 1, label, size=size, color=(0.3, 0.3, 0.35))
        palette = {"fact": ((0.91, 0.94, 0.99), (0.45, 0.58, 0.8)), "source": ((0.92, 0.97, 0.93), (0.4, 0.65, 0.48)),
                   "report": ((0.99, 0.95, 0.9), (0.8, 0.6, 0.35)), "muted": ((0.95, 0.95, 0.95), (0.6, 0.6, 0.6))}
        for box in boxes:
            x, y, w, h = frames[box.key]
            fill, stroke = palette.get(box.kind, palette["fact"])
            self.rect(x, y, w, h, fill=fill, stroke=stroke, width=0.8)
            size = max(4.5, min(8.5, 8.5 * scale * 1.3))
            lines = box.lines
            step = size * 1.2
            ty = y + h / 2 + (len(lines) * step) / 2 - size
            for index, text in enumerate(lines):
                font = "bold" if index == 0 else "regular"
                fitted = pdf_text(text)
                while len(fitted) > 4 and text_width(fitted, font, size) > w - 4:
                    fitted = fitted[:-4].rstrip() + "..."
                self.text(x + (w - text_width(fitted, font, size)) / 2, ty - index * step, fitted, font=font, size=size,
                          color=(0.1, 0.12, 0.18))
        self.space(drawn + 6)

    # Output -------------------------------------------------------------------------------------
    def render(self) -> bytes:
        objects: list[bytes] = []

        def reserve() -> int:
            objects.append(b"")
            return len(objects)

        catalog, pages_id, info = reserve(), reserve(), reserve()
        font_ids = {}
        for name, base in _BASE_FONTS:
            font_ids[name] = reserve()
            objects[font_ids[name] - 1] = (f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} "
                                           "/Encoding /WinAnsiEncoding >>").encode("latin-1")
        fonts = " ".join(f"/{name} {font_ids[name]} 0 R" for name, _ in _BASE_FONTS)
        page_ids = [reserve() for _ in self.pages]
        total = len(self.pages)
        for index, page in enumerate(self.pages):
            footer = [
                f"0.75 0.78 0.83 RG 0.5 w [] 0 d {_num(MARGIN)} {_num(MARGIN + 10)} m {_num(MARGIN + CONTENT_WIDTH)} {_num(MARGIN + 10)} l S".encode("latin-1"),
                b"BT 0.4 0.4 0.4 rg /F1 7.5 Tf " + f"{_num(MARGIN)} {_num(MARGIN)} Td (".encode("latin-1") + _escape(pdf_text(self.footer)) + b") Tj ET",
            ]
            label = f"Page {index + 1} of {total}"
            footer.append(b"BT 0.4 0.4 0.4 rg /F1 7.5 Tf " + f"{_num(MARGIN + CONTENT_WIDTH - text_width(label, 'regular', 7.5))} {_num(MARGIN)} Td (".encode("latin-1")
                          + _escape(label) + b") Tj ET")
            stream = zlib.compress(b"\n".join([*page.ops, *footer]), 6)
            content = reserve()
            objects[content - 1] = f"<< /Length {len(stream)} /Filter /FlateDecode >>\nstream\n".encode("latin-1") + stream + b"\nendstream"
            annots = []
            for (x1, y1, x2, y2), target, y in page.links:
                annot = reserve()
                objects[annot - 1] = (f"<< /Type /Annot /Subtype /Link /Rect [{_num(x1)} {_num(y1)} {_num(x2)} {_num(y2)}] /Border [0 0 0] "
                                      f"/Dest [{page_ids[target]} 0 R /XYZ 0 {_num(y)} 0] >>").encode("latin-1")
                annots.append(f"{annot} 0 R")
            annot_text = f" /Annots [{' '.join(annots)}]" if annots else ""
            objects[page_ids[index] - 1] = (f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {_num(PAGE_WIDTH)} {_num(PAGE_HEIGHT)}] "
                                            f"/Resources << /Font << {fonts} >> >> /Contents {content} 0 R{annot_text} >>").encode("latin-1")
        objects[pages_id - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{item} 0 R' for item in page_ids)}] /Count {total} >>".encode("latin-1")
        outline_root = self._outlines(objects, reserve, page_ids)
        outlines = f" /Outlines {outline_root} 0 R /PageMode /UseOutlines" if outline_root else ""
        objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R{outlines} >>".encode("latin-1")
        objects[info - 1] = (b"<< /Title (" + _escape(pdf_text(self.title)) + b") /Producer (PBIBrain documentation export) "
                             + f"/CreationDate ({self.created}) >>".encode("latin-1"))
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for number, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += f"{number} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
        for offset in offsets:
            out += f"{offset:010d} 00000 n \n".encode("latin-1")
        out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("latin-1")
        return bytes(out)

    def _outlines(self, objects: list[bytes], reserve, page_ids: list[int]) -> int | None:
        if not self.bookmarks:
            return None
        root = reserve()

        def build(items: list[Bookmark], parent: int) -> tuple[int, int, int]:
            ids = [reserve() for _ in items]
            count = 0
            for index, (item, number) in enumerate(zip(items, ids)):
                first_last = ""
                if item.children:
                    first, last, sub = build(item.children, number)
                    first_last = f" /First {first} 0 R /Last {last} 0 R /Count -{sub}"
                count += 1
                links = ""
                if index > 0:
                    links += f" /Prev {ids[index - 1]} 0 R"
                if index + 1 < len(ids):
                    links += f" /Next {ids[index + 1]} 0 R"
                objects[number - 1] = (b"<< /Title (" + _escape(item.title) + b")"
                                       + f" /Parent {parent} 0 R{links}{first_last} /Dest [{page_ids[item.page]} 0 R /XYZ 0 {_num(item.y)} 0] >>".encode("latin-1"))
            return ids[0], ids[-1], count

        first, last, count = build(self.bookmarks, root)
        objects[root - 1] = f"<< /Type /Outlines /First {first} 0 R /Last {last} 0 R /Count {count} >>".encode("latin-1")
        return root
