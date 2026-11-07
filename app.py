from flask import Flask, render_template, Response, send_file, request, redirect, url_for, session, jsonify
import cv2
import mediapipe as mp
import winsound
import time
import os
import csv
import io
import math
from location_email_alert import send_location_email
import pymongo
from pymongo.errors import DuplicateKeyError

import sys
import re
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import hashlib
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bson import ObjectId

from dotenv import load_dotenv

load_dotenv(override=True)

app = Flask(__name__)
def validate_and_load_secret_key():
    raw_key = os.getenv('SECRET_KEY', '').strip()
    is_prod = (os.getenv('FLASK_ENV') == 'production')

    known_placeholders = {
        'generate_a_secure_random_key_here',
        'your_secure_random_secret_key_here',
        'your_secret_key',
        'change_me',
        'secret',
        'default',
        'password'
    }

    if is_prod:
        if not raw_key:
            raise RuntimeError('SECRET_KEY environment variable is mandatory in production')
        if raw_key.lower() in known_placeholders:
            raise RuntimeError('Production SECRET_KEY cannot use an insecure placeholder value')
        if len(raw_key) < 32:
            raise RuntimeError('Production SECRET_KEY must be at least 32 characters in length')
        return raw_key

    if raw_key:
        return raw_key
    # Development default: generate secure random key in memory per startup
    return secrets.token_hex(32)

app.secret_key = validate_and_load_secret_key()
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# Production HTTPS uses SESSION_COOKIE_SECURE=True by default.
# Local development uses SESSION_COOKIE_SECURE=False unless explicitly requested.
if os.getenv('FLASK_ENV') == 'production':
    app.config['SESSION_COOKIE_SECURE'] = True
else:
    app.config['SESSION_COOKIE_SECURE'] = (os.getenv('PREFER_HTTPS', 'false').lower() in ('true', '1'))

# MongoDB setup
mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
mongo_db_name = os.getenv("MONGO_DB_NAME", "drowsiness_db")
client = pymongo.MongoClient(mongo_uri)
db = client[mongo_db_name]
logs_collection = db["logs"]
users_collection = db["users"]
contacts_collection = db["emergency_contacts"]
password_resets_collection = db["password_resets"]
signup_verifications_collection = db["signup_verifications"]

# Ensure unique indexes for users and TTL/unique indexes for pending signups
try:
    users_collection.create_index([("username", 1)], unique=True, sparse=True)
    users_collection.create_index([("email", 1)], unique=True, sparse=True)
    signup_verifications_collection.create_index([("created_at", 1)], expireAfterSeconds=600)
    signup_verifications_collection.create_index([("email", 1)], sparse=True)
except Exception as _e_idx:
    print(f"[SafeDrive DB] Index initialization note: {_e_idx}")

# Seed initial test user if not exists
if not users_collection.find_one({'username': 'test'}):
    users_collection.insert_one({
        'username': 'test',
        'password_hash': generate_password_hash('test'),
        'favorite_car': 'car',
        'favorite_person': 'person'
    })

# Configuration
SOUNDS_DIR = 'static/sounds'
os.makedirs(SOUNDS_DIR, exist_ok=True)

# Emergency email dispatch is strictly user-configured via Emergency Contacts

# Initialize camera
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    cap = cv2.VideoCapture(1)  # Try secondary camera
if not cap.isOpened():
    raise RuntimeError("Cannot open camera")

# MediaPipe face mesh setup
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False,
                                  max_num_faces=1,
                                  refine_landmarks=True,
                                  min_detection_confidence=0.5,
                                  min_tracking_confidence=0.5)

# Detection state
beep_playing = False
monitoring_active = True
monitoring_paused = False
alert_playing = False
beep_end_time = 0
alert_end_time = 0
closed_start_time = None
open_start_time = None
warning_count = 0
EYES_CLOSED_THRESHOLD = 6
EYES_OPEN_RESET_THRESHOLD = 3
last_eyes_open_time = time.time()
event_registered = False
current_location = {}
location_history = []



def log_event(event_type, message):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_data = {
        "timestamp": timestamp,
        "event_type": event_type,
        "warning_count": warning_count,
        "message": message
    }
    try:
        logs_collection.insert_one(log_data)
    except Exception as e:
        print(f"Failed to log to MongoDB: {e}")
    # Backup to CSV
    with open('drowsiness_logs.csv', 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, event_type, warning_count, message])

def eye_aspect_ratio(landmarks, eye_indices, frame_width, frame_height):
    import math
    def euclidean_dist(p1, p2):
        return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

    points = [(int(landmarks.landmark[i].x * frame_width), int(landmarks.landmark[i].y * frame_height)) for i in eye_indices]
    A = euclidean_dist(points[1], points[5])
    B = euclidean_dist(points[2], points[4])
    C = euclidean_dist(points[0], points[3])
    ear = (A + B) / (2.0 * C)
    return ear

