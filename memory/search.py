"""Memory retrieval and catalog maintenance.

The read side of memory. It answers two questions: which stored items are
worth looking at (search) and what does one of them actually say (read). It
also owns maintenance of the SQLite catalog, because a catalog can only be
rebuilt by reading the Markdown files, which remain the source of truth.

Functions:
* search(query, memory_type=None, limit=5)
* read(reference)
* rebuild()

Search is targeted: it returns a ranked, limited list of candidates and never
loads all memory (spec sections 11, 32). A score is a retrieval aid only; the
Agent decides whether a candidate is actually relevant.
"""

import re
import sqlite3
from datetime import datetime, timezone

import config

# Allowed catalog `type` values (spec section 15).
MEMORY_TYPES = ("knowledge", "experience")

# Simple relevance ranking (spec section 33): exact title first, then
# technique, tags, keywords, substring - weighted by how much of the query is
# covered, so scores are graded instead of tied. No embeddings, no vector DB.
_SCORE_EXACT_TITLE = 1.0
_SCORE_TECHNIQUE = 0.35
_SCORE_TAG = 0.25
_SCORE_TECHNIQUE_KEYWORD = 0.15
_SCORE_TITLE_KEYWORD = 0.15
_SCORE_PATH_KEYWORD = 0.10
_SCORE_SUBSTRING = 0.05

_SELECT = "SELECT id, type, title, path, tags, technique FROM memories"
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


def _tokenize(text) -> list[str]:
    """Split text into lowercase alphanumeric tokens."""
    return [token for token in re.split(r"[^a-z0-9]+", str(text or "").lower()) if token]


def _parse_metadata(text: str) -> dict:
    """Extract title, tags, and technique from a Markdown memory document.

    Reads the first "## Metadata" section (Key: value lines, as composed by
    the writing modules) and falls back to the first H1 heading. Only the
    first Metadata section counts, so a body that repeats the heading can
    never overwrite the real metadata. Never raises: unusable values simply
    default to empty strings.
    """
    meta: dict[str, str] = {}
    heading: str | None = None
    in_metadata = False
    seen_metadata = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            name = line[3:].strip().lower()
            if name == "metadata" and not seen_metadata:
                in_metadata, seen_metadata = True, True
            else:
                in_metadata = False
            continue
        if in_metadata:
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip().lower()] = value.strip()
        elif heading is None and line.startswith("# "):
            heading = line[2:].strip()

    return {
        "title": meta.get("title") or heading or "",
        "tags": meta.get("tags", ""),
        "technique": meta.get("technique", ""),
    }


