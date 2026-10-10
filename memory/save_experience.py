"""Save a challenge Experience.

An Experience records what actually happened in one specific challenge:
observations, hypothesis, attempts (including the ones that failed), the
successful approach, and the lessons (spec section 9). Each challenge gets its
own file named after a unique challenge ID.

Function:
* save_experience(exp_id, title, content, tags=None, technique=None,
                  source=None, challenge_type=None, overwrite=False)

Consistency contract
--------------------
Same contract as save_knowledge: the caller supplies the body, this module
owns the header, and a record is returned only when the file and its catalog
row agree. On failure the previous content is restored. A duplicate ID is
refused rather than silently overwritten; revisiting a challenge is an
explicit decision made by passing overwrite=True (spec section 40).
"""

import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone

import config

MEMORY_TYPE = "experience"

# Challenge IDs become single, flat, filesystem-safe file stems.
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


def _experience_name(exp_id) -> str | None:
    """Validate a challenge ID and return its Markdown file name, or None."""
    if not isinstance(exp_id, str):
        return None
    name = exp_id.strip()
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


def _document(exp_id: str, title: str, content: str, source: str,
              challenge_type: str, tags: str, technique: str) -> str:
    """Compose the Experience document (spec section 9 structure)."""
    body = _strip_leading_header(content)
    lines = [f"# {title}", "", "## Metadata", "", f"ID: {exp_id}", f"Title: {title}"]
    if source:
        lines.append(f"Source: {source}")
    if challenge_type:
        lines.append(f"Type: {challenge_type}")
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
    """Read the tags and technique already stored for a challenge.

    Metadata the caller omits is preserved rather than blanked, so revisiting
    a challenge can never silently destroy what made it searchable.
    """
    try:
        row = conn.execute(
            "SELECT tags, technique FROM memories WHERE path = ?", (relative,)
        ).fetchone()
    except sqlite3.Error:
        row = None
    return (row[0] or "", row[1] or "") if row else ("", "")


def _store(conn, relative: str, title: str, tags: str, technique: str) -> dict | None:
    """Write the catalog row and return the record, or None on failure."""
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


def _rollback(relative: str, path, previous) -> None:
    """Undo an incomplete write: remove a new file, restore an updated one."""
    try:
        if previous is None:
            path.unlink(missing_ok=True)
        else:
            _write_atomic(path, previous)
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


def save_experience(exp_id, title, content, tags=None, technique=None,
                    source=None, challenge_type=None, overwrite=False) -> dict | None:
    """Store one challenge Experience and update its catalog row.

    `exp_id` is the unique challenge ID and becomes the file name. `content`
    is the Markdown body this module stores under a Metadata section it
    composes itself. Returns the stored catalog record (id, type, title,
    path, tags, technique), or None when the ID is invalid, already used
    without overwrite=True, or the write could not be completed. `tags` and
    `technique` you omit keep their current values; pass them again only to
    change them.

    Save what a future challenge would actually benefit from: how it was
    solved, what failed along the way, and what to avoid. Do not store every
    attempt or every payload.
    """
    name = _experience_name(exp_id)
    if name is None or not isinstance(content, str) or not content.strip():
        return None

    identifier = name[:-3]
    heading = _text(title) or identifier
    relative = f"experiences/{name}"
    target = config.EXPERIENCE_DIR / name

    if target.exists() and not overwrite:
        return None

    previous = None
    if target.is_file():
        try:
            previous = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            previous = None

    conn = _connect()
    try:
        stored_tags, stored_technique = _previous_metadata(conn, relative)
        tags_text = _text(tags) or stored_tags
        technique_text = _text(technique) or stored_technique

        document = _document(identifier, heading, content, _text(source),
                             _text(challenge_type), tags_text, technique_text)
        if not _write_atomic(target, document):
            return None
        record = _store(conn, relative, heading, tags_text, technique_text)
    finally:
        conn.close()

    if record is None or not target.is_file():
        _rollback(relative, target, previous)
        return None
    return record