LEFT_EYE_INDICES = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_INDICES = [362, 385, 387, 263, 373, 380]

def generate_frames(driver_username=None):
    global beep_playing, alert_playing, beep_end_time, alert_end_time
    global closed_start_time, open_start_time, warning_count, last_eyes_open_time, event_registered
    global cap

    while True:
        if not monitoring_active:
            if cap is not None and cap.isOpened():
                cap.release()
                cap = None
            import numpy as np
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "MONITORING STOPPED", (150, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
            _, buffer = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(1)
            continue

        if cap is None or not cap.isOpened():
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                cap = cv2.VideoCapture(1)

        success, frame = cap.read()
        if not success:
            time.sleep(0.1)
            continue

        if monitoring_paused:
            cv2.putText(frame, "PAUSED", (280, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,255), 2)
            _, buffer = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.1)
            continue

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(frame_rgb)

        eyes_open = False

        if results.multi_face_landmarks:
            for face_landmarks in results.multi_face_landmarks:
                frame_height, frame_width = frame.shape[:2]

                left_ear = eye_aspect_ratio(face_landmarks, LEFT_EYE_INDICES, frame_width, frame_height)
                right_ear = eye_aspect_ratio(face_landmarks, RIGHT_EYE_INDICES, frame_width, frame_height)
                avg_ear = (left_ear + right_ear) / 2.0

                mp.solutions.drawing_utils.draw_landmarks(
                    frame, face_landmarks, mp_face_mesh.FACEMESH_CONTOURS,
                    landmark_drawing_spec=None,
                    connection_drawing_spec=mp.solutions.drawing_utils.DrawingSpec(color=(0,255,0), thickness=1, circle_radius=1)
                )

                EAR_THRESHOLD = 0.25

                if avg_ear > EAR_THRESHOLD:
                    eyes_open = True

        current_time = time.time()

        # Check if beep/alert duration has ended
        if beep_playing and current_time >= beep_end_time:
            beep_playing = False
        if alert_playing and current_time >= alert_end_time:
            alert_playing = False

        if eyes_open:
            if beep_playing or alert_playing:
                winsound.PlaySound(None, winsound.SND_ASYNC)
                beep_playing = False
                alert_playing = False
            closed_start_time = None
            event_registered = False
            last_eyes_open_time = current_time

            if warning_count > 0:
                if open_start_time is None:
                    open_start_time = current_time
                elif (current_time - open_start_time) > EYES_OPEN_RESET_THRESHOLD:
                    log_event("reset", "Eyes opened, warnings reset")
                    warning_count = 0
                    open_start_time = None
            else:
                open_start_time = None
        else:
            open_start_time = None
            if closed_start_time is None:
                closed_start_time = current_time
                event_registered = False
            closed_duration = current_time - closed_start_time
            if closed_duration >= EYES_CLOSED_THRESHOLD * (warning_count + 1):
                warning_count += 1
                log_event("warning", f"Eyes closed for {closed_duration:.1f}s")
                event_registered = True
                if warning_count < 4:
                    winsound.Beep(2000, 3500)
                    beep_playing = True
                    beep_end_time = current_time + 3.5
                else:
                    winsound.Beep(3500, 5000)
                    alert_playing = True
                    alert_end_time = current_time + 5.0
                    log_event("alert", "Final alert triggered")
                    try:
                        import threading
                        def email_thread_func(loc_data):
                            try:
                                print("Starting background email thread...")
                                current_driver = driver_username
                                if not current_driver:
                                    print('[SafeDrive] No authenticated driver session provided to stream. Email dispatch skipped.')
                                    return
                                contact = contacts_collection.find_one({'username': current_driver, 'type': 'trusted'})
                                if not contact or not contact.get('email'):
                                    print(f"[SafeDrive] No trusted emergency contact configured for driver '{current_driver}'. Email dispatch skipped.")
                                    return
                                recipient = contact['email']
                                send_location_email(recipient, loc_data)
                                log_event("email", "Emergency email sent")
                                print("Background email sent successfully")
                            except Exception as e:
                                print(f"Background email failed: {e}")
                                log_event("error", f"Failed to send email: {str(e)}")

                        loc_copy = current_location.copy() if current_location else {}
                        email_thread = threading.Thread(target=email_thread_func, args=(loc_copy,))
                        email_thread.daemon = True
                        email_thread.start()
                        print("Email thread started")
                    except Exception as e:
                        log_event("error", f"Failed to start email thread: {str(e)}")

        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/login', methods=['GET', 'POST'])
