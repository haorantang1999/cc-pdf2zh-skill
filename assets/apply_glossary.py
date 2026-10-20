#!/usr/bin/env python3
"""Apply a glossary to an already-translated PDF (post-processing).

Use this when the translator (typically the default Google one) produced
unwanted translations for specific terms — e.g. "LLM" rendered as "法学硕士".
The script erases each occurrence of the source term and writes the target
term in its place, preserving the surrounding layout.

Two things this script gets right that a naive "draw a white box" does not:

1. The original glyphs are genuinely removed from the content stream via
   redaction annotations, not merely covered. A white rectangle leaves the
   old text intact underneath: it stays selectable, copy-pastable and findable
   by full-text search, so readers get BOTH terms.

2. The erased region is widened to fit the *replacement* text. CJK->Latin
   replacements are usually longer than the term they replace (三维掩码 is 4
   glyphs, "3D mask" is noticeably wider), so a mask sized to the original
   leaves the old word sticking out and the two overlap.

Glossary file
-------------
    # comment
    source -> target

Lines starting with '#' are ignored. Matching is literal and case-sensitive.
For best results, list longer phrases before shorter ones that contain them.

Usage
-----
    python apply_glossary.py translated.pdf -g glossary.txt -o out.pdf

Requires PyMuPDF (`uv pip install pymupdf` — the pdf2zh venv already has it).
The CJK font is auto-discovered from the babeldoc font cache, common system
fonts, or the PDF2ZH_CJK_FONT env var.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pymupdf

# Candidate CJK fonts, tried in order. The first that exists wins.
# The babeldoc cache is created automatically on the first pdf2zh run.
_CANDIDATES: list[str] = [
    os.environ.get("PDF2ZH_CJK_FONT", ""),
    "~/.cache/babeldoc/fonts/SourceHanSansCN-Regular.ttf",
    "~/.cache/babeldoc/fonts/SourceHanSerifCN-Regular.ttf",
    "~/.cache/babeldoc/fonts/LXGWWenKaiGB-Regular.ttf",
    "~/.cache/babeldoc/fonts/SourceHanSansSC-Regular.otf",
    "~/Library/Caches/babeldoc/fonts/SourceHanSansCN-Regular.ttf",
    "~/AppData/Local/babeldoc/fonts/SourceHanSansCN-Regular.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
]


def find_cjk_font() -> Path | None:
    for raw in _CANDIDATES:
        if not raw:
            continue
        p = Path(os.path.expanduser(raw))
        if p.is_file():
            return p
    # Last resort: scan babeldoc caches for any font file.
    for cache in (Path.home() / ".cache" / "babeldoc" / "fonts",
                  Path.home() / "AppData" / "Local" / "babeldoc" / "fonts"):
        if not cache.is_dir():
            continue
        for p in cache.iterdir():
            if p.suffix.lower() in (".ttf", ".otf", ".ttc"):
                return p
    return None


def parse_glossary(path: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for sep in ("->", "=>", "=", ","):
            if sep in line:
                src, tgt = line.split(sep, 1)
                src, tgt = src.strip(), tgt.strip()
                if src and tgt and src != tgt:
                    pairs.append((src, tgt))
                break
        else:
            print(f"warning: skipped unparseable line: {raw!r}", file=sys.stderr)
    return pairs


def _fit_scale(
    target: str,
    fontsize: float,
    font: "pymupdf.Font",
    avail_w: float,
) -> float:
    """Largest scale <= 1 that fits `target` into `avail_w` (never scales up)."""
    w = font.text_length(target, fontsize=fontsize)
    if w <= 0 or w <= avail_w:
        return 1.0
    return max(0.6, avail_w / w)


def apply_glossary(
    pdf: Path,
    glossary: list[tuple[str, str]],
    output: Path,
    cjk_font: Path,
) -> tuple[int, int]:
    """Returns (total_replacements, pages_touched).

    Each page is processed in two phases, because PyMuPDF's
    ``apply_redactions`` also removes anything already drawn inside the
    redaction rectangle — including text inserted earlier in the same loop:

        phase 1  queue redact annots for every hit, apply them  (removal)
        phase 2  draw the replacement terms                     (insert)

    Doing both in one pass silently deletes the replacements again.
    """
    doc = pymupdf.open(str(pdf))
    total = 0
    pages_touched: set[int] = set()
    cjk = pymupdf.Font(fontfile=str(cjk_font))

    for pi, page in enumerate(doc):
        jobs: list[tuple[pymupdf.Rect, str, float]] = []

        for source, target in glossary:
            if not source:
                continue
            rects = page.search_for(source)
            if not rects:
                continue
            pages_touched.add(pi)
            for rect in rects:
                fontsize = max(6.0, min(14.0, rect.height * 0.9))
                # Shrink rather than let a much longer replacement run into
                # the neighbouring column.
                scale = _fit_scale(target, fontsize, cjk, rect.width)
                fontsize *= scale
                new_w = cjk.text_length(target, fontsize=fontsize)
                # Erase wide enough for the replacement, not just the original.
                erase = pymupdf.Rect(rect.x0, rect.y0,
                                     max(rect.x1, rect.x0 + new_w + 1.0),
                                     rect.y0 + rect.height)
                jobs.append((erase, target, fontsize))
                total += 1

        if not jobs:
            continue

        # Phase 1: genuinely remove the source glyphs.
        for erase, _, _ in jobs:
            page.add_redact_annot(erase)
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )

        # Phase 2: write the replacements at the original baselines.
        page.insert_font(fontname=f"g{pi}", fontfile=str(cjk_font))
        for erase, target, fontsize in jobs:
            page.insert_text(
                (erase.x0, erase.y0 + erase.height * 0.78),
                target,
                fontname=f"g{pi}",
                fontsize=fontsize,
                color=(0, 0, 0),
            )

    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output), garbage=4, deflate=True)
    doc.close()
    return total, len(pages_touched)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Patch a translated PDF with a glossary (find/replace).",
    )
    ap.add_argument("pdf", type=Path, help="Translated PDF to patch")
    ap.add_argument("-g", "--glossary", type=Path, required=True,
                    help="Glossary file (one 'source -> target' per line)")
    ap.add_argument("-o", "--output", type=Path, required=True,
                    help="Output PDF path")
    args = ap.parse_args()

    cjk = find_cjk_font()
    if cjk is None:
        print(
            "error: no CJK font found. Run pdf2zh once (it downloads fonts to "
            "the babeldoc cache), install a Source Han / Noto CJK font, or set "
            "the PDF2ZH_CJK_FONT env var to a font file.",
            file=sys.stderr,
        )
        return 2

    pairs = parse_glossary(args.glossary)
    if not pairs:
        print("error: glossary is empty", file=sys.stderr)
        return 1
    print(f"loaded {len(pairs)} glossary entries from {args.glossary}")
    print(f"CJK font: {cjk}")

    n, p = apply_glossary(args.pdf, pairs, args.output, cjk)
    print(f"replaced {n} occurrence(s) on {p} page(s) -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
