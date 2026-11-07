# SafeDrive — AI-Powered Driver Safety Prototype

> **Driver Drowsiness Detection and Alertness Research Prototype**  
> An experimental computer-vision application developed to detect signs of driver eye closure in real time using a standard webcam, trigger progressive audible warnings, and send notification emails with location data to manually designated emergency contacts.

---

### Important Prototype Safety & Academic Disclaimer

> **SafeDrive is strictly an experimental academic research prototype and demonstration tool.**
> - **No Regulatory or Safety Certification**: SafeDrive is **not** certified under automotive safety standards (such as ISO 26262, UNECE, or FMVSS) or medical monitoring guidelines.
> - **No Direct Emergency Service Dispatch**: This application **does not** automatically contact 911, 112, police, ambulance, fire rescue, or municipal emergency dispatch services. Emergency emails are transmitted **exclusively** to the email addresses manually configured by the user in the emergency contacts settings.
> - **Human Responsibility**: SafeDrive is **not** a substitute for an attentive, unimpaired driver or adequate rest. Computer vision accuracy varies based on lighting conditions, camera hardware, facial orientation, eyeglasses, and sunglasses. Drivers must always pull over safely and take a break when feeling fatigued.

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Framework-Flask%202.3-green.svg)](https://flask.palletsprojects.com/)
[![OpenCV](https://img.shields.io/badge/Computer%20Vision-OpenCV%204.8-red.svg)](https://opencv.org/)
[![MediaPipe](https://img.shields.io/badge/AI%20Model-MediaPipe%20FaceMesh-orange.svg)](https://developers.google.com/mediapipe)
[![MongoDB](https://img.shields.io/badge/Database-MongoDB%20Community-brightgreen.svg)](https://www.mongodb.com/)

---

## 🚀 Key Features

- **Real-Time Eye Aspect Ratio (EAR) Analysis**: High-precision eye closure tracking using OpenCV and Google MediaPipe FaceMesh (refine_landmarks=True; 468 mesh points plus iris/eye refinement).
- **Multi-Stage Progressive Escalation**:
  - **Warning 1 (6 seconds)**: Initial audio beep and caution banner.
  - **Warning 2 (12 seconds)**: Secondary audible warning with intensified alert frequency.
  - **Warning 3 (18 seconds)**: Critical audio buzzer alerting driver to pull over.
  - **Warning 4 / Emergency Alert (24 seconds)**: High-pitch emergency alert and automated dispatch trigger.
- **Continuous Eyes-Open Recovery**: 3 continuous seconds of open eyes automatically resets the warning cycle and logs a `RESET` event.
- **Automated Emergency Dispatch**: Sends an emergency email in a background daemon thread exclusively to user-saved trusted emergency contacts (or fallback receiver) containing live browser GPS coordinates (or IP location) and direct navigation links (Google Maps, Waze, Apple Maps).
- **Two-Phase OTP Signup Verification**: Prevents fake accounts by checking email syntax, domain MX records, and validating a 6-digit OTP before user creation.
- **Duplicate Account Protection**: Unique MongoDB sparse indexes and atomic transaction conflict handling (`HTTP 409`).
- **OTP Password Reset**: Secure password recovery via time-limited 6-digit email OTPs (no insecure security questions).
- **Safety Events Audit & CSV Export**: Real-time logging of all safety state transitions (`STARTED`, `WARNING`, `ALERT`, `RESET`, `PAUSED`, `RESUMED`, `STOPPED`) with one-click CSV report downloads.
- **Modern Responsive Dashboard**: Light and dark mode support, webcam permission helper, profile management, and trusted contact configuration.

---

## 🛠️ Technology Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Language** | Python 3.10 / 3.11 | Core application logic |
| **Web Framework** | Flask 2.3.3 | Routing, session management, and Jinja2 templating |
| **Computer Vision** | OpenCV (`opencv-python 4.8`) | Camera capture, frame processing, and video stream |
| **Facial Landmark AI** | MediaPipe FaceMesh (`0.10.5`) | Sub-millimeter eye landmark coordinate extraction |
| **Database** | MongoDB Community Server (`pymongo 4.6`) | User accounts, event logs, and emergency contacts |
| **Password Hashing** | Werkzeug Security | Salted PBKDF2 password hashing |
| **Alert Transport** | SMTP (SSL: 465 / STARTTLS: 587) | Emergency alert emails and verification OTPs |
| **Frontend Styling** | Custom Responsive CSS & Vanilla JS | Clean dashboard, light/dark themes, permission handling |

---

## ⚙️ Detection & Escalation Workflow

```text
[Webcam Stream] 
       │
       ▼
[MediaPipe FaceMesh] ───► Extract 6 landmarks per eye
       │
       ▼
[Calculate EAR] ────────► EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
       │
   EAR <= 0.25 ?
  ┌────┴────┐
 [YES]     [NO] ───► Eyes Open >= 3.0s? ──► Reset Warning Count to 0
  │
Eye closed timer starts:
  ├── 6.0s  ──► Warning 1 (2000 Hz beep)
  ├── 12.0s ──► Warning 2 (Intensified beep)
  ├── 18.0s ──► Warning 3 (High urgency buzzer)
  └── 24.0s ──► Warning 4 / Final Alert (3500 Hz alarm + Asynchronous Emergency Email)
```

---

## 📦 Installation & Setup

### Prerequisites
- **Operating System**: Windows 10/11 (or Linux/macOS with standard camera drivers)
- **Python**: Version 3.10 or 3.11
- **MongoDB**: MongoDB Community Server running locally on port `27017`
- **Webcam**: Built-in laptop camera or USB webcam

### 1. Clone the Repository
```bash
git clone https://github.com/arjun6-vm/Drowsiness-Detection-System.git
cd Drowsiness-Detection-System
```

### 2. Create and Activate Virtual Environment
```bash
# Windows
python -m venv new_env  # Python 3.10 or 3.11 recommended
new_env\Scripts\activate

# Linux / macOS
python3 -m venv new_env
source new_env/bin/activate
```

### 3. Install Required Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy the `.env.example` template to `.env`:
```bash
copy .env.example .env
```
Open `.env` and fill in your configuration:
```env
# Gmail SMTP Configuration (Use a 16-character Google App Password)
SENDER_EMAIL=your_email@gmail.com
SENDER_PASSWORD=xxxx_xxxx_xxxx_xxxx

# MongoDB Connection String
MONGO_URI=mongodb://127.0.0.1:27017/drowsiness_db

# Flask Application Secret Key (Required in production: minimum 32 chars, no placeholders)
# Generate secure key via: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=generate_with_python_secrets_token_hex_32
```
> **Note**: For Gmail, generate an App Password under **Google Account -> Security -> 2-Step Verification -> App Passwords**. Never use your regular Google account password.

### 5. Start MongoDB Community Server
Ensure MongoDB is running on your machine:
```bash
# Default Windows MongoDB service path:
"C:\Program Files\MongoDB\Server\8.0\bin\mongod.exe" --dbpath "C:\data\db"
```

### 6. Run SafeDrive
```bash
python app.py
```
Open your browser and navigate to:
**`http://127.0.0.1:8000/`**

---

## 🔒 Security & Privacy

- **No Hardcoded Credentials**: Passwords and SMTP tokens are loaded exclusively from `.env` via `python-dotenv` with process override protection.
- **Git Exclusions**: `.env`, temporary logs, user databases, and `.bak` files are explicitly excluded via `.gitignore`.
- **Password Security**: Passwords are never stored in plaintext; all credentials use salted PBKDF2 hashing.
- **Camera Privacy**: Video frames are processed in-memory for landmark calculations and are **never stored or recorded to disk**.
- **Rate-Limited OTPs**: Verification codes expire automatically in 5 minutes with strict attempt rate-limiting.

---

## ⚠️ Safety Disclaimer & Project Limitations

> [!IMPORTANT]
> **SafeDrive is an academic and experimental research prototype.**  
> - It is **not** certified by automotive safety standards (such as ISO 26262) or transportation regulatory authorities.  
> - It is **not** a substitute for attentive driving or adequate rest.  
> - Detection accuracy may vary depending on ambient lighting, camera resolution, driver head angle, or eyeglasses with thick frames. Drivers must always remain alert and take physical rest breaks when fatigued.

---

## License & Intellectual Property Notice
SafeDrive is an open-source academic prototype. A formal open-source license specification file (LICENSE) will be published in a future release. All source code in this repository is provided for research, educational, and evaluation purposes only.