def login():
    message = request.args.get('message')
    if request.method == 'POST':
        identifier = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        user = users_collection.find_one({
            '$or': [
                {'username': identifier},
                {'email': identifier.lower()}
            ]
        })
        if user and check_password_hash(user.get('password_hash', ''), password):
            session['user'] = user.get('username')
            return redirect(url_for('live_monitor'))
        else:
            return render_template('login.html', error='Invalid credentials')
    return render_template('login.html', message=message)


@app.route('/api/control', methods=['POST'])
def control_monitoring():
    global monitoring_active, monitoring_paused, closed_start_time, open_start_time, warning_count
    action = request.json.get('action')
    if action == 'pause':
        monitoring_paused = True
        log_event("PAUSED", "Monitoring paused by user")
    elif action == 'resume':
        monitoring_paused = False
        closed_start_time = None
        open_start_time = None
        log_event("RESUMED", "Monitoring resumed by user")
    elif action == 'stop':
        monitoring_active = False
        monitoring_paused = False
        log_event("STOPPED", "Monitoring stopped by user")
    elif action == 'start':
        monitoring_active = True
        monitoring_paused = False
        closed_start_time = None
        open_start_time = None
        warning_count = 0
        log_event("STARTED", "Monitoring started by user")
    return jsonify({'status': action})

@app.route('/api/contact', methods=['GET', 'POST', 'DELETE'])
def handle_contact():
    current_username = session.get('user')
    if not current_username:
        return jsonify({'error': 'Authentication required'}), 401

    if request.method == 'DELETE':
        contacts_collection.delete_many({'username': current_username, 'type': 'trusted'})
        return jsonify({'status': 'deleted'})
    if request.method == 'POST':
        data = request.json or {}
        if data.get('action') == 'delete':
            contacts_collection.delete_many({'username': current_username, 'type': 'trusted'})
            return jsonify({'status': 'deleted'})
        email = (data.get('email') or '').strip()
        phone = (data.get('phone') or '').strip()
        contacts_collection.update_one(
            {'username': current_username, 'type': 'trusted'},
            {'$set': {'email': email, 'phone': phone, 'username': current_username, 'type': 'trusted'}},
            upsert=True
        )
        return jsonify({'status': 'success', 'email': email, 'phone': phone})
    contact = contacts_collection.find_one({'username': current_username, 'type': 'trusted'})
    if contact and (contact.get('email') or contact.get('phone')):
        return jsonify({
            'exists': True,
            'email': contact.get('email', ''),
            'phone': contact.get('phone', '')
        })
    return jsonify({'exists': False, 'email': '', 'phone': ''})

@app.route('/')
def index():
    print("Index route called")
    return render_template('landing.html')

@app.route('/live_monitor')
def live_monitor():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')


@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/landing')
def landing():
    return render_template('landing.html')



def get_event_warning_level(event):
    et = (event.get('event_type') or '').strip()
    msg = (event.get('message') or '').strip().upper()
    et_lower = et.lower()

    # Reset and all monitoring control events must always show '-'
    if et_lower in ['started', 'paused', 'resumed', 'stopped', 'reset']:
        return None

    # Warning events retain their actual event-specific level
    if et_lower == 'warning':
        import re
        m = re.search(r'eyes closed for (\d+(?:\.\d+)?)s', event.get('message', ''), re.IGNORECASE)
        if m:
            dur = float(m.group(1))
            if dur >= 24.0:
                return 4
            elif dur >= 18.0:
                return 3
            elif dur >= 12.0:
                return 2
            elif dur >= 6.0:
                return 1
        wc = event.get('warning_count')
        if wc in [1, 2, 3, 4]:
            return wc
        return 1

    # ALERT and EMERGENCY EMAIL retain Level 4
    if et_lower in ['alert', 'email']:
        return 4
    if 'ALERT' in et.upper() or 'FINAL ALERT' in msg:
        return 4
    if 'EMAIL' in et.upper() or 'EMERGENCY EMAIL' in msg:
        return 4

    return None

@app.route('/safety_events')
def safety_events():
    if 'user' not in session:
        return redirect(url_for('login'))
    try:
        events = list(logs_collection.find().sort('_id', -1).limit(50))
        for ev in events:
            ev['display_warning_level'] = get_event_warning_level(ev)
    except Exception:
        events = []
    return render_template('safety_events.html', events=events)



@app.route('/emergency_contacts')
def emergency_contacts():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('emergency_contacts.html')



@app.route('/settings')
def settings():
    if 'user' not in session:
        return redirect(url_for('login'))
    user_doc = users_collection.find_one({'username': session['user']})
    return render_template('settings.html', user=user_doc)

