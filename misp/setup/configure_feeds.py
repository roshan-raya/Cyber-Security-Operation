#!/usr/bin/env python3
"""
Enable and cache MISP threat feeds by name (idempotent).
"""
import os
import sys
import time

import requests

from misp_http_session import MispSession, browser_form_login
from repo_env import load_repo_dotenv

load_repo_dotenv()

MISP_BASEURL = os.environ.get("MISP_BASEURL", "http://localhost:8080").rstrip("/")
ADMIN_EMAIL = os.environ.get("MISP_ADMIN_EMAIL", "admin@catnipgames.com")
ADMIN_PASSWORD = os.environ.get("MISP_ADMIN_PASSWORD", "Nepsoft@321!")

TARGET_SUBSTRINGS = [
    "circl osint",
    "urlhaus",
    "feodo",
    "ssl blacklist",
    "botvrij",
    "blocklist.de",
]


def json_headers():
    return {"Accept": "application/json", "Content-Type": "application/json"}


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


def fetch_feeds(session):
    response = session.get(
        f"{MISP_BASEURL}/feeds/index.json",
        headers=json_headers(),
        timeout=60,
    )
    if response.status_code != 200:
        response = session.get(
            f"{MISP_BASEURL}/feeds",
            headers=json_headers(),
            timeout=60,
        )
    if response.status_code != 200:
        print(f"ERROR: GET /feeds failed: HTTP {response.status_code} {response.text[:500]}")
        sys.exit(1)
    try:
        return normalize_feeds(response.json())
    except ValueError:
        print("ERROR: feeds response not JSON.")
        sys.exit(1)


def feed_name_lower(feed):
    return (feed.get("name") or "").lower()


def find_feed_by_substring(feeds, substring):
    sub = substring.lower()
    for feed in feeds:
        if sub in feed_name_lower(feed):
            return feed
    return None


def edit_feed(session, feed_id, body):
    for url in (
        f"{MISP_BASEURL}/feeds/edit/{feed_id}",
        f"{MISP_BASEURL}/feeds/edit/{feed_id}.json",
    ):
        response = session.post(url, headers=json_headers(), json=body, timeout=60)
        if response.status_code in (200, 201, 204):
            return True
    return False


def cache_endpoints(session):
    headers = json_headers()
    for path in (
        "/feeds/cacheFeeds/csv",
        "/feeds/cacheFeeds/freetext",
        "/feeds/cacheFeeds/misp",
    ):
        response = session.post(f"{MISP_BASEURL}{path}", headers=headers, timeout=120)
        print(f"  cache {path}: HTTP {response.status_code}")


def main():
    session = MispSession(MISP_BASEURL)
    if not browser_form_login(session, MISP_BASEURL, ADMIN_EMAIL, ADMIN_PASSWORD):
        print("ERROR: could not log in to MISP.")
        sys.exit(1)
    feeds = fetch_feeds(session)

    enabled = 0
    already = 0
    missing_labels = []

    print("Configuring feeds...\n")
    for label in TARGET_SUBSTRINGS:
        feed = find_feed_by_substring(feeds, label)
        if not feed:
            print(f"  [NOT FOUND] pattern: {label!r}")
            missing_labels.append(label)
            continue
        fid = feed.get("id")
        name = feed.get("name", f"id {fid}")
        is_on = bool(int(feed.get("enabled", 0) or 0))
        caching_on = bool(int(feed.get("caching_enabled", 0) or 0))
        if is_on and caching_on:
            print(f"  [ALREADY ENABLED] {name}")
            already += 1
            continue
        body = {"enabled": True, "caching_enabled": True}
        if edit_feed(session, fid, body):
            print(f"  [ENABLED] {name}")
            enabled += 1
        else:
            print(f"  [FAIL] {name} (id {fid})")

    print("\nTriggering feed cache jobs...")
    cache_endpoints(session)

    print("\nSummary")
    print(f"  feeds enabled this run: {enabled}")
    print(f"  already enabled: {already}")
    print(f"  cache POSTs issued: 3")
    if missing_labels:
        print(f"  not found by name pattern: {', '.join(missing_labels)}")
    time.sleep(1)
    print("Done.")


if __name__ == "__main__":
    main()
