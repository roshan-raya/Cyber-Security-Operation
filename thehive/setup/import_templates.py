#!/usr/bin/env python3
"""
TheHive Case Template Verifier (strict)

- Lists templates via POST /api/v1/query listCaseTemplate (TheHive 5 CE).
- Requires exact canonical `name` (BOT_ATTACK, …) matching case_templates.json.
- Verifies each template includes the expected tasks (titles, in order).

Run `make thehive-canonicalize-templates` if names were created with UI defaults.
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


def load_expected_specs():
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        specs = json.load(handle)
    order = [spec["name"] for spec in specs]
    by_name = {spec["name"]: spec for spec in specs}
    return order, by_name


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
        print(f"ERROR: query returned {response.status_code}: {response.text}")
        sys.exit(1)
    return [row for row in response.json() if isinstance(row, dict)]


def ordered_task_titles(template):
    tasks = template.get("tasks") or []
    decorated = []
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            continue
        order = task.get("order")
        if order is None:
            order = index
        decorated.append((int(order), (task.get("title") or "").strip()))
    decorated.sort(key=lambda item: item[0])
    return [title for _, title in decorated if title]


def verify_tasks(canonical, template, expected_spec):
    expected_titles = [task["title"] for task in expected_spec.get("tasks", [])]
    actual_titles = ordered_task_titles(template)
    if actual_titles == expected_titles:
        return True, ""
    return False, f"tasks mismatch for {canonical}:\n  expected: {expected_titles}\n  actual:   {actual_titles}"


if __name__ == "__main__":
    api_key = get_api_key()
    required_names, expected_by_name = load_expected_specs()

    print("Checking case templates (strict names + tasks)...\n")

    templates = list_templates(api_key)
    by_name = {template.get("name"): template for template in templates if template.get("name")}

    missing = []
    task_errors = []

    for canonical in required_names:
        template = by_name.get(canonical)
        if not template:
            print(f"  [MISSING] {canonical}")
            missing.append(canonical)
            continue
        spec = expected_by_name[canonical]
        ok, detail = verify_tasks(canonical, template, spec)
        if ok:
            task_count = len(ordered_task_titles(template))
            print(f"  [OK]      {canonical} ({task_count} tasks)")
        else:
            print(f"  [TASKS]   {canonical}")
            task_errors.append(detail)

    print()
    if missing:
        print("Missing canonical templates. Names in TheHive:", sorted(by_name.keys()))
        print("Fix: run  make thehive-canonicalize-templates  or rename in the UI.")
        sys.exit(1)
    if task_errors:
        print("Task verification failed:\n")
        for block in task_errors:
            print(block)
            print()
        sys.exit(1)

    print("All templates present with correct task lists.")
    sys.exit(0)
