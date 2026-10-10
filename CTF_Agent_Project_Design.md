# CTF-Agent — Complete Project Design Specification

## 1. Project Goal

Build a local autonomous CTF-solving assistant in which **Agent is the only AI reasoning engine**.

The system must allow Agent to:

1. Observe a CTF challenge.
2. Understand and acknowledge what it sees.
3. Decide whether existing memory is useful.
4. Search reusable knowledge and/or previous challenge experiences.
5. Reason about the vulnerability and possible attack paths.
6. Select available tools.
7. Execute tools safely.
8. Analyze tool results.
9. Iterate when the current approach fails.
10. Create a script when existing tools are insufficient.
11. Test the created script.
12. Keep the scripts that proved reusable and remove the rest.
13. Determine when the challenge is solved.
14. Record the completed challenge as an Experience.
15. Extract genuinely reusable knowledge and update Knowledge when appropriate.

The system must remain minimal.

Do NOT introduce unnecessary AI agents, learning engines, strategy engines, vector databases, or separate reasoning modules.

---

# 2. Core Architecture

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

The fundamental rule is:

> Agent is the brain.
> Everything else provides capabilities to AAgent.

---

# 3. Responsibilities

| Component             | Responsibility                                                |
| --------------------- | ------------------------------------------------------------- |
| Agent                 | Reasoning, recognition, planning, solving, learning decisions |
| `search.py`           | Memory search, read, and catalog maintenance                  |
| `save_knowledge.py`   | Create a new Knowledge topic                                 |
| `update_knowledge.py` | Update an existing Knowledge topic                           |
| `save_experience.py`  | Store a challenge Experience                                 |
| `memory.db`          | Searchable metadata/catalog                                   |
| `knowledge/*.md`     | General reusable knowledge                                    |
| `experiences/*.md`   | Specific challenge experiences                                |
| `runner.py`          | Tool scripts: list, create, run, remove                       |
| `tools/scripts/`     | The Agent's tool scripts, kept or removed per challenge      |
| `config.py`          | Runtime configuration                                         |
| `.env`               | Secrets/environment values                                    |
| `prompts/system.md`  | Instructions defining how Agent operates                      |

No component other than Agent should perform CTF reasoning.

---

# 4. Required Project Structure

```text
CTF-Agent/
│
├── README.md
├── config.py
├── .env
│
├── prompts/
│   └── system.md
│
├── tools/
│   ├── runner.py
│   └── scripts/
│       └── ...
│
└── memory/
    ├── search.py
    ├── save_knowledge.py
    ├── update_knowledge.py
    ├── save_experience.py
    ├── memory.db
    │
    ├── knowledge/
    │   └── *.md
    │
    └── experiences/
        └── *.md
```

Do not create:

```text
agent/
learner.py
strategy.py
reasoning_engine.py
vector_db/
```

unless explicitly requested later.

---

# 5. Agent
Agent is the only intelligent component.

It is responsible for all decisions.

Agent must be able to decide:

* What the challenge appears to involve.
* Whether memory should be searched.
* Whether to search Knowledge.
* Whether to search Experience.
* What query to use.
* Which memories are relevant.
* Which tool should be used.
* Whether the result is useful.
* Whether the current hypothesis is wrong.
* Whether another attempt is needed.
* Whether a new script is necessary.
* Whether a created script is worth keeping.
* Whether the challenge is solved.
* What should be stored as Experience.
* What information is sufficiently general to become Knowledge.

No Python module should attempt to reproduce these decisions.

---

# 6. Acknowledge

"Acknowledge" is an operation performed by Agent.

It is NOT a separate module.

The purpose is to let Agent explicitly identify what it currently understands from the challenge.

Example:

```text
Observed:
- URL contains a search parameter.
- User-controlled value appears in HTML.
- JavaScript reads the value.
- Value reaches innerHTML.

Acknowledge:
- Possible DOM XSS.
- Relevant concepts: DOM XSS, innerHTML.
```

This acknowledgement becomes the basis for memory searches and planning.

Do not implement:

```text
acknowledge.py
acknowledger.py
```

Agent performs this reasoning itself.

