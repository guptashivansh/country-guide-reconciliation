---
name: configure-schedule
description: >
  Configure the recurring auto-sync cron schedule for the compliance pipeline. Use when the user
  asks to: set up auto-sync, configure the schedule, change the cron expression, enable or
  disable scheduled syncs, or check when the next sync runs.
---

# Configure Schedule Skill

Manages the `SYNC_CRON_SCHEDULE` environment variable that controls when the compliance pipeline automatically syncs. When set, the Flask app starts a background APScheduler job that runs `run_sync()` on the given cron schedule and posts results to Slack.

## Steps to follow

### 1. Show current schedule configuration

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app.utils.config import load_env_file, sync_cron_schedule, slack_webhook_url
load_env_file()
cron = sync_cron_schedule()
slack = slack_webhook_url()
if cron:
    print(f'Current cron schedule: {cron}')
else:
    print('Auto-sync is DISABLED (SYNC_CRON_SCHEDULE not set)')
print(f'Slack webhook: {\"configured\" if slack else \"NOT configured\"}')
"
```

Also check the `.env` file:
```bash
grep -n 'SYNC_CRON_SCHEDULE\|SLACK_WEBHOOK_URL' .env 2>/dev/null || echo "No schedule or webhook in .env"
```

### 2. Ask what to configure

Present the current state and ask:

> "What would you like to do?
> - **Set schedule** — provide a 5-field cron expression (e.g., `0 8 * * *` for daily at 8am UTC)
> - **Disable schedule** — remove the cron schedule
> - **Common presets**:
>   - Daily at 8am UTC: `0 8 * * *`
>   - Every 12 hours: `0 */12 * * *`
>   - Weekly Monday 6am UTC: `0 6 * * 1`
>   - Every 6 hours: `0 */6 * * *`"

Wait for the user's answer.

### 3. Apply the configuration

**Set a schedule:**

Edit `.env` to add or update `SYNC_CRON_SCHEDULE`:

If the line already exists, update it. If not, append it.

```bash
grep -q 'SYNC_CRON_SCHEDULE' .env 2>/dev/null
```

If the variable exists, edit the line. If not, append it:
```bash
echo 'SYNC_CRON_SCHEDULE=0 8 * * *' >> .env
```

**Disable the schedule:**

Comment out or remove the `SYNC_CRON_SCHEDULE` line from `.env`.

### 4. Verify the configuration

```bash
python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from app.utils.config import load_env_file, sync_cron_schedule
# Reload to pick up changes
for key in list(os.environ):
    if key == 'SYNC_CRON_SCHEDULE':
        del os.environ[key]
load_env_file()
cron = sync_cron_schedule()
if cron:
    from apscheduler.triggers.cron import CronTrigger
    trigger = CronTrigger.from_crontab(cron)
    print(f'Schedule set: {cron}')
    print(f'Valid cron expression: yes')
else:
    print('Auto-sync is disabled.')
"
```

### 5. Remind about Slack

If `SLACK_WEBHOOK_URL` is not set, tell the user:

> "Note: Sync results are posted to Slack. To receive notifications, add `SLACK_WEBHOOK_URL` to `.env`.
> Without it, syncs will still run but you won't get notified of results."

### 6. Remind about restart

Tell the user:

> "The schedule takes effect on the next app restart. Run `python app.py` to start the server with the new schedule. The scheduler runs in UTC timezone."
