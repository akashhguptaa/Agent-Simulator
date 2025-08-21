from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
from loguru import logger
from app.reminder_service import ReminderService



def setup_webhook_routes(app: FastAPI, reminder_service: ReminderService):
    """Add webhook routes to handle incoming messages"""
    
    @app.post("/webhook/sms", response_class=PlainTextResponse)
    async def handle_sms_webhook(
        From: str = Form(...),
        Body: str = Form(...),
        To: str = Form(...),
        MessageSid: str = Form(...)
    ):
        """Handle incoming SMS messages"""
        try:
            message_body = Body.strip().lower()
            
            # Check for opt-out keywords
            opt_out_keywords = ['stop', 'unsubscribe', 'quit', 'cancel', 'end', 'opt out']
            
            if any(keyword in message_body for keyword in opt_out_keywords):
                reminder_service.opt_out_user(From)
                logger.info(f"User {From} opted out via SMS")
                
                response = "You have been unsubscribed from all reminders. Reply START to resubscribe."
                return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response><Message>{response}</Message></Response>"
            
            # Check for opt-in keywords
            elif message_body in ['start', 'yes', 'subscribe']:
                response = "Welcome back! You can now receive reminders again."
                return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response><Message>{response}</Message></Response>"
            
            else:
                # Default response for unrecognized messages
                response = "Thank you for your message. Reply STOP to unsubscribe from reminders."
                return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response><Message>{response}</Message></Response>"
                
        except Exception as e:
            logger.error(f"Error handling SMS webhook: {str(e)}")
            return "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response></Response>"
    
    @app.post("/webhook/whatsapp", response_class=PlainTextResponse)
    async def handle_whatsapp_webhook(
        From: str = Form(...),
        Body: str = Form(...),
        To: str = Form(...),
        MessageSid: str = Form(...)
    ):
        """Handle incoming WhatsApp messages"""
        try:
            message_body = Body.strip().lower()
            
            # Extract phone number from WhatsApp format (whatsapp:+1234567890)
            phone_number = From.replace("whatsapp:", "")
            
            # Check for opt-out keywords
            opt_out_keywords = ['stop', 'unsubscribe', 'quit', 'cancel', 'end', 'opt out']
            
            if any(keyword in message_body for keyword in opt_out_keywords):
                reminder_service.opt_out_user(phone_number)
                logger.info(f"User {phone_number} opted out via WhatsApp")
                
                response = "You have been unsubscribed from all reminders. Reply START to resubscribe."
                return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response><Message>{response}</Message></Response>"
            
            # Check for opt-in keywords
            elif message_body in ['start', 'yes', 'subscribe']:
                response = "Welcome back! You can now receive reminders again."
                return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response><Message>{response}</Message></Response>"
            
            else:
                # Default response for unrecognized messages
                response = "Thank you for your message. Reply STOP to unsubscribe from reminders."
                return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response><Message>{response}</Message></Response>"
                
        except Exception as e:
            logger.error(f"Error handling WhatsApp webhook: {str(e)}")
            return "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response></Response>"