---

# 7. Memory System

The memory system has two types of information:

```text
Knowledge
Experience
```

They must remain conceptually separate.

---

# 8. Knowledge

Knowledge contains general and reusable understanding.

Examples:

```text
memory/knowledge/
├── xss.md
├── sqli.md
├── csrf.md
├── ssrf.md
├── file-upload.md
└── ...
```

Knowledge should normally grow by updating existing topic files rather than creating unnecessary files.

For example:

```text
xss.md
```

may contain:

```text
# XSS

## Reflected XSS

...

## Stored XSS

...

## DOM XSS

...

## innerHTML

...

## document.write

...

## jQuery

...

## AngularJS

...

## Detection methodology

...

## Lessons learned

...
```

The exact number of Knowledge files is not fixed.

Create a new Knowledge file only when a topic is sufficiently independent.

---

# 9. Experience

Experience represents what happened in a specific challenge.

Normally one challenge gets one Experience file.

Example:

```text
memory/experiences/
├── lab-001.md
├── lab-002.md
├── lab-003.md
└── ...
```

An Experience should contain enough information for Agent to understand how a similar challenge was solved.

Recommended structure:

```markdown
# Challenge Experience

## Metadata

ID:
Title:
Source:
Type:
Tags:

## Challenge Summary

...

## Initial Observations

...

## Acknowledgement

...

## Hypothesis

...

## Attempts

### Attempt 1

Action:
Result:
Analysis:

### Attempt 2

Action:
Result:
Analysis:

## Successful Approach

...

## Tools Used

...

## Final Result

...

## Failed Approaches

...

## Lessons Learned

...

## Reusable Knowledge

...
```

The exact content is decided by Agent.

---

# 10. Knowledge vs Experience

The distinction is:

```text
Knowledge
"What generally works?"

Experience
"What happened in this particular challenge?"
```

Example:

### Experience

```text
lab-125.md

The challenge used:
location.hash
      ↓
JavaScript
      ↓
innerHTML

The successful payload was ...

An earlier attempt failed because ...
```

### Knowledge

```text
xss.md

When investigating DOM XSS:

1. Find the source.
2. Track the data flow.
3. Identify the sink.
4. Determine whether the value is attacker-controlled.
5. Test the appropriate context.
```

Experience preserves the concrete history.

Knowledge preserves the generalized lesson.

---

# 11. How Agent Uses Memory

Agent must NOT automatically load all memory.

It decides whether memory is useful.

The normal decision flow is:

```text
New challenge
     ↓
Agent observes
     ↓
Acknowledge
     ↓
Does general knowledge help?
     │
     ├── yes → search Knowledge
     │
     └── no
     
Does a previous challenge look relevant?
     │
     ├── yes → search Experience
     │
     └── no
```

It may also use both.

Example:

```text
New challenge
     ↓
Agent
     ↓
Search Knowledge/xss.md
     +
Search relevant Experiences
     ↓
Reason
```

There must be no rule saying:

```text
Every challenge must load Knowledge and Experience.
```

That would unnecessarily increase context size.

---

# 12. How Agent Recognizes a Familiar Challenge

Agent does NOT magically remember challenge IDs.

It first analyzes the current challenge.

Example:

```text
Current challenge:

location.hash
    ↓
JavaScript
    ↓
innerHTML
```

Agent may acknowledge:

```text
Possible vulnerability:
DOM XSS

Relevant concepts:
- location.hash
- innerHTML
- client-side JavaScript
```

It then creates a memory query such as:

```text
DOM XSS innerHTML location.hash
```

The memory system searches previous experiences.

Possible results:

```text
lab-125.md
lab-231.md
lab-412.md
```

Agent reads the relevant results and determines:

```text
lab-125 is highly similar.
```

Therefore:

> The memory system finds candidates. Agent determines whether they are actually similar.

---

# 13. Memory Search Flow

The memory search flow must be:

```text
Agent
    ↓
search.py
    ↓
memory.db
    ↓
candidate memory records
    ↓
search.read() reads the selected .md file
    ↓
Agent
```

`search.py` must NOT decide which vulnerability is correct.

