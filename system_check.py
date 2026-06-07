import sys
import os
import time

def print_status(component, status, message=""):
    symbol = "✅" if status else "❌"
    print(f"{symbol} {component}: {message}")

print("=== Drowsiness Detection System Health Check ===\n")

# 1. Dependency Check
print("--- Checking Dependencies ---")
try:
    import cv2
    print_status("OpenCV", True, cv2.__version__)
except ImportError as e:
    print_status("OpenCV", False, str(e))

try:
    import mediapipe as mp
    print_status("MediaPipe", True, mp.__version__)
    
    # Try initializing Face Mesh to ensure model loads
    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1)
    print_status("MediaPipe Model Load", True, "FaceMesh initialized")
except Exception as e:
    print_status("MediaPipe", False, str(e))

try:
    import pymongo
    print_status("PyMongo", True, pymongo.__version__)
except ImportError as e:
    print_status("PyMongo", False, str(e))

try:
    import winsound
    print_status("Winsound", True, "Available")
except ImportError:
    print_status("Winsound", False, "Not available (Windows only)")


# 2. Database Check
print("\n--- Checking Database ---")
try:
    client = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
    client.server_info() # Trigger connection
    print_status("MongoDB Connection", True, "Connected to localhost:27017")
except Exception as e:
    print_status("MongoDB Connection", False, f"Failed: {e}")
    print("   (Ensure MongoDB Community Server is installed and running)")


# 3. Location & Internet Check
print("\n--- Checking Location Services ---")
try:
    import requests
    try:
        response = requests.get("https://ipinfo.io/json", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_status("IP Location API", True, f"Region detected: {data.get('region')}")
        else:
            print_status("IP Location API", False, f"Status Code: {response.status_code}")
    except Exception as e:
        print_status("IP Location API", False, f"Connection Failed: {e}")
except ImportError:
    print_status("Requests Library", False, "Missing")


# 4. Email Configuration Check
print("\n--- Checking Email Configuration ---")
import smtplib
# from location_email_alert import send_location_email

# Extract credentials from the actual file to test them
# Note: We are doing a static analysis extraction or just importing if possible, 
# but simply trying to login is the best test.
try:
    # Hardcoded credentials from location_email_alert.py as observed in file
    sender_email = "c.arjun6623@gmail.com"
    sender_password = "qxai sgmd hsvy vsym" 
    
    # Test SSL Connection (Port 465)
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(sender_email, sender_password)
        print_status("SMTP Authentication", True, "Login Successful (Port 465)")
        server.quit()
    except Exception as e:
        print_status("SMTP Authentication", False, f"Login Failed: {e}")

except Exception as e:
    print_status("Email Check", False, str(e))


# 5. Camera Check
print("\n--- Checking Camera ---")
try:
    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        print_status("Camera (Index 0)", True, "Opened successfully")
        ret, frame = cap.read()
        if ret:
            print_status("Camera Read", True, f"Frame captured: {frame.shape}")
        else:
            print_status("Camera Read", False, "Opened but failed to read frame")
        cap.release()
    else:
        # Try index 1
        cap_alt = cv2.VideoCapture(1)
        if cap_alt.isOpened():
            print_status("Camera (Index 1)", True, "Opened")
            cap_alt.release()
        else:
            print_status("Camera", False, "No camera found on index 0 or 1")
except Exception as e:
    print_status("Camera Check", False, str(e))

print("\n=== Check Complete ===")
