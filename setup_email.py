#!/usr/bin/env python3
"""
Setup script for email configuration
Configures email credentials for emergency alerts via environment variables or .env file
"""

import os
from dotenv import load_dotenv

# Load credentials from .env if present
load_dotenv()

# Email configuration loaded strictly from environment
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

if SENDER_PASSWORD:
    SENDER_PASSWORD = SENDER_PASSWORD.strip().replace(" ", "")

if SENDER_EMAIL and SENDER_PASSWORD:
    print("Email configuration loaded successfully from environment!")
    print(f"Sender Email: {SENDER_EMAIL}")
    print("App Password: [CONFIGURED IN ENVIRONMENT]")
else:
    print("Email credentials are not configured in environment or .env file.")
    print("Please set SENDER_EMAIL and SENDER_PASSWORD in your .env file.")
