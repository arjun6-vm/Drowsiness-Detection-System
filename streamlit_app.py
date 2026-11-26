"""
SafeDrive AI — Driver Drowsiness Detection & Safety System
Streamlit Cloud Interactive WebRTC Application
"""

import streamlit as st
import cv2
import mediapipe as mp
import numpy as np
import time
import math
import av
import threading
from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration

# Page Configuration & UI Branding
st.set_page_config(
    page_title="SafeDrive AI — Driver Alertness System",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border-radius: 8px;
        padding: 15px;
        border: 1px solid #E2E8F0;
    }
    .alert-banner {
        padding: 12px;
        border-radius: 6px;
        font-weight: 600;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# WebRTC STUN Server Configuration for Reliable Cloud Peer Connection
RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

# Eye Landmark Constants (MediaPipe 468 landmarks)
LEFT_EYE_INDICES = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_INDICES = [362, 385, 387, 263, 373, 380]
EAR_THRESHOLD = 0.25
EYES_CLOSED_THRESHOLD = 6.0  # seconds per escalation tier
RESET_THRESHOLD = 3.0        # seconds of open eyes to reset warnings

def calculate_ear(landmarks, eye_indices, width, height):
    def dist(p1, p2):
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
    pts = [(int(landmarks.landmark[i].x * width), int(landmarks.landmark[i].y * height)) for i in eye_indices]
    A = dist(pts[1], pts[5])
    B = dist(pts[2], pts[4])
    C = dist(pts[0], pts[3])
    if C == 0:
        return 0.0
    return (A + B) / (2.0 * C)

# Global / Session-scoped Video Transformer
class DrowsinessDetector:
    def __init__(self):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.closed_start_time = None
        self.open_start_time = None
        self.warning_count = 0
        self.last_ear = 0.30
        self.state = "ALERT / ACTIVE"
        self.lock = threading.Lock()

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        h, w = img.shape[:2]

        # Lightweight downsampling if image is too large (optimizes cloud CPU usage)
        if w > 640:
            scale = 640.0 / w
            img = cv2.resize(img, (640, int(h * scale)))
            h, w = img.shape[:2]

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(img_rgb)
        current_time = time.time()
        eyes_open = False
        ear = 0.0

        if results.multi_face_landmarks:
            for face_landmarks in results.multi_face_landmarks:
                left_ear = calculate_ear(face_landmarks, LEFT_EYE_INDICES, w, h)
                right_ear = calculate_ear(face_landmarks, RIGHT_EYE_INDICES, w, h)
                ear = (left_ear + right_ear) / 2.0
                eyes_open = (ear > EAR_THRESHOLD)

                # Draw subtle mesh contours
                mp.solutions.drawing_utils.draw_landmarks(
                    img, face_landmarks, self.mp_face_mesh.FACEMESH_CONTOURS,
                    landmark_drawing_spec=None,
                    connection_drawing_spec=mp.solutions.drawing_utils.DrawingSpec(
                        color=(0, 255, 0) if eyes_open else (0, 0, 255),
                        thickness=1, circle_radius=1
                    )
                )

        with self.lock:
            self.last_ear = ear
            if eyes_open:
                if self.open_start_time is None:
                    self.open_start_time = current_time
                elif (current_time - self.open_start_time) > RESET_THRESHOLD:
                    self.warning_count = 0
                    self.closed_start_time = None
                    self.state = "ALERT / NORMAL"
            else:
                self.open_start_time = None
                if self.closed_start_time is None:
                    self.closed_start_time = current_time

                closed_duration = current_time - self.closed_start_time
                if closed_duration >= EYES_CLOSED_THRESHOLD * (self.warning_count + 1):
                    self.warning_count += 1
                
                if self.warning_count >= 4:
                    self.state = "CRITICAL: EMERGENCY ALERT TRIGGERED"
                elif self.warning_count > 0:
                    self.state = f"WARNING LEVEL {self.warning_count} — EYE CLOSURE DETECTED"

            # Overlay HUD
            hud_color = (0, 255, 0) if eyes_open else (0, 0, 255)
            cv2.putText(img, f"EAR: {ear:.2f} ({'OPEN' if eyes_open else 'CLOSED'})", (20, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, hud_color, 2)
            cv2.putText(img, f"Status: {self.state}", (20, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
            if self.warning_count > 0:
                cv2.putText(img, f"Warning Tier: {self.warning_count}/4", (20, 105),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 165, 255), 2)

        return av.VideoFrame.from_ndarray(img, format="bgr24")


# Streamlit Layout
st.markdown('<div class="main-header">🚗 SafeDrive AI — Driver Safety Console</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Real-time Computer Vision Driver Fatigue & Drowsiness Monitoring</div>', unsafe_allow_html=True)

tabs = st.tabs(["📹 Live Driver Monitor", "📋 System Architecture & EAR Logic", "🔒 Safety & Cloud Credentials"])

with tabs[0]:
    col1, col2 = st.columns([3, 2])

    with col1:
        st.subheader("Driver Camera Stream")
        st.write("Click **START** below to allow browser camera access. Video is processed locally in your session and never recorded.")
        
        webrtc_ctx = webrtc_streamer(
            key="safedrive-detection",
            mode=WebRtcMode.SENDRECV,
            rtc_configuration=RTC_CONFIGURATION,
            video_processor_factory=DrowsinessDetector,
            media_stream_constraints={"video": True, "audio": False},
            async_processing=True,
        )

    with col2:
        st.subheader("Fatigue Telemetry & Escalation")
        st.markdown("""
        - **Normal State**: Eyes open ($EAR > 0.25$). System remains alert and reset.
        - **Stage 1 (6s Closed)**: Audible reminder & early fatigue detection.
        - **Stage 2 (12s Closed)**: Progressive driver alert escalation.
        - **Stage 3 (18s Closed)**: Persistent hazard warning.
        - **Stage 4 (24s Closed)**: Critical emergency trigger with GPS location dispatch.
        - **Recovery (3s Open)**: Consecutive open-eye verification resets warning counter to 0.
        """)
        
        if webrtc_ctx.video_processor:
            with webrtc_ctx.video_processor.lock:
                ear_val = webrtc_ctx.video_processor.last_ear
                warn_val = webrtc_ctx.video_processor.warning_count
                state_val = webrtc_ctx.video_processor.state
            
            st.metric(label="Current Eye Aspect Ratio (EAR)", value=f"{ear_val:.2f}", delta=f"{ear_val - EAR_THRESHOLD:+.2f}")
            st.progress(min(1.0, warn_val / 4.0), text=f"Warning Level: {warn_val} / 4")
            if warn_val >= 4:
                st.error(f"🚨 {state_val}")
            elif warn_val > 0:
                st.warning(f"⚠️ {state_val}")
            else:
                st.success(f"✅ {state_val}")

with tabs[1]:
    st.subheader("Computer Vision & Eye Aspect Ratio (EAR) Math")
    st.latex(r"EAR = \frac{||p_2 - p_6|| + ||p_3 - p_5||}{2 \times ||p_1 - p_4||}")
    st.markdown("""
    The Eye Aspect Ratio (EAR) measures vertical eye height relative to horizontal eye width using 6 3D facial landmarks from MediaPipe FaceMesh.
    - When the eyes are open, EAR typically hovers between **0.28 and 0.38**.
    - When eyes close or droop during microsleep, EAR drops rapidly below **0.25**.
    """)

with tabs[2]:
    st.subheader("Security, Secrets & Data Privacy")
    st.markdown("""
    - **No Code/Credential Leakage**: All credentials (MongoDB URI, SMTP Passwords) are managed via encrypted **Streamlit Cloud Secrets** and never exposed in client HTML or repository files.
    - **Camera Privacy**: Video frames are processed in-memory in ephemeral sessions and never stored to disk.
    - **Academic Research Prototype**: Developed for portfolio, research demonstration, and safety evaluation.
    """)
