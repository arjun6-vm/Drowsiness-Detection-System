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

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure secret key

# In-memory user storage (for demonstration; use database in production)
users = {
    'test': {
        'password': 'test',
        'favorite_car': 'car',
        'favorite_person': 'person'
    }
}

# MongoDB setup
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["drowsiness_db"]
logs_collection = db["logs"]

# Configuration
SOUNDS_DIR = 'static/sounds'
os.makedirs(SOUNDS_DIR, exist_ok=True)

# Receiver email for emergency alerts
RECEIVER_EMAIL = "c.arjun6623@gmail.com,99220040825@klu.ac.in"  # Updated with provided emails

# Initialize camera
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    cap = cv2.VideoCapture(1)  # Try secondary camera
if not cap.isOpened():
    raise RuntimeError("Cannot open camera")

# Fix: Reset warning_count when eyes open for more than threshold seconds
EYES_OPEN_RESET_THRESHOLD = 6  # Updated from 3 to 6 seconds
last_eyes_open_time = time.time()
    
# MediaPipe face mesh setup
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False,
                                  max_num_faces=1,
                                  refine_landmarks=True,
                                  min_detection_confidence=0.5,
                                  min_tracking_confidence=0.5)

# Detection state
beep_playing = False
alert_playing = False
beep_end_time = 0
alert_end_time = 0
closed_start_time = None
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

def generate_frames():
    global beep_playing, alert_playing
    global closed_start_time, warning_count, last_eyes_open_time, event_registered

    while True:
        success, frame = cap.read()
        if not success:
            break

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
            if warning_count > 0 and (current_time - last_eyes_open_time) > EYES_OPEN_RESET_THRESHOLD:
                log_event("reset", "Eyes opened, warnings reset")
                warning_count = 0
        else:
            if closed_start_time is None:
                closed_start_time = current_time
                event_registered = False
            closed_duration = current_time - closed_start_time
            if closed_duration >= EYES_CLOSED_THRESHOLD and not event_registered:
                warning_count += 1
                log_event("warning", f"Eyes closed for {closed_duration:.1f}s")
                event_registered = True
                if warning_count < 4:
                    
                        winsound.Beep(2000, 3500)  # Increased from 1500 to 3500 ms
                        beep_playing = True
                        beep_end_time = current_time + 3.5  # 3500ms = 3.5 seconds
                else:
    
                        winsound.Beep(3500, 5000)  # Increased from 3000 to 5000 ms
                        alert_playing = True
                        alert_end_time = current_time + 5.0  # 5000ms = 5 seconds
                        log_event("alert", "Final alert triggered")
                        try:
                            # Send email in a separate thread to prevent video freezing ("jamming")
                            import threading
                            def email_thread_func(loc_data):
                                try:
                                    print("✉️ Starting background email thread...")
                                    send_location_email(RECEIVER_EMAIL, loc_data)
                                    log_event("email", "Emergency email sent")
                                    print("✅ Background email sent successfully")
                                except Exception as e:
                                    print(f"❌ Background email failed: {e}")
                                    log_event("error", f"Failed to send email: {str(e)}")

                            # Pass a copy of the current location data to the thread
                            loc_copy = current_location.copy() if current_location else {}
                            email_thread = threading.Thread(target=email_thread_func, args=(loc_copy,))
                            email_thread.daemon = True # Ensure thread dies if app closes
                            email_thread.start()
                            print("➡️ Email thread started")
                            
                        except Exception as e:
                            log_event("error", f"Failed to start email thread: {str(e)}")

        _, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/login', methods=['GET', 'POST'])
def login():
    print("Login route called")
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username in users and users[username]['password'] == password:
            session['user'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/')
def index():
    print("Index route called")
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.before_request
def require_login():
    allowed_routes = ['login', 'signup', 'forgot_password', 'static']
    if request.endpoint not in allowed_routes and 'user' not in session:
        return redirect(url_for('login'))
        
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))
        
@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/download_report')
def download_report():
    try:
        logs = list(logs_collection.find())
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["timestamp", "event_type", "warning_count", "message"])
        for log in logs:
            writer.writerow([log["timestamp"], log["event_type"], log["warning_count"], log["message"]])
        output.seek(0)
        return send_file(io.BytesIO(output.getvalue().encode()), as_attachment=True, download_name="drowsiness_report.csv", mimetype="text/csv")
    except Exception as e:
        return f"Error generating report: {e}", 500

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
            
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        favorite_car = request.form.get('favorite_car')
        favorite_person = request.form.get('favorite_person')
        if password != confirm_password:
            return render_template('signup.html', error='Passwords do not match')
        if username in users:
            return render_template('signup.html', error='Username already exists')
        users[username] = {
            'password': password,
            'favorite_car': favorite_car,
            'favorite_person': favorite_person
        }
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username')
        favorite_car = request.form.get('favorite_car')
        favorite_person = request.form.get('favorite_person')
        if username in users:
            if users[username]['favorite_car'] == favorite_car and users[username]['favorite_person'] == favorite_person:
                return render_template('forgot_password.html', success=f"Your password is: {users[username]['password']}")
            else:
                return render_template('forgot_password.html', error='Incorrect answers')
        else:
            return render_template('forgot_password.html', error='Username not found')
    return render_template('forgot_password.html')

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, port=8000)
