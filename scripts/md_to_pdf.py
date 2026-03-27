"""
scripts/md_to_pdf.py — Markdown → PDF converter for Crucible research documents.

Uses pandoc + weasyprint engine. Automatically selects the correct CSS based on
the document type (research brief, assessment, findings, architecture, proposal).

Usage:
    python scripts/md_to_pdf.py <input.md> [output.pdf]
    python scripts/md_to_pdf.py forge/research/theory-brief-deepseek.md
    python scripts/md_to_pdf.py forge/research/deepseek-assessment.md

If output path is omitted, the PDF is written to the same directory as the
input file with the same stem: theory-brief-deepseek.md → theory-brief-deepseek.pdf.

CSS selection (auto):
    forge/research/*.md           → forge/research/forge-research.css
    md2pdf/* or ARCHITECTURE*.md  → proposal.css  (legacy)
    anything else                 → forge/research/forge-research.css

Integration:
    Called by /research-theory, /research-data, /forge-assessment, /forge-findings
    skills after writing the markdown document.

    Callable from Python:
        from scripts.md_to_pdf import convert
        pdf_path = convert("forge/research/theory-brief-deepseek.md")
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# ── CSS selection ──────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parent.parent

_CSS_RESEARCH = _REPO_ROOT / "forge" / "research" / "forge-research.css"
_CSS_LEGACY   = _REPO_ROOT / "proposal.css"

def _select_css(md_path: Path) -> Path:
    """Return the CSS file to use for this document."""
    parts = md_path.parts
    # Legacy: md2pdf/, ARCHITECTURE*.md, PROPOSAL.md, CONTEXT.md
    if md_path.stem.upper() in ("PROPOSAL", "CONTEXT", "DEVPLAN", "TODOS") or \
       "md2pdf" in parts or md_path.stem.startswith("ARCHITECTURE"):
        return _CSS_LEGACY
    return _CSS_RESEARCH


# ── Converter ─────────────────────────────────────────────────────────────────

def convert(
    md_path: str | Path,
    pdf_path: str | Path | None = None,
    css: str | Path | None = None,
    *,
    quiet: bool = False,
) -> Path:
    """
    Convert a Markdown file to PDF via pandoc + weasyprint.

    Parameters
    ----------
    md_path  : path to the input .md file
    pdf_path : output path (default: same dir and stem as md_path, .pdf extension)
    css      : CSS file to use (auto-selected if None)
    quiet    : suppress pandoc warnings in stderr

    Returns
    -------
    Path to the generated PDF.

    Raises
    ------
    FileNotFoundError  if md_path does not exist
    RuntimeError       if pandoc exits non-zero
    """
    md_path = Path(md_path).resolve()
    if not md_path.exists():
        raise FileNotFoundError(f"Input file not found: {md_path}")

    if pdf_path is None:
        pdf_path = md_path.with_suffix(".pdf")
    pdf_path = Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    css_path = Path(css).resolve() if css else _select_css(md_path)
    if not css_path.exists():
        raise FileNotFoundError(f"CSS file not found: {css_path}")

    cmd = [
        "pandoc",
        str(md_path),
        "-o", str(pdf_path),
        "--pdf-engine=weasyprint",
        f"--css={css_path}",
        "--standalone",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"pandoc failed (exit {result.returncode}):\n{result.stderr}"
        )

    if not quiet and result.stderr.strip():
        # Print weasyprint warnings to stderr but don't fail
        for line in result.stderr.splitlines():
            if "WARNING" in line or "Error" in line:
                print(f"  [pdf] {line}", file=sys.stderr)

    return pdf_path


# ── CLI entry point ────────────────────────────────────────────────────────────

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
