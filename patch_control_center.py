#!/usr/bin/env python3
"""
Patch Operations Control Center.

This standalone localhost tool provides a controlled interface for
system maintenance operations: patch orchestration, health checks,
rollback, reporting validation, and integrity verification.

Design constraints:
- No changes required in other project files
- No extra frontend assets
- Whitelisted command execution only

In simple terms: this file is a "single control room" for the project.
It lets you run the important maintenance commands from one clean place
instead of switching between many terminal commands during assessment.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8787


@dataclass(frozen=True)
class Action:
    id: str
    title: str
    overview: str
    description: str
    commands: Sequence[Sequence[str]]
    expected_exit_codes: Sequence[int] = (0,)
    expected_exit_codes_per_command: Sequence[Sequence[int]] = ()
    caution: bool = False


ACTIONS: Dict[str, Action] = {
    "up_sim": Action(
        id="up_sim",
        title="Start Simulation Stack",
        overview="Starts all demo containers defined under the sim profile.",
        description="Brings up containers required for patch testing.",
        commands=[["docker", "compose", "--profile", "sim", "up", "-d"]],
    ),
    "down_sim": Action(
        id="down_sim",
        title="Stop Simulation Stack",
        overview="Stops and removes sim containers while keeping named volumes.",
        description="Useful to reset runtime state between demos.",
        commands=[["docker", "compose", "--profile", "sim", "down"]],
    ),
    "patch": Action(
        id="patch",
        title="Run Patch Orchestrator",
        overview="Executes full patch flow (common -> health_check -> patch -> security_scan -> reporting).",
        description="Executes project patch flow and generates latest report artifacts.",
        commands=[["make", "patch"]],
    ),
    "patch_dryrun": Action(
        id="patch_dryrun",
        title="Patch Dry Run",
        overview="Runs patch logic in check mode to preview changes without applying them.",
        description="Good for safe pre-change validation.",
        commands=[["make", "patch-dryrun"]],
    ),
    "patch_canary": Action(
        id="patch_canary",
        title="Patch Canary",
        overview="Applies patches to a limited canary group first before wider rollout.",
        description="Use this before production-like broad patch runs.",
        commands=[["make", "patch-canary"]],
    ),
    "health_check": Action(
        id="health_check",
        title="Run Health Check",
        overview="Validates host readiness before patching.",
        description="Executes health gate checks used by orchestrator flow.",
        commands=[["make", "patch-health"]],
    ),
    "drift_check": Action(
        id="drift_check",
        title="Run Drift Check",
        overview="Scans package state to detect drift/held packages across hosts.",
        description="Reports package-count and potential held/bad states.",
        commands=[
            [
                "docker",
                "compose",
                "exec",
                "ansible",
                "ansible-playbook",
                "/ansible/playbooks/drift_check.yml",
                "-i",
                "/ansible/inventory/hosts.ini",
            ]
        ],
    ),
    "rollback": Action(
        id="rollback",
        title="Run Rollback Playbook",
        overview="Triggers rollback path in patch role for recovery scenarios.",
        description="Use for controlled rollback demos after failed scenarios.",
        commands=[["make", "rollback"]],
        caution=True,
    ),
    "verify_integrity": Action(
        id="verify_integrity",
        title="Verify Report Integrity",
        overview="Validates that report hash in .sha256 matches current report content.",
        description="Checks SHA-256 checksum for patch_report_latest.json in container.",
        commands=[
            [
                "docker",
                "compose",
                "exec",
                "ansible",
                "sh",
                "-lc",
                "cd /ansible/reports && sha256sum -c patch_report_latest.json.sha256",
            ]
        ],
    ),
    "tamper_report": Action(
        id="tamper_report",
        title="Integrity Control Test",
        overview="Intentionally changes report bytes to prove cryptographic integrity checks.",
        description="Intentionally appends text to latest report to trigger checksum failure.",
        commands=[
            [
                "docker",
                "compose",
                "exec",
                "ansible",
                "sh",
                "-lc",
                "echo 'tampered' >> /ansible/reports/patch_report_latest.json",
            ]
        ],
        caution=True,
    ),
    "show_report_files": Action(
        id="show_report_files",
        title="List Report Files",
        overview="Shows generated reporting artifacts inside /ansible/reports.",
        description="Lists files currently available in /ansible/reports.",
        commands=[
            [
                "docker",
                "compose",
                "exec",
                "ansible",
                "sh",
                "-lc",
                "ls -lah /ansible/reports",
            ]
        ],
    ),
    "show_report_json": Action(
        id="show_report_json",
        title="Show Latest JSON Report",
        overview="Prints key sections from patch_report_latest.json for quick review.",
        description="Displays compliance, duration, and host outcomes.",
        commands=[
            [
                "docker",
                "compose",
                "exec",
                "ansible",
                "sh",
                "-lc",
                "jq '{compliance_percentage, duration_seconds, host_count: (.hosts|length), hosts: [.hosts[] | {host, changed, failed}]}' /ansible/reports/patch_report_latest.json",
            ]
        ],
    ),
    "validate_reports": Action(
        id="validate_reports",
        title="Validate Reporting Gates",
        overview="Runs compliance/SLA checks from Makefile validation target.",
        description="Confirms report quality gates expected by CI.",
        commands=[["make", "validate-reports"]],
    ),
    "ansible_syntax_check": Action(
        id="ansible_syntax_check",
        title="Syntax Check Orchestrator",
        overview="Verifies patch_orchestrator.yml syntax using project inventory.",
        description="Quick static check before running heavier workflows.",
        commands=[
            [
                "docker",
                "compose",
                "exec",
                "ansible",
                "ansible-playbook",
                "/ansible/playbooks/patch_orchestrator.yml",
                "-i",
                "/ansible/inventory/hosts.ini",
                "--syntax-check",
            ]
        ],
    ),
    "show_ansible_cfg": Action(
        id="show_ansible_cfg",
        title="Show ansible.cfg",
        overview="Prints control-node Ansible defaults used by this project.",
        description="Useful for showing inventory, roles_path, timeout, and logging config.",
        commands=[["sed", "-n", "1,220p", "ansible/ansible.cfg"]],
    ),
    "show_inventory_production": Action(
        id="show_inventory_production",
        title="Show Production Inventory",
        overview="Displays production inventory entries and groups used for targeting.",
        description="Maps hosts/groups for phased rollout demos.",
        commands=[["sed", "-n", "1,240p", "ansible/inventory/production.ini"]],
    ),
    "show_patch_role_tasks": Action(
        id="show_patch_role_tasks",
        title="Show Patch Role Tasks",
        overview="Displays core patch role task steps from roles/patch/tasks/main.yml.",
        description="Great for explaining how updates are applied.",
        commands=[["sed", "-n", "1,260p", "ansible/roles/patch/tasks/main.yml"]],
    ),
    "show_security_scan_tasks": Action(
        id="show_security_scan_tasks",
        title="Show Security Scan Tasks",
        overview="Displays security scan role task steps and controls.",
        description="Use this to explain security posture checks.",
        commands=[["sed", "-n", "1,260p", "ansible/roles/security_scan/tasks/main.yml"]],
    ),
    "show_reporting_tasks": Action(
        id="show_reporting_tasks",
        title="Show Reporting Tasks",
        overview="Displays how JSON/CSV/metrics artifacts are generated.",
        description="Useful for explaining evidence pipeline internals.",
        commands=[["sed", "-n", "1,280p", "ansible/roles/reporting/tasks/main.yml"]],
    ),
    "assessment_flow": Action(
        id="assessment_flow",
        title="Run End-to-End Assessment Flow",
        overview="Complete operational sequence: generate report, verify integrity, validate control failure, recover, and re-verify.",
        description="Patch -> verify OK -> tamper -> verify FAIL -> patch -> verify OK.",
        commands=[
            ["make", "patch"],
            [
                "docker",
                "compose",
                "exec",
                "ansible",
                "sh",
                "-lc",
                "cd /ansible/reports && sha256sum -c patch_report_latest.json.sha256",
            ],
            [
                "docker",
                "compose",
                "exec",
                "ansible",
                "sh",
                "-lc",
                "echo 'tampered' >> /ansible/reports/patch_report_latest.json",
            ],
            [
                "docker",
                "compose",
                "exec",
                "ansible",
                "sh",
                "-lc",
                "cd /ansible/reports && sha256sum -c patch_report_latest.json.sha256",
            ],
            ["make", "patch"],
            [
                "docker",
                "compose",
                "exec",
                "ansible",
                "sh",
                "-lc",
                "cd /ansible/reports && sha256sum -c patch_report_latest.json.sha256",
            ],
        ],
        expected_exit_codes_per_command=((0,), (0,), (0,), (1,), (0,), (0,)),
        caution=True,
    ),
}


def cmd_to_text(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def run_action(action: Action) -> Dict[str, object]:
    started = time.time()
    log_chunks: List[str] = []
    per_command = []
    success = True

    for idx, command in enumerate(action.commands, start=1):
        text = cmd_to_text(command)
        log_chunks.append(f"\n$ {text}\n")
        result = subprocess.run(
            list(command),
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        if stdout:
            log_chunks.append(stdout)
        if stderr:
            log_chunks.append(stderr)
        log_chunks.append(f"\n[exit_code={result.returncode}] command {idx}/{len(action.commands)}\n")

        expected_codes = action.expected_exit_codes
        if action.expected_exit_codes_per_command and len(action.expected_exit_codes_per_command) >= idx:
            expected_codes = action.expected_exit_codes_per_command[idx - 1]

        per_command.append(
            {
                "command": text,
                "exit_code": result.returncode,
                "expected_exit_codes": list(expected_codes),
            }
        )
        if result.returncode not in expected_codes:
            success = False
            break

    elapsed_ms = int((time.time() - started) * 1000)
    return {
        "ok": success,
        "elapsed_ms": elapsed_ms,
        "action": action.id,
        "title": action.title,
        "commands": per_command,
        "log": "".join(log_chunks),
    }


def dashboard_html() -> str:
    action_cards = []
    for action in ACTIONS.values():
        cmd_block = "\n".join(cmd_to_text(cmd) for cmd in action.commands)
        caution_badge = "<span class='badge caution'>Caution</span>" if action.caution else "<span class='badge'>Safe</span>"
        action_cards.append(
            f"""
            <article class="card">
              <div class="card-head">
                <h3>{action.title}</h3>
                {caution_badge}
              </div>
              <p><strong>Overview:</strong> {action.overview}</p>
              <p>{action.description}</p>
              <pre>{cmd_block}</pre>
              <div class="actions">
                <button class="run-btn" data-action="{action.id}">Run</button>
                <button class="copy-btn" data-copy="{cmd_block.replace('"', '&quot;')}">Copy Commands</button>
              </div>
            </article>
            """
        )

    cards = "\n".join(action_cards)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Patch Operations Control Center</title>
  <style>
    :root {{
      --bg: #0a0c14;
      --panel: #131827;
      --panel-2: #0f1422;
      --line: #2a3350;
      --text: #e8ecff;
      --sub: #a8b2d8;
      --brand: #4f7cff;
      --ok: #31c76a;
      --warn: #f5b93f;
      --bad: #ff5d6c;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --sans: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: var(--sans);
      color: var(--text);
      background: radial-gradient(1200px 700px at 15% -10%, #293f89 0%, transparent 40%),
                  radial-gradient(1000px 700px at 85% -10%, #30417a 0%, transparent 40%),
                  var(--bg);
      min-height: 100vh;
    }}
    .wrap {{ max-width: 1200px; margin: 40px auto; padding: 0 20px 40px; }}
    .hero {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 24px;
      background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01));
      backdrop-filter: blur(8px);
      margin-bottom: 22px;
    }}
    .hero h1 {{ margin: 0 0 10px; font-size: 30px; letter-spacing: 0.3px; }}
    .hero p {{ margin: 0; color: var(--sub); }}
    .status {{
      margin-top: 14px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      color: var(--sub);
    }}
    .dot {{ width: 10px; height: 10px; border-radius: 50%; background: var(--warn); box-shadow: 0 0 16px var(--warn); }}
    .dot.ok {{ background: var(--ok); box-shadow: 0 0 16px var(--ok); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 14px;
      margin-bottom: 16px;
    }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 14px;
      background: linear-gradient(180deg, var(--panel), var(--panel-2));
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      min-height: 250px;
    }}
    .card-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }}
    h3 {{ margin: 0; font-size: 18px; }}
    .badge {{
      border: 1px solid #2f9f53;
      color: #9ff0bc;
      background: rgba(49, 199, 106, 0.1);
      padding: 3px 8px;
      border-radius: 999px;
      font-size: 12px;
      white-space: nowrap;
    }}
    .badge.caution {{
      border-color: #b98920;
      color: #ffd98e;
      background: rgba(245, 185, 63, 0.12);
    }}
    .card p {{ margin: 0; color: var(--sub); font-size: 14px; }}
    pre {{
      margin: 0;
      flex: 1;
      background: #0b101d;
      border: 1px solid #1f2b48;
      border-radius: 10px;
      padding: 10px;
      font-size: 12px;
      line-height: 1.5;
      overflow: auto;
      font-family: var(--mono);
      color: #c5d0f8;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .actions {{ display: flex; gap: 8px; }}
    button {{
      border: 0;
      border-radius: 10px;
      padding: 9px 12px;
      font-weight: 600;
      cursor: pointer;
      transition: transform 0.08s ease, opacity 0.2s ease;
    }}
    button:hover {{ transform: translateY(-1px); }}
    button:disabled {{ opacity: 0.55; cursor: not-allowed; transform: none; }}
    .run-btn {{ background: var(--brand); color: white; }}
    .copy-btn {{ background: #222b45; color: #c7d3ff; }}
    .log-panel {{
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #070c16;
      padding: 0;
      overflow: hidden;
    }}
    .log-head {{
      border-bottom: 1px solid #223051;
      padding: 10px 12px;
      display: flex;
      justify-content: space-between;
      font-size: 13px;
      color: var(--sub);
      background: #0d1323;
    }}
    #log {{
      margin: 0;
      border: 0;
      border-radius: 0;
      min-height: 260px;
      max-height: 420px;
      background: #070c16;
      color: #dbe4ff;
      padding: 14px;
      font-size: 12px;
    }}
    .ok-text {{ color: var(--ok); }}
    .bad-text {{ color: var(--bad); }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>Patch Operations Control Center</h1>
      <p>Execute patch management, maintenance checks, recovery controls, and reporting validation from a localhost operations dashboard. Commands are whitelisted and executed in <code>{PROJECT_ROOT}</code>.</p>
      <div class="status"><span id="dot" class="dot"></span><span id="status-text">Idle</span></div>
    </section>
    <section class="grid">
      {cards}
    </section>
    <section class="log-panel">
      <div class="log-head">
        <span>Execution Log</span>
        <span id="meta">No run yet</span>
      </div>
      <pre id="log">Ready. Select an operation to execute approved command sequences.</pre>
    </section>
  </main>
  <script>
    const statusText = document.getElementById("status-text");
    const dot = document.getElementById("dot");
    const log = document.getElementById("log");
    const meta = document.getElementById("meta");
    const runButtons = [...document.querySelectorAll(".run-btn")];
    const copyButtons = [...document.querySelectorAll(".copy-btn")];

    function setBusy(isBusy, label) {{
      statusText.textContent = label;
      dot.className = isBusy ? "dot" : "dot ok";
      runButtons.forEach((btn) => btn.disabled = isBusy);
    }}

    async function runAction(action) {{
      setBusy(true, "Running " + action + "...");
      log.textContent = "$ Running action: " + action + "\\n";
      meta.textContent = "Executing...";
      const started = Date.now();
      try {{
        const res = await fetch("/api/run", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ action }})
        }});
        const data = await res.json();
        const ok = !!data.ok;
        log.textContent = data.log || "(no output)";
        const ms = data.elapsed_ms ?? (Date.now() - started);
        meta.innerHTML = ok
          ? `<span class="ok-text">Success</span> in ${{ms}} ms`
          : `<span class="bad-text">Failed</span> in ${{ms}} ms`;
        setBusy(false, ok ? "Last run: success" : "Last run: failed");
      }} catch (err) {{
        log.textContent += "\\n" + (err?.message || String(err));
        meta.innerHTML = `<span class="bad-text">Request error</span>`;
        setBusy(false, "Last run: request error");
      }}
    }}

    runButtons.forEach((btn) => {{
      btn.addEventListener("click", () => runAction(btn.dataset.action));
    }});

    copyButtons.forEach((btn) => {{
      btn.addEventListener("click", async () => {{
        try {{
          await navigator.clipboard.writeText(btn.dataset.copy);
          const original = btn.textContent;
          btn.textContent = "Copied";
          setTimeout(() => (btn.textContent = original), 900);
        }} catch {{
          btn.textContent = "Copy failed";
          setTimeout(() => (btn.textContent = "Copy Commands"), 900);
        }}
      }});
    }});
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _json(self, data: Dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _html(self, text: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = text.encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/" or self.path.startswith("/?"):
            self._html(dashboard_html())
            return
        if self.path == "/api/actions":
            data = {
                "actions": [
                    {
                        "id": action.id,
                        "title": action.title,
                        "description": action.description,
                        "commands": [cmd_to_text(cmd) for cmd in action.commands],
                        "caution": action.caution,
                    }
                    for action in ACTIONS.values()
                ]
            }
            self._json(data)
            return
        self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/run":
            self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self._json({"error": "Invalid JSON body"}, HTTPStatus.BAD_REQUEST)
            return

        action_id = payload.get("action")
        if not isinstance(action_id, str) or action_id not in ACTIONS:
            self._json({"error": "Unknown action"}, HTTPStatus.BAD_REQUEST)
            return

        result = run_action(ACTIONS[action_id])
        self._json(result, HTTPStatus.OK if result["ok"] else HTTPStatus.BAD_REQUEST)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Patch Operations Control Center running on http://{HOST}:{PORT}")
    print(f"Project root: {PROJECT_ROOT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
