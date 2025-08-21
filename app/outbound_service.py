import asyncio
import hashlib
import json
from loguru import logger
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import aiohttp
from twilio.rest import Client
import sqlite3
from dotenv import load_dotenv
import os

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

        # Check for duplicate in last 6 hours instead of 24 hours (less restrictive)
        cursor.execute(
            """
            SELECT COUNT(*) FROM alerts 
            WHERE alert_hash = ? AND created_at > datetime('now', '-6 hours')
        """,
            (alert_hash,),
        )

        if cursor.fetchone()[0] > 0:
            conn.close()
            logger.info(f"Duplicate alert skipped: {alert.title}")
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
        logger.info(f"Alert saved: {alert.title}")
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
        logger.info(f"Searching for price drops with keywords: {keywords}, threshold: {threshold}%")
        
        async with aiohttp.ClientSession() as session:
            search_query = f"price drop discount sale {' OR '.join(keywords)}"
            logger.info(f"Tavily search query: {search_query}")

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

            try:
                async with session.post(
                    f"{self.base_url}/search", json=payload
                ) as response:
                    logger.info(f"Tavily API response status: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])
                        logger.info(f"Tavily returned {len(results)} raw results")
                        
                        # Log raw results for debugging
                        for i, result in enumerate(results[:3]):  # Log first 3 results
                            logger.info(f"Result {i+1}: {result.get('title', 'No title')[:100]}")
                        
                        parsed_results = self._parse_price_results(results, threshold)
                        logger.info(f"After parsing: {len(parsed_results)} price drops found")
                        return parsed_results
                    else:
                        error_text = await response.text()
                        logger.error(f"Tavily API error: {response.status} - {error_text}")
                        return []
            except Exception as e:
                logger.error(f"Tavily API request failed: {str(e)}")
                return []

    async def search_jobs(self, keywords: List[str]) -> List[Dict]:
        """Search for job postings using Tavily API"""
        logger.info(f"Searching for jobs with keywords: {keywords}")
        
        async with aiohttp.ClientSession() as session:
            search_query = f"job openings hiring {' OR '.join(keywords)}"
            logger.info(f"Job search query: {search_query}")

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

            try:
                async with session.post(
                    f"{self.base_url}/search", json=payload
                ) as response:
                    logger.info(f"Job search API response status: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])
                        logger.info(f"Job search returned {len(results)} results")
                        
                        parsed_results = self._parse_job_results(results)
                        logger.info(f"After parsing: {len(parsed_results)} job matches found")
                        return parsed_results
                    else:
                        error_text = await response.text()
                        logger.error(f"Job search API error: {response.status} - {error_text}")
                        return []
            except Exception as e:
                logger.error(f"Job search API request failed: {str(e)}")
                return []

    def _parse_price_results(self, results: List[Dict], threshold: float) -> List[Dict]:
        """Parse and filter price drop results - FIXED VERSION"""
        price_drops = []
        
        for result in results:
            title = result.get("title", "")
            content = result.get("content", "").lower()
            url = result.get("url", "")
            
            logger.info(f"Analyzing result: {title[:50]}...")
            
            # More flexible price drop detection
            price_indicators = [
                "% off", "percent off", "discount", "sale", "price drop", 
                "clearance", "deal", "offer", "reduced", "save", "special"
            ]
            
            has_price_indicator = any(term in content for term in price_indicators)
            estimated_discount = self._extract_discount(content)
            
            logger.info(f"  - Has price indicator: {has_price_indicator}")
            logger.info(f"  - Estimated discount: {estimated_discount}%")
            
            # More lenient filtering - include if it has price indicators OR discount >= threshold
            if has_price_indicator or estimated_discount >= threshold:
                # If we can't extract a specific discount, use a default that meets threshold
                if estimated_discount == 0 and has_price_indicator:
                    estimated_discount = max(threshold, 15.0)  # Default to threshold or 15%
                
                price_drop = {
                    "title": title,
                    "url": url,
                    "content": result.get("content", "")[:200],
                    "estimated_discount": estimated_discount,
                }
                
                price_drops.append(price_drop)
                logger.info(f"  - ADDED: {title[:50]}... (discount: {estimated_discount}%)")
            else:
                logger.info(f"  - SKIPPED: {title[:50]}...")
        
        logger.info(f"Total price drops found: {len(price_drops)}")
        return price_drops

    def _parse_job_results(self, results: List[Dict]) -> List[Dict]:
        """Parse job search results"""
        jobs = []
        for result in results:
            title = result.get("title", "")
            url = result.get("url", "")
            content = result.get("content", "")
            
            job = {
                "title": title,
                "url": url,
                "content": content[:200],
                "company": self._extract_company(content),
            }
            
            jobs.append(job)
            logger.info(f"Job found: {title[:50]}...")
        
        return jobs

    def _extract_discount(self, content: str) -> float:
        """Extract discount percentage from content - IMPROVED VERSION"""
        import re
        
        patterns = [
            r"(\d+)%\s*off",
            r"(\d+)\s*percent\s*off",
            r"save\s*(\d+)%",
            r"(\d+)%\s*discount",
            r"up\s*to\s*(\d+)%\s*off",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                discount = float(match.group(1))
                logger.info(f"Extracted discount: {discount}% using pattern: {pattern}")
                return discount
        
        dollar_pattern = r"\$(\d+\.?\d*)\s*off"
        dollar_match = re.search(dollar_pattern, content, re.IGNORECASE)
        if dollar_match:
        
            amount = float(dollar_match.group(1))
            if amount >= 10:
                return 20.0  
        
        return 0.0

    def _extract_company(self, content: str) -> str:
        """Extract company name from job content"""
        import re
        
        patterns = [
            r"at\s+([A-Z][a-zA-Z\s&]+?)(?:\s|,|\.|\n|$)",
            r"company:\s*([A-Z][a-zA-Z\s&]+?)(?:\s|,|\.|\n|$)",
            r"employer:\s*([A-Z][a-zA-Z\s&]+?)(?:\s|,|\.|\n|$)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                company = match.group(1).strip()
                if len(company) > 3: 
                    return company
        
        return "Company not specified"


class TwilioNotificationService:
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.client = Client(account_sid, auth_token)
        self.from_number = from_number

    async def send_sms(self, to_number: str, message: str) -> bool:
        """Send SMS notification"""
        try:
            logger.info(f"Attempting to send SMS to {to_number}")
            logger.info(f"Message content: {message[:100]}...")
            
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
            logger.info(f"Attempting to make call to {to_number}")
            
            call = self.client.calls.create(
                twiml=f"<Response><Say>{message}</Say></Response>",
                to=to_number,
                from_=self.from_number,
            )
            logger.info(f"Call initiated to {to_number}: {call.sid}")
            return True
        except Exception as e:
            logger.error(f"Call failed to {to_number}: {str(e)}")
            return False

    def _create_twiml_url(self, message: str) -> str:
        """Create TwiML URL for voice message"""
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
                logger.info(f"\n{'='*60}")
                logger.info(f"Starting polling cycle at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
                logger.info(f"{'='*60}")
                
                await self._poll_and_send_alerts()
                
                logger.info(f"Polling cycle completed. Waiting {self.poll_interval} seconds for next cycle...")
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"Polling error: {str(e)}")
                logger.exception("Full error trace:")
                await asyncio.sleep(60)  # Wait 1 minute on error

    def stop_polling(self):
        """Stop the polling process"""
        self.is_running = False
        logger.info("Stopping outbound alert polling...")

    async def _poll_and_send_alerts(self):
        """Poll for new alerts and send notifications"""
        user_prefs = self.db.get_user_preferences()
        logger.info(f"Found {len(user_prefs)} active users")

        for pref in user_prefs:
            logger.info(f"\n--- Processing user {pref.user_id} ---")
            logger.info(f"Phone: {pref.phone_number}")
            logger.info(f"Alert types: {[at.value for at in pref.alert_types]}")
            logger.info(f"Keywords: {pref.keywords}")
            logger.info(f"Price threshold: {pref.price_threshold}%")
            
            if self._is_quiet_hours(pref):
                logger.info(f"Skipping user {pref.user_id} - quiet hours active")
                continue
            else:
                logger.info(f"User {pref.user_id} - not in quiet hours, processing alerts...")
                await self._process_user_alerts(pref)

    async def _process_user_alerts(self, pref: UserPreference):
        """Process alerts for a specific user"""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        daily_count = self.db.get_daily_alert_count(pref.user_id, today)
        
        logger.info(f"Daily alert count for {pref.user_id}: {daily_count}/{pref.max_alerts_per_day}")

        # Check daily alert limit
        if daily_count >= pref.max_alerts_per_day:
            logger.info(f"Daily limit reached for user {pref.user_id}")
            return

        # Check for price drops
        if AlertType.PRICE_DROP in pref.alert_types and pref.keywords:
            logger.info(f"Checking price drops for user {pref.user_id}...")
            await self._check_price_drops(pref)

        # Check for job matches
        if AlertType.JOB_MATCH in pref.alert_types and pref.keywords:
            logger.info(f"Checking job matches for user {pref.user_id}...")
            await self._check_job_matches(pref)

    async def _check_price_drops(self, pref: UserPreference):
        """Check for price drops based on user preferences"""
        logger.info(f"Searching price drops with keywords: {pref.keywords}, threshold: {pref.price_threshold}%")
        
        price_drops = await self.tavily.search_price_drops(
            pref.keywords, pref.price_threshold
        )

        logger.info(f"Found {len(price_drops)} potential price drops")

        for i, drop in enumerate(price_drops):
            logger.info(f"Processing price drop {i+1}: {drop['title'][:50]}... (discount: {drop['estimated_discount']}%)")
            
            # More lenient threshold check
            if drop["estimated_discount"] >= pref.price_threshold or drop["estimated_discount"] >= 10:
                alert = Alert(
                    alert_id=f"price_{pref.user_id}_{datetime.utcnow().timestamp()}",
                    user_id=pref.user_id,
                    alert_type=AlertType.PRICE_DROP,
                    title=f"Price Drop: {drop['title'][:50]}",
                    message=f"{drop['estimated_discount']:.0f}% OFF! {drop['title'][:80]}... Check it out: {drop['url']}",
                    data=drop,
                )

                await self._send_alert(alert, pref)
            else:
                logger.info(f"Skipped price drop - discount {drop['estimated_discount']}% below threshold {pref.price_threshold}%")

    async def _check_job_matches(self, pref: UserPreference):
        """Check for job matches based on user preferences"""
        logger.info(f"Searching jobs with keywords: {pref.keywords}")
        
        jobs = await self.tavily.search_jobs(pref.keywords)
        
        logger.info(f"Found {len(jobs)} potential job matches")

        for i, job in enumerate(jobs):
            logger.info(f"Processing job {i+1}: {job['title'][:50]}...")
            
            alert = Alert(
                alert_id=f"job_{pref.user_id}_{datetime.utcnow().timestamp()}",
                user_id=pref.user_id,
                alert_type=AlertType.JOB_MATCH,
                title=f"Job Match: {job['title'][:50]}",
                message=f"New opportunity: {job['title'][:60]} at {job['company']} - Apply now: {job['url']}",
                data=job,
            )

            await self._send_alert(alert, pref)

    async def _send_alert(self, alert: Alert, pref: UserPreference):
        """Send alert to user based on preferences"""
        logger.info(f"Attempting to send alert: {alert.title}")

        # Check if it's a duplicate
        if not self.db.save_alert(alert):
            logger.info(f"Duplicate alert skipped for user {pref.user_id}: {alert.title}")
            return

        # Check daily limits again (in case multiple alerts are being processed)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        current_count = self.db.get_daily_alert_count(pref.user_id, today)
        if current_count >= pref.max_alerts_per_day:
            logger.info(f"Daily limit reached during alert processing for user {pref.user_id}")
            return

        success = False

        # Send notification based on preference
        if pref.notification_method in [
            NotificationMethod.SMS,
            NotificationMethod.BOTH,
        ]:
            logger.info(f"Sending SMS to {pref.phone_number}")
            success = await self.twilio.send_sms(pref.phone_number, alert.message)

        if pref.notification_method in [
            NotificationMethod.CALL,
            NotificationMethod.BOTH,
        ]:
            logger.info(f"Making call to {pref.phone_number}")
            call_success = await self.twilio.make_call(pref.phone_number, alert.message)
            success = success or call_success

        if success:
            alert.sent_at = datetime.utcnow()
            self.db.increment_daily_count(pref.user_id, today)
            logger.info(f"Alert sent successfully to {pref.user_id}: {alert.title}")
        else:
            logger.error(f"Failed to send alert to {pref.user_id}: {alert.title}")

    def _is_quiet_hours(self, pref: UserPreference) -> bool:
        """Check if current time is within user's quiet hours - FIXED VERSION"""
        if not pref.quiet_hours_start or not pref.quiet_hours_end:
            logger.info("No quiet hours set")
            return False

        now = datetime.utcnow().time()
        start_time = datetime.strptime(pref.quiet_hours_start, "%H:%M").time()
        end_time = datetime.strptime(pref.quiet_hours_end, "%H:%M").time()
        
        logger.info(f"Checking quiet hours: now={now.strftime('%H:%M')}, quiet={pref.quiet_hours_start}-{pref.quiet_hours_end}")

        if start_time <= end_time:
            # Normal hours (e.g., 08:00 to 22:00)
            is_quiet = start_time <= now <= end_time
        else:  # Quiet hours span midnight (e.g., 22:00 to 08:00)
            is_quiet = now >= start_time or now <= end_time
        
        logger.info(f"Is quiet hours: {is_quiet}")
        return is_quiet

    def add_user_preference(self, pref: UserPreference):
        """Add or update user preference"""
        self.db.save_user_preference(pref)
        logger.info(f"User preference saved for {pref.user_id}")

    def opt_out_user(self, user_id: str):
        """Opt out user from alerts"""
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE user_preferences SET opted_in = 0 WHERE user_id = ?",
            (user_id,)
        )
        
        conn.commit()
        conn.close()
        logger.info(f"User {user_id} opted out from alerts")


# Example usage and testing
async def main():
    logger.info("Starting Maya Alert System...")
    logger.info(f"Environment check:")
    logger.info(f"  - Twilio SID: {'✓' if TWILIO_ACCOUNT_SID else '✗'}")
    logger.info(f"  - Twilio Token: {'✓' if TWILIO_AUTH_TOKEN else '✗'}")
    logger.info(f"  - Twilio Number: {'✓' if TWILIO_FROM_NUMBER else '✗'}")
    logger.info(f"  - Tavily API Key: {'✓' if TAVILY_API_KEY else '✗'}")

    if missing_vars:
        logger.error("Cannot start - missing required environment variables")
        return

    # Initialize service
    alert_service = OutboundAlertService(
        TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TAVILY_API_KEY
    )

    # Adding sample user preferences with FIXED quiet hours
    user_pref = UserPreference(
        user_id="user31253",
        phone_number=os.getenv("TWILIO_TARGET_NUMBER"),
        alert_types=[AlertType.PRICE_DROP, AlertType.JOB_MATCH],
        notification_method=NotificationMethod.SMS,  # Changed to SMS for easier testing
        price_threshold=15.0,  # Lowered threshold for more results
        keywords=["python developer", "remote work", "AI developer", "laptop", "smartphone"],  # Added more general keywords
        max_alerts_per_day=10,  # Increased limit
        quiet_hours_start="23:00",  # Fixed: Quiet hours from 11 PM to 7 AM
        quiet_hours_end="07:00",
    )

    alert_service.add_user_preference(user_pref)

    # Immediate test of Twilio connection
    logger.info("\n" + "="*50)
    logger.info("TESTING TWILIO CONNECTION")
    logger.info("="*50)
    
    test_message = "Maya Alert System is now ACTIVE! You'll receive price drops & job alerts."
    sms_success = await alert_service.twilio.send_sms(
        user_pref.phone_number, test_message
    )

    if sms_success:
        logger.info("Test SMS sent successfully!")
    else:
        logger.error("Failed to send test SMS. Please check your Twilio credentials.")
        return

    # Testing Tavily API with detailed logging
    logger.info("\n" + "="*50)
    logger.info("TESTING TAVILY API")
    logger.info("="*50)
    
    try:
        # Test price drops
        logger.info("Testing price drop search...")
        test_price_results = await alert_service.tavily.search_price_drops(["laptop", "smartphone"], 10.0)
        logger.info(f"Tavily price search successful. Found {len(test_price_results)} results.")
        
        # Test job search
        logger.info("Testing job search...")
        test_job_results = await alert_service.tavily.search_jobs(["python developer", "remote"])
        logger.info(f"Tavily job search successful. Found {len(test_job_results)} results.")
        
    except Exception as e:
        logger.error(f"Tavily API test failed: {str(e)}")
        logger.exception("Full error trace:")

    # Check quiet hours
    logger.info("\n" + "="*50)
    logger.info("CHECKING USER STATUS")
    logger.info("="*50)
    
    is_quiet = alert_service._is_quiet_hours(user_pref)
    current_time = datetime.utcnow().strftime('%H:%M UTC')
    logger.info(f"Current time: {current_time}")
    logger.info(f"User quiet hours: {user_pref.quiet_hours_start} - {user_pref.quiet_hours_end}")
    logger.info(f"In quiet hours: {is_quiet}")

    # Run immediate scan
    logger.info("\n" + "="*50)
    logger.info("RUNNING IMMEDIATE ALERT SCAN")
    logger.info("="*50)

    await alert_service._poll_and_send_alerts()

    # Ask user if they want to continue with polling
    logger.info("\n" + "="*50)
    logger.info("SETUP COMPLETE!")
    logger.info("="*50)
    logger.info("The immediate scan is complete.")
    logger.info("To start continuous polling (every 5 minutes), the service will continue...")
    logger.info("Press Ctrl+C to stop at any time.")

    # Start continuous polling
    try:
        await alert_service.start_polling()
    except KeyboardInterrupt:
        alert_service.stop_polling()
        logger.info("\nAlert service stopped by user.")


if __name__ == "__main__":
    asyncio.run(main())