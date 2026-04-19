#!/usr/bin/env python3
"""Continuous Catnip Games security log generator."""
import argparse
import json
import os
import random
import string
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT / "config" / "log_profiles.json"
DEFAULT_STATE_PATH = ROOT / "state" / "metrics.json"
MAX_LOG_BYTES = 10 * 1024 * 1024


def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class LogGenerator:
    def __init__(self, config_path, log_dir):
        self.config_path = Path(config_path)
        self.log_dir = Path(log_dir)
        with self.config_path.open(encoding="utf-8") as fh:
            self.config = json.load(fh)
        self.profiles = self.config.get("attack_profiles", {})
        self.settings = self.config.get("global_settings", {})
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir = ROOT / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = DEFAULT_STATE_PATH
        self.start_time = time.time()
        self.counters = {name: 0 for name in self.profiles}
        self.total_events = 0
        self.ids_rule_counts = {}
        self.recent_timestamps = []
        self.recent_events = []
        self.total_cases_created = 0
        self.total_iocs_exported = 0
        self.attack_wave_active = 0
        self.attack_waves_triggered = 0
        self.active_profile = None
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.last_state_write = 0.0
        self._load_existing_state()

    def _load_existing_state(self):
        if not self.state_path.exists():
            self._write_state_locked()
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._write_state_locked()
            return
        with self.lock:
            counts = data.get("profile_counts", {})
            for name in self.counters:
                self.counters[name] = _safe_int(counts.get(name), 0)
            self.total_events = _safe_int(data.get("total_events"), sum(self.counters.values()))
            self.total_cases_created = _safe_int(data.get("thehive_cases_created"), 0)
            self.total_iocs_exported = _safe_int(data.get("misp_iocs_exported"), 0)
            self.attack_waves_triggered = _safe_int(data.get("attack_waves_triggered"), 0)
            self.ids_rule_counts = dict(data.get("ids_rule_counts", {}))
            self.recent_events = data.get("recent_events", [])[-200:]
            self.last_state_write = time.time()
        self._write_state()

    def _weighted_profiles(self):
        if self.active_profile:
            return [self.active_profile]
        weighted = []
        for name, profile in self.profiles.items():
            sev = profile.get("severity_range", [1, 1])
            weight = max(1, _safe_int(sev[-1] if sev else 1, 1))
            weighted.extend([name] * weight)
        return weighted or list(self.profiles)

    def _random_ip(self, pool):
        return random.choice(pool or ["203.0.113.45"])

    def _player_id(self):
        return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))

    def _value_for_profile(self, profile_name, profile, severity):
        ts = iso_now()
        data = {
            "timestamp": ts,
            "severity": severity,
            "profile_name": profile_name,
            "display_name": profile.get("display_name", profile_name),
        }
        if "src_ip_pool" in profile:
            data["src_ip"] = self._random_ip(profile.get("src_ip_pool"))
        if "dst_ip_pool" in profile:
            data["dst_ip"] = self._random_ip(profile.get("dst_ip_pool"))
        if "rules" in profile:
            data["rule"] = random.choice(profile.get("rules", ["GENERIC"]))
        if "reasons" in profile:
            data["reason"] = random.choice(profile.get("reasons", ["BLOCKED"]))
        if "proto_pool" in profile:
            data["proto"] = random.choice(profile.get("proto_pool", ["TCP"]))
        if "port_pool" in profile:
            data["port"] = random.choice(profile.get("port_pool", [443]))
        if "services" in profile:
            data["service"] = random.choice(profile.get("services", ["player-portal"]))
            data["attempts"] = random.randint(1, 25)
        if "username_pool" in profile:
            data["username"] = random.choice(profile.get("username_pool", ["admin"]))
        if "servers" in profile:
            data["server"] = random.choice(profile.get("servers", ["game-server-dc1-01"]))
            data["player_id"] = self._player_id()
            data["event"] = random.choice(profile.get("events", ["BOT_BEHAVIOR"]))
            data["value"] = random.randint(10, 99999)
        if "methods" in profile:
            data["method"] = random.choice(profile.get("methods", ["GET"]))
            data["path"] = random.choice(profile.get("paths", ["/"]))
            data["action"] = random.choice(profile.get("actions", ["LOG"]))
            data["rule"] = random.choice(profile.get("rules", ["BOT_SIGNATURE"]))
        if "actions" in profile and "data_types" in profile:
            data["action"] = random.choice(profile.get("actions", ["UNUSUAL_ACCESS"]))
            data["data_type"] = random.choice(profile.get("data_types", ["PLAYER_PII"]))
            data["volume"] = random.randint(50, 5000)
            data["destination"] = random.choice(profile.get("destinations", ["unknown-ip"]))
            data["username"] = random.choice(profile.get("username_pool", ["dev_user_1"]))
        return data

    def generate_event(self, profile_name):
        profile = self.profiles[profile_name]
        sev_min, sev_max = profile.get("severity_range", [1, 1])
        severity = random.randint(_safe_int(sev_min, 1), _safe_int(sev_max, 1))
        data = self._value_for_profile(profile_name, profile, severity)
        log_line = profile["log_format"].format(**data)
        iocs = []
        src_ip = data.get("src_ip")
        if src_ip:
            iocs.append(src_ip)
        if data.get("dst_ip") and not str(data["dst_ip"]).startswith("10."):
            iocs.append(data["dst_ip"])
        event = {
            "timestamp": data["timestamp"],
            "profile": profile_name,
            "severity": severity,
            "log_line": log_line,
            "src_ip": src_ip,
            "iocs": iocs,
            "raw": data,
        }
        return event

    def _rotate_if_needed(self, path):
        if not path.exists():
            return
        if path.stat().st_size <= MAX_LOG_BYTES:
            return
        rotated = path.with_suffix(path.suffix + ".1")
        if rotated.exists():
            rotated.unlink()
        path.rename(rotated)

    def write_log(self, event):
        profile_path = self.log_dir / ("%s.log" % event["profile"])
        combined_path = self.log_dir / "combined.log"
        self._rotate_if_needed(profile_path)
        self._rotate_if_needed(combined_path)
        line = event["log_line"] + "\n"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        with profile_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        with combined_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        self.record_event(event)

    def record_event(self, event):
        now = time.time()
        with self.lock:
            self.total_events += 1
            self.counters[event["profile"]] = self.counters.get(event["profile"], 0) + 1
            self.recent_timestamps.append(now)
            cutoff = now - 60.0
            self.recent_timestamps = [ts for ts in self.recent_timestamps if ts >= cutoff]
            raw = event.get("raw", {})
            if event["profile"] == "ids_alert":
                rule = raw.get("rule", "GENERIC")
                self.ids_rule_counts[rule] = self.ids_rule_counts.get(rule, 0) + 1
            recent_entry = {
                "timestamp": event["timestamp"],
                "epoch": int(now),
                "profile": event["profile"],
                "severity": event["severity"],
                "src_ip": event.get("src_ip"),
                "iocs": event.get("iocs", []),
                "raw": raw,
            }
            self.recent_events.append(recent_entry)
            self.recent_events = self.recent_events[-200:]
            should_write = (self.total_events % 10 == 0) or (now - self.last_state_write >= 30)
            if should_write:
                self._write_state_locked()

    def _write_state_locked(self):
        existing = {}
        if self.state_path.exists():
            try:
                existing = json.loads(self.state_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                existing = {}
        self.total_cases_created = max(
            self.total_cases_created,
            _safe_int(existing.get("thehive_cases_created"), 0),
        )
        self.total_iocs_exported = max(
            self.total_iocs_exported,
            _safe_int(existing.get("misp_iocs_exported"), 0),
        )
        self.attack_waves_triggered = max(
            self.attack_waves_triggered,
            _safe_int(existing.get("attack_waves_triggered"), 0),
        )
        uptime = max(0, int(time.time() - self.start_time))
        payload = {
            "profile_counts": dict(self.counters),
            "total_events": self.total_events,
            "events_per_minute": len(self.recent_timestamps),
            "start_time": int(self.start_time),
            "uptime_seconds": uptime,
            "attack_wave_active": self.attack_wave_active,
            "attack_waves_triggered": self.attack_waves_triggered,
            "thehive_cases_created": self.total_cases_created,
            "misp_iocs_exported": self.total_iocs_exported,
            "ids_rule_counts": dict(self.ids_rule_counts),
            "recent_events": list(self.recent_events[-100:]),
            "updated_at": iso_now(),
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.last_state_write = time.time()

    def _write_state(self):
        with self.lock:
            self._write_state_locked()

    def increment_cases_created(self, count=1):
        with self.lock:
            self.total_cases_created += _safe_int(count, 1)
            self._write_state_locked()

    def increment_iocs_exported(self, count=1):
        with self.lock:
            self.total_iocs_exported += _safe_int(count, 1)
            self._write_state_locked()

    def set_attack_wave_active(self, active):
        with self.lock:
            self.attack_wave_active = 1 if active else 0
            self._write_state_locked()

    def get_counts(self):
        existing = {}
        if self.state_path.exists():
            try:
                existing = json.loads(self.state_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                existing = {}
        with self.lock:
            return {
                "profile_counts": dict(self.counters),
                "total_events": self.total_events,
                "events_per_minute": len(self.recent_timestamps),
                "start_time": int(self.start_time),
                "uptime_seconds": max(0, int(time.time() - self.start_time)),
                "attack_wave_active": self.attack_wave_active,
                "attack_waves_triggered": max(
                    self.attack_waves_triggered,
                    _safe_int(existing.get("attack_waves_triggered"), 0),
                ),
                "thehive_cases_created": max(
                    self.total_cases_created,
                    _safe_int(existing.get("thehive_cases_created"), 0),
                ),
                "misp_iocs_exported": max(
                    self.total_iocs_exported,
                    _safe_int(existing.get("misp_iocs_exported"), 0),
                ),
                "ids_rule_counts": dict(self.ids_rule_counts),
            }

    def run_burst(self, profile_name, count=20):
        for _ in range(max(0, count)):
            if self.stop_event.is_set():
                break
            event = self.generate_event(profile_name)
            self.write_log(event)
            time.sleep(0.1)

    def _sleep_until(self, seconds):
        end = time.time() + max(0.0, seconds)
        while not self.stop_event.is_set() and time.time() < end:
            time.sleep(min(0.25, end - time.time()))

    def run_continuous(self, interval_range=(1, 5), duration=None, profile_name=None, rate=None):
        self.active_profile = profile_name
        interval_min, interval_max = interval_range
        if rate is not None and rate > 0:
            interval_min = max(0.2, 60.0 / float(rate))
            interval_max = max(interval_min, interval_min * 1.2)
        weighted_profiles = self._weighted_profiles()
        start = time.time()
        next_print = start + 30
        while not self.stop_event.is_set():
            if duration is not None and (time.time() - start) >= duration:
                break
            profile = random.choice(weighted_profiles)
            event = self.generate_event(profile)
            self.write_log(event)
            total = self.get_counts()["total_events"]
            if total % 10 == 0 and random.random() < float(self.settings.get("burst_probability", 0.1)):
                burst_count = int(max(1, int(self.settings.get("burst_multiplier", 5))) * 4)
                self.run_burst(profile, count=burst_count)
            if total % 100 == 0 and random.random() < float(self.settings.get("attack_wave_probability", 0.05)):
                self.set_attack_wave_active(True)
                with self.lock:
                    self.attack_waves_triggered += 1
                    self._write_state_locked()
                self.run_burst(profile, count=50)
                self._sleep_until(10.0)
                self.set_attack_wave_active(False)
            if time.time() >= next_print:
                counts = self.get_counts()
                print(
                    "Events generated: %s total (%s/min)"
                    % (counts["total_events"], counts["events_per_minute"]),
                    flush=True,
                )
                next_print = time.time() + 30
            self._sleep_until(random.uniform(interval_min, interval_max))
        self._write_state()


def _parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=None)
    parser.add_argument("--rate", type=int, default=0)
    parser.add_argument("--burst", action="store_true")
    parser.add_argument("--duration", type=int, default=0)
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv or sys.argv[1:])
    with DEFAULT_CONFIG_PATH.open(encoding="utf-8") as fh:
        config = json.load(fh)
    log_dir = ROOT / config.get("global_settings", {}).get("log_directory", "log_generator/logs")
    generator = LogGenerator(DEFAULT_CONFIG_PATH, log_dir)
    print("Log generator started. Writing to log_generator/logs/", flush=True)
    if args.burst:
        profile = args.profile or random.choice(list(generator.profiles))
        generator.run_burst(profile, count=20)
        generator._write_state()
        return
    generator.run_continuous(
        interval_range=(1, 5),
        duration=(args.duration or None),
        profile_name=args.profile,
        rate=(args.rate or None),
    )


if __name__ == "__main__":
    main()
