import asyncio
from loguru import logger
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import uuid
import json
from twilio.rest import Client
from twilio.base.exceptions import TwilioException
import os
from dotenv import load_dotenv
from models.models import Event, EventRequest, EventResponse, NotificationType, EventStatus

# Load environment variables
load_dotenv()
from config.config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,
)



class MockGoogleCalendarService:
    """Mock Google Calendar integration"""
    
    def __init__(self):
        self.events_storage = {}
    
    async def create_event(self, event_data: dict) -> str:
        """Mock Google Calendar event creation"""
        try:
            # Simulation for the API response time
            await asyncio.sleep(0.2)
            
            calendar_event_id = f"gcal_{uuid.uuid4().hex[:12]}"

            self.events_storage[calendar_event_id] = {
                "id": calendar_event_id,
                "summary": event_data["title"],
                "description": event_data.get("description", ""),
                "start": event_data["start_time"].isoformat(),
                "end": event_data["end_time"].isoformat(),
                "location": event_data.get("location", ""),
                "created": datetime.now().isoformat()
            }
            
            logger.info(f"Mock Google Calendar event created: {calendar_event_id}")
            return calendar_event_id
            
        except Exception as e:
            logger.error(f"Mock Google Calendar error: {e}")
            raise Exception(f"Failed to create calendar event: {e}")
    
    async def update_event(self, event_id: str, event_data: dict) -> bool:
        """Mock Google Calendar event update"""
        try:
            if event_id not in self.events_storage:
                return False
            
            await asyncio.sleep(0.1)
            self.events_storage[event_id].update({
                "summary": event_data["title"],
                "description": event_data.get("description", ""),
                "start": event_data["start_time"].isoformat(),
                "end": event_data["end_time"].isoformat(),
                "location": event_data.get("location", ""),
                "updated": datetime.now().isoformat()
            })
            
            logger.info(f"Mock Google Calendar event updated: {event_id}")
            return True
            
        except Exception as e:
            logger.error(f"Mock Google Calendar update error: {e}")
            return False
    
    async def delete_event(self, event_id: str) -> bool:
        """Mock Google Calendar event deletion"""
        try:
            if event_id in self.events_storage:
                del self.events_storage[event_id]
                logger.info(f"Mock Google Calendar event deleted: {event_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Mock Google Calendar delete error: {e}")
            return False

class TwilioNotificationService:
    """Twilio SMS/WhatsApp notification service"""
    
    def __init__(self):
        self.account_sid = TWILIO_ACCOUNT_SID
        self.auth_token = TWILIO_AUTH_TOKEN
        self.phone_number = TWILIO_FROM_NUMBER
        print(self.account_sid, self.auth_token, self.phone_number)

        if not all([self.account_sid, self.auth_token, self.phone_number]):
            logger.warning("Twilio credentials not configured - using mock mode")
            self.client = None
        else:
            self.client = Client(self.account_sid, self.auth_token)
    
    async def send_notification(self, phone: str, message: str, notification_type: NotificationType) -> bool:
        """Send SMS or WhatsApp notification"""
        try:
            if not self.client:
                # Mock notification for demo
                logger.info(f"MOCK NOTIFICATION ({notification_type.value.upper()})")
                logger.info(f"To: {phone}")
                logger.info(f"Message: {message}")
                await asyncio.sleep(0.2)  # Simulate network delay
                return True
            
            # Format phone number for WhatsApp
            if notification_type == NotificationType.WHATSAPP:
                from_number = f"whatsapp:{self.phone_number}"
                to_number = f"whatsapp:{phone}"
            else:
                from_number = self.phone_number
                to_number = phone
            
            logger.info(f"Attempting to send {notification_type.value} from {from_number} to {to_number}")
            
            # Send message
            message_obj = self.client.messages.create(
                body=message,
                from_=from_number,
                to=to_number
            )
            
            logger.info(f"Notification sent successfully: {message_obj.sid}")
            logger.info(f"Message status: {message_obj.status}")
            return True
            
        except TwilioException as e:
            logger.error(f"Twilio error: {e}")
            return False
        except Exception as e:
            logger.error(f"Notification error: {e}")
            return False

class MemoryStorage:
    """In-memory storage with mock defaults"""
    
    def __init__(self):
        self.events: Dict[str, Event] = {}
        self.user_preferences = {
            "default_reminder_minutes": 15,
            "default_notification_type": NotificationType.SMS,
            "timezone": "UTC"
        }
        self._load_mock_defaults()
    
    def _load_mock_defaults(self):
        """Load some mock default events for demonstration"""
        mock_events = [
            {
                "title": "Team Meeting",
                "description": "Weekly team sync",
                "start_time": datetime.now() + timedelta(hours=1),
                "end_time": datetime.now() + timedelta(hours=2),
                "attendee_phone": "+919315563013",
                "location": "Conference Room A"
            },
            {
                "title": "Project Deadline",
                "description": "Submit final project deliverables",
                "start_time": datetime.now() + timedelta(days=1),
                "end_time": datetime.now() + timedelta(days=1, hours=1),
                "attendee_phone": "+919315563013",
                "location": "Remote"
            }
        ]
        
        for mock_data in mock_events:
            event_id = str(uuid.uuid4())
            event = Event(
                id=event_id,
                created_at=datetime.now(),
                reminder_minutes=15,
                notification_type=NotificationType.SMS,
                status=EventStatus.SCHEDULED,
                **mock_data
            )
            self.events[event_id] = event
    
    def save_event(self, event: Event) -> None:
        """Save event to memory storage"""
        self.events[event.id] = event
    
    def get_event(self, event_id: str) -> Optional[Event]:
        """Get event by ID"""
        return self.events.get(event_id)
    
    def get_all_events(self) -> List[Event]:
        """Get all events"""
        return list(self.events.values())
    
    def update_event_status(self, event_id: str, status: EventStatus) -> bool:
        """Update event status"""
        if event_id in self.events:
            self.events[event_id].status = status
            return True
        return False
    
    def get_events_for_reminder(self) -> List[Event]:
        """Get events that need reminders sent"""
        now = datetime.now()
        reminder_events = []
        
        for event in self.events.values():
            if event.status != EventStatus.SCHEDULED:
                continue
            
            reminder_time = event.start_time - timedelta(minutes=event.reminder_minutes)
            if now >= reminder_time and now < event.start_time:
                reminder_events.append(event)
        
        return reminder_events