It only helps locate relevant memory.

---

# 14. memory.db

`memory.db` is a SQLite metadata/index database.

It is NOT the main memory content.

The actual memory remains in Markdown files.

Example metadata:

```text
id
type
title
tags
technique
path
created_at
updated_at
```

Example:

```text
125 | experience | DOM XSS innerHTML | dom-xss,innerHTML | xss | experiences/lab-125.md
```

For Knowledge:

```text
12 | knowledge | XSS | xss,dom-xss | xss | knowledge/xss.md
```

The database exists to make memory searchable and manageable.

---

# 15. Suggested Database Schema

Implement a simple SQLite database.

Suggested table:

```sql
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
```

Allowed `type` values:

```text
knowledge
experience
```

Tags may be stored as a simple serialized string initially.

Do not introduce a complex database system.

---

# 16. search.py

`search.py` provides memory search, reading, and catalog support.

Responsibilities:

* Search memory records.
* Filter by type.
* Search by title.
* Search by tags.
* Search by technique.
* Return ranked candidates.
* Read one Knowledge topic or Experience in full.
* Rebuild the metadata catalog from the Markdown files.

It must NOT:

* Reason about vulnerabilities.
* Decide what a challenge means.
* Decide whether a memory is useful.
* Solve challenges.
* Generate knowledge.

Example API:

```python
search(
    query: str,
    memory_type: str | None = None,
    limit: int = 5
)
```

Example result:

```python
[
    {
        "id": 125,
        "type": "experience",
        "title": "DOM XSS via innerHTML",
        "path": "experiences/lab-125.md",
        "score": 0.94
    }
]
```

The score is only a search relevance score.

Agent makes the final judgment.

---

# 17. The four memory modules

Memory is written through four modules, each owning one operation. There is
no separate indexer: the module that writes a file also writes its metadata
row, so the catalog cannot fall behind the files.

### `search.py` — read side

```text
search(query, memory_type=None, limit=5)
read(reference)
rebuild()
```

### `save_knowledge.py` — create a new Knowledge topic

```text
save_knowledge(topic, content, tags=None, technique=None)
```

### `update_knowledge.py` — change an existing Knowledge topic

```text
update_knowledge(topic, content, tags=None, technique=None)
```

### `save_experience.py` — store a challenge Experience

```text
save_experience(exp_id, title, content, tags=None, technique=None,
                source=None, challenge_type=None, overwrite=False)
```

The modules must:

* Validate input and reject unsafe names.
* Prevent writes outside the memory directories.
* Create missing directories.
* Write Markdown atomically.
* Write the SQLite metadata row in the same operation.
* Keep DB metadata synchronized with files.
* Return a record only when both the file and its row exist; otherwise undo
  the write and report failure.

The modules do NOT decide what the content means.

Agent supplies the content.

---

# 18. Example Memory Read

Agent:

```text
Search for:
DOM XSS innerHTML
```

search:

```text
search.search(...)
```

Catalog:

```text
Search memory.db
```

Result:

```text
lab-125.md
lab-231.md
lab-412.md
```

search.read() then reads the selected Markdown files.

Agent receives:

```text
Experience 125:
...

Experience 231:
...
```

Agent evaluates them.

---

# 19. Example Memory Write

After solving:

```text
Agent
     ↓
"I should preserve this experience."
     ↓
save_experience.save_experience(...)
     ↓
memory/experiences/lab-500.md
     +
memory.db metadata
```

If Agent identifies a genuinely reusable rule:

```text
Agent
     ↓
"This is general knowledge."
     ↓
update_knowledge.update_knowledge(...)
     ↓
memory/knowledge/xss.md
     +
memory.db update
```

The module only performs the storage operation.

---

# 20. Learning Behavior

There is NO separate learner.

Learning is performed by Agent through memory updates.

After a challenge:

```text
Challenge solved
      ↓
Agent asks:
"What should I preserve?"
      ↓
      ┌──────────────────────┐
      │                      │
      ▼                      ▼
Specific history       General lesson
      │                      │
      ▼                      ▼
Experience.md          Knowledge.md
```

