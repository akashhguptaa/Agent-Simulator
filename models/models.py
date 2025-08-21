from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text


class NotificationType(str, Enum):
    SMS = "sms"
    WHATSAPP = "whatsapp"


class MessageType(str, Enum):
    SMS = "sms"
    WHATSAPP = "whatsapp"


class EventStatus(str, Enum):
    SCHEDULED = "scheduled"
    REMINDED = "reminded"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class EventRequest(BaseModel):
    title: str = Field(..., description="Event title")
    description: Optional[str] = Field(None, description="Event description")
    start_time: datetime = Field(..., description="Event start time")
    end_time: datetime = Field(..., description="Event end time")
    attendee_phone: str = Field(..., description="Attendee phone number")
    notification_type: NotificationType = Field(
        NotificationType.SMS, description="Notification method"
    )
    reminder_minutes: int = Field(
        15, description="Minutes before event to send reminder"
    )
    location: Optional[str] = Field(None, description="Event location")


class Event(BaseModel):
    id: str
    title: str
    description: Optional[str]
    start_time: datetime
    end_time: datetime
    attendee_phone: str
    notification_type: NotificationType
    reminder_minutes: int
    location: Optional[str]
    status: EventStatus = EventStatus.SCHEDULED
    created_at: datetime
    google_calendar_id: Optional[str] = None


class EventResponse(BaseModel):
    success: bool
    message: str
    event: Optional[Event] = None
    error: Optional[str] = None


class ReminderRequest(BaseModel):
    user_phone: str = Field(
        ..., description="User's phone number with country code (e.g., +1234567890)"
    )
    message: str = Field(..., description="Reminder message to send")
    scheduled_time: str = Field(
        ..., description="When to send the reminder (e.g., '2025-08-21 10:30 AM IST')"
    )
    timezone: str = Field(
        default="UTC",
        description="User's timezone (e.g., 'Asia/Kolkata', 'America/New_York')",
    )
    message_type: MessageType = Field(
        default=MessageType.SMS, description="Message type: SMS or WhatsApp"
    )
    recurrence: Optional[str] = Field(
        default=None,
        description="Recurrence pattern: 'daily', 'weekly', 'every 2 days', etc.",
    )


class OptOutRequest(BaseModel):
    phone_number: str = Field(..., description="Phone number to opt out")


class ReminderResponse(BaseModel):
    success: bool
    message: str
    reminder_id: Optional[int] = None
