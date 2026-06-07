#!/usr/bin/env python3
"""
Setup script for email configuration
Run this once to configure email credentials for emergency alerts
"""

import os

# Email configuration
SENDER_EMAIL = "c.arjun6623@gmail.com"
SENDER_PASSWORD = "qxai sgmd hsvy vsym"

# Set environment variables
os.environ['SENDER_EMAIL'] = SENDER_EMAIL
os.environ['SENDER_PASSWORD'] = SENDER_PASSWORD

print("✅ Email configuration set successfully!")
print(f"Sender Email: {SENDER_EMAIL}")
print("App Password: [HIDDEN FOR SECURITY]")
print("\n🚀 Your drowsiness detection system is now ready with emergency email alerts!")
print("The system will send detailed location information when drowsiness is detected.")
