 🚗 AI-Based Driver Drowsiness Detection System

A complete Flask + OpenCV-based real-time driver monitoring and alert system that detects drowsiness using webcam video. The system tracks eye closure, triggers alert sounds for safety, and optionally provides emergency handling using location and email notifications.

---

## 📌 Table of Contents

- [🎯 Objective](#-objective)
- [💡 Features](#-features)
- [🛠️ Technologies Used](#️-technologies-used)
- [📂 Project Structure](#-project-structure)
- [⚙️ Installation](#️-installation)
- [🚀 How to Run](#-how-to-run)
- [📸 Screenshots](#-screenshots)
- [🧠 How It Works](#-how-it-works)
- [📈 Future Improvements](#-future-improvements)
- [👥 Team Members](#-team-members)

---

## 🎯 Objective

The system is designed to monitor driver drowsiness and raise alarms when the eyes remain closed for a certain duration. This enhances road safety by alerting drowsy drivers and optionally notifying emergency contacts.

---

## 💡 Features

✅ Real-time eye tracking using webcam  
✅ Detects prolonged eye closure  
✅ 3 warning beep alerts + final alarm  
✅ Plays alert sound through browser  
✅ Flask-based web dashboard  
✅ Emergency handler with GPS & email (optional)  
✅ Webcam & pre-recorded video input support  
✅ Team profile section included

---

## 🛠️ Technologies Used

- **Python 3.11+**
- **OpenCV** – Real-time face and eye detection
- **Haarcascade Classifiers** – Pretrained models
- **Flask** – Backend server
- **HTML / CSS / JS** – Frontend UI
- **Werkzeug / Jinja2** – Templating
- **playsound / pygame** – Alert audio
- **smtplib** – Email alert (optional)
- **geocoder / requests** – Location detection (optional)

---

## 📂 Project Structure

```

Eye\_Tracking\_using\_predefined\_dataset-main/
│
├── haarcascade/
│   ├── haarcascade\_frontalface\_default.xml
│   └── haarcascade\_eye.xml
│
├── static/
│   ├── alert.mp3
│   ├── style.css
│   └── team.jpg
│
├── templates/
│   └── index.html
│
├── app.py
├── requirements.txt
└── README.md

````

---

## ⚙️ Installation

1. **Clone the repository**

```bash
git clone https://github.com/mmdnayeem4705/Eye_Tracking_using_predefined_dataset.git
cd Eye_Tracking_using_predefined_dataset-main
````

2. **Set up virtual environment (optional)**

```bash
python -m venv venv
venv\Scripts\activate  # On Windows
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Ensure Haarcascade files are placed correctly:**

* `haarcascade_frontalface_default.xml`
* `haarcascade_eye.xml`

Download from: [https://github.com/opencv/opencv/tree/master/data/haarcascades](https://github.com/opencv/opencv/tree/master/data/haarcascades)
Place them inside the `haarcascade/` directory.

---

## 🚀 How to Run

```bash
python app.py
```

Then open your browser and go to:
📍 `http://127.0.0.1:5000/`

---

## 📸 Screenshots

| Feature            | Demo                                                      |
| ------------------ | --------------------------------------------------------- |
| Eye Detection      | ![eye](https://user-images.githubusercontent.com/...)     |
| Drowsiness Warning | ![warning](https://user-images.githubusercontent.com/...) |
| Final Alert        | ![final](https://user-images.githubusercontent.com/...)   |

---

## 🧠 How It Works

1. **Face and eye detection** using Haarcascade models.
2. Eye closed for a threshold duration triggers **beep alert** (3 times).
3. If still closed, a **final warning sound** is played.
4. (Optional) Sends location & email alert for emergency.
5. Live feed is rendered in the browser using Flask stream.

---

## 📈 Future Improvements

* ✅ Replace Haarcascades with **MediaPipe Face Mesh**
* ✅ Add **YOLOv5** or custom CNN model for better detection
* 📧 Use Twilio / SMTP for emergency SMS/email
* 📊 Log events (drowsiness time, duration, GPS)
* 📱 Make responsive for mobile dashboard view
* 🔒 Add user login system (for driver reports)

---

## 👥 Team Members

| Name                  | Role                     | Contact                                       |
| --------------------- | ------------------------ | --------------------------------------------- |
| Mohammed Nayeem Mulla | Full Stack Developer     | [GitHub](https://github.com/mmdnayeem4705)    |
| Nandyala Sivamani     | Vision & Flask Developer | [sivamaninandyala@gmail.com](https://github.com/Sivamanikant/) |

---

> 🚀 Designed to **save lives** by detecting early signs of driver drowsiness. Always drive safe!

```

---

If you want, I can:
- Add badges (e.g., built with Flask, OpenCV)
- Create the `requirements.txt` for you
- Help you host it online (on Render or PythonAnywhere)
- Embed video demos directly in the README

Would you like those as well?
```
