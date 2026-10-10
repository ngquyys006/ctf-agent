# CTF-Agent

Local autonomous CTF-solving assistant in which **Agent is the only AI
reasoning engine**.

Agent is the brain. Memory and tools provide capabilities
to Agent. No other component reasons, decides, or solves challenges.

The authoritative specification is `CTF_Agent_Project_Design.md`.

---

## 1. Project purpose

Give one intelligent model — Agent — enough memory and tools to solve
CTF challenges autonomously and improve through accumulated experience:

* Observe a challenge and acknowledge what it understands.
* Search Knowledge and/or previous Experiences proactively with targeted
  queries before forming attack hypotheses.
* Reason about the vulnerability, select a tool, execute it safely, and
  analyze the result.
* Iterate when an approach fails; generate a temporary script when existing
  tools are insufficient; test it; keep it if it is reusable, remove it otherwise.
* Verify the final result before declaring success.
* Record the completed challenge as an Experience and update Knowledge only
  when a lesson is genuinely generalizable.

The system stays minimal: no extra AI agents, learning engines, strategy
engines, vector databases, or separate reasoning modules.

## 2. Architecture

```text
                             Agent
                              │
                    ┌─────────┼─────────┐
                    │         │
                    ▼         ▼
                 MEMORY      TOOLS
                    │         │
                    ▼         ▼
                 .md + DB     runner
                              + scripts/
```

| Component                 | Responsibility                                          |
| ------------------------- | ------------------------------------------------------- |
| Agent                     | Reasoning, recognition, planning, solving, learning decisions |
| `memory/search.py`        | Memory search, read, and catalog maintenance            |
| `memory/save_knowledge.py`| Create a new Knowledge topic                            |
| `memory/update_knowledge.py` | Update an existing Knowledge topic                    |
| `memory/save_experience.py` | Store a challenge Experience                          |
| `memory/memory.db`        | Searchable metadata/catalog (rebuildable)               |
| `memory/knowledge/`       | General reusable knowledge (Markdown)                   |
| `memory/experiences/`     | Specific challenge experiences (Markdown)               |
| `tools/runner.py`         | Tool scripts: list, create, run, remove                 |
| `tools/scripts/`          | The Agent's tool scripts, kept or removed per challenge |
| `config.py`               | Runtime configuration (non-secret)                      |
| `.env`                    | Secrets/environment values (gitignored)                 |
| `prompts/system.md`       | Instructions defining how Agent operates                |

No component other than Agent performs CTF reasoning.

## 3. Directory structure

```text
CTF-Agent/
├── README.md
├── config.py              # paths, catalog schema, execution limits
├── .env                   # secrets (gitignored); .env.example is the template
├── prompts/
│   └── system.md          # the 20 operating instructions for Agent
├── memory/
│   ├── search.py          # search(), read(), rebuild()
│   ├── save_knowledge.py  # create a new Knowledge topic
│   ├── update_knowledge.py# update an existing Knowledge topic
│   ├── save_experience.py # store a challenge Experience
│   ├── memory.db          # SQLite catalog (generated, rebuildable)
│   ├── knowledge/         # general reusable knowledge (*.md)
│   └── experiences/       # specific challenge experiences (*.md)
├── tools/
│   ├── runner.py          # list_tools/get/create/remove/run
│   └── scripts/           # the Agent's tool scripts (*.py)
└── tests/                 # unittest suite
```

## 4. Memory system

Memory holds two kinds of information, kept conceptually separate:
**Knowledge** (general, reusable) and **Experience** (specific past
challenges).

* **Markdown is the source of truth.** Knowledge and Experience content
  lives in human-readable Markdown files under `memory/knowledge/` and
  `memory/experiences/`.
* **`memory.db` is an index, not the memory.** It stores only metadata
  (type, title, path, tags, technique, timestamps) so memory can be
  searched without loading it. It initializes automatically on first use
  and can be rebuilt from the Markdown files at any time.
* **Targeted retrieval only.** Agent formulates targeted queries to
  search memory proactively on every challenge. Searches are ranked (exact title match first, then
  technique, tag, and keyword matches, weighted by how much of the query is
  covered) and limited (default 5 results). There is no operation that loads
  all memory.
* **Writes go through the memory modules.** Each writing module validates the
  name, prevents writes outside the memory directories, writes the Markdown
  file atomically, and writes the SQLite row in the same operation. Agent
  supplies all content; the modules never decide what the content means.
