"""Bilingual player manual built from packaged Markdown chapters.

Chapter prose lives in ``data/manual/<nn>-<chapter>.<lang>.md``. Key tables and
standard procedures are never written into the prose: the markers
``<!-- keys:<table> -->`` and ``<!-- sop:<station> -->`` expand from
``src/core/help.py`` and the i18n catalogs, so the F1 overlay, the in-game
manual reader, the Remote Crew web page, and the exported ``docs/manual``
Markdown always show the same bindings.

Only a small Markdown subset is accepted (headings with explicit anchors,
paragraphs, lists, pipe tables, fenced blocks, ``>`` notes, inline
``code``/``**strong**``); anything the parser does not understand stays plain
text. The module is Pygame-free: the game wraps ``text_lines`` output and the
commander server serves ``html_page`` output.
"""

from __future__ import annotations

import html
import re
import textwrap
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files as _resource_files

from src.core.help import (_GLOBAL_HELP, _UBOOT_HELP, _WEB_HELP, STATION_HELP,
                           STATION_SOP, UBOOT_SOP, UBOOT_SOP_SLUGS)
from src.core.i18n import Translator
from src.core.station import Station

LANGUAGES = ("en", "de")
CHAPTERS = ("quickstart", "bridge", "sonar", "weapons", "damage", "opz", "radio",
            "engine", "helicopter", "eloka", "submarine", "reference")
STATION_CHAPTERS = {
    Station.BRIDGE: "bridge", Station.SONAR: "sonar", Station.WEAPONS: "weapons",
    Station.DAMAGE: "damage", Station.OPZ: "opz", Station.RADIO: "radio",
    Station.ENGINE: "engine", Station.HELICOPTER: "helicopter", Station.ELOKA: "eloka",
}
_CHAPTER_STATIONS = {chapter: station for station, chapter in STATION_CHAPTERS.items()}
KEY_TABLES = ("global", "web", *STATION_CHAPTERS.values())

