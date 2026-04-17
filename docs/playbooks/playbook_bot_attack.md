# Playbook: Bot Attack / Game Exploit
## Metadata
- ID: PB-001
- MITRE ATT&CK: T1078 (Valid Accounts), T1499 (Endpoint DoS)
- Severity: Medium
- SLA: 15 minutes to triage, 2 hours to contain
- TheHive Template: BOT_ATTACK

## Trigger
- IDS alert: repeated API calls from single IP
- Game server log: abnormal matchmaking request rate
- Player report: suspected cheating or unfair advantage

## Triage (0-15 min)
1. Open TheHive case using BOT_ATTACK template
2. Record affected server in custom field: affected-server
3. Check source IP against MISP: is it a known bot network?
4. Determine: automated script, botnet C2, or manual exploitation?
5. Severity decision: if player data at risk → escalate to High

## Contain (15 min - 2 hours)
1. Block offending IP(s) at firewall level
2. Flag associated player account(s) in game database
3. Rate-limit affected API endpoint
4. Notify game development team via secure channel

## Investigate
1. Analyse full traffic pattern for past 24 hours
2. Identify exploit method and affected game mechanic
3. Check for similar patterns across other servers
4. Document all IOCs: IPs, user agents, request patterns

## Remediate
1. Patch exploited game endpoint
2. Update bot detection rules
3. Add IOCs to MISP for team sharing
4. Update rate limiting thresholds

## Escalation
- Escalate to L3 if: player data accessed, financial impact,
  exploit affects core game integrity pre-launch

## Lessons Learned
- Document in TheHive case notes
- Update this playbook if new bot technique identified
