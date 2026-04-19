"""
Helpers for MISP over plain HTTP: session cookies are often marked Secure, and
Python's http.cookiejar will not send them on http:// unless we clear the flag
before each request (curl does send them).
"""
import re
import sys

import requests


def relax_secure_cookies_if_http(session, base_url):
    if not (base_url or "").lower().startswith("http://"):
        return
    for cookie in session.cookies:
        cookie.secure = False


class MispSession(requests.Session):
    """requests.Session that sends MISP Secure cookies over http://localhost."""

    def __init__(self, base_url):
        super().__init__()
        self._misp_base_url = base_url

    def request(self, method, url, **kwargs):
        relax_secure_cookies_if_http(self, self._misp_base_url)
        return super().request(method, url, **kwargs)


def parse_login_tokens(html):
    key = None
    fields = None
    match = re.search(r'name="data\[_Token\]\[key\]" value="([^"]+)"', html)
    if match:
        key = match.group(1)
    match = re.search(r'name="data\[_Token\]\[fields\]" value="([^"]+)"', html)
    if match:
        fields = match.group(1)
    return key, fields


def browser_form_login(session, base_url, email, password, login_path="/users/login"):
    """
    Log in via CakePHP form; session cookie is used for subsequent REST-style JSON calls.
    Returns True if GET /servers/getVersion.json succeeds with the session.
    """
    base = (base_url or "").rstrip("/")
    login_url = f"{base}{login_path}"

    relax_secure_cookies_if_http(session, base)
    response = session.get(login_url, timeout=30)
    if response.status_code != 200:
        return False

    token_key, token_fields = parse_login_tokens(response.text)
    if not token_key or not token_fields:
        return False

    data = {
        "_method": "POST",
        "data[_Token][key]": token_key,
        "data[_Token][fields]": token_fields,
        "data[_Token][unlocked]": "",
        "data[User][email]": email,
        "data[User][password]": password,
    }

    relax_secure_cookies_if_http(session, base)
    response = session.post(login_url, data=data, timeout=30, allow_redirects=False)
    relax_secure_cookies_if_http(session, base)

    if response.is_redirect and "location" in response.headers:
        session.get(response.headers["location"], timeout=30, allow_redirects=True)
        relax_secure_cookies_if_http(session, base)
    elif response.status_code not in (200,):
        if response.status_code == 403 and "maximum number of login attempts" in (
            response.text or ""
        ):
            print(
                "MISP: login temporarily blocked (brute-force limit). "
                "Wait ~5 minutes before retrying; repeated exporter runs count as attempts.",
                file=sys.stderr,
            )
        return False

    relax_secure_cookies_if_http(session, base)
    probe = session.get(
        f"{base}/servers/getVersion.json",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=30,
    )
    return probe.status_code == 200
