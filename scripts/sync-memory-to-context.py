"""
scripts/sync-memory-to-context.py

Reads all memory files from the Claude memory directory for this project
and writes them into the ## Claude Working Rules section of CONTEXT.md.

Uses <!-- memory:start --> / <!-- memory:end --> markers so the replacement
is unambiguous regardless of what the memory files contain.

Run automatically by the Stop hook before each git commit.
Can also be run manually: python scripts/sync-memory-to-context.py
"""
import pathlib
import re
import sys

MEMORY_DIR = pathlib.Path.home() / ".claude" / "projects" / "d--dev-crucible" / "memory"
CONTEXT_FILE = pathlib.Path(__file__).parent.parent / "CONTEXT.md"

SKIP_FILES = {"MEMORY.md"}

MARKER_START = "<!-- memory:start -->"
MARKER_END   = "<!-- memory:end -->"

SECTION_HEADER = "## Claude Working Rules"

TYPE_ORDER  = ["feedback", "user", "project", "reference"]
TYPE_LABELS = {
    "feedback":  "### Feedback & Working Preferences",
    "user":      "### About the User",
    "project":   "### Project Context",
    "reference": "### References",
}


def parse_memory_file(path: pathlib.Path) -> dict | None:
    text = path.read_text(encoding="utf-8").strip()
    if not text.startswith("---"):
        return None

    parts = text.split("---", 2)
    if len(parts) < 3:
        return None

    frontmatter_raw, body = parts[1], parts[2].strip()

    meta: dict = {}
    for line in frontmatter_raw.strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()

    return {
        "name":        meta.get("name", path.stem),
        "type":        meta.get("type", "reference"),
        "description": meta.get("description", ""),
        "body":        body,
    }


def render_memory_block(memories: list[dict]) -> str:
    """Render all memory files into a block wrapped in markers."""
    by_type: dict[str, list] = {t: [] for t in TYPE_ORDER}
    for m in memories:
        t = m["type"] if m["type"] in by_type else "reference"
        by_type[t].append(m)

    lines = [MARKER_START, ""]

    for t in TYPE_ORDER:
        items = by_type[t]
        if not items:
            continue
        lines.append(TYPE_LABELS[t])
        lines.append("")
        for m in items:
            lines.append(f"**{m['name']}**  ")
            if m["description"]:
                lines.append(f"*{m['description']}*")
                lines.append("")
            lines.extend(m["body"].splitlines())
            lines.append("")

    lines.append(MARKER_END)
    return "\n".join(lines)


def ensure_section_with_markers(context: str) -> str:
    """
    Ensure CONTEXT.md has the ## Claude Working Rules section with markers.
    If the section doesn't exist at all, add it before ## How to Use This File.
    If it exists but has no markers, insert them after the section header line.
    """
    if SECTION_HEADER not in context:
        # Add entire section before How to Use, or at end
        placeholder = f"{SECTION_HEADER}\n\n{MARKER_START}\n{MARKER_END}\n"
        if "## How to Use This File" in context:
            context = context.replace(
                "## How to Use This File",
                f"{placeholder}\n---\n\n## How to Use This File",
            )
        else:
            context = context.rstrip() + f"\n\n---\n\n{placeholder}\n"
        return context

    if MARKER_START not in context:
        # Section exists but no markers yet — insert markers after header line
        header_pos = context.index(SECTION_HEADER)
        after_header = context.index("\n", header_pos) + 1
        # Skip any blank lines immediately after header
        insert_pos = after_header
        while insert_pos < len(context) and context[insert_pos] == "\n":
            insert_pos += 1
        # Find end of section (next ## heading or ---)
        rest = context[insert_pos:]
        end_match = re.search(r"^(##\s|---\s*$)", rest, re.MULTILINE)
        if end_match:
            section_body = rest[:end_match.start()].rstrip()
            after_section = rest[end_match.start():]
        else:
            section_body = rest.rstrip()
            after_section = ""
        context = (
            context[:insert_pos]
            + f"{MARKER_START}\n{section_body}\n{MARKER_END}\n\n"
            + after_section
        )

    return context


def sync():
    if not MEMORY_DIR.exists():
        print(f"Memory dir not found: {MEMORY_DIR}", file=sys.stderr)
        sys.exit(1)

    if not CONTEXT_FILE.exists():
        print(f"CONTEXT.md not found: {CONTEXT_FILE}", file=sys.stderr)
        sys.exit(1)

    # Load and parse memory files
    memories = []
    for path in sorted(MEMORY_DIR.glob("*.md")):
        if path.name in SKIP_FILES:
            continue
        parsed = parse_memory_file(path)
        if parsed:
            memories.append(parsed)

    if not memories:
        print("No memory files found -- CONTEXT.md unchanged.")
        return

    context = CONTEXT_FILE.read_text(encoding="utf-8")

    # Ensure section + markers exist
    context = ensure_section_with_markers(context)

    # Replace only what's between the markers
    # Use a lambda so Windows backslashes in new_block aren't treated as regex escapes
    new_block = render_memory_block(memories)
    context = re.sub(
        rf"{re.escape(MARKER_START)}.*?{re.escape(MARKER_END)}",
        lambda _: new_block,
        context,
        flags=re.DOTALL,
    )

    CONTEXT_FILE.write_text(context, encoding="utf-8")
    print(f"Synced {len(memories)} memory files -> CONTEXT.md")


if __name__ == "__main__":
    sync()
