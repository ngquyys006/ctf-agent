---
name: ctf-agent
description: Operate the existing CTF-Agent project according to solve.md, CTF_Agent_Project_Design.md, prompts/system.md, and README.md. Use this skill whenever initializing the project or solving a user-provided CTF challenge.
compatibility: opencode
metadata:
  project: CTF-Agent
  role: project-operating-procedure
---

# CTF-Agent — Mandatory Operating Skill

## Purpose and authority

Use this skill whenever working inside this CTF-Agent repository. Its purpose is to make OpenCode operate the existing project according to its own documentation—not to redesign, rebuild, or replace it.

Before taking action, read these repository files from the project root:

1. `CTF_Agent_Project_Design.md`
2. `prompts/system.md`
3. `README.md`
4. `solve.md`

Read their current contents; do not rely on memory, summaries, assumptions, or an older copy. If a required file is missing or unreadable, report that fact and stop to ask the user how to proceed. Do not invent its contents.

Authority and consistency:
- `CTF_Agent_Project_Design.md` is the architecture source of truth.
- `prompts/system.md` defines the solving and reasoning workflow.
- `solve.md` defines the master operating procedure, startup gate, challenge lifecycle, restrictions, and final report.
- `README.md` explains the documented implementation and usage.
- Follow all four together. If they appear to conflict, do not silently rewrite project behavior; explain the conflict and ask the user before making structural changes.
- Inspect actual source code before relying on an API. Documentation does not prove an API exists or has a particular signature.

## One reasoning engine only

The active OpenCode Agent is the only AI reasoning engine for this OpenCode-based workflow. It alone performs analysis, forms hypotheses, chooses strategies, selects payloads and tools, interprets results, decides whether to iterate, verifies challenge success, and decides what to preserve in memory.

Never create or introduce another AI agent, reasoning engine, planner AI, strategy engine, learner AI, or autonomous decision-making component. Memory, Knowledge, Experience, the runner, and the tool scripts are capability providers; they do not reason or make challenge decisions.

Do not modify the project architecture unless the user explicitly approves a specific change.

## State 1 — Initialization (strict read-only gate)

When this skill is first activated for a project/session, or before beginning work if the project context is uncertain:

1. Read and understand the four files listed above.
2. Understand the documented architecture, APIs, memory rules, tool lifecycle, safety limits, challenge workflow, and restrictions.
3. Do not edit, create, move, rename, or delete project files.
4. Do not execute project files or scripts.
5. Do not run tests, including anything under `tests/`, unless the user has explicitly authorized running tests.
6. Do not probe, analyze, or interact with a CTF target.
7. Do not invent or create a sample challenge.
8. Do not start solving before the user supplies challenge information.

After completing initialization, respond briefly in Vietnamese:
“Đã đọc và hiểu toàn bộ tài liệu của CTF-Agent và đã sẵn sàng. Hãy cung cấp thông tin thử thách.”
Then stop and wait for the user’s challenge.

Do not claim to have read a file unless you actually read it during this session.

## State 2 — Solve only after the user provides a challenge

Start solving only after the user supplies challenge information (for example a URL, challenge description, source code, file, request/response, target details, or relevant environment details). Use the existing workflow and tools documented by the project.

Do not ask the user to prescribe the exploit path, memory query, payload, or tool when enough information exists to begin. Ask a concise question only when a necessary detail is genuinely missing or an action requires authorization.

### Required solving loop

Follow `prompts/system.md` and `solve.md`, including these steps:

1. **Observe** the challenge, inputs, outputs, endpoints, environment, behavior, and goal.
2. **Acknowledge** current understanding: state observations and initial suspicion, clearly separating facts from hypotheses.
3. **Decide whether memory is useful:** once the attack surface or likely technique is recognized, proactively consider searching Memory with targeted relevant keywords. Search both Knowledge and Experience categories as appropriate; searching is not required at every step, but do not skip it merely because the technique seems familiar. Use `search.search(...)` and `search.read(...)`.
4. **Read and critically assess** relevant memory candidates. Treat Experience as evidence, not truth. Never load all Knowledge or all Experience into context.
5. **Form a testable hypothesis** and plan: what to test, which tool/request to use, and what result would support or refute the hypothesis.
6. **Select an existing tool first** with `runner.list_tools()`.
7. **Execute through the runner** with `runner.run(name, args)` and arguments as a list. Never bypass the runner by directly running a script or building an unsafe shell command.
8. **Analyze the actual result.** A successful tool execution, changed response, or suspicious behavior is not proof that the challenge is solved.
9. **Update and iterate.** Learn from failures, record useful evidence, change the hypothesis or approach when justified, and do not repeat a failed attempt without a reason.
10. **Create a tool script only when necessary**, after existing tools prove insufficient.
11. **Test created tool scripts through the runner.** Evaluate whether a verified script is worth keeping before removing it.
12. **Verify the actual challenge goal** before declaring success.
13. **Persist useful results** through the memory write modules, then verify the saved record can be found with `search.search(...)`.
14. **Return the required Full Solve Summary** after successful completion, following the exact fields and format in `solve.md` / `prompts/system.md`.

## Memory rules — mandatory

