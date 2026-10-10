"""The Agent's tool scripts: list, create, run, and remove.

The Agent writes a script only when existing capabilities are not enough
(spec sections 22, 26). There is one script directory and no promotion step:
after the challenge the Agent keeps the scripts that earned their place and
removes the rest (spec section 27).

Every script describes itself in its module docstring:

    \"\"\"Scan a URL for reflection.

    Category: web
    Arguments: url, timeout
    \"\"\"

The first prose line becomes the description. Keyword arguments must be a
list - never build a shell command by string concatenation.

Functions:
* list_tools()
* get(name)
* create(name, content)
* remove(name)
* run(name, args=None, timeout=None)

Safety boundaries (spec section 28): structured subprocess arguments with no
shell, an execution timeout, an output size limit, and a hard restriction on
which scripts may run. Only scripts that exist in tools/scripts/ can be run;
failures are returned for the Agent to analyze, never raised.
"""

import ast
import os
import re
import subprocess
import sys
import time

import config

# Script names are simple, safe file stems (letters, digits, "_", "-").
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _script(name) -> "os.PathLike | None":
    """Return the script path for a tool name, or None when the name is unsafe."""
    if not isinstance(name, str):
        return None
    safe = name.strip()
    if _SAFE_NAME.fullmatch(safe) is None:
        return None
    return config.TOOLS_SCRIPTS_DIR / f"{safe}.py"


def _docstring_metadata(path) -> dict:
    """Read description, category, and arguments from the module docstring."""
    metadata: dict = {}
    try:
        source = path.read_text(encoding="utf-8")
        docstring = ast.get_docstring(ast.parse(source)) or ""
    except (OSError, SyntaxError, ValueError, UnicodeDecodeError):
        return metadata

    description = ""
    for raw_line in docstring.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        key, separator, value = line.partition(":")
        key = key.strip().lower()
        if separator and key in ("description", "category", "arguments"):
            value = value.strip()
            if key == "description":
                description = value
            elif key == "category":
                metadata["category"] = value
            else:
                metadata["arguments"] = [
                    item.strip() for item in value.split(",") if item.strip()
                ]
        elif not description:
            description = line
    if description:
        metadata["description"] = description
    return metadata


def _record(name: str, path) -> dict:
    """Build a tool's metadata record."""
    metadata = _docstring_metadata(path)
    return {
        "name": name,
        "description": metadata.get("description", ""),
        "category": metadata.get("category"),
        "arguments": metadata.get("arguments"),
        "script_path": str(path.relative_to(config.BASE_DIR)),
    }


def list_tools() -> list[dict]:
    """List the tool scripts available, sorted by name.

    Returns one metadata record per script. Files whose name starts with "_"
    are helper files, not tools, and are skipped. Nothing is executed.
    """
    try:
        config.TOOLS_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        paths = sorted(config.TOOLS_SCRIPTS_DIR.glob("*.py"))
    except OSError:
        return []
    return [
        _record(path.stem, path)
        for path in paths
        if not path.stem.startswith("_")
    ]


def get(name) -> dict | None:
    """Get one tool's metadata record, or None when there is no such script."""
    path = _script(name)
    if path is None or not path.is_file():
        return None
    return _record(path.stem, path)


def create(name, content) -> dict | None:
    """Write a new tool script into tools/scripts/ and describe it.

    `content` is the script source; its module docstring supplies the
    description, category, and arguments (see this module's docstring).
    Returns the tool's metadata record, or None when the name is unsafe, the
    content is empty or not valid Python, a script of that name already
    exists, or the write fails. An existing script is never overwritten.
    """
    path = _script(name)
    if path is None or not isinstance(content, str) or not content.strip():
        return None
    if path.exists():
        return None
    try:
        ast.parse(content)
    except (SyntaxError, ValueError):
        return None
    try:
        config.TOOLS_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        # write_text follows the umask; tool scripts are meant to be readable.
        os.chmod(path, 0o644)
    except OSError:
        return None
    return _record(path.stem, path)


def remove(name) -> bool:
    """Delete a tool script the Agent no longer needs.

    Returns True when a script was deleted, False when there was none.
    """
    path = _script(name)
    if path is None or not path.is_file():
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True


def _normalize_args(args) -> list[str] | None:
    """Validate arguments: a flat sequence of scalars, one argv entry each."""
    if args is None:
        return []
    if isinstance(args, (str, bytes, dict)) or not isinstance(args, (list, tuple)):
        return None
    normalized = []
    for arg in args:
        if not isinstance(arg, (str, int, float, bool)):
            return None
        normalized.append(str(arg))
    return normalized


def _resolve(path):
    """Resolve a script path, or None when it is not permitted to run."""
    try:
        resolved = path.resolve()
        resolved.relative_to(config.TOOLS_SCRIPTS_DIR.resolve())
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def _failure(error: str, duration: float = 0.0) -> dict:
    """Build a structured failure result (spec section 24)."""
    return {
        "success": False,
        "exit_code": None,
        "stdout": "",
        "stderr": error,
        "duration": round(duration, 2),
    }


def _decode(data) -> str:
    """Decode subprocess output as UTF-8, replacing errors."""
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def _truncate(text: str) -> str:
    """Limit output size to config.MAX_OUTPUT_SIZE bytes."""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= config.MAX_OUTPUT_SIZE:
        return text
    return encoded[: config.MAX_OUTPUT_SIZE].decode("utf-8", errors="replace") + "\n[output truncated]"


def run(name, args=None, timeout=None) -> dict:
    """Run a tool script safely and return a structured result.

    The result always has the shape from spec section 24:

        {"success": bool, "exit_code": int | None,
         "stdout": str, "stderr": str, "duration": float}

    `timeout` overrides config.DEFAULT_TIMEOUT seconds. Validation and
    execution failures are captured as success=False rather than raised, so
    the Agent can analyze them. Tool success says nothing about whether the
    challenge is solved.
    """
    if not isinstance(name, str) or not name.strip():
        return _failure("Invalid tool name.")

    path = _script(name.strip())
    if path is None or not path.is_file():
        return _failure(f"Tool not found: {name.strip()}")

    normalized = _normalize_args(args)
    if normalized is None:
        return _failure("Invalid arguments: expected a list of scalar values.")

    if timeout is None:
        timeout = config.DEFAULT_TIMEOUT
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        return _failure("Invalid timeout: expected a positive number of seconds.")

    resolved = _resolve(path)
    if resolved is None:
        return _failure(f"Script not permitted or missing: {path}")

    start = time.monotonic()
    try:
        completed = subprocess.run(
            [sys.executable, str(resolved)] + normalized,
            capture_output=True,
            timeout=timeout,
            cwd=config.BASE_DIR,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - start
        stderr = _truncate(_decode(exc.stderr))
        return {
            "success": False,
            "exit_code": None,
            "stdout": _truncate(_decode(exc.stdout)),
            "stderr": (stderr + "\n" if stderr else "")
                      + f"[execution timed out after {timeout} seconds]",
            "duration": round(duration, 2),
        }
    except OSError as exc:
        return _failure(f"Execution failed: {exc}", time.monotonic() - start)

    return {
        "success": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": _truncate(_decode(completed.stdout)),
        "stderr": _truncate(_decode(completed.stderr)),
        "duration": round(time.monotonic() - start, 2),
    }