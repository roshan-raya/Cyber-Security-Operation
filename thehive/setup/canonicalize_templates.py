#!/usr/bin/env python3
"""
Rename case templates in TheHive to canonical machine names (and display names)
from thehive/config/case_templates.json.

PATCH /api/v1/caseTemplate/{_id} is available for org-admin in CE even when
POST create is restricted. Run after manual template creation if names drifted.
"""
import json
import os
import sys

import requests

THEHIVE_URL = os.environ.get("THEHIVE_URL", "http://localhost:9000")
API_KEY_FILE = "thehive/setup/api_key.txt"
ORG = "CatnipGamesSOC"
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "case_templates.json")


def get_api_key():
    if not os.path.exists(API_KEY_FILE):
        print(f"ERROR: {API_KEY_FILE} not found. Run make thehive-init first.")
        sys.exit(1)
    with open(API_KEY_FILE, encoding="utf-8") as handle:
        return handle.read().strip()


def list_templates(api_key):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Organisation": ORG,
    }
    response = requests.post(
        f"{THEHIVE_URL}/api/v1/query",
        headers=headers,
        json={"query": [{"_name": "listCaseTemplate"}]},
        timeout=30,
    )
    if response.status_code != 200:
        print(f"ERROR: listCaseTemplate returned {response.status_code}: {response.text}")
        sys.exit(1)
    return [row for row in response.json() if isinstance(row, dict)]


def template_matches(required_id, template):
    name = (template.get("name") or "").strip()
    display = (template.get("displayName") or "").strip()
    nl = name.lower()
    dl = display.lower()

    if required_id == "BOT_ATTACK":
        return (
            name == "BOT_ATTACK"
            or nl == "bot attack"
            or "bot attack" in dl
            or "bot attack / game exploit" in dl
        )
    if required_id == "ACCOUNT_COMPROMISE":
        return name == "ACCOUNT_COMPROMISE" or "account compromise" in nl
    if required_id == "SOCIAL_ENGINEERING":
        compact = name.replace(" ", "").upper()
        return (
            name == "SOCIAL_ENGINEERING"
            or display == "SOCIAL_ENGINEERING"
            or compact.startswith("SOCIAL_ENGINEERING")
            or "social engineering" in nl
        )
    if required_id == "DDOS_INFRASTRUCTURE":
        return (
            name == "DDOS_INFRASTRUCTURE"
            or ("ddos" in nl and "infra" in nl)
        )
    return False


def find_template(required_id, templates):
    for template in templates:
        if template_matches(required_id, template):
            return template
    return None


def patch_template(api_key, template_id, payload):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Organisation": ORG,
    }
    response = requests.patch(
        f"{THEHIVE_URL}/api/v1/caseTemplate/{template_id}",
        headers=headers,
        json=payload,
        timeout=30,
    )
    return response


def main():
    api_key = get_api_key()
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        specs = json.load(handle)

    templates = list_templates(api_key)
    print("Canonicalizing case template names to match case_templates.json...\n")

    for spec in specs:
        canonical = spec["name"]
        found = find_template(canonical, templates)
        if not found:
            print(f"  [SKIP] No template matched {canonical}; create it in the UI first.")
            continue
        template_id = found.get("_id")
        if not template_id:
            print(f"  [SKIP] {canonical}: missing _id on template object.")
            continue
        current_name = found.get("name")
        current_display = found.get("displayName") or ""
        target_display = spec.get("displayName", "")
        if current_name == canonical and current_display == target_display:
            print(f"  [OK]    {canonical} already canonical.")
            continue
        response = patch_template(
            api_key,
            template_id,
            {"name": canonical, "displayName": target_display},
        )
        if response.status_code == 204:
            print(f"  [FIXED] {current_name!r} -> {canonical!r} (displayName -> {target_display!r})")
        else:
            print(f"  [FAIL]  {canonical}: HTTP {response.status_code} {response.text}")
            sys.exit(1)

    print("\nDone. Run: make thehive-templates")


if __name__ == "__main__":
    main()
