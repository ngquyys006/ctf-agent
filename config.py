"""Central runtime configuration (spec section 34).

Contains central NON-SECRET configuration only.
Secrets and environment-specific values live in .env (section 35), never here.

All paths are generated relative to the project root (the directory containing
this file). There are no hardcoded absolute paths.
"""

from pathlib import Path

# Project root: the directory containing this file.
BASE_DIR = Path(__file__).resolve().parent

# Memory system (sections 4, 7, 14).
# The Markdown files are the source of truth; memory.db is rebuildable metadata.
MEMORY_DIR = BASE_DIR / "memory"
KNOWLEDGE_DIR = MEMORY_DIR / "knowledge"
EXPERIENCE_DIR = MEMORY_DIR / "experiences"
DATABASE_PATH = MEMORY_DIR / "memory.db"

# Metadata catalog schema (spec section 15). Declared once here so every
# memory module opens the database the same way. `path` is UNIQUE, so each
# Markdown file maps to at most one catalog row.
DATABASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    tags TEXT,
    technique TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# Tools (sections 22, 26): scripts the Agent creates, then keeps or removes.
TOOLS_DIR = BASE_DIR / "tools"
TOOLS_SCRIPTS_DIR = TOOLS_DIR / "scripts"

# System prompt (section 29).
PROMPTS_DIR = BASE_DIR / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system.md"

# Execution limits (sections 24, 28).
DEFAULT_TIMEOUT = 30  # seconds; applied to every tool execution
MAX_OUTPUT_SIZE = 1_048_576  # bytes (1 MiB); stdout/stderr are truncated to this