@app.route('/api/profile', methods=['GET', 'POST'])
def api_profile():
    if 'user' not in session:
        return jsonify({'status': 'error', 'error': 'Unauthorized'}), 401

    current_user_doc = users_collection.find_one({'username': session['user']})
    if not current_user_doc:
        return jsonify({'status': 'error', 'error': 'User not found'}), 404

    if request.method == 'GET':
        return jsonify({
            'status': 'success',
            'username': current_user_doc.get('username', session['user']),
            'email': current_user_doc.get('email', ''),
            'name': current_user_doc.get('name', ''),
            'gender': current_user_doc.get('gender', ''),
            'age': current_user_doc.get('age', '')
        })

    data = request.get_json(silent=True) or request.form
    name = (data.get('name') or '').strip()
    gender = (data.get('gender') or '').strip()
    age_raw = data.get('age')
    new_username = (data.get('username') or '').strip()
    new_email = (data.get('email') or '').strip().lower()

    if not name or not gender or not age_raw or not new_username or not new_email:
        return jsonify({'status': 'error', 'error': 'All profile fields (Full Name, Gender, Age, Username, Email) are required'}), 400

    import re
    email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    if not re.match(email_regex, new_email):
        return jsonify({'status': 'error', 'error': 'Please enter a valid email address'}), 400

    try:
        age = int(age_raw)
        if age < 16 or age > 120:
            return jsonify({'status': 'error', 'error': 'Age must be between 16 and 120'}), 400
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'error': 'Age must be a valid number'}), 400

    valid_genders = ['Male', 'Female', 'Other', 'Prefer not to say']
    if gender not in valid_genders:
        return jsonify({'status': 'error', 'error': 'Invalid gender selection'}), 400

    user_id = current_user_doc['_id']

    # Validate uniqueness of new username if changed
    if new_username != current_user_doc.get('username'):
        existing_username = users_collection.find_one({'username': new_username, '_id': {'$ne': user_id}})
        if existing_username:
            return jsonify({'status': 'error', 'error': 'Username is already taken by another account'}), 400

    # Validate uniqueness of new email if changed
    if new_email != (current_user_doc.get('email') or '').lower():
        existing_email = users_collection.find_one({'email': new_email, '_id': {'$ne': user_id}})
        if existing_email:
            return jsonify({'status': 'error', 'error': 'Email is already registered with another account'}), 400

    users_collection.update_one(
        {'_id': user_id},
        {'$set': {
            'username': new_username,
            'email': new_email,
            'name': name,
            'gender': gender,
            'age': age
        }}
    )

    # Update session to preserve login state seamlessly
    session['user'] = new_username

    return jsonify({
        'status': 'success',
        'message': 'Profile updated successfully',
        'username': new_username,
        'email': new_email,
        'name': name,
        'gender': gender,
        'age': age
    })


@app.route('/api/change_password', methods=['POST'])
def api_change_password():
    if 'user' not in session:
        return jsonify({'status': 'error', 'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or request.form
    current_password = data.get('current_password') or ''
    new_password = data.get('new_password') or ''
    confirm_password = data.get('confirm_password') or ''

    if not current_password or not new_password or not confirm_password:
        return jsonify({'status': 'error', 'error': 'All password fields are required'}), 400

    if new_password != confirm_password:
        return jsonify({'status': 'error', 'error': 'New passwords do not match'}), 400

    if len(new_password) < 6:
        return jsonify({'status': 'error', 'error': 'New password must be at least 6 characters'}), 400

    user_doc = users_collection.find_one({'username': session['user']})
    if not user_doc or not check_password_hash(user_doc.get('password_hash', ''), current_password):
        return jsonify({'status': 'error', 'error': 'Current password is incorrect'}), 400

    new_hash = generate_password_hash(new_password)
    users_collection.update_one(
        {'username': session['user']},
        {'$set': {'password_hash': new_hash}}
    )
    return jsonify({'status': 'success', 'message': 'Password changed successfully'})

@app.route('/help')
def help():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('help.html')




import csv
from io import StringIO
from flask import Response

@app.route('/download_report')
def download_report():
    if 'user' not in session:
        return redirect(url_for('login'))
    events = list(logs_collection.find().sort("timestamp", -1))

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Timestamp', 'Event Type', 'Message', 'Warning Count'])

    for event in events:
        cw.writerow([
            event.get('timestamp', ''),
            event.get('event_type', ''),
            event.get('message', ''),
            event.get('warning_count', '')
        ])

    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=safedrive_report.csv"}
    )

@app.before_request
def require_login():
    if request.endpoint is None:
        return
    allowed_routes = ['login', 'signup', 'forgot_password', 'api_generate_otp', 'api_verify_otp', 'api_reset_password', 'api_signup_send_otp', 'api_signup_verify_otp', 'static', 'landing', 'index']
    if request.endpoint not in allowed_routes and 'user' not in session:
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))

