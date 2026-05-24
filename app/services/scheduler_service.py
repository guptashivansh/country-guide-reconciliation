import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.sync_service import run_sync
from app.services.slack_service import send_sync_alert

logger = logging.getLogger(__name__)


def _run_scheduled_sync(services, slack_webhook_url):
    logger.info("Scheduled sync triggered", extra={"stage": "scheduler"})
    try:
        result = run_sync(services)
        send_sync_alert(slack_webhook_url, result, triggered_by="scheduler")
    except Exception as e:
        logger.error("Scheduled sync failed", extra={"stage": "scheduler", "failure": str(e)})
        send_sync_alert(
            slack_webhook_url,
            {
                "total_changes": 0,
                "endpoints_processed": 0,
                "failures": 1,
                "per_country": {},
                "sync_error": str(e),
            },
            triggered_by="scheduler",
        )


def start_scheduler(flask_app, services, cron_expression, slack_webhook_url):
    """
    Start a background scheduler that runs the full sync on the given cron schedule.

    cron_expression: standard 5-field cron string, e.g. "0 8 * * *" for 8am UTC daily.
    """
    scheduler = BackgroundScheduler(timezone="UTC")
    trigger = CronTrigger.from_crontab(cron_expression)
    scheduler.add_job(
        _run_scheduled_sync,
        trigger=trigger,
        args=[services, slack_webhook_url],
        id="country_guide_sync",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.start()

    next_run = scheduler.get_job("country_guide_sync").next_run_time
    logger.info(
        "Scheduler started",
        extra={"stage": "scheduler", "cron": cron_expression, "next_run": str(next_run)},
    )

    # Shut down gracefully when the Flask app exits.
    import atexit
    def _shutdown():
        if scheduler.running:
            scheduler.shutdown(wait=False)

    atexit.register(_shutdown)

    flask_app.config["scheduler"] = scheduler
    return scheduler