def _mtime(path) -> str:
    """Return the file modification time as an ISO 8601 UTC string."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return datetime.now(tz=timezone.utc).isoformat()


def _iter_documents():
    """Yield (type, file_path, relative_path) for every Markdown memory file."""
    for kind, directory, prefix in (
        ("knowledge", config.KNOWLEDGE_DIR, "knowledge"),
        ("experience", config.EXPERIENCE_DIR, "experiences"),
    ):
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.md")):
            yield kind, path, f"{prefix}/{path.relative_to(directory).as_posix()}"


def _document_exists(relative: str) -> bool:
    """Return True when the catalog entry still has its Markdown file."""
    return (config.MEMORY_DIR / relative).is_file()


def rebuild() -> int:
    """Rebuild the catalog from the Markdown files.

    The Markdown files are the source of truth; memory.db is derived metadata
    that can always be thrown away and rebuilt from disk (spec sections
    14, 39). This also repairs a catalog that disagrees with the files.
    Returns the number of indexed files. Corrupted or undecodable files are
    skipped, never fatal (spec section 38).
    """
    conn = _connect()
    try:
        conn.execute("DELETE FROM memories")
        indexed = 0
        for kind, path, relative in _iter_documents():
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            meta = _parse_metadata(text)
            stamp = _mtime(path)
            conn.execute(
                _UPSERT,
                (kind, meta["title"] or path.stem, relative,
                 meta["tags"], meta["technique"], stamp, stamp),
            )
            indexed += 1
        conn.commit()
    finally:
        conn.close()
    return indexed


def _heal() -> None:
    """Rebuild the catalog when it is empty but Markdown files exist.

    memory.db is derived data: if it is deleted or lost, memory must stay
    searchable without any manual step (spec sections 38, 39).
    """
    conn = _connect()
    try:
        count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    finally:
        conn.close()
    if count:
        return
    if any(True for _ in _iter_documents()):
        rebuild()


def _score(record: dict, query_lower: str, tokens: list[str]) -> float:
    """Score one catalog record against a query (spec section 33).

    Matches title, tags, technique and the record's own path, so a query
    naming the file (a challenge ID such as "xebec-ssti2-charfilter")
    still finds the record. The path is already stored in the catalog, so
    this adds recall without touching the Markdown files.
    """
    if not tokens:
        return 0.0
    title = (record.get("title") or "").lower()
    technique = (record.get("technique") or "").lower()
    tags = (record.get("tags") or "").lower()
    path = (record.get("path") or "").lower()

    # 1. Exact title match.
    if query_lower == title:
        return _SCORE_EXACT_TITLE

    score = 0.0
    total = len(tokens)
    # 2. Technique match.
    if query_lower in technique:
        score += _SCORE_TECHNIQUE
    # 3-5. Tag, keyword and path matches, weighted by query-token coverage.
    for field, weight in ((tags, _SCORE_TAG), (technique, _SCORE_TECHNIQUE_KEYWORD),
                          (title, _SCORE_TITLE_KEYWORD), (path, _SCORE_PATH_KEYWORD)):
        hits = sum(1 for token in tokens if token in set(_tokenize(field)))
        if hits:
            score += weight * (hits / total)
    # 6. Fallback substring match in tags/technique.
    if any(token in tags or token in technique for token in tokens):
        score += _SCORE_SUBSTRING
    return min(score, 1.0)


def search(query: str, memory_type: str | None = None, limit: int = 5) -> list[dict]:
    """Search memory and return ranked candidates.

    The query is matched against title, tags, and technique metadata only
    (the catalog stores no memory content). Records whose Markdown file no
    longer exists are skipped, so search never returns a dead entry.
    Returns records ordered by descending score, each with id, type, title,
    path, tags, technique, and score. An empty list means nothing matched -
    a valid outcome, not an error. The Agent makes the final judgment about
    whether a candidate is relevant.
    """
    if memory_type is not None and memory_type not in MEMORY_TYPES:
        raise ValueError(
            f"memory_type must be one of {MEMORY_TYPES} or None, got {memory_type!r}"
        )

    _heal()

    conn = _connect()
    try:
        if memory_type is None:
            rows = conn.execute(_SELECT).fetchall()
        else:
            rows = conn.execute(_SELECT + " WHERE type = ?", (memory_type,)).fetchall()
    finally:
        conn.close()

    query_lower = str(query or "").strip().lower()
    tokens = _tokenize(query_lower)

    scored = []
    for row in rows:
        record = {
            "id": row[0],
            "type": row[1],
            "title": row[2] or "",
            "path": row[3],
            "tags": row[4] or "",
            "technique": row[5] or "",
        }
        if not _document_exists(record["path"]):
            continue
        score = _score(record, query_lower, tokens)
        if score > 0.0:
            scored.append((score, record))

    # Highest score first; ties broken by record id for deterministic order.
    scored.sort(key=lambda item: (-item[0], item[1]["id"]))
    results = []
    for score, record in scored[: max(limit, 0)]:
        result = dict(record)
        result["score"] = round(score, 4)
        results.append(result)
    return results


def _normalized_name(reference: str) -> str:
    """Return the Markdown file name for a topic reference."""
    name = reference.strip()
    if not name.lower().endswith(".md"):
        name = f"{name}.md"
    return name


def _resolve(reference: str):
    """Resolve a reference to (type, file name), or (None, None).

    Accepts a memory-relative path ("knowledge/xss.md",
    "experiences/lab-001.md") or a bare Knowledge topic / Experience ID.
    A bare reference that exists as Knowledge wins over Experience.
    """
    text = str(reference).strip()
    if not text or ".." in text.split("/"):
        return None, None
    for prefix, kind in (("knowledge/", "knowledge"), ("experiences/", "experience")):
        if text.lower().startswith(prefix):
            name = _normalized_name(text[len(prefix):])
            if not name or "/" in name:
                return None, None
            return kind, name
    name = _normalized_name(text)
    if "/" in name:
        return None, None
    if (config.KNOWLEDGE_DIR / name).is_file():
        return "knowledge", name
    if (config.EXPERIENCE_DIR / name).is_file():
        return "experience", name
    return None, None


def read(reference) -> dict | None:
    """Read one Knowledge topic or Experience in full.

    `reference` is a memory-relative path, a bare Knowledge topic, or a bare
    Experience ID. Returns {"type", "path", "content"}, or None when the
    reference is missing, unreadable, or outside the memory directories.
    """
    if not isinstance(reference, str) or not reference.strip():
        return None
    kind, name = _resolve(reference)
    if kind is None:
        return None

    directory = config.KNOWLEDGE_DIR if kind == "knowledge" else config.EXPERIENCE_DIR
    target = directory / name
    try:
        target.resolve().relative_to(directory.resolve())
    except ValueError:
        return None
    if not target.is_file():
        return None
    try:
        content = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return {
        "type": kind,
        "path": f"{'knowledge' if kind == 'knowledge' else 'experiences'}/{name}",
        "content": content,
    }