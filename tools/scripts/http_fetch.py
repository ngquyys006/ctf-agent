"""Fetch a URL over HTTP and print the full response.

Category: web
Arguments: url, method, data, headers_json, body, follow
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
        return r.status, r.headers, r.read(), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read(), req.full_url


def main(argv):
    url = argv[0]
    method = (argv[1] if len(argv) > 1 else "GET").upper()
    data_raw = argv[2] if len(argv) > 2 else ""
    headers_json = argv[3] if len(argv) > 3 else "{}"
    body_file = argv[4] if len(argv) > 4 else ""
    follow = (argv[5] if len(argv) > 5 else "0") == "1"

    try:
        headers = json.loads(headers_json) if headers_json else {}
    except ValueError:
        headers = {}
    headers.setdefault("User-Agent", UA)

    payload = None
    if body_file:
        with open(body_file, "rb") as fh:
            payload = fh.read()
    elif data_raw:
        payload = data_raw.encode()
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    opener = urllib.request.build_opener(
        *( [urllib.request.HTTPRedirectHandler()] if follow else [NoRedirect] )
    )
    req = urllib.request.Request(url, data=payload, method=method, headers=headers)
    status, hdrs, body, final = fetch(opener, req)

    print("REQUEST :", method, url)
    print("FINAL   :", final)
    print("STATUS  :", status)
    print("=== HEADERS ===")
    for k, v in hdrs.items():
        print("%s: %s" % (k, v))
    print("=== BODY (%d bytes) ===" % len(body))
    print(body.decode("utf-8", errors="replace")[:20000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
