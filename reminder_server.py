import asyncio
import logging
import signal
import sys
from utils.reminder_config import load_config
from api_wrapper import app
from utils.webhook_handler import setup_webhook_routes
from app.reminder_service import ReminderService
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_signal_handlers(reminder_service):
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        if reminder_service:
            reminder_service.stop_service()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def main():
    """Main entry point"""
    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = load_config()
        
        # Set logging level
        logging.getLogger().setLevel(getattr(logging, config.service.log_level.upper()))
        
        # Initialize reminder service
        logger.info("Initializing reminder service...")
        reminder_service = ReminderService(
            config.twilio.account_sid,
            config.twilio.auth_token,
            config.twilio.from_number,
            config.twilio.whatsapp_number
        )
        
        # Setup webhook routes
        setup_webhook_routes(app, reminder_service)
        
        # Setup signal handlers
        setup_signal_handlers(reminder_service)
        
        # Start the reminder service
        reminder_service.start_service()
        logger.info("Reminder service started successfully")
        
        # Run the API server
        logger.info("Starting API server...")
        uvicorn_config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8000,
            log_level=config.service.log_level.lower()
        )
        server = uvicorn.Server(uvicorn_config)
        await server.serve()
        
    except Exception as e:
        logger.error(f"Failed to start service: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())