@app.route('/video_feed')
def video_feed():
    driver = session.get('user')
    return Response(generate_frames(driver_username=driver), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get_ip_location')
def get_ip_location():
    """Endpoint to get IP-based location as fallback"""
    try:
        import requests
        try:
            response = requests.get("https://ipinfo.io/json", timeout=5)
            response.raise_for_status()
        except Exception:
            response = requests.get("https://ipapi.co/json", timeout=5)
            response.raise_for_status()

        data = response.json()
        location_str = data.get('loc') or f"{data.get('latitude')},{data.get('longitude')}"

        if location_str and ',' in location_str:
            lat, lng = location_str.split(',')
            return jsonify({
                'location': {'lat': float(lat), 'lng': float(lng)},
                'city': data.get('city', 'Unknown'),
                'region': data.get('region', data.get('region_code', 'Unknown')),
                'country': data.get('country', 'Unknown'),
                'accuracy': 10000  # IP location accuracy in meters
            })
        else:
            return jsonify({'error': 'Location data not available'}), 500
    except Exception as e:
        print(f"Error fetching IP location: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/update_location', methods=['POST'])
def update_location():
    """Endpoint to receive location updates from client"""
    global current_location, location_history

    try:
        location_data = request.get_json()
        if not location_data:
            return jsonify({'error': 'No location data provided'}), 400

        # Update current location
        current_location = location_data

        # Add to history (keep last 10 locations)
        location_history.append(location_data)
        if len(location_history) > 10:
            location_history.pop(0)

        print(f"Location updated: {location_data}")
        return jsonify({'status': 'success', 'message': 'Location updated'})

    except Exception as e:
        print(f"Error updating location: {e}")
        return jsonify({'error': str(e)}), 500

EMAIL_SYNTAX_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')

def validate_signup_email_syntax(email):
    if not email or len(email) > 254:
        return False
    if not EMAIL_SYNTAX_REGEX.match(email):
        return False
    parts = email.split('@')
    if len(parts) != 2:
        return False
    local, domain = parts
    if not local or not domain or len(local) > 64:
        return False
    if domain.startswith('.') or domain.endswith('.') or '..' in domain:
        return False
    domain_parts = domain.split('.')
    if len(domain_parts) < 2 or any(len(p) == 0 for p in domain_parts):
        return False
    if len(domain_parts[-1]) < 2:
        return False
    return True

def validate_email_domain_dns(domain):
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, 'MX', lifetime=3.0)
        if answers and len(answers) > 0:
            return True, None
    except Exception as e_mx:
        try:
            import dns.resolver
            if isinstance(e_mx, dns.resolver.NXDOMAIN):
                return False, 'Domain does not exist'
            a_answers = dns.resolver.resolve(domain, 'A', lifetime=2.5)
            if a_answers and len(a_answers) > 0:
                return True, None
            return False, 'Domain has no mail routing (MX) or address records'
        except Exception as e_a:
            if 'NXDOMAIN' in type(e_a).__name__:
                return False, 'Domain does not exist'
            return True, None
    return True, None

def send_otp_email(recipient_email, otp_code, purpose="Password Reset"):
    load_dotenv(override=True)
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD", "")
    if sender_password:
        sender_password = sender_password.strip().replace(" ", "")

    if purpose == "Signup Verification":
        subject = "SafeDrive - Account Registration Verification Code"
        lead_text = "Use the following One-Time Password (OTP) to complete your SafeDrive account registration:"
    else:
        subject = "SafeDrive - Password Reset Verification Code"
        lead_text = "Use the following One-Time Password (OTP) to reset your account password:"

    plain_text = f"""SafeDrive {purpose}

Your One-Time Password (OTP) is: {otp_code}

This OTP is valid for 5 minutes.
If you did not request this {purpose.lower()}, please ignore this email.

SafeDrive Driver Safety AI"""

    html_content = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 24px; background: #ffffff; border: 1px solid #E2E8F0; border-radius: 12px;">
        <h2 style="color: #0F172A; text-align: center; margin-top: 0;">SafeDrive</h2>
        <p style="color: #475569; font-size: 15px;">{lead_text}</p>
        <div style="text-align: center; margin: 24px 0;">
            <span style="font-size: 32px; font-weight: 800; letter-spacing: 6px; color: #2563EB; background: #EFF6FF; padding: 12px 24px; border-radius: 8px; border: 1px dashed #93C5FD; display: inline-block;">
                {otp_code}
            </span>
        </div>
        <p style="color: #64748B; font-size: 13px; text-align: center;">This code will expire in <strong>5 minutes</strong>. If you did not request this, you can safely ignore this email.</p>
        <hr style="border: none; border-top: 1px solid #F1F5F9; margin: 20px 0;">
        <p style="color: #94A3B8; font-size: 11px; text-align: center; margin-bottom: 0;">SafeDrive Intelligent Driver Safety System &bull; Automated Security Service</p>
    </div>
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg.attach(MIMEText(plain_text, 'plain'))
    msg.attach(MIMEText(html_content, 'html'))

    # Delivery attempt
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender_email, sender_password)
            server.send_message(msg)
            print(f"[SafeDrive OTP] Delivered {purpose} OTP email to {recipient_email} via Port 587")
            return True
    except Exception as e587:
        print(f"[SafeDrive OTP] Port 587 delivery attempt: {e587}")
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
                server.login(sender_email, sender_password)
                server.send_message(msg)
                print(f"[SafeDrive OTP] Delivered {purpose} OTP email to {recipient_email} via Port 465")
                return True
        except Exception as e465:
            print(f"[SafeDrive OTP] Port 465 delivery attempt: {e465}")
    return False


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    return render_template('signup.html')


