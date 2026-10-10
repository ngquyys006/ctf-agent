"""Submit a template payload to a form, with custom headers, and show the render.

Same 307-preserving redirect handling as ssti_probe, but lets the Agent set
request headers and cookies - useful when the filter can only be bypassed
with values echoed back by the server (for example reading an injected
header value to rebuild a blocked token).

Category: web
Arguments: url, field, payload, headers_json
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def fetch(opener, req):
    try:
        r = opener.open(req, timeout=20)
        return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def main(argv):
    if len(argv) < 3:
        print("usage: ssti_post <url> <field> <payload> [headers_json]", file=sys.stderr)
        return 2
    url, field, payload = argv[0], argv[1], " ".join(argv[2:])
    raw_headers = argv[3] if len(argv) > 3 else ""
    headers = {"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"}
    if raw_headers:
        try:
            headers.update(json.loads(raw_headers))
        except ValueError as exc:
            print("bad headers_json: %s" % exc, file=sys.stderr)
            return 2

    opener = urllib.request.build_opener(NoRedirect)
    data = urllib.parse.urlencode({field: payload}).encode()

    def post(target):
        return fetch(opener, urllib.request.Request(target, data=data, method="POST", headers=headers))

    status, hdrs, body = post(url)
    location = hdrs.get("Location")
    if location:
        target = urllib.parse.urljoin(url, location)
        print("REDIRECT TO:", target)
        if status in (307, 308):
            status, hdrs, body = post(target)
        else:
            status, hdrs, body = fetch(
                opener, urllib.request.Request(target, headers=headers))

    print("STATUS:", status)
    print("=== RESPONSE ===")
    print(body.decode("utf-8", errors="replace")[:20000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
