from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text
from database import Base

class NotificationType(str, Enum):
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
    notification_type: NotificationType = Field(NotificationType.SMS, description="Notification method")
    reminder_minutes: int = Field(15, description="Minutes before event to send reminder")
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

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class DealWatch(Base):
    __tablename__ = "deal_watches"
    
    id = Column(String, primary_key=True)
    email = Column(String, index=True)
    origin = Column(String)
    destination = Column(String)
    departure_date = Column(String)
    return_date = Column(String, nullable=True)
    max_price = Column(Float, nullable=True)
    price_drop_threshold = Column(Float)
    watch_end_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    alerts_sent = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)