# Drowsiness Detection System with Emergency Alerts

An advanced, real-time web application designed to monitor driver fatigue, track eye closure, and trigger safety alerts including progressive audio warnings and automated emergency location emails.

## 🚀 Features

- **Real-Time Eye Aspect Ratio (EAR) Tracking**: Uses computer vision (OpenCV) and MediaPipe FaceMesh for highly accurate tracking of landmarks around the eyes.
- **Progressive Alert System**: 
  - **First 3 warnings**: Intermittent 2000Hz beeps (3.5 seconds).
  - **4th warning (Alert)**: High-pitch 3500Hz beep (5.0 seconds).
- **Asynchronous Emergency Alerts**: On the 4th consecutive warning, the system automatically fetches the driver's location (using high-accuracy GPS or IP-based location fallback) and emails emergency contacts in a separate background thread (to prevent camera stream lag).
- **Interactive Web Interface**: Complete Flask-based web app containing:
  - User Sign Up and Login.
  - Password recovery using security questions.
  - Real-time video feed streaming.
  - Dashboard logs display.
- **Data Persistence**:
  - Automatically logs events (warnings, resets, alerts) to a local MongoDB database (`drowsiness_db`).
  - Automatically exports local backup log files to `drowsiness_logs.csv`.
  - Downloadable CSV report feature.

---

## 🛠️ Prerequisites

Before running the application, make sure you have the following installed:

1. **Python 3.10+** (Recommended)
2. **MongoDB Community Server**: Download and run MongoDB locally on port `27017`.
3. **Webcam**: A built-in or external USB webcam.

---

## 📦 Setup & Installation

1. **Activate the Environment and Install Dependencies**:
   Double-click the `install.bat` script or run:
   ```bash
   install.bat
   ```
   *This will activate the local virtual environment and install dependencies like MediaPipe, OpenCV, Flask, and PyMongo.*

2. **Configure SMTP Credentials**:
   Modify the `.env` file in the root directory to include your credentials for emergency alerts:
   ```env
   SENDER_EMAIL=your-email@gmail.com
   SENDER_PASSWORD=your-app-password
   ```
   *Note: For Gmail accounts, you must generate an "App Password" by going to your [Google Account Settings](https://myaccount.google.com/apppasswords).*

---

## 🚦 How to Run

1. **Start MongoDB**:
   Ensure your local MongoDB instance is active.

2. **Run the Application**:
   Double-click `run.bat` or run:
   ```bash
   run.bat
   ```

3. **Access the Dashboard**:
   Open your browser and navigate to:
   ```
   http://localhost:8000/
   ```

4. **Test the System**:
   - Create a test account via the sign-up page or use the default developer credentials:
     - **Username:** `test`
     - **Password:** `test`
   - Close your eyes for **6 seconds** to trigger a warning.
   - Close your eyes multiple times to trigger the emergency alert.

---

## 📂 Project Structure

- `app.py`: Main Flask application handling routing, MediaPipe processing, and logs.
- `location_email_alert.py`: Module for geolocating and sending emergency email notifications.
- `system_check.py`: Diagnostic script to test your camera, MongoDB connection, dependencies, and SMTP configuration.
- `setup_email.py`: Command-line utility to configure and print environment setups.
- `requirements.txt`: Python package requirements.
- `templates/`: HTML structures for login, signup, recovery, and dashboard index.
- `static/`: Frontend static assets (CSS, JS, audio files).
- `.gitignore`: Configures files and directories that Git should ignore.
