"""
scripts/md_to_pdf.py — Markdown → PDF converter for Crucible research documents.

Primary engine: markdown + xhtml2pdf (pure Python, no system dependencies).
Fallback: pandoc --pdf-engine=weasyprint (if pandoc is on PATH).

Usage:
    python scripts/md_to_pdf.py <input.md> [output.pdf]

CSS selection (auto):
    forge/research/*.md           → forge/research/forge-research.css
    md2pdf/* or ARCHITECTURE*.md  → proposal.css  (legacy)
    anything else                 → forge/research/forge-research.css

Integration:
    Called by assessment_generator.py and skill scripts after writing MD documents.

    Callable from Python:
        from scripts.md_to_pdf import convert
        pdf_path = convert("forge/research/iran-assessment.md")
"""
from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_CSS_RESEARCH = _REPO_ROOT / "forge" / "research" / "forge-research.css"
_CSS_LEGACY   = _REPO_ROOT / "proposal.css"


def _select_css(md_path: Path) -> Path:
    parts = md_path.parts
    if md_path.stem.upper() in ("PROPOSAL", "CONTEXT", "DEVPLAN", "TODOS") or \
       "md2pdf" in parts or md_path.stem.startswith("ARCHITECTURE"):
        return _CSS_LEGACY
    return _CSS_RESEARCH


def _embed_images(html: str, base_dir: Path) -> str:
    """Replace local image src paths with base64 data URIs so xhtml2pdf renders them."""
    import re
    def replace_src(m: re.Match) -> str:
        src = m.group(1)
        # Skip already-embedded or remote URLs
        if src.startswith("data:") or src.startswith("http"):
            return m.group(0)
        img_path = Path(src) if Path(src).is_absolute() else base_dir / src
        if img_path.exists():
            suffix = img_path.suffix.lower().lstrip(".")
            mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif", "svg": "svg+xml"}.get(suffix, "png")
            data = base64.b64encode(img_path.read_bytes()).decode()
            return f'src="data:image/{mime};base64,{data}"'
        return m.group(0)
    return re.sub(r'src="([^"]+)"', replace_src, html)


def _convert_xhtml2pdf(md_path: Path, pdf_path: Path, css_path: Path) -> None:
    """Convert MD → PDF via markdown + xhtml2pdf (pure Python)."""
    import markdown as md_lib
    from xhtml2pdf import pisa

    md_text = md_path.read_text(encoding="utf-8")
    html_body = md_lib.markdown(
        md_text,
        extensions=["tables", "fenced_code", "nl2br"],
    )

    css_text = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<style>{css_text}</style>
</head><body>
{html_body}
</body></html>"""

    # Embed images as base64 so xhtml2pdf finds them
    html = _embed_images(html, md_path.parent)

    with open(pdf_path, "wb") as fout:
        result = pisa.CreatePDF(html, dest=fout, encoding="utf-8")

    if result.err:
        raise RuntimeError(f"xhtml2pdf error: {result.err}")


def _convert_pandoc(md_path: Path, pdf_path: Path, css_path: Path) -> None:
    """Fallback: pandoc + weasyprint (requires pandoc on PATH)."""
    cmd = [
        "pandoc", str(md_path),
        "-o", str(pdf_path),
        "--pdf-engine=weasyprint",
        f"--css={css_path}",
        "--standalone",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"pandoc failed (exit {result.returncode}):\n{result.stderr}")


def convert(
    md_path: str | Path,
    pdf_path: str | Path | None = None,
    css: str | Path | None = None,
    *,
    quiet: bool = False,
) -> Path:
    """
    Convert a Markdown file to PDF.

    Parameters
    ----------
    md_path  : path to the input .md file
    pdf_path : output path (defaults to same dir/stem as md_path, .pdf extension)
    css      : CSS file to use (auto-selected if None)
    quiet    : suppress warnings

    Returns
    -------
    Path to the generated PDF.
    """
    md_path = Path(md_path).resolve()
    if not md_path.exists():
        raise FileNotFoundError(f"Input file not found: {md_path}")

    if pdf_path is None:
        pdf_path = md_path.with_suffix(".pdf")
    pdf_path = Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    css_path = Path(css).resolve() if css else _select_css(md_path)

    # Try xhtml2pdf first (no system deps), then pandoc as fallback
    try:
        _convert_xhtml2pdf(md_path, pdf_path, css_path)
        return pdf_path
    except Exception as e1:
        if not quiet:
            print(f"  [pdf] xhtml2pdf failed: {e1} — trying pandoc", file=sys.stderr)

    try:
        _convert_pandoc(md_path, pdf_path, css_path)
        return pdf_path
    except Exception as e2:
        raise RuntimeError(f"All PDF engines failed.\n  xhtml2pdf: {e1}\n  pandoc: {e2}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/md_to_pdf.py <input.md> [output.pdf]")
        sys.exit(1)

    md_path = Path(sys.argv[1])
    pdf_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    try:
        out = convert(md_path, pdf_path)
        print(f"PDF written: {out}")
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
