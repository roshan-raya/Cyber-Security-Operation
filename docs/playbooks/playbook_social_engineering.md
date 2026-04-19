# Playbook: Social Engineering / Phishing
## Metadata
- ID: PB-003
- MITRE ATT&CK: T1566 (Phishing), T1598 (Spearphishing)
- Severity: High
- SLA: 15 minutes to triage, 1 hour to contain
- TheHive Template: SOCIAL_ENGINEERING

## MITRE ATT&CK Mapping
| Tactic | Technique | ID |
|--------|-----------|-----|
| Initial Access | Phishing | T1566 |
| Initial Access | Spearphishing | T1598 |
| Reconnaissance | Gather Victim Identity | T1589 |
| Defense Evasion | Impersonation | T1656 |

## Escalation Integration
- L1 handles: Initial report, block malicious domain
- Escalate to L2 immediately: All confirmed social engineering
- Escalate to L3 if: Data accessed, executive targeted
- TheHive: This is the near-breach scenario — always assign to L2

## Trigger
- Staff report of suspicious email or message
- Phishing link clicked by staff member
- Unusual access pattern following social contact
- This playbook was created following the near-breach incident
  at Catnip Games where player data was nearly exposed

## Triage (0-15 min)
1. Open TheHive case using SOCIAL_ENGINEERING template
2. Identify targeted user and attack vector
3. Determine if credentials or data were compromised
4. Immediate question: was player data accessed?
   → If YES: escalate to L3 IR Lead immediately

## Contain (15 min - 1 hour)
1. Isolate affected user account
2. Block malicious domain or sender at email gateway
3. Revoke any tokens or sessions created during attack window
4. Preserve evidence: email headers, chat logs, call recordings

## Investigate
1. Trace full attack chain from initial contact
2. Identify what data was targeted and whether accessed
3. Check if other staff members received same attack
4. Search MISP for associated domains/IPs

## Escalate
1. Notify L3 IR Lead if any data was accessed
2. Notify management if attack targeted executive staff
3. If player data at risk: begin GDPR breach assessment

## Remediate
1. Security awareness communication to all staff
2. Update email filtering rules
3. Export IOCs (domains, IPs, sender addresses) to MISP
4. Review and update social engineering response procedures

## Lessons Learned
- This playbook directly addresses the near-breach incident
- Ensure all staff know to report suspicious contacts immediately
- Regular social engineering simulation exercises recommended