- Markdown files under `memory/knowledge/` and `memory/experiences/` are the source of truth. `memory/memory.db` is rebuildable search metadata, not the primary memory content.
- All Memory reads and writes must go through the four memory modules. Never directly edit memory Markdown files using generic file I/O.
- The modules are `search`, `save_knowledge`, `update_knowledge`, and `save_experience` in the `memory` package. Each writing module writes the Markdown file and its SQLite metadata row in the same operation, and returns `None` when the operation did not happen. Signatures:
  - `search.search(query, memory_type=None, limit=5)` → ranked candidates. `memory_type` is `"knowledge"`, `"experience"`, or `None`; `limit` defaults to 5.
  - `search.read(reference)` → `{"type", "path", "content"}`. `reference` is a memory-relative path (`knowledge/xss.md`, `experiences/lab-001.md`) or a bare Knowledge topic / Experience ID.
  - `save_knowledge.save_knowledge(topic, content, tags=None, technique=None)` → record or `None` when the topic already exists. Topics are flat names ("xss").
  - `update_knowledge.update_knowledge(topic, content, tags=None, technique=None)` → record or `None` when the topic does not exist. Metadata you omit keeps its current value.
  - `save_experience.save_experience(exp_id, title, content, tags=None, technique=None, source=None, challenge_type=None, overwrite=False)` → record or `None` for a duplicate ID unless `overwrite=True`.
  - `search.rebuild()` → rebuilds `memory.db` from the Markdown files. `search` also rebuilds automatically if the catalog is missing or empty.
- Search targeted candidates only. Do not load all memory.
- Keep **Knowledge** general and reusable. Do not store target-specific URLs, temporary IPs/ports, credentials, session cookies, flags, or other challenge-specific secrets in Knowledge.
- Keep **Experience** specific to one challenge, including important observations, hypotheses, successful steps, meaningful failed approaches, tools used, verification evidence, and lessons.
- Do not silently overwrite an existing Experience. `save_experience` returns `None` for a duplicate ID; choose a unique ID and retry, or pass `overwrite=True` to explicitly update the existing record.
- After any memory write, call `search.search(...)` again to verify that the record is indexed and retrievable. Never claim a write succeeded unless it returned a record.
- Update existing Knowledge topics when appropriate. Create a new Knowledge topic only when the lesson is genuinely generalizable and sufficiently independent. Do not copy every challenge into Knowledge.
- Do not store redundant or low-value information.

## Tool rules — mandatory

- Inspect the actual `tools/runner.py` implementation when API details matter.
- Prefer existing tools in `tools/scripts/`; discover them with `runner.list_tools()` rather than assuming a tool exists.
- Create a tool script only when existing tools cannot reasonably perform the task. Use `runner.create(name, content)`; do not create an unmanaged script by direct file writing.
- Run tools only with `runner.run(name, args)` and pass `args` as a list. Respect the configured timeout, output limits, and structured result.
- Never use unsafe shell-string concatenation for arguments. Treat output as evidence to analyze, not as a decision.
- Tool scripts live in `tools/scripts/`. After a challenge, keep a script only if it is tested, useful beyond the current challenge, sufficiently generic, documented, and free of challenge-specific hardcoding; otherwise remove it with `runner.remove(name)`. Verify that `runner.list_tools()` still shows the kept scripts.
- If a workflow uses separate HTTP requests across processes, follow the project’s session/cookie handling guidance. Treat credentials and cookies as secrets; never place them in kept scripts, Skills, Knowledge, or final reports.
- Do not run files in `tests/` unless the user explicitly permits it. This restriction applies even if a test run would normally be useful.

## Verification and completion

Never declare a challenge solved solely because:
- a script exits with code 0;
- a request succeeds;
- the response changes;
- a payload executes an intermediate behavior; or
- a tool returns `success: true`.

Verify the actual challenge objective. For a platform-hosted challenge, follow the platform’s documented lifecycle and verify the platform accepts the flag when that is part of the challenge.

After verified success:
1. Save a unique Experience through `save_experience.save_experience(...)`.
2. Save/update Knowledge only for genuinely reusable lessons.
3. Verify the saved records are searchable.
4. Provide the `📋 Full Solve Summary` required by `solve.md`, including Observe, Memory searches, Hypothesis, Execute, Tools created/kept, Verify, Experience, and Knowledge. Do not invent a flag or claim verification that did not occur.

If the challenge was not solved, say so plainly and summarize the verified evidence, failed approaches, and next useful step. Do not fabricate a successful summary.

## Project-change and test restrictions

This Skill is not permission to change the project. When the task is to inspect, plan, or solve a challenge, do not modify architecture or unrelated project files.

- Never change the design specification, `solve.md`, `prompts/system.md`, or README unless the user explicitly requests and approves that change.
- Do not create additional AI components or replace existing Memory/runner behavior.
- Do not run tests or files under `tests/` without explicit user permission.
- If asked to implement a project change, first inspect the authoritative documents and relevant code, state the exact intended changes, and wait for approval when approval has not already been given.
- Make the smallest change that satisfies the approved request. Preserve existing behavior and avoid unrelated refactors.
- Never claim tests passed unless they were actually run and their results were observed.

## Activation and persistence limitation

OpenCode Skills are loaded on demand through OpenCode’s Skill mechanism. Use this Skill explicitly at the start of each new CTF-Agent session (for example, ask OpenCode to load/use `ctf-agent`) and confirm it was loaded before proceeding. Do not assume that creating a Skill automatically injects its entire content into every session or that it can force the model to obey. If the user needs repository rules to be active without explicitly loading a Skill, discuss a persistent OpenCode instruction mechanism separately and obtain approval before adding or changing any other file.

## Final rule

Follow the repository’s actual documents and code, preserve the existing architecture, and be truthful about what has and has not been read, executed, verified, or solved. The user’s explicit authorization is required for prohibited actions such as running tests or changing project files.