Not every experience must produce new Knowledge.

Only generalizable information should be added to Knowledge.

This prevents Knowledge from becoming a duplicate copy of every challenge.

---

# 21. Memory Growth Example

After solving 100 challenges:

```text
memory/
│
├── knowledge/
│   ├── xss.md
│   ├── sqli.md
│   ├── csrf.md
│   ├── ssrf.md
│   └── file-upload.md
│
├── experiences/
│   ├── lab-001.md
│   ├── lab-002.md
│   ├── ...
│   └── lab-100.md
│
├── memory.db
├── search.py
├── save_knowledge.py
├── update_knowledge.py
└── save_experience.py
```

Knowledge remains relatively compact.

Experience can grow to thousands of files.

The database allows Agent to find relevant experiences without loading them all.

---

# 22. Tools

Tools provide execution capabilities.

Agent chooses which tool to use.

The tool system contains:

```text
runner.py
scripts/
```

---

# 23. runner.py

`runner.py` manages the Agent's tool scripts. It answers two questions:

> What tools are available?
> Run this tool.

The scripts themselves live in `tools/scripts/` and describe themselves in
their module docstring:

```text
name
description
category
script_path
arguments
```

Example:

```text
http_probe.py

"""Perform HTTP probing.

Category: web
Arguments: url
"""
```

Responsibilities:

* List available tools.
* Get tool metadata.
* Create a tool script.
* Remove a tool script.
* Execute a tool.

It does NOT:

* Analyze results.
* Select attack strategy.

---

# 24. Running a tool

Running a tool is a separate responsibility from describing it.

1. Validate requested tool.
2. Validate arguments.
3. Build the command safely.
4. Execute it.
5. Apply timeout.
6. Capture stdout.
7. Capture stderr.
8. Capture exit code.
9. Capture execution duration.
10. Return a structured result.

Example:

```python
{
    "success": True,
    "exit_code": 0,
    "stdout": "...",
    "stderr": "",
    "duration": 2.41
}
```

The runner must NOT decide:

```text
"This is XSS."
"This payload is correct."
"The challenge is solved."
```

Those are Agent decisions.

---

# 25. Tool Scripts

Tool scripts live here:

```text
tools/scripts/
```

Examples:

```text
http_probe.py
url_fetch.py
custom_xss_test.py
...
```

Agent may create a new script when existing tools are insufficient.

---

# 26. The Tool Lifecycle

Workflow:

```text
Existing tools insufficient
        ↓
Agent creates script
        ↓
tools/scripts/
        ↓
Agent runs script
        ↓
Analyze result
        ↓
   ┌────┴────┐
   │         │
  fail     success
   │         │
   ▼         ▼
 remove   evaluate
              │
      useful beyond this challenge?
           │       │
          yes      no
           │        │
           ▼        ▼
         keep     remove
```

Keeping or removing a script must be an explicit decision by Agent.

A script is created with a safe name, is never overwritten, and must parse
as valid Python.

---

# 27. Keeping a Tool

When a script succeeds, Agent should decide:

```text
Is this script reusable beyond this challenge?
```

If yes:

```text
Keep it in tools/scripts/ and describe it properly.
```

If no:

```text
Remove it with runner.remove(name).
```

There is no second tool directory and no promotion step: a script either
earns its place in `tools/scripts/` or it is deleted.

---

# 28. Safety Boundaries

The runner must not allow arbitrary uncontrolled filesystem operations.

At minimum:

* Restrict executable tool paths to `tools/scripts/`.
* Apply execution timeouts.
* Limit output size.
* Capture failures.
* Avoid shell injection through unsafe string concatenation.
* Prefer structured subprocess arguments.
* Validate script names.
* Prevent directory traversal.
* Do not allow scripts to overwrite project files unless explicitly permitted.
* Keep tool execution isolated as much as practical.

Isolation is provided by the runner rather than by a separate sandbox
directory: scripts are restricted to `tools/scripts/`, validated before they
run, and executed as a subprocess under a timeout with a capped output. A
script is not confined from the filesystem it runs on, so Agent must not keep
a script that writes outside what the challenge needs.

