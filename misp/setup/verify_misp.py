#!/usr/bin/env python3
"""
Verify MISP deployment: reachability, login, org, feeds, TheHive server, version.
"""
import os
import sys

import requests

from misp_http_session import MispSession, browser_form_login
from repo_env import load_repo_dotenv

load_repo_dotenv()

MISP_BASEURL = os.environ.get("MISP_BASEURL", "http://localhost:8080").rstrip("/")
ADMIN_EMAIL = os.environ.get("MISP_ADMIN_EMAIL", "admin@catnipgames.com")
ADMIN_PASSWORD = os.environ.get("MISP_ADMIN_PASSWORD", "Nepsoft@321!")
ORG_EXPECTED = os.environ.get("MISP_ORG", "CatnipGamesSOC")
MISP_AUTHKEY_CACHE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".misp_auth_key")
)
# Default MISP image ships two built-in feeds; require at least this many enabled.
MIN_FEEDS_ENABLED = int(os.environ.get("MISP_VERIFY_MIN_FEEDS", "2"))


def json_headers():
    return {"Accept": "application/json", "Content-Type": "application/json"}


def try_browser_login(session):
    if browser_form_login(session, MISP_BASEURL, ADMIN_EMAIL, ADMIN_PASSWORD):
        return True, None
    return (
        False,
        "browser form login or REST probe failed (check MISP_ADMIN_PASSWORD vs DB; "
        "MISP requires ~12+ chars — run `make misp-init` to sync via cake CLI)",
    )


def normalize_feeds(raw):
    rows = []
    if isinstance(raw, dict) and isinstance(raw.get("Feed"), list):
        raw = raw["Feed"]
    if not isinstance(raw, list):
        return rows
    for row in raw:
        if isinstance(row, dict) and "Feed" in row and isinstance(row["Feed"], dict):
            rows.append(row["Feed"])
        elif isinstance(row, dict):
            rows.append(row)
    return rows


def main():
    checks = []
    session = MispSession(MISP_BASEURL)

    # 1 reachability
    try:
        response = requests.get(f"{MISP_BASEURL}/users/login", timeout=20)
        ok = response.status_code == 200
        checks.append(("MISP login page reachable (GET /users/login == 200)", ok, response.status_code))
    except requests.RequestException as exc:
        checks.append(("MISP login page reachable (GET /users/login == 200)", False, str(exc)))

    # 2 admin login (browser form + session cookie)
    ok_login, err = try_browser_login(session)
    checks.append(("Admin login (browser session)", ok_login, err or "ok"))

    if not ok_login:
        _print_checks(checks)
        sys.exit(1)

    headers = json_headers()

    # 3 organisation
    org_ok = False
    detail = ""
    for url in (
        f"{MISP_BASEURL}/users/view/me.json",
        f"{MISP_BASEURL}/users/view/me",
    ):
        response = session.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            detail = f"HTTP {response.status_code}"
            continue
        try:
            body = response.json()
        except ValueError:
            detail = "not json"
            continue
        org = None
        if isinstance(body, dict):
            org_block = body.get("Organisation")
            if isinstance(org_block, dict):
                org = org_block.get("name")
            if not org:
                user = body.get("User")
                if isinstance(user, dict):
                    nested = user.get("Organisation") or user.get("org") or user.get("organisation")
                    if isinstance(nested, dict):
                        org = nested.get("name")
        org_ok = org == ORG_EXPECTED
        detail = f"found org={org!r}"
        break
    checks.append((f"Organisation is {ORG_EXPECTED}", org_ok, detail))

    # 4 feeds enabled count
    response = session.get(f"{MISP_BASEURL}/feeds/index.json", headers=headers, timeout=60)
    if response.status_code != 200:
        response = session.get(f"{MISP_BASEURL}/feeds", headers=headers, timeout=60)
    feed_ok = False
    feed_detail = ""
    if response.status_code == 200:
        feeds = normalize_feeds(response.json())
        def feed_on(row):
            v = row.get("enabled")
            if v is True:
                return True
            try:
                return int(v or 0) == 1
            except (TypeError, ValueError):
                return False

        enabled_n = sum(1 for f in feeds if feed_on(f))
        feed_ok = enabled_n >= MIN_FEEDS_ENABLED
        feed_detail = f"{enabled_n} feeds enabled (min {MIN_FEEDS_ENABLED})"
    else:
        feed_detail = f"HTTP {response.status_code}"
    checks.append((f"At least {MIN_FEEDS_ENABLED} feeds enabled", feed_ok, feed_detail))

    # 5 TheHive sync server (MISP servers/add authkey must be a 40-char MISP key, not TheHive Bearer token)
    server_ok = False
    server_detail = ""
    skip_thehive_server = False
    misp_link_key = os.environ.get("MISP_THEHIVE_API_KEY", "").strip()
    if not (len(misp_link_key) == 40 and misp_link_key.isalnum()):
        misp_link_key = ""
        if os.path.isfile(MISP_AUTHKEY_CACHE):
            try:
                with open(MISP_AUTHKEY_CACHE, encoding="utf-8") as handle:
                    cached = handle.read().strip()
                if len(cached) == 40 and cached.isalnum():
                    misp_link_key = cached
            except OSError as exc:
                server_detail = f"skipped: could not read .misp_auth_key ({exc})"
                skip_thehive_server = True
    if not misp_link_key and not skip_thehive_server:
        skip_thehive_server = True
        server_detail = (
            "skipped: no 40-char MISP authkey (set MISP_THEHIVE_API_KEY or run make misp-init to create .misp_auth_key)"
        )

    if skip_thehive_server:
        server_ok = True
    else:
        response = session.get(f"{MISP_BASEURL}/servers/index.json", headers=headers, timeout=60)
        if response.status_code != 200:
            response = session.get(f"{MISP_BASEURL}/servers", headers=headers, timeout=60)
        if response.status_code == 200:
            try:
                rows = response.json()
            except ValueError:
                rows = []
            if isinstance(rows, dict) and "Server" in rows:
                rows = rows["Server"] if isinstance(rows["Server"], list) else [rows["Server"]]
            if not isinstance(rows, list):
                rows = []
            for row in rows:
                item = row.get("Server") if isinstance(row, dict) and "Server" in row else row
                if isinstance(item, dict) and item.get("name") == "TheHive-CatnipSOC":
                    server_ok = True
                    break
            server_detail = "found" if server_ok else "TheHive-CatnipSOC not in server list"
        else:
            server_detail = f"HTTP {response.status_code}"
    checks.append(("TheHive sync server TheHive-CatnipSOC (skipped without 40-char MISP key)", server_ok, server_detail))

    # 6 version
    version_ok = False
    version_detail = ""
    response = session.get(f"{MISP_BASEURL}/servers/getVersion.json", headers=headers, timeout=30)
    if response.status_code != 200:
        response = session.get(f"{MISP_BASEURL}/servers/getVersion", headers=headers, timeout=30)
    if response.status_code == 200:
        version_ok = True
        try:
            version_detail = str(response.json())
        except ValueError:
            version_detail = response.text[:200]
    else:
        version_detail = f"HTTP {response.status_code}"
    checks.append(("MISP version endpoint returns data", version_ok, version_detail))

    _print_checks(checks)
    if all(item[1] for item in checks):
        sys.exit(0)
    sys.exit(1)


def _print_checks(checks):
    for label, ok, extra in checks:
        status = "[OK]" if ok else "[FAIL]"
        print(f"{status} {label}")
        if extra and extra != "ok":
            print(f"       ({extra})")


if __name__ == "__main__":
    main()