class EventSchedulerService:
    """Main event scheduler service"""
    
    def __init__(self):
        self.calendar_service = MockGoogleCalendarService()
        self.notification_service = TwilioNotificationService()
        self.storage = MemoryStorage()
    
    async def create_event(self, event_request: EventRequest) -> EventResponse:
        """Create a new event with calendar integration and notifications"""
        try:
            # Validate event timing
            if event_request.start_time <= datetime.now():
                return EventResponse(
                    success=False,
                    message="Event start time must be in the future",
                    error="Invalid timing"
                )
            
            if event_request.end_time <= event_request.start_time:
                return EventResponse(
                    success=False,
                    message="Event end time must be after start time",
                    error="Invalid timing"
                )
            
            # Generate event ID
            event_id = str(uuid.uuid4())
            
            # Create Google Calendar event
            try:
                google_calendar_id = await self.calendar_service.create_event({
                    "title": event_request.title,
                    "description": event_request.description,
                    "start_time": event_request.start_time,
                    "end_time": event_request.end_time,
                    "location": event_request.location
                })
            except Exception as e:
                logger.error(f"Calendar integration failed: {e}")
                google_calendar_id = None
            
            # Create event object
            event = Event(
                id=event_id,
                title=event_request.title,
                description=event_request.description,
                start_time=event_request.start_time,
                end_time=event_request.end_time,
                attendee_phone=event_request.attendee_phone,
                notification_type=event_request.notification_type,
                reminder_minutes=event_request.reminder_minutes,
                location=event_request.location,
                status=EventStatus.SCHEDULED,
                created_at=datetime.now(),
                google_calendar_id=google_calendar_id
            )
            
            # Save to storage
            self.storage.save_event(event)
            
            # Send confirmation notification
            confirmation_message = self._format_confirmation_message(event)
            notification_sent = await self.notification_service.send_notification(
                event.attendee_phone,
                confirmation_message,
                event.notification_type
            )
            
            logger.info(f"Event created successfully: {event_id}")
            
            return EventResponse(
                success=True,
                message=f"Event scheduled successfully! {'Confirmation sent.' if notification_sent else 'Note: Confirmation notification failed.'}",
                event=event
            )
            
        except Exception as e:
            logger.error(f"Failed to create event: {e}")
            return EventResponse(
                success=False,
                message="Failed to create event",
                error=str(e)
            )
    
    async def send_reminders(self) -> Dict[str, int]:
        """Send reminders for upcoming events (called by cron)"""
        try:
            events_to_remind = self.storage.get_events_for_reminder()
            
            results = {
                "reminders_sent": 0,
                "reminders_failed": 0,
                "events_processed": len(events_to_remind)
            }
            
            for event in events_to_remind:
                try:
                    reminder_message = self._format_reminder_message(event)
                    
                    success = await self.notification_service.send_notification(
                        event.attendee_phone,
                        reminder_message,
                        event.notification_type
                    )
                    
                    if success:
                        self.storage.update_event_status(event.id, EventStatus.REMINDED)
                        results["reminders_sent"] += 1
                        logger.info(f"Reminder sent for event: {event.id}")
                    else:
                        results["reminders_failed"] += 1
                        logger.error(f"Failed to send reminder for event: {event.id}")
                        
                except Exception as e:
                    logger.error(f"Error processing reminder for event {event.id}: {e}")
                    results["reminders_failed"] += 1
            
            return results
            
        except Exception as e:
            logger.error(f"Error in send_reminders: {e}")
            return {"error": str(e)}
    
    def _format_confirmation_message(self, event: Event) -> str:
        """Format confirmation message"""
        return (
            f"✅ Event Confirmed: {event.title}\n"
            f"📅 {event.start_time.strftime('%B %d, %Y at %I:%M %p')}\n"
            f"⏰ Duration: {event.start_time.strftime('%I:%M %p')} - {event.end_time.strftime('%I:%M %p')}\n"
            f"📍 {event.location or 'Location TBD'}\n"
            f"🔔 Reminder set for {event.reminder_minutes} minutes before"
        )
    
    def _format_reminder_message(self, event: Event) -> str:
        """Format reminder message"""
        time_until = event.start_time - datetime.now()
        minutes_until = int(time_until.total_seconds() / 60)
        
        return (
            f"⏰ REMINDER: {event.title}\n"
            f"📅 Starting in {minutes_until} minutes\n"
            f"🕒 {event.start_time.strftime('%I:%M %p')}\n"
            f"📍 {event.location or 'Location TBD'}\n"
            f"{event.description or ''}"
        )
    
    async def get_events(self) -> List[Event]:
        """Get all events"""
        return self.storage.get_all_events()
    
    async def get_event(self, event_id: str) -> Optional[Event]:
        """Get specific event"""
        return self.storage.get_event(event_id)
