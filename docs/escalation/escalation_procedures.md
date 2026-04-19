# Escalation Procedures — Catnip Games SOC

## Escalation Tiers

### L1 — SOC Analyst
- Account: soc.analyst@catnipgames.com
- Handles: Initial triage, alert validation, low/medium severity
- SLA: 15 minutes to triage
- Escalates to L2 when: severity is High, SLA exceeded, player data at risk

### L2 — SOC Admin / Senior Analyst  
- Account: soc.admin@catnipgames.com
- Handles: High severity incidents, confirmed breaches, coordination
- SLA: 30 minutes to respond after escalation
- Escalates to L3 when: player data confirmed accessed, financial impact,
  infrastructure down, social engineering confirmed

### L3 — IR Lead / Management
- Handles: Critical incidents, GDPR notifications, public communications
- SLA: Immediate response
- External escalation: Legal, PR, Regulatory (ICO for GDPR)

## Escalation Triggers (with TheHive mappings)

### Immediate L3 Escalation (do not wait for L2)
- Player personal data confirmed accessed → GDPR 72-hour clock starts
- Payment data accessed → PCI DSS incident response required  
- Matchmaking service down during game launch window
- Evidence of insider threat
- Ransomware detected on any server

### L1 → L2 Escalation Triggers
- Case open > 15 minutes without triage action
- Severity upgraded to High during investigation
- More than 5 accounts compromised in single incident
- Bot attack affecting game economy integrity
- Social engineering attempt confirmed

### L2 → L3 Escalation Triggers
- Case open > 2 hours without containment
- Player data exfiltration confirmed
- Attack is coordinated/targeted (pre-launch sabotage suspected)
- Media or player community awareness of incident

## Escalation Process in TheHive

### Step 1 — Document escalation in case
Add task note: "ESCALATED TO L[X] at [TIME] — Reason: [REASON]"
Update custom field: incident-category to reflect escalation

### Step 2 — Notify via secure channel
L1 → L2: TheHive case assignment + direct message
L2 → L3: TheHive case assignment + phone call + email

### Step 3 — Update case severity if needed
Escalation often means severity upgrade:
PATCH /api/v1/case/{caseId} with {"severity": 3}

### Step 4 — Start escalation timer
Document time of escalation in TheHive case timeline
L2 has 30 minutes to respond before further escalation

## Communication Templates

### Player Data Breach Notification (GDPR)
Subject: Security Incident — Player Account Notification
We are writing to inform you that your account may have been 
affected by a security incident on [DATE]. We have taken 
immediate steps to secure your account including [ACTIONS].
Your data [WAS/WAS NOT] accessed. Please [NEXT STEPS].

### Internal Escalation Message
SECURITY ESCALATION — [SEVERITY]
Incident: [CASE TITLE]
TheHive Case: [CASE ID]
Time: [TIMESTAMP]
Summary: [2-3 sentences]
Immediate action required: [YES/NO]
Contact: [NAME] at [CONTACT]

## GDPR Considerations
- 72-hour reporting window to ICO starts when breach is confirmed
- Document all personal data categories affected
- Record number of individuals affected
- Preserve evidence for regulatory investigation
- Legal team must be notified for all personal data breaches
