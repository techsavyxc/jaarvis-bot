# JARVIS-Bot 🤖

An AI-powered mobile assistant robot with local LLM, built on NVIDIA Jetson Orin Nano.

## 🎯 Project Overview

JARVIS-Bot is a voice-controlled mobile robot assistant that processes all AI locally without cloud dependencies. Built for my Senior Design Project at Cal Poly Pomona.

**Demo Day:** May 1, 2026 | ECE 4th Floor Symposium

## ✅ Working Features

| Feature | Status | Description |
|---------|--------|-------------|
| Face Display | ✅ Working | Animated eyes with expressions and personalities |
| Vision Tracking | ✅ Working | Person detection with Intel RealSense D435 + MediaPipe |
| LIDAR Obstacle Detection | ✅ Working | 360° scanning with RPLIDAR A1 |
| Text-to-Speech | ✅ Working | Natural voice with Piper TTS |
| Speech Recognition | ✅ Working | Offline recognition with Vosk |
| Motor Control | 🔄 In Progress | Upgrading to Jetson-compatible motor driver |

## 🛠️ Hardware

- **Brain:** NVIDIA Jetson Orin Nano
- **Vision:** Intel RealSense D435 Depth Camera
- **LIDAR:** RPLIDAR A1 (360° scanning)
- **Display:** 5" Touchscreen (800x480)
- **Audio:** USB Microphone + Speaker
- **Power:** TalentCell 12V/9000mAh Battery
- **Chassis:** 4WD Robot Chassis with TT Motors

## 📁 Project Structure
## 🚀 Quick Start

### Prerequisites
- NVIDIA Jetson Orin Nano with JetPack
- ROS 2 Humble
- Python 3.10+

### Installation
```bash
# Clone the repo
git clone https://github.com/techsavyxc/jaarvis-bot.git

# Navigate to workspace
cd jarvis_ws

# Build
colcon build

# Source
source install/setup.bash
```

### Running Individual Nodes
```bash
# Face display
python3 jarvis_agent/face_node.py

# Vision tracking
python3 jarvis_agent/vision_node.py

# LIDAR scanning
python3 jarvis_agent/lidar_node.py
```

## 🎭 Personality Modes

JARVIS has 7 distinct personalities:
1. **Normal** - Professional assistant (cyan)
2. **Professional** - Formal tone (white)
3. **Sassy** - Witty responses (pink)
4. **Funny** - Humorous (yellow)
5. **Pirate** - Arrr matey! (orange)
6. **Yoda** - Speak like Yoda, I do (green)
7. **Surfer** - Chill vibes bro (blue)

## 🎥 Demo

Coming soon!

## 👨‍💻 Author

**Chris Venegas**
- Senior, Electrical & Computer Engineering
- Cal Poly Pomona, Class of 2026

## 📄 License

MIT License
