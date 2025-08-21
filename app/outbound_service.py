import asyncio
import hashlib
import json
from loguru import logger
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, asdict
from enum import Enum
import aiohttp
from twilio.rest import Client
import sqlite3
from dotenv import load_dotenv
import os
from contextlib import asynccontextmanager
# from config.config import (
#     TWILIO_ACCOUNT_SID,
#     TWILIO_AUTH_TOKEN,
#     TWILIO_FROM_NUMBER,
#     TAVILY_API_KEY,
# )

# Load environment variables from .env file
load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_NUMBER")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

missing_vars = []
if not TWILIO_ACCOUNT_SID:
    missing_vars.append("TWILIO_ACCOUNT_SID")
if not TWILIO_AUTH_TOKEN:
    missing_vars.append("TWILIO_AUTH_TOKEN")
if not TWILIO_FROM_NUMBER:
    missing_vars.append("TWILIO_FROM_NUMBER")
if not TAVILY_API_KEY:
    missing_vars.append("TAVILY_API_KEY")

if missing_vars:
    logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
    logger.error("Please check your .env file")


class AlertType(Enum):
    PRICE_DROP = "price_drop"
    JOB_MATCH = "job_match"
    TRANSACTION = "transaction"


class NotificationMethod(Enum):
    SMS = "sms"
    CALL = "call"
    BOTH = "both"


@dataclass
class UserPreference:
    user_id: str
    phone_number: str
    opted_in: bool = True
    alert_types: List[AlertType] = None
    notification_method: NotificationMethod = NotificationMethod.SMS
    price_threshold: float = 0.0  # Minimum price drop percentage
    keywords: List[str] = None  # Job keywords
    max_alerts_per_day: int = 5
    quiet_hours_start: Optional[str] = "22:00"  # Format: "HH:MM"
    quiet_hours_end: Optional[str] = "08:00"
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.alert_types is None:
            self.alert_types = [AlertType.PRICE_DROP, AlertType.JOB_MATCH]
        if self.keywords is None:
            self.keywords = []
        if self.created_at is None:
            self.created_at = datetime.utcnow()


@dataclass
class Alert:
    alert_id: str
    user_id: str
    alert_type: AlertType
    title: str
    message: str
    data: Dict[str, Any]
    created_at: datetime = None
    sent_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

    def get_hash(self) -> str:
        """Generate hash for deduplication"""
        content = f"{self.user_id}_{self.alert_type.value}_{self.title}_{json.dumps(self.data, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()


