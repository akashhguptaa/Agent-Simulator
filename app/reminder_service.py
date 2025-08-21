import asyncio
import json
import logging
from datetime import datetime, timedelta
import os
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import pytz
from twilio.rest import Client
from twilio.base.exceptions import TwilioException
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from dotenv import load_dotenv

load_dotenv()


class ReminderStatus(Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RecurrenceType(Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class User:
    user_id: str
    phone_number: str
    timezone: str = "UTC"
    opt_out: bool = False
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


@dataclass
class Reminder:
    reminder_id: str
    user_id: str
    message: str
    scheduled_time: datetime
    status: ReminderStatus = ReminderStatus.PENDING
    recurrence: RecurrenceType = RecurrenceType.NONE
    created_at: datetime = None
    sent_at: Optional[datetime] = None
    next_occurrence: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

        if self.recurrence != RecurrenceType.NONE and self.next_occurrence is None:
            self.next_occurrence = self._calculate_next_occurrence()

    def _calculate_next_occurrence(self) -> datetime:
        """Calculate the next occurrence based on recurrence type"""
        if self.recurrence == RecurrenceType.DAILY:
            return self.scheduled_time + timedelta(days=1)
        elif self.recurrence == RecurrenceType.WEEKLY:
            return self.scheduled_time + timedelta(weeks=1)
        elif self.recurrence == RecurrenceType.MONTHLY:
            return self.scheduled_time + timedelta(days=30)
        return None


class MockMemoryStore:
    """In-memory storage for demonstration - replace with actual database in production"""

    def __init__(self):
        self.users: Dict[str, User] = {}
        self.reminders: Dict[str, Reminder] = {}
        self._load_from_file()

    def _load_from_file(self):
        """Load data from JSON file on startup"""
        try:
            with open("reminder_data.json", "r") as f:
                data = json.load(f)

            for user_data in data.get("users", []):
                user_data["created_at"] = datetime.fromisoformat(
                    user_data["created_at"]
                )
                user = User(**user_data)
                self.users[user.user_id] = user

            for reminder_data in data.get("reminders", []):
                reminder_data["scheduled_time"] = datetime.fromisoformat(
                    reminder_data["scheduled_time"]
                )
                reminder_data["created_at"] = datetime.fromisoformat(
                    reminder_data["created_at"]
                )
                if reminder_data.get("sent_at"):
                    reminder_data["sent_at"] = datetime.fromisoformat(
                        reminder_data["sent_at"]
                    )
                if reminder_data.get("next_occurrence"):
                    reminder_data["next_occurrence"] = datetime.fromisoformat(
                        reminder_data["next_occurrence"]
                    )

                reminder_data["status"] = ReminderStatus(reminder_data["status"])
                reminder_data["recurrence"] = RecurrenceType(
                    reminder_data["recurrence"]
                )

                reminder = Reminder(**reminder_data)
                self.reminders[reminder.reminder_id] = reminder

        except FileNotFoundError:
            logger.info("No existing data file found, starting fresh")
        except Exception as e:
            logger.error(f"Error loading data: {e}")

    def _save_to_file(self):
        """Save data to JSON file"""
        try:
            data = {"users": [], "reminders": []}

            for user in self.users.values():
                user_dict = asdict(user)
                user_dict["created_at"] = user_dict["created_at"].isoformat()
                data["users"].append(user_dict)

            for reminder in self.reminders.values():
                reminder_dict = asdict(reminder)
                reminder_dict["scheduled_time"] = reminder_dict[
                    "scheduled_time"
                ].isoformat()
                reminder_dict["created_at"] = reminder_dict["created_at"].isoformat()
                if reminder_dict.get("sent_at"):
                    reminder_dict["sent_at"] = reminder_dict["sent_at"].isoformat()
                if reminder_dict.get("next_occurrence"):
                    reminder_dict["next_occurrence"] = reminder_dict[
                        "next_occurrence"
                    ].isoformat()

                reminder_dict["status"] = reminder_dict["status"].value
                reminder_dict["recurrence"] = reminder_dict["recurrence"].value
                data["reminders"].append(reminder_dict)

            with open("reminder_data.json", "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Error saving data: {e}")

    async def save_user(self, user: User):
        """Save or update user"""
        self.users[user.user_id] = user
        self._save_to_file()
        logger.info(f"User {user.user_id} saved")

    async def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        return self.users.get(user_id)

    async def save_reminder(self, reminder: Reminder):
        """Save or update reminder"""
        self.reminders[reminder.reminder_id] = reminder
        self._save_to_file()
        logger.info(f"Reminder {reminder.reminder_id} saved")

    async def get_reminder(self, reminder_id: str) -> Optional[Reminder]:
        """Get reminder by ID"""
        return self.reminders.get(reminder_id)

    async def get_pending_reminders(self) -> List[Reminder]:
        """Get all pending reminders that are due"""
        now = datetime.utcnow()
        pending = []

        for reminder in self.reminders.values():
            if (
                reminder.status == ReminderStatus.PENDING
                and reminder.scheduled_time <= now
            ):
                pending.append(reminder)

        return pending

    async def get_user_reminders(self, user_id: str) -> List[Reminder]:
        """Get all reminders for a user"""
        return [r for r in self.reminders.values() if r.user_id == user_id]


class TwilioService:
    """Service for sending SMS and WhatsApp messages via Twilio"""

    def __init__(self, account_sid: str, auth_token: str, whatsapp_number: str = None):
        self.client = Client(account_sid, auth_token)
        self.whatsapp_number = (
            whatsapp_number or "whatsapp:+14155238886"
        )  # Twilio Sandbox

    async def send_sms(self, to_number: str, message: str, from_number: str) -> bool:
        """Send SMS message"""
        try:
            message_obj = self.client.messages.create(
                body=message, from_=from_number, to=to_number
            )
            logger.info(f"SMS sent successfully. SID: {message_obj.sid}")
            return True

        except TwilioException as e:
            logger.error(f"Failed to send SMS: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending SMS: {e}")
            return False

    async def send_whatsapp(self, to_number: str, message: str) -> bool:
        """Send WhatsApp message"""
        try:
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"

            logger.info(f"Attempting to send WhatsApp message:")
            logger.info(f"  From: {self.whatsapp_number}")
            logger.info(f"  To: {to_number}")
            logger.info(f"  Message length: {len(message)} characters")

            message_obj = self.client.messages.create(
                body=message, from_=self.whatsapp_number, to=to_number
            )

            logger.info(f"WhatsApp message created successfully!")
            logger.info(f"  SID: {message_obj.sid}")
            logger.info(f"  Status: {message_obj.status}")
            logger.info(f"  Direction: {message_obj.direction}")

            return True

        except TwilioException as e:
            logger.error(f"Twilio WhatsApp error: {e}")
            logger.error(f"Error code: {getattr(e, 'code', 'No code')}")
            logger.error(f"Error details: {getattr(e, 'details', 'No details')}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending WhatsApp: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            return False


class ReminderService:
    """Main service for managing reminders"""

    def __init__(
        self,
        twilio_account_sid: str,
        twilio_auth_token: str,
        sms_from_number: str,
        whatsapp_number: str = None,
    ):
        self.store = MockMemoryStore()
        self.twilio = TwilioService(
            twilio_account_sid, twilio_auth_token, whatsapp_number
        )
        self.sms_from_number = sms_from_number
        self.scheduler = AsyncIOScheduler()
        self.running = False

    async def create_user(
        self, user_id: str, phone_number: str, timezone: str = "UTC"
    ) -> User:
        """Create a new user"""
        user = User(user_id=user_id, phone_number=phone_number, timezone=timezone)
        await self.store.save_user(user)
        return user

    async def create_reminder(
        self,
        user_id: str,
        reminder_id: str,
        message: str,
        scheduled_time: datetime,
        recurrence: RecurrenceType = RecurrenceType.NONE,
    ) -> Reminder:
        """Create a new reminder"""
        user = await self.store.get_user(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        reminder = Reminder(
            reminder_id=reminder_id,
            user_id=user_id,
            message=message,
            scheduled_time=scheduled_time,
            recurrence=recurrence,
        )

        await self.store.save_reminder(reminder)
        return reminder

    async def opt_out_user(self, user_id: str):
        """Opt out user from receiving reminders"""
        user = await self.store.get_user(user_id)
        if user:
            user.opt_out = True
            await self.store.save_user(user)
            logger.info(f"User {user_id} opted out")

    async def opt_in_user(self, user_id: str):
        """Opt user back in to receive reminders"""
        user = await self.store.get_user(user_id)
        if user:
            user.opt_out = False
            await self.store.save_user(user)
            logger.info(f"User {user_id} opted in")

    async def cancel_reminder(self, reminder_id: str):
        """Cancel a reminder"""
        reminder = await self.store.get_reminder(reminder_id)
        if reminder:
            reminder.status = ReminderStatus.CANCELLED
            await self.store.save_reminder(reminder)
            logger.info(f"Reminder {reminder_id} cancelled")

    def _convert_to_user_timezone(self, dt: datetime, user_timezone: str) -> datetime:
        """Convert UTC datetime to user's timezone"""
        try:
            utc_tz = pytz.UTC
            user_tz = pytz.timezone(user_timezone)

            # Ensure datetime is UTC aware
            if dt.tzinfo is None:
                dt = utc_tz.localize(dt)

            return dt.astimezone(user_tz)
        except:
            return dt  

    async def send_reminder(self, reminder: Reminder) -> bool:
        """Send a single reminder"""
        logger.info(f"Processing reminder: {reminder.reminder_id}")

        user = await self.store.get_user(reminder.user_id)
        if not user:
            logger.error(
                f"User {reminder.user_id} not found for reminder {reminder.reminder_id}"
            )
            return False

        if user.opt_out:
            logger.info(f"User {reminder.user_id} has opted out, skipping reminder")
            reminder.status = ReminderStatus.CANCELLED
            await self.store.save_reminder(reminder)
            return False

        local_time = self._convert_to_user_timezone(
            reminder.scheduled_time, user.timezone
        )
        message_with_context = f"Reminder: {reminder.message}\n\nScheduled for: {local_time.strftime('%Y-%m-%d %H:%M %Z')}"

        logger.info(f"Sending reminder to {user.phone_number}")

        success = await self.twilio.send_whatsapp(
            user.phone_number, message_with_context
        )

        if not success:
            logger.warning("WhatsApp delivery failed, attempting SMS fallback...")
            success = await self.twilio.send_sms(
                user.phone_number, message_with_context, self.sms_from_number
            )
            if success:
                logger.info("SMS fallback successful")
            else:
                logger.error("Both WhatsApp and SMS delivery failed")

        if success:
            reminder.status = ReminderStatus.SENT
            reminder.sent_at = datetime.utcnow()
            logger.info(f"Reminder {reminder.reminder_id} marked as SENT")

    
            if reminder.recurrence != RecurrenceType.NONE:

                next_reminder = Reminder(
                    reminder_id=f"{reminder.reminder_id}_{int(time.time())}",
                    user_id=reminder.user_id,
                    message=reminder.message,
                    scheduled_time=reminder.next_occurrence,
                    recurrence=reminder.recurrence,
                )
                await self.store.save_reminder(next_reminder)
                logger.info(f"Created recurring reminder: {next_reminder.reminder_id}")
        else:
            reminder.status = ReminderStatus.FAILED
            logger.error(f"Reminder {reminder.reminder_id} marked as FAILED")

        await self.store.save_reminder(reminder)
        return success

    async def process_pending_reminders(self):
        """Process all pending reminders"""
        pending_reminders = await self.store.get_pending_reminders()

        if not pending_reminders:
            logger.debug("No pending reminders to process")
            return

        logger.info(f"Processing {len(pending_reminders)} pending reminders")

        for reminder in pending_reminders:
            try:
                await self.send_reminder(reminder)
            except Exception as e:
                logger.error(f"Error processing reminder {reminder.reminder_id}: {e}")

    def start_service(self):
        """Start the background scheduler"""
        self.running = True

        self.scheduler.add_job(
            self.process_pending_reminders,
            CronTrigger(second=0),  
            id="reminder_processor",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info("Reminder scheduler started")

    def stop_service(self):
        """Stop the background scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
        self.running = False
        logger.info("Reminder scheduler stopped")


async def main():
    """Example usage of the reminder system"""
  
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
    SMS_FROM_NUMBER = os.getenv("TWILIO_NUMBER")
    WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
    print(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, SMS_FROM_NUMBER, WHATSAPP_NUMBER)

    reminder_service = ReminderService(
        twilio_account_sid=TWILIO_ACCOUNT_SID,
        twilio_auth_token=TWILIO_AUTH_TOKEN,
        sms_from_number=SMS_FROM_NUMBER,
        whatsapp_number=WHATSAPP_NUMBER,
    )

    reminder_service.start_service()

    try:
        user = await reminder_service.create_user(
            user_id="user123",
            phone_number=os.getenv("TWILIO_TARGET_NUMBER"),
            timezone="America/New_York",
        )
        print(f"Created user: {user.user_id}")
        scheduled_time = datetime.utcnow() + timedelta(minutes=1)
        reminder = await reminder_service.create_reminder(
            user_id="user123",
            reminder_id="reminder123",
            message="Don't forget to take your medication!",
            scheduled_time=scheduled_time,
            recurrence=RecurrenceType.DAILY,
        )
        print(f"Created reminder: {reminder.reminder_id} for {scheduled_time}")

        print("Reminder service is running. Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        reminder_service.stop_service()


if __name__ == "__main__":
    asyncio.run(main())
