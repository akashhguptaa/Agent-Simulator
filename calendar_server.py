from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from datetime import datetime, timedelta
from typing import List
import uvicorn
from contextlib import asynccontextmanager

from app.calendar_service import EventSchedulerService
from utils.cron_scheduler import CronScheduler
from models.models import EventRequest, EventResponse, Event, NotificationType

event_service = None
cron_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    global event_service, cron_scheduler

    # Startup
    print("......Starting Event Scheduler Service...")
    event_service = EventSchedulerService()
    cron_scheduler = CronScheduler(event_service)
    cron_scheduler.start()
    print("Event Scheduler Service started!")
    print("Mock notifications will be displayed in console")
    print("Cron scheduler checking for reminders every minute")

    yield

    # Shutdown
    print("Shutting down Event Scheduler Service...")
    if cron_scheduler:
        cron_scheduler.stop()
    print("Event Scheduler Service stopped!")


# Initialize FastAPI app
app = FastAPI(
    title="Event Scheduler API",
    description="Automated Event Scheduler with Notification Cron",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "running",
        "service": "Event Scheduler API",
        "message": "Event scheduler is running with cron notifications",
    }


@app.post("/events", response_model=EventResponse)
async def create_event(event_request: EventRequest):
    """Create a new event"""
    try:
        response = await event_service.create_event(event_request)
        if not response.success:
            raise HTTPException(status_code=400, detail=response.message)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events", response_model=List[Event])
async def get_all_events():
    """Get all events"""
    try:
        events = await event_service.get_events()
        return events
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events/{event_id}", response_model=Event)
async def get_event(event_id: str):
    """Get specific event by ID"""
    try:
        event = await event_service.get_event(event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        return event
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/test/send-reminders")
async def test_send_reminders():
    """Manual trigger for sending reminders (for testing)"""
    try:
        results = await event_service.send_reminders()
        return {"status": "completed", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events/status/{status}")
async def get_events_by_status(status: str):
    """Get events by status"""
    try:
        all_events = await event_service.get_events()
        filtered_events = [
            event for event in all_events if event.status.value == status
        ]
        return filtered_events
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    print("Event Scheduler API")
    print("=" * 50)
    print("Features:")
    print("• Event creation with Google Calendar mock integration")
    print("• SMS/WhatsApp notifications via Twilio (mock mode)")
    print("• Automated reminder cron jobs every minute")
    print("• In-memory storage with pre-loaded demo events")
    print("=" * 50)
    print()

    uvicorn.run(
        "calendar_server:app", host="0.0.0.0", port=8000, reload=True, log_level="info"
    )
