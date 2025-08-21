import requests
import json
from datetime import datetime, timedelta
from typing import Dict, Any

class EventSchedulerTestClient:
    """Test client for Event Scheduler API"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def test_connection(self) -> Dict[str, Any]:
        """Test if the API is running"""
        try:
            response = self.session.get(f"{self.base_url}/")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f" Connection failed: {e}")
            return {"error": str(e)}
    
    def create_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new event"""
        try:
            response = self.session.post(
                f"{self.base_url}/events",
                json=event_data,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f" Failed to create event: {e}")
            if hasattr(e, 'response'):
                print(f"Response: {e.response.text}")
            return {"error": str(e)}
    
    def get_all_events(self) -> Dict[str, Any]:
        """Get all events"""
        try:
            response = self.session.get(f"{self.base_url}/events")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f" Failed to get events: {e}")
            return {"error": str(e)}
    
    def get_event(self, event_id: str) -> Dict[str, Any]:
        """Get specific event"""
        try:
            response = self.session.get(f"{self.base_url}/events/{event_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f" Failed to get event: {e}")
            return {"error": str(e)}
    
    def trigger_reminders(self) -> Dict[str, Any]:
        """Manually trigger reminder check"""
        try:
            response = self.session.post(f"{self.base_url}/test/send-reminders")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f" Failed to trigger reminders: {e}")
            return {"error": str(e)}

def run_tests():
    """Run comprehensive tests"""
    print(" Event Scheduler API Test Suite")
    print("=" * 50)
    
    client = EventSchedulerTestClient()
    
    # Test 1: Connection
    print("\n Testing API connection...")
    connection_result = client.test_connection()
    if "error" not in connection_result:
        print(" API is running!")
        print(f"   Status: {connection_result.get('status')}")
    else:
        print(" API connection failed!")
        return
    
    # Test 2: Get existing events (mock defaults)
    print("\n Getting existing events (mock defaults)...")
    existing_events = client.get_all_events()
    if "error" not in existing_events:
        print(f" Found {len(existing_events)} existing events:")
        for event in existing_events:
            print(f"   • {event['title']} - {event['start_time'][:16]}")
    else:
        print("Failed to get existing events")
    
    # Test 3: Create new event
    print("\n Creating a new event...")
    
    # Event starting in 2 minutes (for quick reminder testing)
    import os
    from dotenv import load_dotenv
    load_dotenv()
    new_event = {
        "title": "Test Meeting - Client Demo",
        "description": "Testing the event scheduler system with a quick demo",
        "start_time": (datetime.now() + timedelta(minutes=2)).isoformat(),
        "end_time": (datetime.now() + timedelta(minutes=3)).isoformat(),
        "attendee_phone": os.getenv("TWILIO_TARGET_NUMBER"),
        "notification_type": "sms",
        "reminder_minutes": 1,  # 1 minute reminder for quick testing
        "location": "Test Conference Room"
    }
    
    create_result = client.create_event(new_event)
    if "error" not in create_result and create_result.get("success"):
        print(" New event created successfully!")
        print(f"   Event ID: {create_result['event']['id']}")
        print(f"   Title: {create_result['event']['title']}")
        print(f"   Start: {create_result['event']['start_time'][:16]}")
        new_event_id = create_result['event']['id']
    else:
        print("Failed to create new event")
        print(f"   Error: {create_result}")
        new_event_id = None
    
    # Test 4: Create another event for later today
    print("\nCreating another event for later...")
    
    later_event = {
        "title": "Daily Standup",
        "description": "Team daily standup meeting",
        "start_time": (datetime.now() + timedelta(hours=4)).isoformat(),
        "end_time": (datetime.now() + timedelta(hours=4, minutes=30)).isoformat(),
        "attendee_phone": "+919315563013",
        "notification_type": "whatsapp",
        "reminder_minutes": 15,
        "location": "Zoom Call"
    }
    
    create_result2 = client.create_event(later_event)
    if "error" not in create_result2 and create_result2.get("success"):
        print("Second event created successfully!")
        print(f"   Event ID: {create_result2['event']['id']}")
        print(f"   Title: {create_result2['event']['title']}")
    else:
        print("Failed to create second event")
    
    # Test 5: Get updated events list
    print("\n5 Getting updated events list...")
    updated_events = client.get_all_events()
    if "error" not in updated_events:
        print(f"Total events now: {len(updated_events)}")
        print("\nAll Events:")
        for i, event in enumerate(updated_events, 1):
            start_time = datetime.fromisoformat(event['start_time'].replace('Z', '+00:00'))
            print(f"   {i}. {event['title']}")
            print(f"       {start_time.strftime('%Y-%m-%d %H:%M')}")
            print(f"      {event['attendee_phone']} ({event['notification_type']})")
            print(f"       {event['reminder_minutes']} min reminder")
            print(f"       Status: {event['status']}")
    
    # Test 6: Get specific event
    if new_event_id:
        print(f"\nGetting specific event ({new_event_id[:8]}...)...")
        specific_event = client.get_event(new_event_id)
        if "error" not in specific_event:
            print("Successfully retrieved specific event!")
            print(f"   Google Calendar ID: {specific_event.get('google_calendar_id', 'N/A')}")
        else:
            print(" Failed to get specific event")
    
    # Test 7: Manual reminder trigger (for testing)
    print("\n7️ Testing manual reminder trigger...")
    reminder_result = client.trigger_reminders()
    if "error" not in reminder_result:
        print("Reminder check triggered!")
        results = reminder_result.get("results", {})
        print(f"   Events processed: {results.get('events_processed', 0)}")
        print(f"   Reminders sent: {results.get('reminders_sent', 0)}")
        print(f"   Reminders failed: {results.get('reminders_failed', 0)}")
    else:
        print("Failed to trigger reminders")
    
    print("\n" + "=" * 50)
    print(" Test suite completed!")
    print("\nWhat to expect:")
    print("   • Check your console for mock notification messages")
    print("   • The cron job runs every minute to check for reminders") 
    print("   • Events with 1-minute reminders should trigger soon")
    print("   • Keep the server running to see automatic reminders")
    print("\nTo see live reminders, wait 1-2 minutes and check server logs")

if __name__ == "__main__":
    run_tests()
 