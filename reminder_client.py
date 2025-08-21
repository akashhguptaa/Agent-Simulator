import requests
import json
from datetime import datetime, timedelta

class ReminderClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def create_reminder(self, phone, message, scheduled_time, timezone="Asia/Kolkata", 
                       message_type="sms", recurrence=None):
        """Create a new reminder"""
        data = {
            "user_phone": phone,
            "message": message,
            "scheduled_time": scheduled_time,
            "timezone": timezone,
            "message_type": message_type
        }
        
        if recurrence:
            data["recurrence"] = recurrence
        
        try:
            response = self.session.post(f"{self.base_url}/reminders", json=data)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
    
    def opt_out_user(self, phone):
        """Opt out a user from all reminders"""
        data = {"phone_number": phone}
        
        try:
            response = self.session.post(f"{self.base_url}/opt-out", json=data)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
    
    def health_check(self):
        """Check service health"""
        try:
            response = self.session.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": str(e)}
    
    def get_examples(self):
        """Get API usage examples"""
        try:
            response = self.session.get(f"{self.base_url}/examples")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": str(e)}


def main():
    client = ReminderClient("http://localhost:8000")

    while True:
        print("\n=== Reminder Service Client ===")
        print("1. Create a reminder")
        print("2. Opt-out a user")
        print("3. Health check")
        print("4. Get examples")
        print("5. Exit")
        
        choice = input("Select an option: ").strip()
        
        if choice == "1":
            phone = input("Enter phone number (with country code): ").strip()
            message = input("Enter reminder message: ").strip()
            
            # Instead of full datetime, just seconds offset
            seconds_from_now = input("Enter delay in seconds (e.g., 1 or 2): ").strip()
            try:
                seconds_from_now = int(seconds_from_now)
            except ValueError:
                print("Invalid number, defaulting to 1 second.")
                seconds_from_now = 1
            
            scheduled_time = (datetime.now() + timedelta(seconds=seconds_from_now)).strftime("%Y-%m-%d %H:%M:%S")
            
            timezone = input("Enter timezone (default: Asia/Kolkata): ").strip() or "Asia/Kolkata"
            msg_type = input("Enter type (sms/whatsapp, default: sms): ").strip() or "sms"
            recurrence = input("Enter recurrence (daily/weekly or leave blank): ").strip() or None
            
            result = client.create_reminder(
                phone=phone,
                message=message,
                scheduled_time=scheduled_time,
                timezone=timezone,
                message_type=msg_type,
                recurrence=recurrence
            )
            print(json.dumps(result, indent=2))
        
        elif choice == "2":
            phone = input("Enter phone number to opt-out: ").strip()
            result = client.opt_out_user(phone)
            print(json.dumps(result, indent=2))
        
        elif choice == "3":
            result = client.health_check()
            print(json.dumps(result, indent=2))
        
        elif choice == "4":
            result = client.get_examples()
            print(json.dumps(result, indent=2))
        
        elif choice == "5":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()