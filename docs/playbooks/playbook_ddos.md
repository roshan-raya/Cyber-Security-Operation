# Playbook: DDoS / Infrastructure Attack
## Metadata
- ID: PB-004
- MITRE ATT&CK: T1498 (Network DoS), T1499 (Endpoint DoS)
- Severity: High
- SLA: 15 minutes to triage, 30 minutes to mitigate
- TheHive Template: DDOS_INFRASTRUCTURE

## MITRE ATT&CK Mapping
| Tactic | Technique | ID |
|--------|-----------|-----|
| Impact | Network Denial of Service | T1498 |
| Impact | Endpoint Denial of Service | T1499 |
| Reconnaissance | Active Scanning | T1595 |
| Resource Development | Botnet | T1583.005 |

## Escalation Integration
- L1 handles: Initial detection, rate limiting
- Escalate to L2 immediately: Matchmaking service impacted
- Escalate to L3 if: Extended outage, pre-launch timing suspicious
- TheHive: Set matchmaking-service custom field

## Trigger
- Prometheus alert: server CPU/bandwidth threshold exceeded
- Game server: matchmaking latency spike
- Player reports: mass game disconnections
- Network monitoring: unusual traffic volume spike

## Triage (0-15 min)
1. Open TheHive case using DDOS_INFRASTRUCTURE template
2. Record affected servers in custom field: affected-server
3. Record affected service in: matchmaking-service
4. Determine attack type: volumetric, protocol, or application layer
5. Assess impact: is matchmaking down? are game sessions dropping?

## Contain (15 min - 30 min)
1. Activate rate limiting on affected endpoints immediately
2. Enable DDoS mitigation rules at network edge
3. Null-route most aggressive attack sources
4. Notify L3 IR Lead and management if matchmaking is down
5. Post player-facing status update if outage exceeds 10 minutes

## Investigate
1. Identify attack vectors and primary source IP ranges
2. Determine if attack is targeted (pre-launch sabotage?) or opportunistic
3. Check MISP for known DDoS-for-hire or botnet C2 IOCs
4. Correlate with any recent threats or competitor activity

## Escalate
1. Escalate to L3 immediately if:
   - Matchmaking service is down
   - Attack persists beyond 30 minutes
   - Evidence of coordinated attack pre-launch

## Remediate
1. Restore affected services once attack subsides
2. Review and harden rate limiting and DDoS protection
3. Export attack source IPs to MISP
4. Document timeline for post-incident review

## Post-Incident
1. Full timeline review with development and infrastructure teams
2. Update DDoS protection thresholds
3. Consider CDN or DDoS protection service before game launch