@app.route('/api/signup/send_otp', methods=['POST'])
def api_signup_send_otp():
    data = request.get_json(silent=True) or request.form
    name = (data.get('name') or '').strip()
    gender = (data.get('gender') or '').strip()
    age_raw = str(data.get('age') if data.get('age') is not None else '').strip()
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    confirm_password = data.get('confirm_password') or ''

    # Step 1: Validate required fields
    if not name or not gender or not age_raw or not username or not email or not password or not confirm_password:
        return jsonify({'success': False, 'error': 'All fields are required'}), 400

    valid_genders = ['Male', 'Female', 'Other', 'Prefer not to say']
    if gender not in valid_genders:
        return jsonify({'success': False, 'error': 'Invalid gender selection'}), 400

    try:
        age = int(age_raw)
        if age < 16 or age > 120:
            return jsonify({'success': False, 'error': 'Age must be between 16 and 120'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Age must be a valid number'}), 400

    if len(password) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400

    if password != confirm_password:
        return jsonify({'success': False, 'error': 'Passwords do not match'}), 400

    # Basic email syntax validation
    if not validate_signup_email_syntax(email):
        return jsonify({'success': False, 'error': 'Please provide a valid email address'}), 400

    domain = email.split('@')[1]
    is_domain_valid, domain_err = validate_email_domain_dns(domain)
    if not is_domain_valid:
        return jsonify({'success': False, 'error': f'Invalid email domain: {domain_err}'}), 400

    # Uniqueness checks (case-insensitive username and normalized email)
    if users_collection.find_one({'username': {'$regex': f'^{re.escape(username)}$', '$options': 'i'}}):
        return jsonify({'success': False, 'error': 'Username already exists'}), 400

    if users_collection.find_one({'email': email}):
        return jsonify({'success': False, 'error': 'Email is already registered with another account'}), 400

    # Resend cooldown: 10s cooldown
    recent = signup_verifications_collection.find_one({
        'email': email,
        'created_at': {'$gt': datetime.utcnow() - timedelta(seconds=10)},
        'verified': False,
        'used': False
    })
    if recent:
        return jsonify({
            'success': False,
            'error': 'An OTP was recently requested. Please wait 10 seconds before requesting another.'
        }), 429

    # Generate cryptographically secure random 6-digit OTP
    otp_code = f"{secrets.randbelow(1000000):06d}"
    otp_hash = hashlib.sha256(otp_code.encode('utf-8')).hexdigest()
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=5)

    # Invalidate previous unused verification attempts for this email or username
    signup_verifications_collection.update_many(
        {'$or': [{'email': email}, {'username': username}], 'used': False},
        {'$set': {'used': True}}
    )

    # Store hashed password & secure OTP hash in pending verification record (NO user created yet)
    hashed_pwd = generate_password_hash(password)
    ins = signup_verifications_collection.insert_one({
        'name': name,
        'gender': gender,
        'age': age,
        'username': username,
        'email': email,
        'password_hash': hashed_pwd,
        'otp_hash': otp_hash,
        'created_at': now,
        'expires_at': expires_at,
        'attempts': 0,
        'verified': False,
        'used': False
    })
    signup_id = str(ins.inserted_id)

    # Synchronous delivery check: SMTP delivery failure must never result in registration
    delivered = send_otp_email(email, otp_code, purpose="Signup Verification")
    if not delivered:
        signup_verifications_collection.update_one({'_id': ins.inserted_id}, {'$set': {'used': True}})
        return jsonify({
            'success': False,
            'error': 'Failed to deliver verification code to your email. Please check your address or try again.'
        }), 502

    return jsonify({
        'success': True,
        'message': f'A 6-digit verification code has been sent to {email}. It is valid for 5 minutes.',
        'signup_id': signup_id
    })


@app.route('/api/signup/verify_otp', methods=['POST'])
def api_signup_verify_otp():
    data = request.get_json(silent=True) or request.form
    signup_id = (data.get('signup_id') or '').strip()
    otp = (data.get('otp') or '').strip()

    if not signup_id or not otp:
        return jsonify({'success': False, 'error': 'Verification session and OTP code are required'}), 400

    try:
        oid = ObjectId(signup_id)
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid verification session'}), 400

    record = signup_verifications_collection.find_one({'_id': oid})
    if not record or record.get('used') or record.get('verified'):
        return jsonify({'success': False, 'error': 'Invalid or expired verification session. Please submit signup again.', 'expired': True}), 400

    # Expire after 5 minutes
    if datetime.utcnow() > record['expires_at']:
        signup_verifications_collection.update_one({'_id': oid}, {'$set': {'used': True}})
        return jsonify({'success': False, 'error': 'Verification OTP has expired. Please request a new code.', 'expired': True}), 400

    # Max 5 incorrect attempts
    if record.get('attempts', 0) >= 5:
        signup_verifications_collection.update_one({'_id': oid}, {'$set': {'used': True}})
        return jsonify({'success': False, 'error': 'Too many failed attempts (maximum 5). Please request a new code.', 'expired': True}), 400

    entered_hash = hashlib.sha256(otp.encode('utf-8')).hexdigest()
    if entered_hash != record['otp_hash']:
        signup_verifications_collection.update_one({'_id': oid}, {'$inc': {'attempts': 1}})
        remaining = 4 - record.get('attempts', 0)
        return jsonify({'success': False, 'error': f'Incorrect verification code ({remaining} attempts remaining).'}), 400

    # OTP Verified! Re-check username/email uniqueness atomically before creating user
    username = record['username']
    email = record['email']

    if users_collection.find_one({'username': {'$regex': f'^{re.escape(username)}$', '$options': 'i'}}):
        signup_verifications_collection.update_one({'_id': oid}, {'$set': {'used': True}})
        return jsonify({'success': False, 'error': 'Username was taken before verification completed.'}), 400

    if users_collection.find_one({'email': email}):
        signup_verifications_collection.update_one({'_id': oid}, {'$set': {'used': True}})
        return jsonify({'success': False, 'error': 'Email is already registered.'}), 400

    # Create the single official MongoDB user record
    new_user = {
        'username': username,
        'email': email,
        'name': record['name'],
        'gender': record['gender'],
        'age': record['age'],
        'password_hash': record['password_hash'],
        'created_at': datetime.utcnow()
    }
    try:
        users_collection.insert_one(new_user)
    except DuplicateKeyError as e_dup:
        # Invalidate/consume pending verification to prevent replay
        signup_verifications_collection.update_one(
            {'_id': oid},
            {'$set': {'used': True}}
        )
        # Inspect exception details (keyPattern / keyValue) safely without fragile string matching
        key_pattern = (getattr(e_dup, 'details', None) or {}).get('keyPattern', {})
        if 'username' in key_pattern:
            conflict_msg = 'Username already exists.'
        elif 'email' in key_pattern:
            conflict_msg = 'Email is already registered with another account.'
        else:
            conflict_msg = 'An account with these details already exists.'
        return jsonify({'success': False, 'error': conflict_msg}), 409

    # Mark pending verification as completed and used
    signup_verifications_collection.update_one(
        {'_id': oid},
        {'$set': {'verified': True, 'used': True}}
    )

    return jsonify({
        'success': True,
        'message': 'Account created successfully! Please sign in with your credentials.',
        'redirect': url_for('login', message='Account created successfully! Please sign in.')
    })

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    return render_template('forgot_password.html')


@app.route('/api/forgot_password/generate_otp', methods=['POST'])
def api_generate_otp():
    data = request.get_json(silent=True) or request.form
    identifier = (data.get('identifier') or '').strip()
    if not identifier:
        return jsonify({'success': False, 'error': 'Username or Email is required'}), 400

    user = users_collection.find_one({
        '$or': [
            {'username': identifier},
            {'email': identifier.lower()}
        ]
    })

    # Generic security message if user not found or has no email
    if not user or not user.get('email'):
        return jsonify({
            'success': True,
            'message': 'If the account exists and has a registered email, an OTP has been sent.',
            'reset_id': None
        })

    # Rate limiting: 10s cooldown
    recent = password_resets_collection.find_one({
        'user_id': user['_id'],
        'created_at': {'$gt': datetime.utcnow() - timedelta(seconds=10)},
        'used': False
    })
    if recent:
        return jsonify({
            'success': False,
            'error': 'An OTP was recently generated. Please wait 10 seconds before requesting another.'
        }), 429

    otp_code = f"{secrets.randbelow(1000000):06d}"
    otp_hash = hashlib.sha256(otp_code.encode('utf-8')).hexdigest()
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=5)

    # Invalidate previous unused resets for this user
    password_resets_collection.update_many(
        {'user_id': user['_id'], 'used': False},
        {'$set': {'used': True}}
    )

    ins = password_resets_collection.insert_one({
        'user_id': user['_id'],
        'username': user.get('username'),
        'email': user.get('email'),
        'otp_hash': otp_hash,
        'created_at': now,
        'expires_at': expires_at,
        'attempts': 0,
        'verified': False,
        'used': False
    })
    reset_id = str(ins.inserted_id)

    # Attempt SMTP email sending in background thread so HTTP response is non-blocking
    import threading
    threading.Thread(target=send_otp_email, args=(user['email'], otp_code), daemon=True).start()
    # Server-side audit log for operational testing and audit
    print(f"[SafeDrive OTP Audit] Password reset OTP generated for {user.get('username')} ({user.get('email')}) (Valid for 5 min)")

    return jsonify({
        'success': True,
        'message': f'A 6-digit OTP has been sent to the email registered with {user.get("username")}. It is valid for 5 minutes.',
        'reset_id': reset_id
    })


