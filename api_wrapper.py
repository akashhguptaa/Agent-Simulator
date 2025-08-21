

# api_wrapper.py - FastAPI wrapper for the reminder service
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import asyncio
from app.reminder_service import ReminderService, MessageType
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Smart Reminder Service API", version="1.0.0")

# Pydantic models for API requests
class ReminderRequest(BaseModel):
    user_phone: str = Field(..., description="User's phone number with country code (e.g., +1234567890)")
    message: str = Field(..., description="Reminder message to send")
    scheduled_time: str = Field(..., description="When to send the reminder (e.g., '2025-08-21 10:30 AM IST')")
    timezone: str = Field(default="UTC", description="User's timezone (e.g., 'Asia/Kolkata', 'America/New_York')")
    message_type: str = Field(default="sms", description="Message type: 'sms' or 'whatsapp'")
    recurrence: Optional[str] = Field(default=None, description="Recurrence pattern: 'daily', 'weekly', 'every 2 days', etc.")

class OptOutRequest(BaseModel):
    phone_number: str = Field(..., description="Phone number to opt out")

class ReminderResponse(BaseModel):
    success: bool
    message: str
    reminder_id: Optional[int] = None

# Initialize the service (you should set these environment variables)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "your_account_sid")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "your_auth_token")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "+1234567890")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "+1234567890")

# Global service instance
reminder_service = None

@app.on_event("startup")
async def startup_event():
    """Initialize the reminder service when the API starts"""
    global reminder_service
    try:
        reminder_service = ReminderService(
            TWILIO_ACCOUNT_SID,
            TWILIO_AUTH_TOKEN,
            TWILIO_FROM_NUMBER,
            TWILIO_WHATSAPP_NUMBER
        )
        reminder_service.start_service()
        logger.info("Reminder service started successfully")
    except Exception as e:
        logger.error(f"Failed to start reminder service: {str(e)}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown of the reminder service"""
    global reminder_service
    if reminder_service:
        reminder_service.stop_service()
        logger.info("Reminder service stopped")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Smart Reminder Service API is running", "status": "healthy"}

@app.post("/reminders", response_model=ReminderResponse)
async def create_reminder(reminder_request: ReminderRequest):
    """Create a new reminder"""
    try:
        global reminder_service
        
        if not reminder_service:
            raise HTTPException(status_code=500, detail="Reminder service not initialized")
        
        # Validate message type
        if reminder_request.message_type.lower() not in ["sms", "whatsapp"]:
            raise HTTPException(status_code=400, detail="Invalid message_type. Use 'sms' or 'whatsapp'")
        
        message_type = MessageType.SMS if reminder_request.message_type.lower() == "sms" else MessageType.WHATSAPP
        
        # Create the reminder
        reminder_id = await reminder_service.create_reminder(
            user_phone=reminder_request.user_phone,
            message=reminder_request.message,
            scheduled_time_str=reminder_request.scheduled_time,
            timezone_str=reminder_request.timezone,
            message_type=message_type,
            recurrence_str=reminder_request.recurrence
        )
        
        return ReminderResponse(
            success=True,
            message="Reminder created successfully",
            reminder_id=reminder_id
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating reminder: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create reminder")

@app.post("/opt-out", response_model=ReminderResponse)
async def opt_out_user(opt_out_request: OptOutRequest):
    """Opt out a user from all reminders"""
    try:
        global reminder_service
        
        if not reminder_service:
            raise HTTPException(status_code=500, detail="Reminder service not initialized")
        
        reminder_service.opt_out_user(opt_out_request.phone_number)
        
        return ReminderResponse(
            success=True,
            message="User opted out successfully"
        )
        
    except Exception as e:
        logger.error(f"Error opting out user: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to opt out user")

@app.get("/health")
async def health_check():
    """Detailed health check"""
    try:
        global reminder_service
        
        status = {
            "service_status": "running" if reminder_service and reminder_service.scheduler.is_running else "stopped",
            "database_status": "connected",  # We could add a DB health check here
            "twilio_status": "configured",    # We could add a Twilio API check here
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return status
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Health check failed")

# Usage examples and documentation
@app.get("/examples")
async def get_examples():
    """Get API usage examples"""
    return {
        "create_sms_reminder": {
            "method": "POST",
            "url": "/reminders",
            "body": {
                "user_phone": "+1234567890",
                "message": "Take your medicine!",
                "scheduled_time": "2025-08-21 10:30",
                "timezone": "Asia/Kolkata",
                "message_type": "sms"
            }
        },
        "create_whatsapp_reminder": {
            "method": "POST",
            "url": "/reminders",
            "body": {
                "user_phone": "+1234567890",
                "message": "Daily standup meeting in 15 minutes",
                "scheduled_time": "2025-08-21 09:45",
                "timezone": "Asia/Kolkata",
                "message_type": "whatsapp",
                "recurrence": "daily"
            }
        },
        "create_recurring_reminder": {
            "method": "POST",
            "url": "/reminders",
            "body": {
                "user_phone": "+1234567890",
                "message": "Weekly team meeting today at 2 PM",
                "scheduled_time": "2025-08-25 13:45",
                "timezone": "Asia/Kolkata",
                "message_type": "sms",
                "recurrence": "every week"
            }
        },
        "opt_out_user": {
            "method": "POST",
            "url": "/opt-out",
            "body": {
                "phone_number": "+1234567890"
            }
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