class DatabaseManager:
    def __init__(self, db_path: str = "alerts.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize SQLite database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # User preferences table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY,
                phone_number TEXT NOT NULL,
                opted_in BOOLEAN DEFAULT 1,
                alert_types TEXT,
                notification_method TEXT DEFAULT 'sms',
                price_threshold REAL DEFAULT 0.0,
                keywords TEXT,
                max_alerts_per_day INTEGER DEFAULT 5,
                quiet_hours_start TEXT,
                quiet_hours_end TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Alerts table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                alert_id TEXT PRIMARY KEY,
                user_id TEXT,
                alert_type TEXT,
                title TEXT,
                message TEXT,
                data TEXT,
                alert_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user_preferences (user_id)
            )
        """
        )

        # Daily alert counts table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_alert_counts (
                user_id TEXT,
                date TEXT,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )
        """
        )

        conn.commit()
        conn.close()

    def save_user_preference(self, pref: UserPreference):
        """Save or update user preference"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO user_preferences 
            (user_id, phone_number, opted_in, alert_types, notification_method, 
             price_threshold, keywords, max_alerts_per_day, quiet_hours_start, quiet_hours_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                pref.user_id,
                pref.phone_number,
                pref.opted_in,
                json.dumps([at.value for at in pref.alert_types]),
                pref.notification_method.value,
                pref.price_threshold,
                json.dumps(pref.keywords),
                pref.max_alerts_per_day,
                pref.quiet_hours_start,
                pref.quiet_hours_end,
            ),
        )

        conn.commit()
        conn.close()

    def get_user_preferences(self) -> List[UserPreference]:
        """Get all opted-in user preferences"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM user_preferences WHERE opted_in = 1
        """
        )

        prefs = []
        for row in cursor.fetchall():
            pref = UserPreference(
                user_id=row[0],
                phone_number=row[1],
                opted_in=bool(row[2]),
                alert_types=[AlertType(at) for at in json.loads(row[3])],
                notification_method=NotificationMethod(row[4]),
                price_threshold=row[5],
                keywords=json.loads(row[6]),
                max_alerts_per_day=row[7],
                quiet_hours_start=row[8],
                quiet_hours_end=row[9],
            )
            prefs.append(pref)

        conn.close()
        return prefs

    def save_alert(self, alert: Alert) -> bool:
        """Save alert if not duplicate"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        alert_hash = alert.get_hash()

        # Check for duplicate
        cursor.execute(
            """
            SELECT COUNT(*) FROM alerts 
            WHERE alert_hash = ? AND created_at > datetime('now', '-1 day')
        """,
            (alert_hash,),
        )

        if cursor.fetchone()[0] > 0:
            conn.close()
            return False  # Duplicate found

        # Save alert
        cursor.execute(
            """
            INSERT INTO alerts 
            (alert_id, user_id, alert_type, title, message, data, alert_hash, sent_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                alert.alert_id,
                alert.user_id,
                alert.alert_type.value,
                alert.title,
                alert.message,
                json.dumps(alert.data),
                alert_hash,
                alert.sent_at,
            ),
        )

        conn.commit()
        conn.close()
        return True

    def get_daily_alert_count(self, user_id: str, date: str) -> int:
        """Get daily alert count for user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT count FROM daily_alert_counts 
            WHERE user_id = ? AND date = ?
        """,
            (user_id, date),
        )

        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0

    def increment_daily_count(self, user_id: str, date: str):
        """Increment daily alert count"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR IGNORE INTO daily_alert_counts (user_id, date, count)
            VALUES (?, ?, 0)
        """,
            (user_id, date),
        )

        cursor.execute(
            """
            UPDATE daily_alert_counts 
            SET count = count + 1 
            WHERE user_id = ? AND date = ?
        """,
            (user_id, date),
        )

        conn.commit()
        conn.close()


class TavilyClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.tavily.com"

    async def search_price_drops(
        self, keywords: List[str], threshold: float = 10.0
    ) -> List[Dict]:
        """Search for price drops using Tavily API"""
        async with aiohttp.ClientSession() as session:
            search_query = f"price drop discount sale {' OR '.join(keywords)}"

            payload = {
                "api_key": self.api_key,
                "query": search_query,
                "search_depth": "basic",
                "include_domains": [
                    "amazon.com",
                    "ebay.com",
                    "walmart.com",
                    "target.com",
                ],
                "max_results": 10,
            }

            async with session.post(
                f"{self.base_url}/search", json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_price_results(data.get("results", []), threshold)
                else:
                    logger.error(f"Tavily API error: {response.status}")
                    return []

    async def search_jobs(self, keywords: List[str]) -> List[Dict]:
        """Search for job postings using Tavily API"""
        async with aiohttp.ClientSession() as session:
            search_query = f"job openings hiring {' OR '.join(keywords)}"

            payload = {
                "api_key": self.api_key,
                "query": search_query,
                "search_depth": "basic",
                "include_domains": [
                    "indeed.com",
                    "linkedin.com",
                    "glassdoor.com",
                    "monster.com",
                ],
                "max_results": 10,
            }

            async with session.post(
                f"{self.base_url}/search", json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_job_results(data.get("results", []))
                else:
                    logger.error(f"Tavily API error: {response.status}")
                    return []

    def _parse_price_results(self, results: List[Dict], threshold: float) -> List[Dict]:
        """Parse and filter price drop results"""
        price_drops = []
        for result in results:
            # Simple price drop detection (you'd want more sophisticated parsing)
            content = result.get("content", "").lower()
            if any(
                term in content for term in ["% off", "discount", "sale", "price drop"]
            ):
                price_drops.append(
                    {
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "content": result.get("content", "")[:200],
                        "estimated_discount": self._extract_discount(content),
                    }
                )
        return price_drops

    def _parse_job_results(self, results: List[Dict]) -> List[Dict]:
        """Parse job search results"""
        jobs = []
        for result in results:
            jobs.append(
                {
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "content": result.get("content", "")[:200],
                    "company": self._extract_company(result.get("content", "")),
                }
            )
        return jobs

    def _extract_discount(self, content: str) -> float:
        """Extract discount percentage from content"""
        import re

        match = re.search(r"(\d+)%\s*off", content)
        return float(match.group(1)) if match else 0.0

    def _extract_company(self, content: str) -> str:
        """Extract company name from job content"""
        # Simple extraction - you'd want more sophisticated parsing
        lines = content.split("\n")
        for line in lines:
            if "company" in line.lower() or "employer" in line.lower():
                return line.strip()
        return "Unknown"


class TwilioNotificationService:
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.client = Client(account_sid, auth_token)
        self.from_number = from_number

    async def send_sms(self, to_number: str, message: str) -> bool:
        """Send SMS notification"""
        try:
            logger.info(f"Attempting to send SMS to {to_number}")
            message_obj = self.client.messages.create(
                body=message, from_=self.from_number, to=to_number
            )
            logger.info(f"SMS sent successfully to {to_number}: {message_obj.sid}")
            logger.info(f"Message status: {message_obj.status}")
            return True
        except Exception as e:
            logger.error(f"SMS sending failed to {to_number}: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            # Check for specific Twilio errors
            if "authenticate" in str(e).lower():
                logger.error("Authentication failed - check your Twilio credentials")
            elif "not a valid phone number" in str(e).lower():
                logger.error("Invalid phone number format")
            elif "trial account" in str(e).lower():
                logger.error(
                    "Trial account limitation - verify the phone number in Twilio console"
                )
            return False

    async def make_call(self, to_number: str, message: str) -> bool:
        """Make voice call with TwiML"""
        try:
            # Create TwiML for voice message
            twiml_url = self._create_twiml_url(message)

            call = self.client.calls.create(
                twiml=f"<Response><Say>{message}</Say></Response>",
                to=to_number,
                from_=self.from_number,
            )
            logger.info(f"Call initiated to {to_number}: {call.sid}")
            return True
        except Exception as e:
            logger.error(f"Call failed: {e}")
            return False

    def _create_twiml_url(self, message: str) -> str:
        """Create TwiML URL for voice message"""
        # In production, you'd host this on your server
        return f"<Response><Say>{message}</Say></Response>"


class OutboundAlertService:
    def __init__(
        self,
        twilio_account_sid: str,
        twilio_auth_token: str,
        twilio_from_number: str,
        tavily_api_key: str,
        db_path: str = "alerts.db",
    ):

        self.db = DatabaseManager(db_path)
        self.tavily = TavilyClient(tavily_api_key)
        self.twilio = TwilioNotificationService(
            twilio_account_sid, twilio_auth_token, twilio_from_number
        )
        self.is_running = False
        self.poll_interval = 300  # 5 minutes

    async def start_polling(self):
        """Start the async polling process"""
        self.is_running = True
        logger.info("Starting outbound alert polling...")

        while self.is_running:
            try:
                await self._poll_and_send_alerts()
                await asyncio.sleep(self.poll_interval)
                logger.info("Polling completed, waiting for next interval...")
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error

    def stop_polling(self):
        """Stop the polling process"""
        self.is_running = False
        logger.info("Stopping outbound alert polling...")

    async def _poll_and_send_alerts(self):
        """Poll for new alerts and send notifications"""
        user_prefs = self.db.get_user_preferences()

        for pref in user_prefs:
            if not self._is_quiet_hours(pref):
                logger.info(f"Processing alerts for user {pref.user_id}")
                await self._process_user_alerts(pref)

    async def _process_user_alerts(self, pref: UserPreference):
        """Process alerts for a specific user"""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        daily_count = self.db.get_daily_alert_count(pref.user_id, today)

        # Checking daily alert limit
        if daily_count >= pref.max_alerts_per_day:
            logger.info(f"Daily limit reached for user {pref.user_id}")
            return

        # Checking for price drops
        if AlertType.PRICE_DROP in pref.alert_types:
            await self._check_price_drops(pref)

        # Checking for job matches
        if AlertType.JOB_MATCH in pref.alert_types:
            await self._check_job_matches(pref)

    # Handling the price drop alerts
    async def _check_price_drops(self, pref: UserPreference):
        """Check for price drops based on user preferences"""
        if not pref.keywords:
            return

        price_drops = await self.tavily.search_price_drops(
            pref.keywords, pref.price_threshold
        )

        for drop in price_drops:
            if drop["estimated_discount"] >= pref.price_threshold:
                alert = Alert(
                    alert_id=f"price_{pref.user_id}_{datetime.utcnow().timestamp()}",
                    user_id=pref.user_id,
                    alert_type=AlertType.PRICE_DROP,
                    title=f"Price Drop Alert: {drop['title']}",
                    message=f"{drop['estimated_discount']:.0f}% off! {drop['title'][:50]}... {drop['url']}",
                    data=drop,
                )

                await self._send_alert(alert, pref)

    # Handling the Job Match alerts
    async def _check_job_matches(self, pref: UserPreference):
        """Check for job matches based on user preferences"""
        if not pref.keywords:
            return

        jobs = await self.tavily.search_jobs(pref.keywords)

        for job in jobs:
            alert = Alert(
                alert_id=f"job_{pref.user_id}_{datetime.utcnow().timestamp()}",
                user_id=pref.user_id,
                alert_type=AlertType.JOB_MATCH,
                title=f"Job Match: {job['title']}",
                message=f"New job match: {job['title']} at {job['company']} - {job['url']}",
                data=job,
            )

            await self._send_alert(alert, pref)

    # Sending messages while avoiding duplications
    async def _send_alert(self, alert: Alert, pref: UserPreference):
        """Send alert to user based on preferences"""

        if not self.db.save_alert(alert):
            logger.info(f"Duplicate alert skipped for user {pref.user_id}")
            return

        # Checking for daily limits
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if (
            self.db.get_daily_alert_count(pref.user_id, today)
            >= pref.max_alerts_per_day
        ):
            return

        success = False

        # Send notification based on preference
        if pref.notification_method in [
            NotificationMethod.SMS,
            NotificationMethod.BOTH,
        ]:
            success = await self.twilio.send_sms(pref.phone_number, alert.message)

        if pref.notification_method in [
            NotificationMethod.CALL,
            NotificationMethod.BOTH,
        ]:
            success = (
                await self.twilio.make_call(pref.phone_number, alert.message) or success
            )

        if success:
            alert.sent_at = datetime.utcnow()
            self.db.increment_daily_count(pref.user_id, today)
            logger.info(f"Alert sent to {pref.user_id}: {alert.title}")

    def _is_quiet_hours(self, pref: UserPreference) -> bool:
        """Check if current time is within user's quiet hours"""
        if not pref.quiet_hours_start or not pref.quiet_hours_end:
            return False

        now = datetime.utcnow().time()
        start_time = datetime.strptime(pref.quiet_hours_start, "%H:%M").time()
        end_time = datetime.strptime(pref.quiet_hours_end, "%H:%M").time()

        if start_time <= end_time:
            return start_time <= now <= end_time
        else:  # Quiet hours span midnight
            return now >= start_time or now <= end_time

    def add_user_preference(self, pref: UserPreference):
        """Add or update user preference"""
        self.db.save_user_preference(pref)
        logger.info(f"User preference saved for {pref.user_id}")

    def opt_out_user(self, user_id: str):
        """Opt out user from alerts"""
        pass


# Example usage and testing
async def main():

    # Initialize service
    alert_service = OutboundAlertService(
        TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TAVILY_API_KEY
    )

    # Adding sample user preferences
    user_pref = UserPreference(
        user_id="user3123",
        phone_number="+919315563013",
        alert_types=[AlertType.PRICE_DROP, AlertType.JOB_MATCH],
        notification_method=NotificationMethod.CALL,
        price_threshold=20.0,  # 20% minimum discount
        keywords=["python developer", "remote", "langchain", "langgraph", "AI developer"],
        max_alerts_per_day=5,
        quiet_hours_start="8:00",
        quiet_hours_end="20:00",
    )

    alert_service.add_user_preference(user_pref)

    # Immediate test of Twilio connection
    logger.info("Testing Twilio connection...")
    test_message = "Test message from Maya Alert System! Your alerts are now active."
    sms_success = await alert_service.twilio.send_sms(
        user_pref.phone_number, test_message
    )

    if sms_success:
        logger.info("\n------Test SMS sent successfully!--------\n")
    else:
        logger.error(
            "Failed to send test SMS. Please check your Twilio credentials."
        )
        return

    # Testing Tavily API
    logger.info("Testing Tavily API...")
    try:
        test_results = await alert_service.tavily.search_price_drops(["laptop"], 10.0)
        logger.info(
            f"Tavily API test successful. Found {len(test_results)} results."
        )
    except Exception as e:
        logger.error(f"Tavily API test failed: {e}")

    # Option to run immediate scan or continuous polling
    logger.info("\n" + "=" * 50)
    logger.info("Running immediate alert scan...")
    logger.info("=" * 50)

    # Run one immediate scan
    await alert_service._poll_and_send_alerts()

    logger.info("\n" + "=" * 50)
    logger.info("Starting continuous polling (every 5 minutes)...")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 50)

    # Start polling (in production, this would run as a background service)
    try:
        await alert_service.start_polling()
    except KeyboardInterrupt:
        alert_service.stop_polling()
        logger.info("Alert service stopped.")


if __name__ == "__main__":
    asyncio.run(main())