---

# 29. System Prompt

`prompts/system.md` defines how Agent operates.

It should instruct Agent to:

```text
1. Observe the challenge.
2. Acknowledge current understanding.
3. Decide whether memory is useful.
4. Search Knowledge when general knowledge is needed.
5. Search Experience when previous concrete attempts may help.
6. Do not load all memory.
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
```

Important instruction:

> Never assume that a retrieved Experience is correct for the current challenge. Treat it as evidence, not truth.

---

# 30. Challenge-Solving Loop

The overall operation is:

```text
START
  │
  ▼
OBSERVE
  │
  ▼
ACKNOWLEDGE
  │
  ▼
MEMORY NEEDED?
  │
  ├── No ────────────────┐
  │                       │
  └── Yes                 │
       │                  │
       ▼                  │
   SEARCH MEMORY          │
       │                  │
       ▼                  │
   READ RELEVANT          │
   KNOWLEDGE/EXPERIENCE   │
       │                  │
       └──────────┬───────┘
                  ▼
                THINK
                  │
                  ▼
                 PLAN
                  │
                  ▼
          SELECT TOOL
                  │
                  ▼
               EXECUTE
                  │
                  ▼
                RESULT
                  │
                  ▼
               ANALYZE
                  │
             solved?
             /      \
           no        yes
           │          │
           ▼          ▼
      update plan   VERIFY
           │          │
           └──→───────┘
                      │
                      ▼
               SAVE EXPERIENCE
                      │
                      ▼
          GENERALIZABLE LESSON?
                 /        \
               no          yes
               │             │
               │             ▼
               │       UPDATE KNOWLEDGE
               │             │
               └──────┬──────┘
                      ▼
                     END
```

---

# 31. Memory Decision Logic

Agent should reason about memory rather than follow a rigid always-search rule.

Recommended behavior:

### Case A — Known general technique

```text
Challenge:
SQL injection

Agent:
"I need a refresher on UNION column counting."

→ Search Knowledge.
```

### Case B — Strong similarity to a previous challenge

```text
Challenge:
DOM XSS through innerHTML.

Agent:
"This resembles a challenge I solved before."

→ Search Experience.
```

### Case C — Difficult challenge

```text
Attempts:
1. failed
2. failed
3. failed

Agent:
"I may benefit from previous concrete experiences."

→ Search Experience.
```

### Case D — Both are useful

```text
Knowledge:
Understand the vulnerability.

Experience:
See how a similar challenge was solved.

→ Search both.
```

---

# 32. Important Memory Principle

Do not implement:

```text
if challenge:
    load_all_knowledge()
    load_all_experiences()
```

This is incorrect.

Instead:

```text
challenge
   ↓
Agent analyzes
   ↓
Agent decides what information is needed
   ↓
targeted memory search
```

This keeps the context manageable.

---

# 33. Search Ranking

The initial implementation should remain simple.

Search relevance can use:

1. Exact title matches.
2. Technique matches.
3. Tag matches.
4. Keyword matches.
5. Full-text matches against the Markdown body.
6. Optional SQLite FTS ranking.

Signals 1-5 are implemented. They are weighted so that metadata outranks the
body: a memory tagged or titled with the query ranks above one that merely
mentions the words. Full-text matters because tags are chosen once, when the
memory is written, while the terms that identify the next challenge are
whatever the target happens to expose. The catalog still stores metadata
only; bodies are read to score them and cached against file mtime, and are
never returned to Agent.

Equal scores are ordered by `updated_at`, most recent first. Ties are common
once a vulnerability class has several Experience files, and there is no
relevance difference among them; returning the freshest first means the
Agent reads a superseded attempt last rather than first. Score still
outranks recency, so a weaker match never displaces a stronger one.

Example:

Query:

```text
DOM XSS innerHTML
```

Possible results:

```text
1. lab-125.md   score 0.94
2. lab-231.md   score 0.87
3. lab-412.md   score 0.71
```

The score is only a retrieval aid.

Agent must make the final decision.

Do not introduce embeddings/vector databases unless the simple system later proves insufficient.

---

# 34. Configuration