@app.route('/api/forgot_password/verify_otp', methods=['POST'])
def api_verify_otp():
    data = request.get_json(silent=True) or request.form
    reset_id = (data.get('reset_id') or '').strip()
    otp = (data.get('otp') or '').strip()

    if not reset_id or not otp:
        return jsonify({'success': False, 'error': 'Reset session and OTP are required'}), 400

    try:
        oid = ObjectId(reset_id)
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid reset session'}), 400

    reset = password_resets_collection.find_one({'_id': oid})
    if not reset or reset.get('used'):
        return jsonify({'success': False, 'error': 'Invalid or expired password reset request. Please generate a new OTP.', 'expired': True}), 400

    # Check expiration (5 minutes)
    if datetime.utcnow() > reset['expires_at']:
        password_resets_collection.update_one({'_id': oid}, {'$set': {'used': True}})
        return jsonify({'success': False, 'error': 'OTP expired. Please generate a new OTP.', 'expired': True}), 400

    # Check attempt limit (5 attempts)
    if reset.get('attempts', 0) >= 5:
        password_resets_collection.update_one({'_id': oid}, {'$set': {'used': True}})
        return jsonify({'success': False, 'error': 'Too many failed attempts. Please generate a new OTP.', 'expired': True}), 400

    entered_hash = hashlib.sha256(otp.encode('utf-8')).hexdigest()
    if entered_hash != reset['otp_hash']:
        password_resets_collection.update_one({'_id': oid}, {'$inc': {'attempts': 1}})
        remaining = 4 - reset.get('attempts', 0)
        return jsonify({'success': False, 'error': f'Incorrect OTP. Please check your email and try again ({remaining} attempts remaining).'}), 400

    # OTP verified! Generate one-time reset token
    reset_token = secrets.token_urlsafe(32)
    password_resets_collection.update_one(
        {'_id': oid},
        {'$set': {'verified': True, 'reset_token': reset_token}}
    )

    return jsonify({'success': True, 'reset_token': reset_token, 'message': 'OTP verified successfully.'})


