import requests
import smtplib
from email.mime.text import MIMEText
import os
import time

def get_location(location_data=None):
    try:
        # First, try to get GPS-based location from the passed data
        if location_data and 'lat' in location_data:
            location = f"{location_data['lat']},{location_data['lng']}"
            city = location_data.get('city', 'Unknown City')
            region = location_data.get('region', 'Unknown Region')
            country = location_data.get('country', 'Unknown Country')

            # If we don't have city/region/country from GPS, try reverse geocoding
            if city == 'Unknown City' or not city:
                try:
                    reverse_response = requests.get(f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={location_data['lat']}&longitude={location_data['lng']}&localityLanguage=en", timeout=5)
                    if reverse_response.status_code == 200:
                        reverse_data = reverse_response.json()
                        city = reverse_data.get('city', city)
                        region = reverse_data.get('principalSubdivision', region)
                        country = reverse_data.get('countryName', country)
                except Exception as e:
                    print(f"Reverse geocoding failed: {e}")

            return location, city, region, country

        # Fallback to IP-based location
        try:
            response = requests.get("https://ipinfo.io/json", timeout=5)
            response.raise_for_status()
        except Exception:
            response = requests.get("https://ipapi.co/json", timeout=5)
            response.raise_for_status()

        data = response.json()
        location = data.get('loc') or f"{data.get('latitude')},{data.get('longitude')}"
        city = data.get('city', 'Unknown City')
        region = data.get('region', data.get('region_code', 'Unknown Region'))
        country = data.get('country', 'Unknown Country')
        if not location:
            raise ValueError("Location data not found")
        return location, city, region, country
    except Exception as e:
        print(f"Error fetching location: {e}")
        return None, None, None, None

def send_location_email(receiver_email, location_data=None):
    loc, city, region, country = get_location(location_data)
    if loc:
        # Determine location source and accuracy info
        if location_data and 'source' in location_data:
            if location_data['source'] == 'gps':
                location_type = "GPS-based Location (High Accuracy)"
                accuracy_note = f"GPS accuracy: ~{location_data.get('accuracy', 'unknown')} meters"
            elif location_data['source'] == 'gps_watch':
                location_type = "GPS Tracking Location (Real-time)"
                accuracy_note = f"GPS accuracy: ~{location_data.get('accuracy', 'unknown')} meters"
            else:
                location_type = "IP-based Location (Approximate)"
                accuracy_note = "Accuracy: ~10 km radius"
        else:
            location_type = "IP-based Location (Approximate)"
            accuracy_note = "Accuracy: ~10 km radius"

        subject = "🚨 URGENT: Driver Drowsiness Emergency Alert"

        # Create detailed location links
        google_maps_link = f"https://www.google.com/maps?q={loc}"
        waze_link = f"https://waze.com/ul?ll={loc}&navigate=yes"
        apple_maps_link = f"http://maps.apple.com/?daddr={loc}"

        body = f"""
🚨 EMERGENCY ALERT: DRIVER DROWSINESS DETECTED 🚨

CRITICAL SITUATION:
The driver has failed to respond to multiple drowsiness warnings and requires immediate assistance.

LOCATION DETAILS ({location_type}):
• City: {city}
• Region/State: {region}
• Country: {country}
• Coordinates: {loc}
• {accuracy_note}

NAVIGATION LINKS:
• Google Maps: {google_maps_link}
• Waze: {waze_link}
• Apple Maps: {apple_maps_link}

TIMESTAMP: {time.strftime('%Y-%m-%d %H:%M:%S')}

⚠️ PLEASE RESPOND IMMEDIATELY - DRIVER SAFETY AT RISK ⚠️

This is an automated emergency alert from the Drowsiness Detection System.
"""

        # Email credentials (configured for emergency alerts)
        sender_email = "c.arjun6623@gmail.com"
        sender_password = "qxai sgmd hsvy vsym"  # Gmail app password
    
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['X-Priority'] = '1'  # High priority
        msg['X-MSMail-Priority'] = 'High'

        try:
            # Use SMTP_SSL for port 465 (implicit SSL) which is often more reliable
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(sender_email, sender_password)
                server.send_message(msg)
                print("🚀 Emergency email sent successfully with detailed location data.")
        except Exception as e:
            print(f"❌ Failed to send email: {e}")
            raise  # Re-raise to allow logging in app.py
    else:
        print("❌ Could not fetch location.")
        raise ValueError("Location fetch failed")

# Example call (trigger this after 4th alert)
# send_location_email("familymember@example.com")
