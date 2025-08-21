import os
from dataclasses import dataclass
from typing import Optional
from config.config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,

)

@dataclass
class TwilioConfig:
    account_sid: str
    auth_token: str
    from_number: str
    whatsapp_number: str

@dataclass
class DatabaseConfig:
    db_path: str = "reminders.db"

@dataclass
class ServiceConfig:
    check_interval_seconds: int = 60
    max_workers: int = 5
    log_level: str = "INFO"

@dataclass
class AppConfig:
    twilio: TwilioConfig
    database: DatabaseConfig
    service: ServiceConfig

def load_config() -> AppConfig:
    """Load configuration from environment variables or defaults"""
    
    # Twilio configuration (required)
    account_sid = TWILIO_ACCOUNT_SID
    auth_token = TWILIO_AUTH_TOKEN
    from_number = TWILIO_FROM_NUMBER


    if not all([account_sid, auth_token, from_number]):
        raise ValueError(
            "Missing required Twilio configuration. Please set:\n"
            "- TWILIO_ACCOUNT_SID\n"
            "- TWILIO_AUTH_TOKEN\n" 
            "- TWILIO_FROM_NUMBER\n"
            "- TWILIO_WHATSAPP_NUMBER (optional, defaults to from_number)"
        )
    
    
    twilio_config = TwilioConfig(
        account_sid=account_sid,
        auth_token=auth_token,
        from_number=from_number,
        whatsapp_number="+919315563013"
    )
    
    # Database configuration
    database_config = DatabaseConfig(
        db_path=os.getenv("DB_PATH", "reminders.db")
    )
    
    # Service configuration
    service_config = ServiceConfig(
        check_interval_seconds=int(os.getenv("CHECK_INTERVAL_SECONDS", "60")),
        max_workers=int(os.getenv("MAX_WORKERS", "5")),
        log_level=os.getenv("LOG_LEVEL", "INFO")
    )
    
    return AppConfig(
        twilio=twilio_config,
        database=database_config,
        service=service_config
    )