_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s+\{#([a-z0-9][a-z0-9-]*)\}\s*$")
_MARKER = re.compile(r"^<!--\s*(keys|sop):([a-z_]+)\s*-->$")
_ORDERED = re.compile(r"^\d+\.\s+(.*)$")
_TABLE_RULE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")
_INLINE = re.compile(r"`([^`]+)`|\*\*([^*]+)\*\*")


class ManualError(ValueError):
    """Raised for a malformed packaged chapter."""


@dataclass(frozen=True)
class Block:
    kind: str                 # heading | para | ul | ol | table | pre | note
    text: str = ""
    level: int = 0
    anchor: str = ""
    items: tuple = ()
    header: tuple = ()
    rows: tuple = ()
    marker: str = ""          # "keys:sonar" when expanded from help.py


def chapter_filename(chapter: str, lang: str) -> str:
    return f"{CHAPTERS.index(chapter):02d}-{chapter}.{lang}.md"


def load_source(chapter: str, lang: str) -> str:
    if chapter not in CHAPTERS or lang not in LANGUAGES:
        raise ManualError(f"unknown manual chapter {chapter!r}/{lang!r}")
    root = _resource_files("data.manual")
    return root.joinpath(chapter_filename(chapter, lang)).read_text(encoding="utf-8")


def _key_table(name: str, tr) -> tuple:
    if name == "global":
        rows = _GLOBAL_HELP[1]
    elif name == "web":
        rows = _WEB_HELP[1]
    elif name == "uboot":
        rows = _UBOOT_HELP[1]
    elif name in _CHAPTER_STATIONS:
        rows = STATION_HELP[_CHAPTER_STATIONS[name]][1]
    else:
        raise ManualError(f"unknown key table {name!r}")
    return tuple((tr(key), tr(action)) for key, action in rows)


_UBOOT_SOP_MARKERS = {f"uboot_{slug}": station for station, slug in UBOOT_SOP_SLUGS.items()}


def _sop(name: str, tr) -> tuple:
    if name in _UBOOT_SOP_MARKERS:
        return tuple(tr(key) for key in UBOOT_SOP[_UBOOT_SOP_MARKERS[name]])
    if name not in _CHAPTER_STATIONS:
        raise ManualError(f"unknown procedure {name!r}")
    return tuple(tr(key) for key in STATION_SOP[_CHAPTER_STATIONS[name]])


def _cells(line: str) -> tuple:
    return tuple(cell.strip() for cell in line.strip().strip("|").split("|"))


def parse(source: str, tr) -> list:
    """Parse one chapter into blocks; ``tr`` resolves generated markers."""
    blocks: list = []
    lines = source.replace("\r\n", "\n").split("\n")
    i = 0
    para: list = []

    def flush():
        if para:
            blocks.append(Block("para", " ".join(para)))
            para.clear()

    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("```"):
            flush()
            body = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i].rstrip())
                i += 1
            if i >= len(lines):
                raise ManualError("unterminated fenced block")
            blocks.append(Block("pre", "\n".join(body)))
            i += 1
            continue
        if not line:
            flush()
            i += 1
            continue
        marker = _MARKER.match(line)
        if marker:
            flush()
            kind, name = marker.groups()
            if kind == "keys":
                blocks.append(Block("table", header=(tr("help.manual.key"),
                                                     tr("help.manual.action")),
                                    rows=_key_table(name, tr), marker=f"keys:{name}"))
            else:
                blocks.append(Block("ol", items=_sop(name, tr), marker=f"sop:{name}"))
            i += 1
            continue
        if line.startswith("<!--"):
            raise ManualError(f"unknown marker {line!r}")
        if line.startswith("#"):
            flush()
            heading = _HEADING.match(line)
            if heading is None:
                raise ManualError(f"heading without {{#anchor}}: {line!r}")
            hashes, text, anchor = heading.groups()
            blocks.append(Block("heading", text, level=len(hashes), anchor=anchor))
            i += 1
            continue
        if line.startswith("|"):
            flush()
            header = _cells(line)
            if i + 1 >= len(lines) or not _TABLE_RULE.match(lines[i + 1].strip()):
                raise ManualError(f"table without separator row: {line!r}")
            rows = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = _cells(lines[i])
                if len(row) != len(header):
                    raise ManualError(f"table row width mismatch: {lines[i]!r}")
                rows.append(row)
                i += 1
            blocks.append(Block("table", header=header, rows=tuple(rows)))
            continue
        if line.startswith("- ") or _ORDERED.match(line):
            flush()
            ordered = not line.startswith("- ")
            items = []
            while i < len(lines):
                current = lines[i].strip()
                match = _ORDERED.match(current) if ordered else None
                if ordered and match:
                    items.append(match.group(1))
                elif not ordered and current.startswith("- "):
                    items.append(current[2:].strip())
                elif current and lines[i].startswith("  ") and items:
                    items[-1] += " " + current
                else:
                    break
                i += 1
            blocks.append(Block("ol" if ordered else "ul", items=tuple(items)))
            continue
        if line.startswith(">"):
            flush()
            note = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                note.append(lines[i].strip()[1:].strip())
                i += 1
            blocks.append(Block("note", " ".join(part for part in note if part)))
            continue
        para.append(line)
        i += 1
    flush()
    return blocks


@lru_cache(maxsize=len(CHAPTERS) * len(LANGUAGES))
def _cached_blocks(chapter: str, lang: str) -> tuple:
    return tuple(parse(load_source(chapter, lang), Translator(lang).t))


def chapter_blocks(chapter: str, lang: str, tr=None) -> list:
    """Parsed chapter; cached unless a custom translator (tests) is supplied."""
    if tr is None:
        return list(_cached_blocks(chapter, lang))
    return parse(load_source(chapter, lang), tr)


def chapter_title(chapter: str, lang: str) -> str:
    for block in chapter_blocks(chapter, lang):
        if block.kind == "heading":
            return plain(block.text)
    return chapter


def manual_language(tr) -> str:
    """Pick the manual language for a translator (pseudolocale -> English)."""
    owner = getattr(tr, "__self__", tr)
    language = getattr(owner, "language", "en")
    return language if language in LANGUAGES else "en"


# ---------------------------------------------------------------- plain text
def plain(text: str) -> str:
    return _INLINE.sub(lambda m: m.group(1) or m.group(2), text)