`config.py` should contain central non-secret configuration.

Example:

```python
BASE_DIR
MEMORY_DIR
KNOWLEDGE_DIR
EXPERIENCE_DIR
DATABASE_PATH

TOOLS_DIR
TOOLS_SCRIPTS_DIR
SYSTEM_PROMPT_PATH

DEFAULT_TIMEOUT
MAX_OUTPUT_SIZE
```

Paths must be generated relative to the project root.

Avoid hardcoded absolute paths.

---

# 35. Environment Variables

`.env` is for secrets and environment-specific settings.

Examples:

```text
API_KEY=...
MODEL_NAME=...
```

Do not put secrets directly into source code.

Do not commit `.env`.

Provide `.env.example` if appropriate.

---

# 36. README.md

README must explain:

1. Project purpose.
2. Architecture.
3. Directory structure.
4. Memory system.
5. Knowledge vs Experience.
6. Tool system.
7. Temporary tool generation.
8. Installation.
9. Configuration.
10. Running the system.
11. Adding tool scripts.
12. Memory maintenance.
13. Development principles.

README should describe the system but should not duplicate implementation logic unnecessarily.

---

# 37. Implementation Principles

The implementation must follow these principles.

## Principle 1 — One Brain

Only Agent reasons.

Do not create another AI reasoning component.

## Principle 2 — Infrastructure Does Not Think

Python modules provide operations.

They do not make CTF decisions.

## Principle 3 — Markdown Is Human-Readable Memory

Actual Knowledge and Experience content must remain readable Markdown.

## Principle 4 — SQLite Is an Index

The DB helps locate memory.

It is not the primary storage of the knowledge itself.

## Principle 5 — Targeted Retrieval

Never load all experiences into the model context.

## Principle 6 — Experience Is Not Knowledge

Do not blindly copy every challenge into Knowledge.

## Principle 7 — Scripts Are Kept Only When Worth Keeping

Only useful verified scripts are kept in tools/scripts/.

## Principle 8 — Verify Before Success

Agent must not declare a challenge solved solely because a tool returned successfully.

Tool success and challenge success are different things.

---

# 38. Error Handling

The system must handle:

* Missing memory files.
* Corrupted Markdown.
* Missing DB.
* DB/index mismatch.
* Tool not found.
* Invalid tool arguments.
* Tool timeout.
* Tool execution failure.
* Generated script failure.
* API/model failure.
* Empty search results.
* Duplicate memory entries.

If `memory.db` is missing, the system should be able to initialize it.

If the DB and Markdown files become inconsistent, the indexer should be able to rebuild metadata from the Markdown files.

---

# 39. Memory Reindexing

The project must support rebuilding the memory index.

Example concept:

```text
memory/*.md
      ↓
indexer
      ↓
memory.db
```

This allows the Markdown files to remain the source of truth for content.

The DB is rebuildable metadata.

Do not make the project dependent on irreplaceable DB-only content.

Reindexing happens on its own. Before answering, search compares the indexed
paths against the files on disk and rebuilds when they differ, so a catalog
that was deleted, restored from an older copy, or edited by hand cannot leave
memory silently unreachable. Checking only for an empty catalog is not
enough: losing it and then writing a new memory recreates it with one row,
which looks healthy while everything else has dropped out of search. A file
that is not a usable database is discarded and recreated rather than raised,
in every module that opens the catalog.

---

# 40. Duplicate Handling

When saving Experience:

* Challenge ID should preferably be unique.
* Do not silently overwrite an existing experience.
* If the same challenge is revisited, update the existing Experience or create a clearly versioned record according to the challenge identity.

For Knowledge:

* Update the existing topic file when the information belongs to an existing topic.
* Avoid creating:

```text
xss1.md
xss2.md
xss3.md
```

for every new discovery.

---

# 41. Minimal Public Interfaces

The implementation should expose simple APIs.

## memory/search.py

Conceptual interface:

```python
search(query, memory_type=None, limit=5)

read(reference)

rebuild()
```

## memory/save_knowledge.py

Conceptual interface:

```python
save_knowledge(topic, content, tags=None, technique=None)
```

