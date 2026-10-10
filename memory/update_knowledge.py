"""Update an existing Knowledge topic.

Knowledge grows by extending topics that already exist, not by creating a new
near-duplicate file for every discovery (spec sections 8, 20, 40). This module
therefore refuses to create anything: a topic that does not exist is reported
as missing, and creating it is save_knowledge's job.

Function:
* update_knowledge(topic, content, tags=None, technique=None)

Consistency contract
--------------------
Same contract as save_knowledge: the caller supplies the body, this module
owns the header, and a record is returned only when the file and its catalog
row agree. On failure the previous content is restored, so a failed update
never damages what was already stored. Pass the topic's tags and technique
again when updating, so its searchable metadata is not lost.
"""

import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone

import config

MEMORY_TYPE = "knowledge"

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_UPSERT = (
    "INSERT INTO memories (type, title, path, tags, technique, created_at, updated_at)"
    " VALUES (?, ?, ?, ?, ?, ?, ?)"
    " ON CONFLICT(path) DO UPDATE SET"
    "   type = excluded.type, title = excluded.title, tags = excluded.tags,"
    "   technique = excluded.technique, updated_at = excluded.updated_at"
)


def _connect() -> sqlite3.Connection:
    """Open the metadata catalog, creating the schema when missing."""
    config.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.executescript(config.DATABASE_SCHEMA)
    conn.commit()
    return conn


def _now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


def _text(value) -> str:
    """Convert a metadata value to a storable single-line string.

    Whitespace runs are collapsed to single spaces, so metadata can never
    break out of its "Key: value" line in the document's Metadata section.
    That is what keeps the Markdown file and the catalog row describing the
    same thing after a rebuild.
    """
    if isinstance(value, (list, tuple, set)):
        raw = ", ".join(str(item).strip() for item in value if str(item).strip())
    else:
        raw = "" if value is None else str(value)
    return " ".join(raw.split())


def _topic_name(topic) -> str | None:
    """Validate a topic and return its Markdown file name, or None."""
    if not isinstance(topic, str):
        return None
    name = topic.strip()
    if name.lower().endswith(".md"):
        name = name[:-3].strip()
    return f"{name}.md" if _SAFE_NAME.fullmatch(name) else None


def _strip_leading_header(content: str) -> str:
    """Remove a caller-supplied '# Title' + '## Metadata' prologue.

    This module always composes the header itself, so a caller that also
    wrote one would otherwise produce a file with two titles and two
    Metadata sections. Only headers at the very start are removed, and the
    body that follows is kept verbatim. If stripping would leave nothing
    behind, the content is returned unchanged.
    """
    body = content.strip()
    while True:
        lines = body.splitlines()
        start = 0
        while start < len(lines) and not lines[start].strip():
            start += 1
        if start >= len(lines) or not lines[start].startswith("# "):
            return body
        meta = None
        for position in range(start + 1, len(lines)):
            if lines[position].strip() == "## Metadata":
                meta = position
                break
            if lines[position].startswith("#"):
                return body  # a section started: this is not a header prologue
        if meta is None:
            return body
        end = meta + 1
        while end < len(lines) and not lines[end].startswith("#"):
            end += 1
        remainder = "\n".join(lines[end:]).strip()
        if not remainder:
            return body
        body = remainder


def _document(title: str, content: str, tags: str, technique: str) -> str:
    """Compose the Knowledge document: title, Metadata section, body."""
    body = _strip_leading_header(content)
    lines = [f"# {title}", "", "## Metadata", "", f"Title: {title}"]
    if tags:
        lines.append(f"Tags: {tags}")
    if technique:
        lines.append(f"Technique: {technique}")
    lines.extend(["", body, ""])
    return "\n".join(lines)


def _write_atomic(path, text: str) -> bool:
    """Write the file atomically so it is never left half-written."""
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
        # mkstemp creates 0600; memory files are meant to be readable.
        os.chmod(path, 0o644)
        return True
    except OSError:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass
        return False


def _created_at(conn, relative: str) -> str:
    """Keep the original creation time of an existing row."""
    try:
        row = conn.execute(
            "SELECT created_at FROM memories WHERE path = ?", (relative,)
        ).fetchone()
    except sqlite3.Error:
        row = None
    return row[0] if row and row[0] else _now()


def _previous_metadata(conn, relative: str) -> tuple[str, str]:
    """Read the tags and technique already stored for a topic.

    Metadata the caller omits is preserved rather than blanked, so updating
    a topic can never silently destroy what made it searchable.
    """
    try:
        row = conn.execute(
            "SELECT tags, technique FROM memories WHERE path = ?", (relative,)
        ).fetchone()
    except sqlite3.Error:
        row = None
    return (row[0] or "", row[1] or "") if row else ("", "")


def _store(conn, relative: str, title: str, tags: str, technique: str) -> dict | None:
    """Update the catalog row and return the record, or None on failure."""
    try:
        conn.execute(
            _UPSERT,
            (MEMORY_TYPE, title, relative, tags, technique,
             _created_at(conn, relative), _now()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, type, title, path, tags, technique FROM memories WHERE path = ?",
            (relative,),
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return {"id": row[0], "type": row[1], "title": row[2], "path": row[3],
            "tags": row[4] or "", "technique": row[5] or ""}


def update_knowledge(topic, content, tags=None, technique=None) -> dict | None:
    """Replace the content of an EXISTING Knowledge topic.

    Returns the stored catalog record, or None when the topic is invalid,
    does not exist, or the write could not be completed. A missing topic is
    never created automatically: call save_knowledge for a genuinely new
    topic. `tags` and `technique` you omit keep their current values; pass
    them again only to change them.
    """
    name = _topic_name(topic)
    if name is None or not isinstance(content, str) or not content.strip():
        return None

    relative = f"knowledge/{name}"
    target = config.KNOWLEDGE_DIR / name
    if not target.is_file():
        return None

    try:
        previous = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        previous = None

    title = name[:-3]
    conn = _connect()
    try:
        stored_tags, stored_technique = _previous_metadata(conn, relative)
        tags_text = _text(tags) or stored_tags
        technique_text = _text(technique) or stored_technique

        if not _write_atomic(target, _document(title, content, tags_text, technique_text)):
            return None
        record = _store(conn, relative, title, tags_text, technique_text)
    finally:
        conn.close()

    if record is None or not target.is_file():
        # Restore what was already stored; a failed update must not damage it.
        if previous is not None:
            _write_atomic(target, previous)
        return None
    return record