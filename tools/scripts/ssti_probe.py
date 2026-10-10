"""Submit a form payload and show what the server renders back.

Handles the common "POST then redirect to a result page" pattern,
including 307 responses which preserve the method.

Category: web
Arguments: url, field, payload
"""

import sys
import urllib.error
import urllib.parse
import urllib.request


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _fetch(opener, request):
    try:
        response = opener.open(request, timeout=15)
        return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


def main(argv):
    if len(argv) < 3:
        print("usage: ssti_probe <url> <field> <payload>", file=sys.stderr)
        return 2

    url, field, payload = argv[0], argv[1], " ".join(argv[2:])
    opener = urllib.request.build_opener(_NoRedirect)
    data = urllib.parse.urlencode({field: payload}).encode()

    def submit(target):
        request = urllib.request.Request(
            target, data=data, method="POST",
            headers={"User-Agent": "Mozilla/5.0",
                     "Content-Type": "application/x-www-form-urlencoded"})
        return _fetch(opener, request)

    status, headers, body = submit(url)
    print("SUBMIT STATUS:", status)

    # 307/308 keep the method (re-POST); 301/302/303 become a GET.
    location = headers.get("Location")
    if location:
        target = urllib.parse.urljoin(url, location)
        print("REDIRECT TO:", target)
        code = status
        if code in (307, 308):
            status, headers, body = submit(target)
        else:
            request = urllib.request.Request(target, headers={"User-Agent": "Mozilla/5.0"})
            status, headers, body = _fetch(opener, request)

    print("STATUS:", status)
    print("=== RESPONSE ===")
    print(body.decode("utf-8", errors="replace")[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
