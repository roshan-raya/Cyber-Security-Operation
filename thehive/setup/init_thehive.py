#!/usr/bin/env python3
import argparse
import os
import sys
import time

import requests

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

BASE_URL = os.getenv("THEHIVE_URL", "http://localhost:9000")
STATUS_URL = f"{BASE_URL}/api/v1/status"
DEFAULT_ADMIN_LOGIN = "admin@thehive.local"
DEFAULT_ADMIN_PASSWORD = "secret"
ORG_NAME = os.getenv("THEHIVE_ORG_NAME", "CatnipGamesSOC")
ORG_DESCRIPTION = os.getenv(
    "THEHIVE_ORG_DESCRIPTION",
    "Catnip Games International Security Operations Centre",
)
API_KEY_OUTPUT = os.path.join(os.path.dirname(__file__), "api_key.txt")


def load_environment() -> None:
    if load_dotenv is not None:
        load_dotenv()


def request_json(method, url, headers=None, payload=None, timeout=20, session=None):
    client = session if session is not None else requests
    try:
        response = client.request(
            method=method,
            url=url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        print(f"Request error: {exc}")
        return None, None

    if response.status_code >= 400:
        if response.status_code == 409:
            print(f"Conflict (already exists): {url}")
            return response, None
        print(f"HTTP {response.status_code} for {url}")
        print(response.text)
        return response, None

    if not response.text.strip():
        return response, {}

    try:
        return response, response.json()
    except ValueError:
        print(f"Non-JSON response from {url}")
        print(response.text)
        return response, {}


def wait_for_thehive_ready(timeout_seconds=300, interval_seconds=10) -> None:
    print("[1/6] Waiting for TheHive readiness...")
    started = time.time()
    while time.time() - started < timeout_seconds:
        try:
            resp = requests.get(STATUS_URL, timeout=10)
            if resp.status_code in (200, 401):
                print("TheHive is ready.")
                return
            print(f"Still waiting... status={resp.status_code}")
        except requests.RequestException as exc:
            print(f"Still waiting... ({exc})")
        time.sleep(interval_seconds)

    print("Timed out waiting for TheHive after 5 minutes.")
    sys.exit(1)


def get_default_admin_headers(session):
    login_url = f"{BASE_URL}/api/v1/login"
    payload = {"user": DEFAULT_ADMIN_LOGIN, "password": DEFAULT_ADMIN_PASSWORD}
    response, body = request_json("POST", login_url, payload=payload, session=session)
    if response is None or response.status_code >= 400:
        print("Failed to authenticate with default admin credentials.")
        sys.exit(1)

    token = None
    if isinstance(body, dict):
        token = body.get("token") or body.get("jwt")
    if not token:
        token = response.headers.get("Authorization")
        if token and token.lower().startswith("bearer "):
            token = token.split(" ", 1)[1]

    if not token:
        # TheHive may rely on an authenticated session cookie instead of JWT.
        if response.cookies:
            return {"Content-Type": "application/json"}
        print("Could not extract auth token from login response.")
        print(response.text)
        sys.exit(1)

    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def create_organisation(headers, session, force=False):
    print("[2/6] Creating SOC organisation...")
    payload = {"name": ORG_NAME, "description": ORG_DESCRIPTION}
    response, _ = request_json(
        "POST",
        f"{BASE_URL}/api/v1/organisation",
        headers=headers,
        payload=payload,
        session=session,
    )
    if response is None:
        sys.exit(1)
    text_lower = (response.text or "").lower()
    if response.status_code == 409:
        print("Organisation already exists, continuing.")
    elif response.status_code == 400 and "already exists" in text_lower:
        print("Organisation already exists (400), continuing.")
    elif force and response.status_code == 400:
        print("Organisation create returned 400; continuing because --force was set.")
    elif response.status_code and response.status_code < 400:
        print("Organisation ready.")
    elif response.status_code == 400:
        print("Failed to create organisation.")
        sys.exit(1)
    else:
        print("Unexpected response creating organisation.")
        sys.exit(1)


def create_users(headers, session):
    print("[3/6] Creating SOC users...")
    admin_password = os.getenv("THEHIVE_ADMIN_PASSWORD", "Nepsoft@321!")
    users = [
        {
            "login": "soc.admin@catnipgames.com",
            "name": "SOC Admin",
            "profile": "org-admin",
            "organisation": ORG_NAME,
            "password": admin_password,
        },
        {
            "login": "soc.analyst@catnipgames.com",
            "name": "SOC Analyst",
            "profile": "analyst",
            "organisation": ORG_NAME,
            "password": admin_password,
        },
        {
            "login": "soc.readonly@catnipgames.com",
            "name": "SOC ReadOnly",
            "profile": "read-only",
            "organisation": ORG_NAME,
            "password": admin_password,
        },
    ]

    for user in users:
        response, _ = request_json(
            "POST",
            f"{BASE_URL}/api/v1/user",
            headers=headers,
            payload=user,
            session=session,
        )
        if response is None:
            sys.exit(1)
        if response.status_code == 409:
            print(f"User {user['login']} already exists, skipping.")
        else:
            print(f"User {user['login']} created.")

    return users


def ensure_soc_admin_org_admin(headers, session):
    """Existing installs may still have analyst; upgrade so UI template admin works."""
    print("[3b/6] Ensuring soc.admin@catnipgames.com is org-admin in this organisation...")
    login = "soc.admin@catnipgames.com"
    response, _ = request_json(
        "PATCH",
        f"{BASE_URL}/api/v1/user/{login}",
        headers=headers,
        payload={"profile": "org-admin", "organisation": ORG_NAME},
        session=session,
    )
    if response is None:
        sys.exit(1)
    if response.status_code == 204:
        print("SOC admin profile set to org-admin.")
        return
    if response.status_code in (400, 404):
        print(f"Note: profile PATCH returned {response.status_code} (user may not exist yet).")
        return
    print(f"Unexpected profile PATCH status {response.status_code}: {response.text}")
    sys.exit(1)


def renew_admin_api_key(headers, session):
    print("[4/6] Generating API key for soc.admin@catnipgames.com...")
    login = "soc.admin@catnipgames.com"
    response, body = request_json(
        "POST",
        f"{BASE_URL}/api/v1/user/{login}/key/renew",
        headers=headers,
        session=session,
    )
    if response is None or response.status_code >= 400:
        print("Failed to renew API key.")
        sys.exit(1)

    api_key = ""
    if isinstance(body, dict):
        api_key = body.get("key") or body.get("apiKey") or body.get("value") or ""
    if not api_key and response.text.strip():
        api_key = response.text.strip().strip('"')

    if not api_key:
        print("Could not parse API key response.")
        print(response.text)
        sys.exit(1)

    with open(API_KEY_OUTPUT, "w", encoding="utf-8") as handle:
        handle.write(api_key + "\n")

    print(f"Generated API key (soc.admin@catnipgames.com): {api_key}")
    print(f"Saved API key to {API_KEY_OUTPUT}")
    return api_key


def create_custom_fields(headers, session):
    print("[5/6] Creating custom fields...")
    fields = [
        {
            "name": "player-id",
            "displayName": "Player ID",
            "description": "Affected player account identifier",
            "type": "string",
            "group": "main",
            "mandatory": False,
        },
        {
            "name": "affected-server",
            "displayName": "Affected Server",
            "description": "Hostname or IP of the affected game server",
            "type": "string",
            "group": "main",
            "mandatory": False,
        },
        {
            "name": "matchmaking-service",
            "displayName": "Matchmaking Service",
            "description": "Matchmaking service instance involved",
            "type": "string",
            "group": "main",
            "mandatory": False,
        },
        {
            "name": "incident-category",
            "displayName": "Incident Category",
            "description": "SOC incident classification",
            "type": "string",
            "group": "main",
            "mandatory": True,
        },
    ]

    for field in fields:
        response, _ = request_json(
            "POST",
            f"{BASE_URL}/api/v1/customField",
            headers=headers,
            payload=field,
            session=session,
        )
        if response is None:
            sys.exit(1)
        if response.status_code == 409:
            print(f"Field {field['name']} already exists, skipping.")
        elif response.status_code >= 400:
            print(f"Failed to create field {field['name']}.")
            sys.exit(1)
        else:
            print(f"Field {field['name']} created.")


def print_summary(users):
    print("[6/6] TheHive setup completed successfully.")
    print("Created/validated users:")
    for user in users:
        print(f" - {user['login']} ({user['profile']})")
    print(f"API key file: {API_KEY_OUTPUT}")


def parse_args():
    parser = argparse.ArgumentParser(description="Bootstrap TheHive org, users, fields, API key.")
    parser.add_argument(
        "--rekey-only",
        action="store_true",
        help="Only renew soc.admin API key (default admin login). Skips org/users/fields.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Continue past organisation create HTTP 400 responses (use after partial wipes).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    load_environment()
    wait_for_thehive_ready()
    session = requests.Session()
    headers = get_default_admin_headers(session)
    if args.rekey_only:
        renew_admin_api_key(headers, session)
        print("Rekey complete.")
        return

    create_organisation(headers, session, force=args.force)
    users = create_users(headers, session)
    ensure_soc_admin_org_admin(headers, session)
    renew_admin_api_key(headers, session)
    create_custom_fields(headers, session)
    print_summary(users)


if __name__ == "__main__":
    main()
