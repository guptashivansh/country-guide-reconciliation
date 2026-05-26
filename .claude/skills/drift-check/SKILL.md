---
name: drift-check
description: >
  Run compliance drift detection to identify stalled reviews, missing provenance, escalation-worthy
  items, and stale rules. Use when the user asks to: check drift, audit compliance health, find
  stale reviews, detect bottlenecks, or run a compliance health check.
---

# Drift Check Skill

Runs the `DriftDetector` against all or specific countries to surface compliance process issues:
- **PENDING_CHANGE**: review queue items sitting unactioned too long
- **ESCALATED_ITEM**: escalated items unresolved past threshold
- **MISSING_SECTION**: newly discovered regulatory requirements not yet in the guide
- **STALE_VERIFICATION**: rules not re-verified against official sources recently
- **NO_PROVENANCE**: rules with no audit trail to a source

Thresholds: pending critical → immediate, pending major → 14d, pending minor → 7d, escalated → 7d, stale → 14/30/90d.

## Steps to follow

### 1. Ask scope

Ask the user:

> "Run drift detection for:
> - **All countries** — full compliance health check
> - **Specific country** — which one?"

Wait for the user's answer.

### 2. Run drift detection

**All countries:**
```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
services['provenance_repository'].initialize_schema()
detector = services['drift_detector']
reports = detector.detect_all()
for report in reports:
    if not report.drift_detected:
        print(f'{report.country}: OK — no drift detected')
        continue
    print(f'\n{report.country}: {report.severity} — {len(report.affected_sections)} issue(s)')
    print(f'  Summary: {report.summary}')
    for rec in report.affected_sections:
        print(f'  [{rec.severity}] {rec.section} — {rec.drift_type}')
        print(f'    {rec.evidence}')
        print(f'    Action: {rec.recommended_action}')
    if report.recommended_action:
        print(f'  Overall: {report.recommended_action}')
"
```

**Single country:**
```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app import build_services
services = build_services()
services['country_guide_repository'].initialize_schema()
services['provenance_repository'].initialize_schema()
detector = services['drift_detector']
report = detector.detect('COUNTRY_NAME')
if not report.drift_detected:
    print(f'{report.country}: OK — no drift detected')
else:
    print(f'{report.country}: {report.severity} — {len(report.affected_sections)} issue(s)')
    print(f'Summary: {report.summary}')
    for rec in report.affected_sections:
        print(f'  [{rec.severity}] {rec.section} — {rec.drift_type}')
        print(f'    {rec.evidence}')
        print(f'    Action: {rec.recommended_action}')
    print(f'\nOverall: {report.recommended_action}')
"
```

### 3. Present results

Format the drift report clearly:
- Group by severity (CRITICAL first, then WARNING, then INFO)
- For each issue, show the section, drift type, evidence, and recommended action
- Highlight the total count of CRITICAL vs WARNING vs INFO issues

### 4. Suggest remediation

Based on the findings, suggest next steps:
- **PENDING_CHANGE / ESCALATED_ITEM**: "Use the **review** skill to approve or reject these items"
- **STALE_VERIFICATION**: "Use the **sync** skill to re-crawl and verify these sections"
- **NO_PROVENANCE**: "Use the **sync** skill to establish source-verified provenance"
- **MISSING_SECTION**: "Use the **review** skill to publish newly detected requirements"
