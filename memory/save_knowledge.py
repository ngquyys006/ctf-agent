"""Create a new Knowledge topic.

Knowledge is general, reusable understanding (spec section 8). This module
writes exactly one topic file and keeps the SQLite catalog in step with it.
It never overwrites an existing topic: an existing topic is changed through
update_knowledge, so Knowledge cannot silently rot and cannot grow a family
of duplicate files such as xss1.md, xss2.md (spec sections 20, 40).

Function:
* save_knowledge(topic, content, tags=None, technique=None)

Consistency contract
--------------------
The caller supplies the body; this module owns the document header, so the
file always carries a complete Metadata section and the catalog row can be
built straight from the arguments - no parsing, no guessing. A call returns
a record only when BOTH the file and its catalog row exist. If the catalog
row cannot be written, the file is removed again and the call returns None,
so disk and database never disagree (spec sections 13, 17).
"""

import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone

import config

MEMORY_TYPE = "knowledge"

# Topics are single, flat, filesystem-safe file stems.
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


def _store(conn, relative: str, title: str, tags: str, technique: str) -> dict | None:
    """Write the catalog row and return the record, or None on failure."""
    try:
        conn.execute(_UPSERT, (MEMORY_TYPE, title, relative, tags, technique, _now(), _now()))
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


def _rollback(relative: str, path) -> None:
    """Undo a write that could not be completed, keeping disk and catalog in step."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        conn = _connect()
        try:
            conn.execute("DELETE FROM memories WHERE path = ?", (relative,))
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        pass


def save_knowledge(topic, content, tags=None, technique=None) -> dict | None:
    """Create a new Knowledge topic from general, reusable content.

    `topic` is a single flat name ("xss", or "xss.md"); `content` is the
    Markdown body this module stores under a title and Metadata section it
    composes itself. `tags` and `technique` are searchable metadata and may
    be a string or a list.

    Returns the stored catalog record (id, type, title, path, tags,
    technique), or None when the topic is invalid, already exists, or the
    write could not be completed. An existing topic is never overwritten -
    use update_knowledge, or pick a genuinely new topic name.
    """
    name = _topic_name(topic)
    if name is None or not isinstance(content, str) or not content.strip():
        return None

    relative = f"knowledge/{name}"
    target = config.KNOWLEDGE_DIR / name
    if target.exists():
        return None

    title = name[:-3]
    document = _document(title, content, _text(tags), _text(technique))
    if not _write_atomic(target, document):
        return None

    conn = _connect()
    try:
        record = _store(conn, relative, title, _text(tags), _text(technique))
    finally:
        conn.close()

    if record is None or not target.is_file():
        _rollback(relative, target)
        return None
    return record