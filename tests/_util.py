"""Shared helpers for the test suite.

The tests run against the real project directories. Each test module
snapshots memory and tools before running, removes every artifact it
created afterwards, and rebuilds the catalog so the project is left with a
memory database that matches the Markdown files on disk.
"""

import shutil

import config
from memory import search


def snapshot():
    """Record the files that exist before a test module runs."""
    return {
        "knowledge": {path.name for path in config.KNOWLEDGE_DIR.glob("*.md")},
        "experiences": {path.name for path in config.EXPERIENCE_DIR.glob("*.md")},
        "scripts": {path.name for path in config.TOOLS_SCRIPTS_DIR.glob("*.py")},
        "database": config.DATABASE_PATH.exists(),
    }


def restore(state):
    """Remove test artifacts and leave the catalog consistent with disk."""
    for directory, key in (
        (config.KNOWLEDGE_DIR, "knowledge"),
        (config.EXPERIENCE_DIR, "experiences"),
        (config.TOOLS_SCRIPTS_DIR, "scripts"),
    ):
        for path in directory.glob("*"):
            if path.is_file() and path.suffix == ".md" and path.name not in state[key]:
                path.unlink()
            elif path.is_file() and path.suffix == ".py" and path.name not in state[key]:
                path.unlink()
    if state["database"]:
        search.rebuild()
    else:
        for suffix in ("", "-shm", "-wal"):
            candidate = config.DATABASE_PATH.with_name(
                config.DATABASE_PATH.name + suffix
            )
            if candidate.exists():
                candidate.unlink()
    for cache in (
        config.BASE_DIR / "__pycache__",
        config.BASE_DIR / "tests" / "__pycache__",
        config.BASE_DIR / "memory" / "__pycache__",
        config.BASE_DIR / "tools" / "__pycache__",
    ):
        if cache.is_dir():
            shutil.rmtree(cache)