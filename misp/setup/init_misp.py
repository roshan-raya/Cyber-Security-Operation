#!/usr/bin/env python3
"""
Bootstrap MISP after first boot: wait, login, server settings, feeds, TheHive sync server.
Credentials from environment variables only.

MISP 2.5+ often rejects JSON POST /users/login without an API key; we use the web form
(CakePHP session) then call REST with the same session cookie.
"""
import os
import subprocess
import sys
import time

import requests

from misp_http_session import MispSession, browser_form_login
from repo_env import load_repo_dotenv

load_repo_dotenv()

MISP_BASEURL = os.environ.get("MISP_BASEURL", "http://localhost:8080").rstrip("/")
LOGIN_URL = f"{MISP_BASEURL}/users/login"
ADMIN_EMAIL = os.environ.get("MISP_ADMIN_EMAIL", "admin@catnipgames.com")
ADMIN_PASSWORD = os.environ.get("MISP_ADMIN_PASSWORD", "Nepsoft@321!")
ORG_NAME = os.environ.get("MISP_ORG", "CatnipGamesSOC")
THEHIVE_URL = os.environ.get("THEHIVE_URL", "http://thehive:9000")
AUTHKEY_CACHE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".misp_auth_key"))


def json_headers():
    return {"Accept": "application/json", "Content-Type": "application/json"}


def wait_for_misp(timeout_seconds=600, interval_seconds=15):
    print("[1/6] Waiting for MISP (login page)...")
    started = time.time()
    while time.time() - started < timeout_seconds:
        try:
            response = requests.get(LOGIN_URL, timeout=20)
            if response.status_code == 200:
                print("MISP login page is reachable.")
                return
            print(f"Still waiting... HTTP {response.status_code}")
        except requests.RequestException as exc:
            print(f"Still waiting... ({exc})")
        time.sleep(interval_seconds)
    print("Timed out waiting for MISP after 10 minutes.")
    sys.exit(1)


def sync_misp_admin_password_via_docker():
    """
    Align the MISP admin password in the database with MISP_ADMIN_PASSWORD.
    Uses cake CLI inside the misp container (avoids mismatch when .env was updated after first boot).
    MISP typically enforces a minimum password length (e.g. 12 characters).
    """
    repo_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    compose_file = os.path.join(repo_root, "docker-compose.yml")
    if not os.path.isfile(compose_file):
        return
    cmd = [
        "docker",
        "compose",
        "-f",
        compose_file,
        "exec",
        "-T",
        "misp",
        "/var/www/MISP/app/Console/cake",
        "user",
        "change_pw",
        ADMIN_EMAIL,
        ADMIN_PASSWORD,
    ]
    try:
        proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"Note: MISP password sync (docker) skipped: {exc}")
        return
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode == 0:
        print("MISP admin password set to match MISP_ADMIN_PASSWORD (cake CLI).")
        return
    print(f"Note: cake user change_pw failed (exit {proc.returncode}): {out[:500]}")


def browser_login(session):
    print("[2/6] Authenticating (session login via web form)...")
    ok = browser_form_login(session, MISP_BASEURL, ADMIN_EMAIL, ADMIN_PASSWORD)
    if ok:
        print("Session authenticated (REST probe OK).")
    else:
        print("POST login failed or REST probe did not return 200.")
    return ok


def mint_authkey(session):
    """Create a dedicated API key and cache it for other scripts (optional)."""
    response = session.post(
        f"{MISP_BASEURL}/auth_keys/add/1.json",
        headers=json_headers(),
        json={"comment": "init_misp automation"},
        timeout=30,
    )
    if response.status_code not in (200, 201):
        print(f"Note: could not mint API key: HTTP {response.status_code}")
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    authkey = None
    if isinstance(body, dict):
        ak = body.get("AuthKey") or {}
        authkey = ak.get("authkey_raw") or ak.get("authkey")
    if authkey:
        try:
            with open(AUTHKEY_CACHE, "w", encoding="utf-8") as handle:
                handle.write(authkey.strip() + "\n")
            print(f"Wrote API key to {AUTHKEY_CACHE} (gitignored).")
        except OSError as exc:
            print(f"Note: could not write API key file: {exc}")
    return authkey


def post_setting(session, setting_key, value):
    """Update a server setting via MISP 2.5 ServersController::serverSettingsEdit (session auth)."""
    headers = json_headers()
    url = f"{MISP_BASEURL}/servers/serverSettingsEdit/{setting_key}.json"
    payload = {"Server": {"value": value}}
    response = session.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code in (200, 204):
        try:
            body = response.json()
        except ValueError:
            return True
        if isinstance(body, dict) and body.get("saved") is False:
            err = body.get("errors", body)
            print(f"Warning: could not set {setting_key}: {str(err)[:500]}")
            return False
        return True
    print(f"Warning: could not set {setting_key} (HTTP {response.status_code}).")
    if response.text:
        print(f"         {response.text[:300].replace(chr(10), ' ')}")
    return False