def _wrap(text: str, width: int, first: str = "", rest: str = "") -> list:
    return textwrap.wrap(plain(text), width=max(8, width), initial_indent=first,
                         subsequent_indent=rest, break_long_words=True,
                         break_on_hyphens=False) or [first.rstrip()]


def _table_lines(block: Block, width: int) -> list:
    rows = [block.header, *block.rows]
    widths = [max(len(plain(row[col])) for row in rows) for col in range(len(block.header))]
    total = sum(widths) + 3 * (len(widths) - 1)
    if total <= width:
        out = []
        for index, row in enumerate(rows):
            out.append(" | ".join(plain(cell).ljust(widths[col])
                                  for col, cell in enumerate(row)).rstrip())
            if index == 0:
                out.append("-+-".join("-" * w for w in widths))
        return out
    # Narrow screen / large text: one record per row, first column as label.
    out = []
    first_width = min(max(widths[0], 4), max(8, width // 3))
    for row in block.rows:
        label = plain(row[0])
        rest = " | ".join(plain(cell) for cell in row[1:])
        if len(label) <= first_width:
            out.extend(_wrap(rest, width, label.ljust(first_width) + "  ",
                             " " * (first_width + 2)))
        else:
            out.extend(_wrap(label, width))
            out.extend(_wrap(rest, width, "    ", "    "))
    return out


def text_lines(blocks, width: int) -> list:
    """Render blocks as monospace text lines no wider than ``width`` chars."""
    width = max(20, int(width))
    out: list = []

    def gap():
        if out and out[-1] != "":
            out.append("")

    for block in blocks:
        if block.kind == "heading":
            gap()
            title = plain(block.text)
            if block.level == 1:
                title = title.upper()
            wrapped = _wrap(title, width)
            out.extend(wrapped)
            out.append({1: "=", 2: "-"}.get(block.level, "~")
                       * min(width, max(len(line) for line in wrapped)))
        elif block.kind == "para":
            gap()
            out.extend(_wrap(block.text, width))
        elif block.kind == "note":
            gap()
            out.extend(_wrap(block.text, width, "! ", "  "))
        elif block.kind in ("ul", "ol"):
            gap()
            for index, item in enumerate(block.items, 1):
                bullet = f"{index}. " if block.kind == "ol" else "- "
                out.extend(_wrap(item, width, bullet, " " * len(bullet)))
        elif block.kind == "table":
            gap()
            out.extend(_table_lines(block, width))
        elif block.kind == "pre":
            gap()
            for line in block.text.split("\n"):
                while len(line) > width:
                    out.append(line[:width])
                    line = line[width:]
                out.append(line)
    while out and out[-1] == "":
        out.pop()
    return out


# ------------------------------------------------------------------ Markdown
def _md_cell(text: str) -> str:
    return text.replace("|", "\\|")


def markdown(lang: str) -> str:
    """Complete manual as Markdown with generated tables expanded."""
    tr = Translator(lang).t
    out = [f"# {tr('help.manual.title')}", "",
           "<!-- Generated by tools/build_manual.py from data/manual; do not edit. -->", ""]
    for chapter in CHAPTERS:
        for block in chapter_blocks(chapter, lang):
            if block.kind == "heading":
                out += [f"{'#' * (block.level + 1)} {block.text}", ""]
            elif block.kind == "para":
                out += [block.text, ""]
            elif block.kind == "note":
                out += [f"> {block.text}", ""]
            elif block.kind in ("ul", "ol"):
                out += [(f"{n}. " if block.kind == "ol" else "- ") + item
                        for n, item in enumerate(block.items, 1)] + [""]
            elif block.kind == "table":
                header = [_md_cell(cell) for cell in block.header]
                out.append("| " + " | ".join(header) + " |")
                out.append("|" + "|".join("---" for _ in header) + "|")
                for row in block.rows:
                    cells = [f"`{_md_cell(row[0])}`" if block.marker else _md_cell(row[0]),
                             *(_md_cell(cell) for cell in row[1:])]
                    out.append("| " + " | ".join(cells) + " |")
                out.append("")
            elif block.kind == "pre":
                out += ["```text", block.text, "```", ""]
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------- HTML
def _inline_html(text: str) -> str:
    parts = []
    last = 0
    for match in _INLINE.finditer(text):
        parts.append(html.escape(text[last:match.start()]))
        if match.group(1) is not None:
            parts.append(f"<kbd>{html.escape(match.group(1))}</kbd>")
        else:
            parts.append(f"<strong>{html.escape(match.group(2))}</strong>")
        last = match.end()
    parts.append(html.escape(text[last:]))
    return "".join(parts)


def _chapter_html(blocks) -> list:
    out: list = []
    section_open = False
    for block in blocks:
        if block.kind == "heading":
            level = block.level + 1
            if block.level == 1:
                out.append(f'<h2 id="{block.anchor}">{_inline_html(block.text)}</h2>')
                continue
            if block.level == 2:
                if section_open:
                    out.append("</section>")
                out.append(f'<section aria-labelledby="{block.anchor}">')
                section_open = True
            out.append(f'<h{level} id="{block.anchor}">{_inline_html(block.text)}</h{level}>')
        elif block.kind == "para":
            out.append(f"<p>{_inline_html(block.text)}</p>")
        elif block.kind == "note":
            out.append(f'<aside class="note"><p>{_inline_html(block.text)}</p></aside>')
        elif block.kind in ("ul", "ol"):
            tag = block.kind
            css = ' class="sop"' if block.marker else ""
            items = "".join(f"<li>{_inline_html(item)}</li>" for item in block.items)
            out.append(f"<{tag}{css}>{items}</{tag}>")
        elif block.kind == "table":
            css = ' class="keys"' if block.marker else ""
            head = "".join(f'<th scope="col">{_inline_html(cell)}</th>' for cell in block.header)
            body = []
            for row in block.rows:
                first = (f"<td><kbd>{html.escape(row[0])}</kbd></td>" if block.marker
                         else f"<td>{_inline_html(row[0])}</td>")
                body.append("<tr>" + first + "".join(
                    f"<td>{_inline_html(cell)}</td>" for cell in row[1:]) + "</tr>")
            out.append(f'<div class="table-wrap"><table{css}><thead><tr>{head}</tr></thead>'
                       f"<tbody>{''.join(body)}</tbody></table></div>")
        elif block.kind == "pre":
            out.append(f'<pre class="diagram">{html.escape(block.text)}</pre>')
    if section_open:
        out.append("</section>")
    return out


@lru_cache(maxsize=len(LANGUAGES))
def html_page(lang: str) -> str:
    """Self-contained, script-free manual page for the Remote Crew server."""
    if lang not in LANGUAGES:
        raise ManualError(f"unknown manual language {lang!r}")
    tr = Translator(lang).t
    other = "de" if lang == "en" else "en"
    title = html.escape(tr("help.manual.title"))
    toc = []
    articles = []
    for chapter in CHAPTERS:
        blocks = chapter_blocks(chapter, lang)
        first = next(block for block in blocks if block.kind == "heading")
        toc.append(f'<li><a href="#{first.anchor}">{html.escape(plain(first.text))}</a></li>')
        articles.append(f'<article id="chapter-{chapter}">'
                        + "".join(_chapter_html(blocks)) + "</article>")
    return (
        "<!doctype html>\n"
        f'<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        # The Remote Crew design tokens and fonts, then the page layout.
        '<link rel="stylesheet" href="/css/tokens.css">\n'
        '<link rel="stylesheet" href="/css/fonts.css">\n'
        '<link rel="stylesheet" href="/manual.css">\n</head>\n<body>\n'
        f'<header class="manual-head"><h1>{title}</h1>'
        f'<a class="lang-switch" href="/manual-{other}" hreflang="{other}" lang="{other}">'
        f"{html.escape(tr('help.manual.other_language'))}</a></header>\n"
        '<div class="manual-layout">\n'
        f'<nav class="toc" aria-labelledby="toc-title"><h2 id="toc-title">'
        f"{html.escape(tr('help.manual.contents'))}</h2><ol>{''.join(toc)}</ol></nav>\n"
        f'<main>{"".join(articles)}</main>\n</div>\n</body>\n</html>\n'
    )
