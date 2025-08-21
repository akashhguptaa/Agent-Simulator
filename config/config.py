import os
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_NUMBER")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

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