## memory/update_knowledge.py

Conceptual interface:

```python
update_knowledge(topic, content, tags=None, technique=None)
```

## memory/save_experience.py

Conceptual interface:

```python
save_experience(exp_id, title, content, tags=None, technique=None,
                source=None, challenge_type=None, overwrite=False)
```

## tools/runner.py

Conceptual interface:

```python
list_tools()

get(name)

create(name, content)

remove(name)

run(name, args, timeout=None)
```

The exact signatures may be adapted during implementation, but responsibilities must remain unchanged.

---

# 42. Agent Tool Interface

Agent should interact with the system through explicit operations.

Conceptually:

```text
memory.search
memory.read
memory.save_knowledge
memory.update_knowledge
memory.save_experience

tools.list
tools.info
tools.run
tools.create
tools.remove
```

These operations may be implemented through Python functions, CLI commands, MCP tools, or another interface depending on the Agent integration.

The architecture must remain independent of the exact interface.

---

# 43. Example Complete Scenario

Suppose Agent receives:

```text
A web challenge with a search page.
User input is reflected through JavaScript.
The JavaScript uses innerHTML.
```

Agent observes:

```text
Possible DOM XSS.
```

Agent acknowledges:

```text
Source:
user-controlled URL value

Potential sink:
innerHTML

Potential vulnerability:
DOM XSS
```

Agent decides:

```text
Knowledge may help.
```

It searches:

```text
DOM XSS innerHTML
```

Knowledge returns:

```text
knowledge/xss.md
```

Agent reads the relevant section.

Then it decides:

```text
This also resembles a previously solved challenge.
```

It searches Experience:

```text
DOM XSS innerHTML
```

Results:

```text
experiences/lab-125.md
experiences/lab-231.md
```

Agent reads the relevant experience.

It then reasons:

```text
lab-125 is structurally similar.
```

It creates a plan.

It selects an available tool.

The runner identifies the tool.

The runner executes it.

The result is returned.

Agent analyzes the result.

If unsuccessful:

```text
update hypothesis
→ run another tool
→ analyze again
```

If existing tools are insufficient:

```text
create a script
→ tools/scripts/
→ run it
→ analyze
```

If useful beyond this challenge:

```text
keep it in tools/scripts/
```

Otherwise:

```text
remove it
```

After success:

```text
save:
experiences/lab-XXX.md
```

Agent then asks:

```text
Is there a generalizable lesson?
```

If yes:

```text
update:
knowledge/xss.md
```

Then the challenge ends.

---

# 44. What Must NOT Happen

Do not implement:

```text
learner.py
```

because Agent itself performs learning decisions.

Do not implement:

```text
reasoning_engine.py
```

because Agent is the reasoning engine.

Do not implement:

```text
strategy_engine.py
```

because strategy is chosen by Agent.

Do not create:

```text
knowledge_agent
experience_agent
memory_agent
```

unless there is a future explicit architectural requirement.

Do not create a second LLM solely for memory.

Do not automatically read every Experience.

Do not automatically update Knowledge after every challenge.

Do not treat successful command execution as proof of successful challenge completion.

Do not store all memory exclusively in SQLite.

Do not use a vector database initially.

---

# 45. Design Philosophy

The entire project can be understood as:

```text
                    Agent
                  THE BRAIN
                      │
        ┌─────────────┴─────────────┐
        │                           │
        ▼                           ▼
     MEMORY                        TOOLS
        │                           │
        │                           │
   remember                 create / execute
        │                           │
        ▼                           ▼
     Markdown                    scripts
        +                    tools/scripts/
      SQLite
```

Agent decides what to do.

Memory helps Agent remember.

Tools help Agent act, and Agent creates a new script when none of the
existing ones fit. Nothing decides for Agent.

---

# 46. Final Implementation Requirement

The AI coding agent must implement the project in a clean, modular, runnable state.

Implementation order should be:

