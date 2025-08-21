import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit
from models.models import Event
from app.calendar_service import EventSchedulerService
from loguru import logger

class CronScheduler:
    """Manages cron jobs for event reminders"""
    
    def __init__(self, event_service: EventSchedulerService):
        self.event_service = event_service
        self.scheduler = AsyncIOScheduler()
        self._setup_jobs()
    
    def _setup_jobs(self):
        """Setup recurring cron jobs"""
        # Check for reminders every minute
        self.scheduler.add_job(
            self._reminder_job,
            IntervalTrigger(minutes=1),
            id='reminder_check',
            name='Check and send event reminders',
            replace_existing=True
        )
        
        # Cleanup completed events daily
        self.scheduler.add_job(
            self._cleanup_job,
            IntervalTrigger(hours=24),
            id='daily_cleanup',
            name='Daily event cleanup',
            replace_existing=True
        )
    
    async def _reminder_job(self):
        """Cron job to check and send reminders"""
        try:
            logger.info("Running reminder check...")
            results = await self.event_service.send_reminders()
            
            if results.get("reminders_sent", 0) > 0:
                logger.info(f"Sent {results['reminders_sent']} reminders")
            
            if results.get("reminders_failed", 0) > 0:
                logger.warning(f"Failed to send {results['reminders_failed']} reminders")
                
        except Exception as e:
            logger.error(f"Reminder job failed: {e}")
    
    async def _cleanup_job(self):
        """Clean up old completed events"""
        try:
            logger.info("Running daily cleanup...")
            # Implementation for cleaning up old events
            # This could move completed events older than X days to archive
            pass
        except Exception as e:
            logger.error(f"Cleanup job failed: {e}")
    
    def start(self):
        """Start the cron scheduler"""
        self.scheduler.start()
        logger.info("Cron scheduler started")
        
        # Ensure scheduler stops on exit
        atexit.register(lambda: self.scheduler.shutdown())
    
    def stop(self):
        """Stop the cron scheduler"""
        self.scheduler.shutdown()
        logger.info("Cron scheduler stopped")

