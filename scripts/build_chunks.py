#!/usr/bin/env python3
"""
build_chunks.py — chunk Big Data in Finance course material for the chat widget.

Walks ../{Lectures,Notes,Codes} (the course folders that sit next to
this script's parent directory), splits each .tex file into
section/subsection blocks, cleans the LaTeX, extracts matching text from
the compiled PDF via pdftotext, and writes course-chunks.json into the
parent directory (next to README.md).

Each chunk entry looks like:

    {
      "id": "lectures-week-2-f012-ridge-regression",
      "source_type": "lectures",     # lectures | notes | tutorials
      "week": 2,
      "title_full": "Big Data in Finance",
      "section": "Ridge Regression",
      "subsection": null,
      "tex_path": "Lectures/Week 2 Slides.tex",
      "pdf_path": "Lectures/Week 2 Slides.pdf",
      "tex_text": "…cleaned LaTeX prose…",
      "pdf_text": "…pdftotext slice that contains the section title…",
      "token_estimate": 412
    }

Run with no arguments:

    python3 scripts/build_chunks.py

Requires Python 3.9+ and pdftotext on $PATH (Poppler or MacTeX).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SOURCE_ROOT = REPO_ROOT
OUTPUT_FILE = REPO_ROOT / "course-chunks.json"

SOURCE_TYPES = {
    "lectures": SOURCE_ROOT / "Lectures",
    "notes": SOURCE_ROOT / "Notes",
    "tutorials": SOURCE_ROOT / "Codes",   # Jupyter tutorial notebooks (.ipynb)
}


# ---------------------------------------------------------------------------
# LaTeX cleaning
# ---------------------------------------------------------------------------

# Regexes we reuse
RE_SECTION = re.compile(r"\\(section|subsection)\*?\s*\{([^}]*)\}")
RE_FRAME_TITLE = re.compile(r"\\begin\{frame\}(?:\[[^\]]*\])?\s*\{([^}]*)\}")
RE_COMMENT = re.compile(r"(?<!\\)%.*")
RE_BEGIN_DOC = re.compile(r"\\begin\{document\}")
RE_END_DOC = re.compile(r"\\end\{document\}")


# Commands whose first argument carries text we want to keep. Rendered as
# plain text (the argument content).
TEXT_COMMANDS = {
    "textbf", "textit", "emph", "underline", "texttt", "textsc",
    "textsf", "textrm", "text", "keyword", "highlight", "good", "bad",
    "emphbox", "mbox", "hbox",
}

# Commands to drop entirely along with their single braced argument.
DROP_COMMANDS = {
    "label", "ref", "pageref", "cite", "footcite", "citep", "citet",
    "includegraphics", "includepdf", "input", "include", "index",
    "hypersetup", "definecolor", "setbeamercolor", "setbeamerfont",
    "setbeamertemplate", "usetheme", "usecolortheme", "usefonttheme",
    "usetikzlibrary", "geometry", "pagestyle", "fancyhf", "lhead",
    "chead", "rhead", "lfoot", "cfoot", "rfoot", "colorbox",
    "textcolor", "fcolorbox", "addcontentsline", "tableofcontents",
    "titlepage", "maketitle", "today", "insertframetitle",
    "insertsection", "insertsubsection", "insertshorttitle",
    "insertshortauthor", "insertshortdate", "insertframenumber",
    "inserttotalframenumber", "insertauthor", "insertinstitute",
    "inserttitle", "insertsubtitle", "insertdate", "renewcommand",
    "newcommand", "providecommand", "newenvironment", "renewenvironment",
    "setlength", "vspace", "hspace", "vskip", "hskip", "vfill", "hfill",
    "leavevmode", "par", "noindent", "indent", "medskip", "bigskip",
    "smallskip", "resizebox", "scalebox", "titleformat", "titlespacing",
}

# Commands in DROP_COMMANDS that take more than one braced argument.
# We list their argument counts here; the default for DROP_COMMANDS is 1.
DROP_COMMAND_ARITY = {
    "addcontentsline": 3,
    "definecolor": 3,
    "setbeamercolor": 2,
    "setbeamerfont": 2,
    "setbeamertemplate": 2,
    "hypersetup": 1,
    "renewcommand": 2,
    "newcommand": 2,
    "providecommand": 2,
    "newenvironment": 2,
    "renewenvironment": 2,
    "setlength": 2,
    "resizebox": 3,
    "scalebox": 2,
    "titleformat": 5,
    "titlespacing": 5,
    "fcolorbox": 3,
    "textcolor": 2,
    "colorbox": 2,
}

# Environments whose content we drop outright (figures, tikz, tables that
# carry no useful prose). Math environments (align, equation, gather, …) are
# NOT dropped — they are extracted and restored verbatim so the model can
# read the derivations.
DROP_ENVIRONMENTS = {
    "tikzpicture", "figure", "wrapfigure", "pspicture",
    "thebibliography", "filecontents",
}

# Math environments whose content we preserve verbatim. Claude/GPT read
# LaTeX math fine, so there is no point stripping it to "[math]".
MATH_ENVIRONMENTS = (
    "align", "align*", "equation", "equation*",
    "gather", "gather*", "multline", "multline*",
    "eqnarray", "eqnarray*", "aligned", "gathered",
)

# Matches display math delimited by environments, \[...\], $$...$$, or $...$.
# Applied in order; longer/more specific patterns first.
_MATH_ENV_ALT = "|".join(re.escape(e) for e in MATH_ENVIRONMENTS)
RE_MATH_PATTERNS = [
    re.compile(r"\\begin\{(" + _MATH_ENV_ALT + r")\}.*?\\end\{\1\}", re.DOTALL),
    re.compile(r"\\\[.*?\\\]", re.DOTALL),
    re.compile(r"\$\$.*?\$\$", re.DOTALL),
    re.compile(r"(?<!\\)\$[^$\n]+?\$"),
]

MATH_PLACEHOLDER_RE = re.compile(r"\x00MATH(\d+)\x00")


def strip_comments(text: str) -> str:
    """Remove % comments, preserving \\%."""
    out_lines = []
    for line in text.splitlines():
        cleaned = RE_COMMENT.sub("", line)
        out_lines.append(cleaned)
    return "\n".join(out_lines)


def strip_environments(text: str, envs: set[str]) -> str:
    """Remove `\\begin{env} ... \\end{env}` blocks for the listed envs."""
    for env in envs:
        pattern = re.compile(
            r"\\begin\{" + re.escape(env) + r"\}.*?\\end\{" + re.escape(env) + r"\}",
            re.DOTALL,
        )
        text = pattern.sub(" ", text)
    return text


def _find_matching_brace(text: str, start: int) -> int:
    """Given index of an opening `{`, return index of matching `}`, or -1."""
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def unwrap_text_commands(text: str) -> str:
    """Replace `\\textbf{foo}` etc. with just `foo`."""
    cmd_pattern = re.compile(r"\\([a-zA-Z]+)\s*")
    out = []
    i = 0
    while i < len(text):
        m = cmd_pattern.match(text, i)
        if not m:
            out.append(text[i])
            i += 1
            continue
        name = m.group(1)
        j = m.end()
        # Skip optional argument `[...]`.
        if j < len(text) and text[j] == "[":
            close = text.find("]", j)
            if close != -1:
                j = close + 1
        if name in DROP_COMMANDS:
            # Eat up to `arity` consecutive braced arguments.
            arity = DROP_COMMAND_ARITY.get(name, 1)
            eaten = 0
            while eaten < arity and j < len(text):
                # Skip whitespace between arguments.
                k = j
                while k < len(text) and text[k].isspace():
                    k += 1
                if k < len(text) and text[k] == "{":
                    end = _find_matching_brace(text, k)
                    if end == -1:
                        break
                    j = end + 1
                    eaten += 1
                    continue
                break
            i = j
            continue
        if name in TEXT_COMMANDS:
            if j < len(text) and text[j] == "{":
                end = _find_matching_brace(text, j)
                if end != -1:
                    out.append(text[j + 1 : end])
                    i = end + 1
                    continue
            i = j
            continue
        # Generic unknown command: drop the command but keep any braced
        # argument content verbatim (one level).
        if j < len(text) and text[j] == "{":
            end = _find_matching_brace(text, j)
            if end != -1:
                out.append(" ")
                out.append(text[j + 1 : end])
                i = end + 1
                continue
        out.append(" ")
        i = j
    return "".join(out)


def strip_list_markers(text: str) -> str:
    """Replace `\\item` with a bullet and `\\begin{itemize}`-style markers
    with nothing."""
    text = re.sub(r"\\begin\{(itemize|enumerate|description)\}(\[[^\]]*\])?", " ", text)
    text = re.sub(r"\\end\{(itemize|enumerate|description)\}", " ", text)
    text = re.sub(r"\\begin\{(block|alertblock|exampleblock|quote|quotation|columns|column|center|flushleft|flushright|tabular|tabular\*|table|frame)\}(\[[^\]]*\])?(\{[^}]*\})?", " ", text)
    text = re.sub(r"\\end\{(block|alertblock|exampleblock|quote|quotation|columns|column|center|flushleft|flushright|tabular|tabular\*|table|frame)\}", " ", text)
    text = re.sub(r"\\item\b", "• ", text)
    return text


def extract_math(text: str) -> tuple[str, list[str]]:
    """Replace math blocks with ``\\x00MATH<n>\\x00`` placeholders and return
    ``(text_with_placeholders, math_blocks)``. The original LaTeX for each
    block is preserved so it can be re-inserted after the surrounding text
    has been cleaned, keeping derivations readable to the downstream LLM."""
    blocks: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        idx = len(blocks)
        blocks.append(match.group(0))
        return f"\x00MATH{idx}\x00"

    for pattern in RE_MATH_PATTERNS:
        text = pattern.sub(_sub, text)
    return text, blocks


def restore_math(text: str, blocks: list[str]) -> str:
    """Swap ``\\x00MATH<n>\\x00`` placeholders back for the original LaTeX."""
    if not blocks:
        return text

    def _sub(match: re.Match[str]) -> str:
        idx = int(match.group(1))
        if idx >= len(blocks):
            return ""
        raw = blocks[idx]
        # Normalise the `{,}` thousands-separator trick (`4{,}000` → `4,000`)
        # so numbers read cleanly. We deliberately leave custom emphasis
        # commands like `\highlight{...}` untouched — an LLM reads them
        # fine as raw LaTeX, and a naive strip breaks on nested braces.
        raw = raw.replace("{,}", ",")
        # Collapse internal whitespace so the placeholder doesn't introduce
        # gratuitous blank lines into the surrounding prose.
        raw = re.sub(r"\s+", " ", raw).strip()
        return " " + raw + " "

    return MATH_PLACEHOLDER_RE.sub(_sub, text)


def normalise_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    return text.strip()


def latex_to_text(latex: str) -> str:
    """Best-effort conversion of a LaTeX fragment to readable plain text.

    Math blocks (``align*``, ``equation``, ``\\[...\\]``, ``$...$``, …) are
    extracted up front and re-inserted verbatim at the end, so derivations
    survive the surrounding prose cleanup intact."""
    text = strip_comments(latex)
    # Pull math out before any cleanup runs — math content would otherwise
    # be mangled by `unwrap_text_commands`, the `\\[a-zA-Z]+` sweep, and the
    # `{` / `}` strip at the bottom of this function.
    text, math_blocks = extract_math(text)
    # Strip the leading \section{...} / \subsection{...} declaration; the
    # title is already captured on the chunk's metadata.
    text = re.sub(
        r"\\(section|subsection|subsubsection|chapter|paragraph)\*?\s*\{[^}]*\}",
        " ",
        text,
    )
    text = strip_environments(text, DROP_ENVIRONMENTS)
    text = strip_list_markers(text)
    text = unwrap_text_commands(text)
    # Collapse leftover LaTeX escapes
    text = text.replace("\\\\", "\n")
    text = re.sub(r"\\[&%_#]", lambda m: m.group(0)[1], text)
    # Collapse `\ ` (non-breaking space after an abbreviation) and `\,`
    # (thin space) to a regular space.
    text = re.sub(r"\\[ ,;:!]", " ", text)
    text = re.sub(r"\\[a-zA-Z]+\*?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = text.replace("~", " ")
    text = text.replace("---", "—").replace("--", "–")
    text = text.replace("``", "“").replace("''", "”")
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = restore_math(text, math_blocks)
    return normalise_whitespace(text)


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

@dataclass
class RawSection:
    level: str  # "section" or "subsection"
    title: str
    start: int  # offset in the *body* (post `\begin{document}`)
    end: int  # exclusive


def split_sections(tex: str) -> list[RawSection]:
    """Return top-level sections (with their subsections flattened inside)
    from the body of a .tex file."""
    # Restrict to document body when present.
    m_begin = RE_BEGIN_DOC.search(tex)
    m_end = RE_END_DOC.search(tex)
    body_start = m_begin.end() if m_begin else 0
    body_end = m_end.start() if m_end else len(tex)
    body = tex[body_start:body_end]

    matches = list(RE_SECTION.finditer(body))
    if not matches:
        return []

    sections: list[RawSection] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections.append(
            RawSection(
                level=m.group(1),
                title=m.group(2).strip(),
                start=start,
                end=end,
            )
        )
    # We also want access to the body text itself, so attach as attribute.
    for s in sections:
        s.__dict__["body_text"] = body[s.start : s.end]
    return sections


# Frame-level chunking for Beamer decks. We walk the body linearly and emit
# one chunk per `\begin{frame}...\end{frame}`, tagging each with the
# most-recent `\section` / `\subsection` so retrieval keeps the parent
# context as metadata without merging all frames under a section into a
# single giant chunk.

RE_BEAMER_EVENT = re.compile(
    r"\\(section|subsection)\*?\s*\{([^}]*)\}"
    r"|\\begin\{frame\}(?:\[[^\]]*\])?\s*(?:\{([^}]*)\})?",
)
RE_FRAME_END = re.compile(r"\\end\{frame\}")
RE_FRAMETITLE_CMD = re.compile(r"\\frametitle\s*\{([^}]*)\}")


@dataclass
class BeamerFrame:
    section: str | None  # most recent \section, if any
    subsection: str | None  # most recent \subsection, if any
    title: str  # frame title (possibly empty)
    body: str  # full `\begin{frame}...\end{frame}` text


def split_beamer_frames(tex: str) -> list[BeamerFrame]:
    """Walk a Beamer .tex body and return one entry per frame, annotated
    with the enclosing `\\section` / `\\subsection`."""
    m_begin = RE_BEGIN_DOC.search(tex)
    m_end = RE_END_DOC.search(tex)
    body = tex[
        (m_begin.end() if m_begin else 0) : (m_end.start() if m_end else len(tex))
    ]

    frames: list[BeamerFrame] = []
    current_section: str | None = None
    current_subsection: str | None = None

    pos = 0
    while pos < len(body):
        m = RE_BEAMER_EVENT.search(body, pos)
        if m is None:
            break
        if m.group(1) is not None:
            # \section or \subsection declaration
            level = m.group(1)
            title = m.group(2).strip()
            if level == "section":
                current_section = title
                current_subsection = None
            else:
                current_subsection = title
            pos = m.end()
            continue

        # `\begin{frame}` — find matching `\end{frame}`.
        frame_title = (m.group(3) or "").strip()
        end_m = RE_FRAME_END.search(body, m.end())
        if end_m is None:
            break
        frame_body = body[m.start() : end_m.end()]

        # Some frames use `\frametitle{...}` instead of the brace form.
        if not frame_title:
            ft = RE_FRAMETITLE_CMD.search(frame_body)
            if ft:
                frame_title = ft.group(1).strip()

        frames.append(
            BeamerFrame(
                section=current_section,
                subsection=current_subsection,
                title=frame_title,
                body=frame_body,
            )
        )
        pos = end_m.end()

    return frames


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def _run_pdftotext(pdf_path: Path, keep_page_breaks: bool) -> str:
    if not pdf_path.exists():
        return ""
    if shutil.which("pdftotext") is None:
        return ""
    args = ["pdftotext", "-layout"]
    if not keep_page_breaks:
        args.append("-nopgbrk")
    args += [str(pdf_path), "-"]
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        return result.stdout or ""
    except Exception:
        return ""


def pdftotext_full(pdf_path: Path) -> str:
    """Full text, with page breaks stripped — used for section-title matching."""
    return _run_pdftotext(pdf_path, keep_page_breaks=False)


def pdftotext_with_pages(pdf_path: Path) -> str:
    """Full text with form-feed (\\f) page markers preserved — used by the
    PDF-only fallback chunker to split pages."""
    return _run_pdftotext(pdf_path, keep_page_breaks=True)


_TOC_LINE_RE = re.compile(r"\.{3,}|\s\d+\s*$")


def _looks_like_toc_line(pdf_dump: str, idx: int) -> bool:
    """Return True if the match at `idx` sits on a ToC-style line
    (trailing dots-and-page-number, e.g. `Overview ........ 2`)."""
    line_start = pdf_dump.rfind("\n", 0, idx) + 1
    line_end = pdf_dump.find("\n", idx)
    if line_end == -1:
        line_end = len(pdf_dump)
    line = pdf_dump[line_start:line_end]
    return bool(_TOC_LINE_RE.search(line))


def slice_pdf_by_title(pdf_dump: str, title: str, next_title: str | None) -> str:
    """Find the first non-ToC occurrence of `title` in `pdf_dump` and return
    text up to the next section title (or up to 8000 chars)."""
    if not pdf_dump:
        return ""
    norm_title = re.sub(r"\s+", " ", title).strip().lower()
    if not norm_title:
        return ""
    lowered = pdf_dump.lower()

    # Walk all occurrences; skip any that look like ToC lines.
    search_from = 0
    idx = -1
    while True:
        found = lowered.find(norm_title, search_from)
        if found == -1:
            break
        if not _looks_like_toc_line(pdf_dump, found):
            idx = found
            break
        search_from = found + len(norm_title)
    if idx == -1:
        return ""

    end_idx = len(pdf_dump)
    if next_title:
        next_norm = re.sub(r"\s+", " ", next_title).strip().lower()
        # Again, skip ToC matches when looking for the next boundary.
        probe = idx + len(norm_title)
        while True:
            nxt = lowered.find(next_norm, probe)
            if nxt == -1:
                break
            if not _looks_like_toc_line(pdf_dump, nxt):
                end_idx = nxt
                break
            probe = nxt + len(next_norm)
    end_idx = min(end_idx, idx + 8000)
    return pdf_dump[idx:end_idx].strip()


# ---------------------------------------------------------------------------
# Chunk building
# ---------------------------------------------------------------------------

WEEK_RE = re.compile(r"Week[\s_]+(\d+)", re.IGNORECASE)


def week_from_filename(name: str) -> int | None:
    m = WEEK_RE.search(name)
    return int(m.group(1)) if m else None


def extract_document_title(tex: str) -> str | None:
    m = re.search(r"\\title\s*\{([^}]*)\}", tex)
    return m.group(1).strip() if m else None


def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


@dataclass
class Chunk:
    id: str
    source_type: str
    week: int | None
    title_full: str | None
    section: str
    subsection: str | None
    tex_path: str
    pdf_path: str
    tex_text: str
    pdf_text: str
    token_estimate: int = 0


def estimate_tokens(text: str) -> int:
    # Rough heuristic: 1 token ≈ 4 characters of English prose.
    return max(1, len(text) // 4)


def build_chunks_for_file(tex_path: Path, source_type: str) -> list[Chunk]:
    tex_raw = tex_path.read_text(encoding="utf-8", errors="replace")
    tex_clean = strip_comments(tex_raw)
    week = week_from_filename(tex_path.name)
    doc_title = extract_document_title(tex_raw)

    pdf_path = tex_path.with_suffix(".pdf")
    pdf_dump = pdftotext_full(pdf_path)

    rel_tex = str(tex_path.relative_to(SOURCE_ROOT))
    rel_pdf = str(pdf_path.relative_to(SOURCE_ROOT))

    chunks: list[Chunk] = []

    # Beamer decks get one chunk per frame (with the enclosing \section /
    # \subsection carried as metadata), so derivations don't get truncated
    # by the per-chunk char clip in the chat UI. Non-Beamer files (Notes,
    # Tutorials) still chunk at the \section / \subsection level.
    is_beamer = "\\begin{frame}" in tex_clean

    if is_beamer:
        frames = split_beamer_frames(tex_clean)
        frame_titles = [f.title for f in frames]
        for i, frame in enumerate(frames):
            title_clean = latex_to_text(frame.title) or frame.title or f"Frame {i + 1}"
            section_clean = latex_to_text(frame.section) if frame.section else None
            subsection_clean = (
                latex_to_text(frame.subsection) if frame.subsection else None
            )
            tex_text = latex_to_text(frame.body)

            # Boundary for the PDF slice: the next frame title that has one.
            next_title = None
            for j in range(i + 1, len(frames)):
                if frame_titles[j]:
                    next_title = frame_titles[j]
                    break
            pdf_text = slice_pdf_by_title(pdf_dump, title_clean, next_title)

            # `section` and `subsection` mirror the article-mode convention:
            # the deepest heading is the subsection label, the parent the
            # section label. For a frame inside a section, that means
            # section=<\section title>, subsection=<frame title>.
            if section_clean:
                section_label = section_clean
                subsection_label: str | None = subsection_clean or title_clean
            else:
                section_label = title_clean
                subsection_label = subsection_clean

            chunk_id = "-".join(
                filter(
                    None,
                    [
                        source_type,
                        f"week-{week}" if week is not None else None,
                        f"f{i + 1:03d}",
                        slugify(title_clean),
                    ],
                )
            )
            chunks.append(
                Chunk(
                    id=chunk_id,
                    source_type=source_type,
                    week=week,
                    title_full=doc_title,
                    section=section_label,
                    subsection=subsection_label,
                    tex_path=rel_tex,
                    pdf_path=rel_pdf,
                    tex_text=tex_text,
                    pdf_text=pdf_text,
                    token_estimate=estimate_tokens(tex_text),
                )
            )
        return chunks

    sections = split_sections(tex_clean)

    if sections:
        # Walk sections, keeping track of the most recent \section title for
        # subsection parents.
        current_section: str | None = None
        idx_counter = 0
        section_titles = [s.title for s in sections]
        for i, sec in enumerate(sections):
            title_clean = latex_to_text(sec.title) or sec.title
            if sec.level == "section":
                current_section = title_clean
                section_label = title_clean
                subsection_label = None
            else:  # subsection
                section_label = current_section or title_clean
                subsection_label = title_clean

            body_latex = sec.__dict__.get("body_text", "")
            tex_text = latex_to_text(body_latex)
            next_title = section_titles[i + 1] if i + 1 < len(sections) else None
            pdf_text = slice_pdf_by_title(pdf_dump, title_clean, next_title)

            idx_counter += 1
            chunk_id = "-".join(
                filter(
                    None,
                    [
                        source_type,
                        f"week-{week}" if week is not None else None,
                        f"s{idx_counter:02d}",
                        slugify(subsection_label or section_label),
                    ],
                )
            )
            chunks.append(
                Chunk(
                    id=chunk_id,
                    source_type=source_type,
                    week=week,
                    title_full=doc_title,
                    section=section_label,
                    subsection=subsection_label,
                    tex_path=rel_tex,
                    pdf_path=rel_pdf,
                    tex_text=tex_text,
                    pdf_text=pdf_text,
                    token_estimate=estimate_tokens(tex_text),
                )
            )
    return chunks


def build_chunks_from_pdf_only(pdf_path: Path, source_type: str) -> list[Chunk]:
    """Fallback chunker for folders that only have PDFs (no .tex source).
    Splits the pdftotext output on form-feed (page break) and emits one
    chunk per non-empty page."""
    dump = pdftotext_with_pages(pdf_path)
    if not dump:
        return []
    week = week_from_filename(pdf_path.name)
    rel_pdf = str(pdf_path.relative_to(SOURCE_ROOT))
    doc_title = pdf_path.stem  # e.g. "Week 2 Tutorial TA Copy"

    pages = dump.split("\f")
    chunks: list[Chunk] = []
    page_idx = 0
    for page in pages:
        page_text = page.strip()
        if len(page_text) < 80:
            continue  # cover / nearly-empty page
        page_idx += 1
        # Use the first non-empty line as a section label (truncated).
        first_line = next((ln.strip() for ln in page.splitlines() if ln.strip()), "")
        section = (first_line[:120] or f"Page {page_idx}")
        chunk_id = "-".join(filter(None, [
            source_type,
            f"week-{week}" if week is not None else None,
            f"p{page_idx:03d}",
            slugify(section),
        ]))
        chunks.append(Chunk(
            id=chunk_id,
            source_type=source_type,
            week=week,
            title_full=doc_title,
            section=section,
            subsection=None,
            tex_path="",
            pdf_path=rel_pdf,
            tex_text="",
            pdf_text=page_text,
            token_estimate=estimate_tokens(page_text),
        ))
    return chunks


def build_chunks_for_notebook(nb_path: Path, source_type: str) -> list[Chunk]:
    """Chunk a Jupyter notebook (.ipynb).

    Cells are grouped under the most recent Markdown heading (``#``/``##``/``###``);
    each group becomes one chunk whose text concatenates the Markdown prose and the
    code (fenced as ```python). There is no compiled PDF, so ``pdf_text`` is empty."""
    try:
        nb = json.loads(nb_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return []
    cells = nb.get("cells", [])
    week = week_from_filename(nb_path.name)
    rel = str(nb_path.relative_to(SOURCE_ROOT))

    heading_re = re.compile(r"^\#{1,3}\s+(.+?)\s*$", re.MULTILINE)

    # Document title: first H1 in the first markdown cell, else the filename stem.
    doc_title = nb_path.stem.replace("_", " ")
    for c in cells:
        if c.get("cell_type") == "markdown":
            m = re.search(r"^\#\s+(.+)$", "".join(c.get("source", [])), re.MULTILINE)
            if m:
                doc_title = m.group(1).strip()
            break

    groups: list[dict] = []
    current = {"section": doc_title, "parts": []}
    for c in cells:
        ctype = c.get("cell_type")
        src = "".join(c.get("source", [])).strip()
        if not src:
            continue
        if ctype == "markdown":
            heads = heading_re.findall(src)
            if heads:
                if current["parts"]:
                    groups.append(current)
                current = {"section": heads[-1].strip(), "parts": [src]}
            else:
                current["parts"].append(src)
        elif ctype == "code":
            current["parts"].append("```python\n" + src + "\n```")
    if current["parts"]:
        groups.append(current)

    chunks: list[Chunk] = []
    for i, g in enumerate(groups, 1):
        section = re.sub(r"[#*`>]", "", g["section"]).strip()[:120] or f"Cell group {i}"
        text = "\n\n".join(g["parts"]).strip()
        if len(text) < 40:
            continue
        chunk_id = "-".join(filter(None, [
            source_type,
            f"week-{week}" if week is not None else None,
            f"n{i:02d}",
            slugify(section),
        ]))
        chunks.append(Chunk(
            id=chunk_id,
            source_type=source_type,
            week=week,
            title_full=doc_title,
            section=section,
            subsection=None,
            tex_path=rel,
            pdf_path="",
            tex_text=text,
            pdf_text="",
            token_estimate=estimate_tokens(text),
        ))
    return chunks


def main() -> int:
    if not SOURCE_ROOT.exists():
        print(f"error: source root not found: {SOURCE_ROOT}", file=sys.stderr)
        return 1

    all_chunks: list[Chunk] = []
    for source_type, folder in SOURCE_TYPES.items():
        if not folder.exists():
            print(f"skip: {folder} not found")
            continue
        tex_files = sorted(folder.glob("*.tex"))
        tex_stems = {p.stem for p in tex_files}
        for tex_path in tex_files:
            file_chunks = build_chunks_for_file(tex_path, source_type)
            all_chunks.extend(file_chunks)
            print(
                f"  {source_type}/{tex_path.name}: {len(file_chunks)} chunks"
            )
        # Jupyter notebooks (.ipynb), e.g. the tutorial notebooks in Codes/.
        for nb_path in sorted(folder.glob("*.ipynb")):
            file_chunks = build_chunks_for_notebook(nb_path, source_type)
            all_chunks.extend(file_chunks)
            print(
                f"  {source_type}/{nb_path.name}: {len(file_chunks)} chunks (notebook)"
            )
        # Process any PDFs that have no matching .tex source.
        pdf_only = [p for p in sorted(folder.glob("*.pdf")) if p.stem not in tex_stems]
        for pdf_path in pdf_only:
            file_chunks = build_chunks_from_pdf_only(pdf_path, source_type)
            all_chunks.extend(file_chunks)
            print(
                f"  {source_type}/{pdf_path.name}: {len(file_chunks)} chunks (from PDF)"
            )

    payload = {
        "schema_version": 1,
        "generated_by": "scripts/build_chunks.py",
        "chunk_count": len(all_chunks),
        "chunks": [asdict(c) for c in all_chunks],
    }
    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    total_tokens = sum(c.token_estimate for c in all_chunks)
    print(
        f"\nwrote {OUTPUT_FILE.relative_to(REPO_ROOT)}: "
        f"{len(all_chunks)} chunks, ~{total_tokens:,} tokens total"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