```text
1. Create project structure.
2. Implement config.py.
3. Implement memory database initialization.
4. Implement search.py.
5. Implement Knowledge/Experience storage.
6. Implement the three memory write modules.
7. Implement runner.py.
8. Implement tool listing and metadata.
9. Implement safe tool execution.
10. Implement tool script creation.
11. Implement tool script removal.
12. Create prompts/system.md.
13. Integrate Agent with memory.
14. Integrate Agent with tools.
15. Implement the solving loop.
16. Implement experience saving.
17. Implement knowledge updating.
18. Add error handling.
19. Add tests.
20. Verify the complete workflow.
```

---

# 47. Minimum Acceptance Criteria

The project is considered complete only when all of the following work.

## Memory

* [ ] SQLite database initializes automatically.
* [ ] Knowledge Markdown files can be created.
* [ ] Experience Markdown files can be created.
* [ ] Metadata is indexed.
* [ ] Memory can be searched.
* [ ] Relevant Markdown can be read.
* [ ] Memory can be reindexed.
* [ ] DB does not contain the only copy of memory content.

## Knowledge

* [ ] Knowledge can be searched.
* [ ] Existing Knowledge can be updated.
* [ ] New Knowledge topics can be created.
* [ ] Knowledge is not automatically duplicated for every challenge.

## Experience

* [ ] Each solved challenge can be stored.
* [ ] Previous experiences can be searched.
* [ ] Agent can retrieve relevant previous challenges.
* [ ] Experience can contain successful and failed approaches.

## Tools

* [ ] Tools can be registered.
* [ ] Tools can be discovered.
* [ ] Tools can be executed.
* [ ] Execution has timeout handling.
* [ ] stdout/stderr/exit code are captured.
* [ ] Tool scripts can be created.
* [ ] Tool scripts can be tested.
* [ ] Useful scripts can be kept and useless ones removed.

## Agent

* [ ] Agent is the only reasoning engine.
* [ ] Agent can acknowledge observations.
* [ ] Agent can decide whether to search memory.
* [ ] Agent can search Knowledge.
* [ ] Agent can search Experience.
* [ ] Agent can select tools.
* [ ] Agent can analyze results.
* [ ] Agent can iterate.
* [ ] Agent can decide when a challenge is solved.
* [ ] Agent can decide what to save as Experience.
* [ ] Agent can decide what to generalize into Knowledge.

---

# 48. Final Rule for the Coding Agent

When implementing this project, always preserve the following mental model:

```text
Agent = THINK

MEMORY = REMEMBER

KNOWLEDGE = GENERAL KNOWLEDGE

EXPERIENCE = SPECIFIC PAST EXPERIENCE

SEARCH = FIND MEMORY

DATABASE = MEMORY CATALOG

SAVE_KNOWLEDGE = WRITE NEW KNOWLEDGE

UPDATE_KNOWLEDGE = CHANGE EXISTING KNOWLEDGE

SAVE_EXPERIENCE = WRITE A SOLVED CHALLENGE

RUNNER = CREATE, LIST AND RUN TOOL SCRIPTS

TOOL SCRIPTS = REUSABLE CAPABILITIES
```

The system must stay simple.

The goal is not to build many intelligent modules.

The goal is to give **one intelligent model — Agent — enough memory and tools to solve CTF challenges autonomously and improve through accumulated experience.**

## Implementation Rules

1. Read this file completely before making any changes.

2. This file is the authoritative specification and source of truth for the entire project.

3. Do not rely on conversation memory for project requirements.

4. Do not change the architecture defined in this file.

5. Do not create components, modules, files, or systems that are not specified in this file.

6. Before implementing a phase, inspect the current project and compare it with this specification.

7. Implement the project one phase at a time.

8. Before starting each new phase, re-read this file completely and use it as the source of truth for that phase.

9. After completing a phase, test the implementation.

10. After testing, verify that the implementation still conforms to this specification.

11. After completing and verifying a phase, STOP and wait for explicit user approval before starting the next phase.

12. Never automatically continue to the next phase.

13. If a new component or architectural change seems necessary but is not specified in this file, ask the user for approval before creating or changing it.

14. Agent must remain the ONLY AI brain of the system.

15. Do not introduce another AI agent, reasoning engine, strategy engine, learner, or autonomous decision-making component.