* **Disk and database cannot drift.** A write returns a record only when the
  file and its catalog row both exist; otherwise the write is undone and the
  call returns `None`. Search hides rows whose file is gone, and rebuilds the
  catalog automatically when `memory.db` is missing or empty.

## 5. Knowledge vs Experience

```text
Knowledge        "What generally works?"
Experience       "What happened in this particular challenge?"
```

**Knowledge** (`memory/knowledge/*.md`) is general and reusable: concepts,
detection methodology, dangerous sinks, lessons that apply to many challenges.
Knowledge grows by *updating existing topic files* (for example `xss.md`
gains new sections), not by spawning `xss1.md`, `xss2.md`, ... A new topic
file is created only when a topic is sufficiently independent.

**Experience** (`memory/experiences/*.md`, typically one file per challenge,
such as `lab-125.md`) records what happened in one specific challenge:
the summary, observations, hypothesis, attempts (including failed ones),
the successful approach, tools used, and lessons learned. Each solved
challenge gets its own Experience, identified by a unique challenge ID.

The distinction is enforced by behavior:

* Saving an Experience never silently overwrites an existing one. Revisiting
  a challenge means passing `overwrite=True` explicitly.
* Updating Knowledge touches an existing topic only; it refuses to create a
  new topic, so Knowledge never becomes a duplicate copy of every challenge.
* Metadata you omit is preserved, so an update can never silently destroy
  what made an item searchable.

## 6. Tool system

**The runner** (`tools/runner.py`) answers *"what tools are available?"* and
*"run this tool"*. The scripts themselves live in `tools/scripts/`, and each
one describes itself in its module docstring (first prose line becomes the
description; `Category:` and `Arguments:` lines supply the rest).

`run()` validates the request, builds a structured command (a list of
arguments — never shell string concatenation), applies a timeout, captures
stdout, stderr, exit code, and duration, and returns a structured result:

```python
{
    "success": True,
    "exit_code": 0,
    "stdout": "...",
    "stderr": "",
    "duration": 2.41,
}
```

Executions may only run scripts inside `tools/scripts/`. Every failure —
unknown tool, invalid arguments, invalid timeout, non-zero exit, crash,
timeout, oversized output — is returned as a result for Agent to analyze,
never raised.

## 7. Creating and keeping tool scripts

When existing tools are insufficient, Agent can create a script:

```text
Existing tools insufficient
        ↓
Agent creates a script -> tools/scripts/
        ↓
Agent runs and tests it
        ↓
   ┌────┴────┐
  fail     success
   │         │
 remove   evaluate: reusable later?
             │            │
           no            yes
             │             │
          remove         keep in tools/scripts/
```

* `create(name, content)` writes `tools/scripts/<name>.py`. Names must be
  safe (`^[A-Za-z0-9][A-Za-z0-9_-]*$`), the content must parse as Python,
  and an existing file is never overwritten.
* `remove(name)` deletes the script.
* `list_tools()` and `get(name)` report what is available.

Keeping or removing a script is an explicit Agent decision, made after the
challenge: keep only what is tested, general, documented, and free of
challenge-specific hardcoding.

## 8. Installation

Requires **Python 3.10 or newer**. The project uses only the Python
standard library — there are no third-party dependencies to install.

```bash
git clone <repository-url> CTF-Agent
cd CTF-Agent
cp .env.example .env   # optional; fill in secrets if your setup needs them
```

## 9. Configuration

`config.py` holds central, non-secret configuration. All paths are generated
relative to the project root; there are no hardcoded absolute paths.

| Setting               | Meaning                                            | Default        |
| --------------------- | -------------------------------------------------- | -------------- |
| `BASE_DIR`            | Project root (directory of `config.py`)            | —              |
| `MEMORY_DIR`          | Memory root                                        | `memory/`      |
| `KNOWLEDGE_DIR`       | Knowledge Markdown files                           | `memory/knowledge/` |
| `EXPERIENCE_DIR`      | Experience Markdown files                          | `memory/experiences/` |
| `DATABASE_PATH`       | SQLite index                                       | `memory/memory.db` |
| `DATABASE_SCHEMA`     | Metadata catalog schema                            | `memories` table |
| `TOOLS_DIR`           | Tools root                                         | `tools/`      |
| `TOOLS_SCRIPTS_DIR`   | The Agent's tool scripts                          | `tools/scripts/` |
| `SYSTEM_PROMPT_PATH`  | Agent's operating instructions                     | `prompts/system.md` |
| `DEFAULT_TIMEOUT`     | Per-execution timeout                              | 30 seconds     |
| `MAX_OUTPUT_SIZE`     | stdout/stderr truncation limit                     | 1 MiB          |

