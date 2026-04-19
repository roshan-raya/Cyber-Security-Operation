#!/usr/bin/env python3
"""Run the full Catnip Games log generator stack on the host."""
import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_project_env():
    """Apply repo-root .env so `make start-logs` sees MISP/TheHive vars without manual export."""
    path = ROOT.parent / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        os.environ[key] = val


_load_project_env()

from generator import DEFAULT_CONFIG_PATH, LogGenerator
import metrics_exporter
from misp_ioc_exporter import MispIOCExporter
from thehive_alerter import TheHiveAlerter


PID_PATH = ROOT / "state" / "orchestrator.pid"


def format_runtime(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return "%02d:%02d:%02d" % (hours, minutes, secs)


def generator_worker(generator, interval_range, profile_name):
    generator.run_continuous(interval_range=interval_range, profile_name=profile_name)


def metrics_worker(stop_event):
    metrics_exporter.serve_forever(stop_event=stop_event)


def thehive_worker(stop_event):
    TheHiveAlerter(dry_run=False).run_forever(stop_event=stop_event)


def misp_worker(stop_event):
    MispIOCExporter(dry_run=False).run_forever(stop_event=stop_event)


def print_banner(config):
    profiles = config.get("attack_profiles", {})
    print("╔══════════════════════════════════════════╗")
    print("║   Catnip Games Log Generator Started     ║")
    print("╚══════════════════════════════════════════╝")
    print("Log directory:    log_generator/logs/")
    print("Metrics port:     9104")
    print("TheHive alerter:  ENABLED (threshold-based)")
    print("MISP exporter:    ENABLED (60s cycle; form-login at most every 300s)")
    print("")
    print("Attack profiles active:")
    print("├─ IDS Alerts          (threshold: %s/30s)" % profiles["ids_alert"]["auto_case_threshold"])
    print("├─ Firewall Blocks     (threshold: %s/30s)" % profiles["firewall_block"]["auto_case_threshold"])
    print("├─ Failed Logins       (threshold: %s/30s)" % profiles["failed_login"]["auto_case_threshold"])
    print("├─ Game Server Alerts  (threshold: %s/30s)" % profiles["game_server_alert"]["auto_case_threshold"])
    print("├─ WAF Alerts          (threshold: %s/30s)" % profiles["waf_alert"]["auto_case_threshold"])
    print("└─ DLP Alerts          (threshold: %s/30s)" % profiles["dlp_alert"]["auto_case_threshold"])
    print("")
    print("Press Ctrl+C to stop all components.")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-thehive", action="store_true")
    parser.add_argument("--no-misp", action="store_true")
    parser.add_argument("--rate", choices=["fast", "slow", "normal"], default="normal")
    parser.add_argument("--profile", default=None)
    args = parser.parse_args(argv or sys.argv[1:])

    rate_map = {"fast": (1, 2), "normal": (1, 5), "slow": (5, 10)}
    interval_range = rate_map[args.rate]
    config = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    generator = LogGenerator(DEFAULT_CONFIG_PATH, ROOT / "logs")
    stop_event = threading.Event()
    ROOT.joinpath("state").mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")

    print_banner(config)

    threads = [
        threading.Thread(target=generator_worker, args=(generator, interval_range, args.profile), daemon=True),
        threading.Thread(target=metrics_worker, args=(stop_event,), daemon=True),
    ]
    if not args.no_thehive:
        threads.append(threading.Thread(target=thehive_worker, args=(stop_event,), daemon=True))
    if not args.no_misp:
        threads.append(threading.Thread(target=misp_worker, args=(stop_event,), daemon=True))

    started = time.time()
    for thread in threads:
        thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()
        generator.stop_event.set()
        for thread in threads:
            thread.join(timeout=5)
        counts = generator.get_counts()
        print("")
        print("══════════════════════════════════════")
        print("Log Generator Session Summary")
        print("══════════════════════════════════════")
        print("Runtime:          %s" % format_runtime(time.time() - started))
        print("Total events:     %s" % counts["total_events"])
        print("IDS Alerts:       %s" % counts["profile_counts"].get("ids_alert", 0))
        print("Firewall Blocks:  %s" % counts["profile_counts"].get("firewall_block", 0))
        print("Failed Logins:    %s" % counts["profile_counts"].get("failed_login", 0))
        print("Game Alerts:      %s" % counts["profile_counts"].get("game_server_alert", 0))
        print("WAF Alerts:       %s" % counts["profile_counts"].get("waf_alert", 0))
        print("DLP Alerts:       %s" % counts["profile_counts"].get("dlp_alert", 0))
        print("")
        print("TheHive cases created:  %s" % counts["thehive_cases_created"])
        print("MISP IOCs exported:     %s" % counts["misp_iocs_exported"])
        print("Attack waves triggered: %s" % counts["attack_waves_triggered"])
        print("══════════════════════════════════════")
        if PID_PATH.exists():
            PID_PATH.unlink()


if __name__ == "__main__":
    main()
