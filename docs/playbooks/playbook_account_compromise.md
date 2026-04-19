# Playbook: Account Compromise / Credential Stuffing
## Metadata
- ID: PB-002
- MITRE ATT&CK: T1078 (Valid Accounts), T1110 (Brute Force)
- Severity: High
- SLA: 15 minutes to triage, 1 hour to contain
- TheHive Template: ACCOUNT_COMPROMISE

## MITRE ATT&CK Mapping
| Tactic | Technique | ID |
|--------|-----------|-----|
| Credential Access | Brute Force | T1110 |
| Credential Access | Credential Stuffing | T1110.004 |
| Initial Access | Valid Accounts | T1078 |
| Collection | Data from Local System | T1005 |

## Escalation Integration
- L1 handles: Single account compromise, password reset
- Escalate to L2 if: >5 accounts, payment data accessed
- Escalate to L3 if: Bulk exfiltration, GDPR notification required
- TheHive: Add player-id custom field, set severity=High

## Trigger
- Failed login spike from single IP across multiple accounts
- Successful login from unusual geolocation
- Player report: account accessed without authorisation

## Triage (0-15 min)
1. Open TheHive case using ACCOUNT_COMPROMISE template
2. Record player ID in custom field: player-id
3. Check source IP against MISP threat feeds
4. Determine scope: single account or credential stuffing campaign?
5. Check if sensitive data (payment info, personal data) was accessed

## Contain (15 min - 1 hour)
1. Force password reset on compromised account(s)
2. Revoke all active sessions immediately
3. Temporarily lock account pending player verification
4. Block attacking IP(s) at firewall

## Investigate
1. Review full login history for affected account
2. Check for data access or in-game purchases post-compromise
3. Identify credential source (paste site, previous breach)
4. Search MISP for associated IOCs

## Notify
1. If personal data accessed: notify player within 72 hours (GDPR)
2. If payment data accessed: notify immediately + escalate to L3
3. Document notification in TheHive case

## Remediate
1. Enable MFA on affected account
2. Update detection thresholds for login anomalies
3. Export attacker IPs to MISP
4. Review and update account lockout policy

## Escalation
- Escalate to L3 if: payment data accessed, bulk account compromise
  (>10 accounts), or evidence of insider threat