Secrets and environment-specific values (for example `API_KEY`,
`MODEL_NAME`) belong in `.env`, which is gitignored and never committed.
Nothing secret is stored in source code.

## 10. Running the system

Agent is the brain, so the system is driven by Agent through
explicit operations — there is no autonomous loop in Python. Load
`prompts/system.md` as the system prompt; it defines the complete solving
loop as 20 instructions:

1. Observe the challenge.
2. Acknowledge current understanding.
3. Decide whether memory is useful.
4. Search Knowledge for general techniques and payloads.
5. Search Experience for similar previous challenges.
6. Targeted searches only (never load all memory).
7. Analyze retrieved memory critically.
8. Form a hypothesis.
9. Select an appropriate tool.
10. Execute through the runner.
11. Analyze the result.
12. Update the hypothesis when necessary.
13. Iterate when not solved.
14. Create a tool script only when necessary.
15. Test created tool scripts.
16. Keep useful scripts and remove the rest.
17. Verify the final result before declaring success.
18. Save the challenge experience.
19. Extract reusable knowledge only when genuinely generalizable.
20. Verify memory persistence after writes.

The operations Agent uses (all CWD-independent):

| Area      | Operations                                                              |
| --------- | ----------------------------------------------------------------------- |
| Memory read | `search.search()`, `search.read()`, `search.rebuild()`                |
| Memory write | `save_knowledge.save_knowledge()`, `update_knowledge.update_knowledge()`, `save_experience.save_experience()` |
| Tools      | `runner.list_tools()`, `runner.get()`, `runner.create()`, `runner.remove()`, `runner.run()` |

A compact example of one solve:

```python
from memory import save_experience, save_knowledge, search, update_knowledge
from tools import runner

hits = search.search("DOM XSS innerHTML", memory_type="knowledge")
xss = search.read("xss")                                # read the relevant section
tool = runner.list_tools()[0]                           # select a tool
result = runner.run(tool["name"], [url])                # execute safely
# ... analyze, iterate, create/keep scripts as needed ...
save_experience.save_experience("lab-500", title, content)   # record the challenge
update_knowledge.update_knowledge("xss", body, tags="xss")  # generalize a lesson
```

Run the test suite:

```bash
python3 -m unittest discover -s tests -t .
```

## 11. Adding tool scripts

1. Create a script in `tools/scripts/`, for example `http_probe.py`.
2. Document it in the module docstring:

   ```python
   """Perform HTTP probing.

   Category: web
   Arguments: url, timeout
   """
   ```

3. Confirm `runner.list_tools()` describes it from the docstring.
   Underscore-prefixed filenames are helper files, not tools, and are
   skipped.

Scripts must be safe to execute: they are run with structured arguments,
a timeout, and captured output, but they are still ordinary Python.

## 12. Memory maintenance

* **The Markdown files are the memory.** Back them up by copying
  `memory/knowledge/` and `memory/experiences/`.
* **`memory.db` is rebuildable metadata.** Delete it freely; the next
  `search.search()` rebuilds it automatically. If it ever disagrees with the
  files, rebuild it explicitly with `search.rebuild()`, which re-extracts
  metadata from every Markdown file on disk.
* Search reads the database only; file content is read on demand. Corrupted
  Markdown is handled with safe defaults (undecodable files are skipped,
  never fatal).
* Keep Knowledge compact by updating existing topics; keep Experiences
  unique by challenge ID.

## 13. Development principles

1. **One brain.** Only Agent reasons. Do not create another AI
   reasoning component.
2. **Infrastructure does not think.** Python modules provide operations;
   they do not make CTF decisions.
3. **Markdown is human-readable memory.** Knowledge and Experience content
   stays in readable Markdown.
4. **SQLite is an index.** The database helps locate memory; it is not the
   primary storage.
5. **Targeted retrieval.** Never load all experiences into the model context.
6. **Experience is not Knowledge.** Do not blindly copy every challenge into
   Knowledge.
7. **Scripts are kept only when worth keeping.** Only useful, verified
   scripts stay in `tools/scripts/`; the rest are removed.
8. **Verify before success.** A tool returning successfully does not prove
   the challenge is solved; tool success and challenge success are different
   things.

The system must stay simple. The goal is not many intelligent modules — it
is giving one intelligent model enough memory and tools to solve CTF
challenges autonomously and improve through accumulated experience.