@app.route('/api/forgot_password/reset_password', methods=['POST'])
def api_reset_password():
    data = request.get_json(silent=True) or request.form
    reset_id = (data.get('reset_id') or '').strip()
    reset_token = (data.get('reset_token') or '').strip()
    password = data.get('password') or ''
    confirm_password = data.get('confirm_password') or ''

    if not reset_id or not reset_token:
        return jsonify({'success': False, 'error': 'Invalid reset session. Please start over.'}), 400

    try:
        oid = ObjectId(reset_id)
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid reset ID'}), 400

    reset = password_resets_collection.find_one({
        '_id': oid,
        'reset_token': reset_token,
        'verified': True,
        'used': False
    })
    if not reset:
        return jsonify({'success': False, 'error': 'Invalid or expired reset session. Please start over.'}), 400

    if not password or not confirm_password:
        return jsonify({'success': False, 'error': 'Both password fields are required'}), 400

    if password != confirm_password:
        return jsonify({'success': False, 'error': 'Passwords do not match'}), 400

    # Update user password securely
    hashed = generate_password_hash(password)
    users_collection.update_one(
        {'_id': reset['user_id']},
        {'$set': {'password_hash': hashed}}
    )

    # Invalidate reset record
    password_resets_collection.update_one(
        {'_id': oid},
        {'$set': {'used': True, 'reset_token': None}}
    )

    print(f"[SafeDrive OTP] Password successfully reset for user '{reset.get('username')}'")

    return jsonify({
        'success': True,
        'message': 'Password has been reset successfully. Please sign in with your new password.',
        'redirect': url_for('login')
    })

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, port=8000)