def configure_server_settings(session):
    print("[3/6] Applying server settings...")
    settings = [
        ("MISP.baseurl", os.environ.get("MISP_BASEURL", "http://localhost:8080")),
        ("MISP.org", ORG_NAME),
        ("MISP.live", True),
        ("MISP.enable_advanced_correlations", True),
        ("Plugin.ZeroMQ_enable", True),
    ]
    for key, val in settings:
        ok = post_setting(session, key, val)
        label = "ok" if ok else "skipped/failed"
        print(f"  {key} -> {label}")


def enable_default_feeds(session):
    print("[4/6] Enabling default feeds (ids 1-4 if present)...")
    headers = json_headers()
    for feed_id in (1, 2, 3, 4):
        url = f"{MISP_BASEURL}/feeds/enable/{feed_id}"
        response = session.post(url, headers=headers, timeout=30)
        if response.status_code in (200, 204):
            print(f"  Feed {feed_id}: enabled")
        elif response.status_code in (403, 404):
            print(f"  Feed {feed_id}: not available (HTTP {response.status_code}), skipping")
        else:
            print(f"  Feed {feed_id}: HTTP {response.status_code} {response.text[:200]}")


def read_cached_misp_authkey():
    """40-char MISP REST key (e.g. from mint_authkey); used for servers/add authkey field."""
    if not os.path.isfile(AUTHKEY_CACHE):
        return ""
    with open(AUTHKEY_CACHE, encoding="utf-8") as handle:
        return handle.read().strip()


def misp_authkey_for_server_entry():
    """
    MISP servers/add requires a 40-character MISP authkey (not TheHive's Bearer token).
    Prefer MISP_THEHIVE_API_KEY, else the key minted to .misp_auth_key during this init.
    """
    env_key = os.environ.get("MISP_THEHIVE_API_KEY", "").strip()
    if len(env_key) == 40 and env_key.isalnum():
        return env_key
    cached = read_cached_misp_authkey()
    if len(cached) == 40 and cached.isalnum():
        return cached
    return ""


def resolve_remote_org_id(session):
    response = session.get(
        f"{MISP_BASEURL}/organisations/index.json",
        headers=json_headers(),
        timeout=30,
    )
    if response.status_code != 200:
        print(f"Warning: could not list organisations: HTTP {response.status_code}")
        return 1
    try:
        rows = response.json()
    except ValueError:
        return 1
    if not isinstance(rows, list):
        return 1
    for row in rows:
        org = row.get("Organisation") if isinstance(row, dict) else None
        if isinstance(org, dict) and org.get("name") == ORG_NAME:
            oid = org.get("id")
            if oid is not None:
                return int(oid)
        if isinstance(row, dict) and row.get("name") == ORG_NAME and row.get("id") is not None:
            return int(row["id"])
    for row in rows:
        org = row.get("Organisation") if isinstance(row, dict) else None
        if isinstance(org, dict) and org.get("id") is not None:
            return int(org["id"])
        if isinstance(row, dict) and row.get("id") is not None:
            return int(row["id"])
    return 1


def add_thehive_server(session):
    print("[5/6] Registering TheHive sync server...")
    authkey_thehive = misp_authkey_for_server_entry()
    if not authkey_thehive:
        print(
            "Warning: skipping servers/add (no 40-char MISP authkey). "
            "Set MISP_THEHIVE_API_KEY in .env or ensure mint_authkey wrote .misp_auth_key."
        )
        return
    remote_org_id = resolve_remote_org_id(session)
    payload = {
        "name": "TheHive-CatnipSOC",
        "url": THEHIVE_URL,
        "authkey": authkey_thehive,
        "push": 0,
        "pull": 0,
        "self_signed": 1,
        "remote_org_id": remote_org_id,
    }
    response = session.post(
        f"{MISP_BASEURL}/servers/add",
        headers=json_headers(),
        json=payload,
        timeout=30,
    )
    if response.status_code in (200, 201):
        print("TheHive sync server added.")
        return
    if response.status_code == 409:
        print("TheHive sync server already exists (409), continuing.")
        return
    print(f"Warning: servers/add returned HTTP {response.status_code}: {response.text[:500]}")


def main():
    wait_for_misp()
    print("Aligning MISP admin password with MISP_ADMIN_PASSWORD (Docker cake CLI)...")
    sync_misp_admin_password_via_docker()
    session = MispSession(MISP_BASEURL)
    if not browser_login(session):
        sys.exit(1)
    mint_authkey(session)
    configure_server_settings(session)
    enable_default_feeds(session)
    add_thehive_server(session)
    print("[6/6] Summary")
    print(f"  MISP URL: {MISP_BASEURL}")
    print(f"  Admin email: {ADMIN_EMAIL}")
    print("  Feeds: attempted enable for ids 1-4 (see logs above)")
    print("  TheHive server: TheHive-CatnipSOC ->", THEHIVE_URL)
    print("Done.")


if __name__ == "__main__":
    main()
