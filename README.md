# Jarvis-Bot 🤖

**An AI-powered mobile assistant robot with local LLM integration**

Jarvis-Bot is a modular robotic agent built with ROS 2 that translates natural human language into physical robot actions. All AI reasoning runs locally—no cloud APIs required.

---

## 🎯 Key Features

- **Natural Language Understanding**: Talk to your robot like a human
- **Local LLM**: AI reasoning runs on-device (Ollama + llama3.2)
- **Modular Architecture**: Clean separation of concerns via ROS 2 topics
- **MQTT Bridge**: Control from external devices (phone, PC, Jetson)
- **Simulation Ready**: Test with TurtleSim before deploying to real hardware
- **Fallback Mode**: Works without LLM using rule-based parsing

---

## 📐 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           JARVIS-BOT ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   EXTERNAL                        ROS 2 SYSTEM                          │
│   ────────                        ────────────                          │
│                                                                          │
│   ┌─────────┐    MQTT          ┌──────────────┐                         │
│   │ Phone/  │ ──────────────▶  │  MQTT Bridge │                         │
│   │ PC/     │  jarvis/voice    │              │                         │
│   │ Jetson  │ ◀──────────────  │  (mqtt_      │                         │
│   └─────────┘  jarvis/status   │   bridge.py) │                         │
│                                └──────┬───────┘                         │
│                                       │                                  │
│                                       ▼ /jarvis/nl_raw                  │
│                                ┌──────────────┐                         │
│                                │   NLP Node   │                         │
│                                │  ┌─────────┐ │                         │
│                                │  │ LLM or  │ │                         │
│                                │  │ Rules   │ │                         │
│                                │  └─────────┘ │                         │
│                                └──────┬───────┘                         │
│                                       │                                  │
│                                       ▼ /jarvis/intent (JSON)           │
│                                ┌──────────────┐                         │
│                                │    Agent     │                         │
│                                │   (Brain)    │                         │
│                                │              │──▶ /jarvis/telemetry    │
│                                └──────┬───────┘                         │
│                                       │                                  │
│                                       ▼ /turtle1/cmd_vel                │
│                                ┌──────────────┐                         │
│                                │   TurtleSim  │                         │
│                                │   (Robot)    │                         │
│                                └──────────────┘                         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

```bash
# Ubuntu 22.04 with ROS 2 Humble
sudo apt update
sudo apt install -y ros-humble-desktop ros-humble-turtlesim

# Python dependencies
pip install paho-mqtt requests --break-system-packages

# MQTT broker (optional, for external control)
sudo apt install -y mosquitto mosquitto-clients
```

### Build the Package

```bash
cd ~/jarvis_ws
colcon build --packages-select jarvis_agent
source install/setup.bash
```

### Run (Simple Mode - No LLM)

```bash
# Terminal 1: Launch the system
ros2 launch jarvis_agent jarvis_sim.launch.py

# Terminal 2: Send commands via ROS topic
ros2 topic pub --once /jarvis/nl_raw std_msgs/String "data: 'move forward 2'"
ros2 topic pub --once /jarvis/nl_raw std_msgs/String "data: 'turn left'"
ros2 topic pub --once /jarvis/nl_raw std_msgs/String "data: 'circle'"
ros2 topic pub --once /jarvis/nl_raw std_msgs/String "data: 'stop'"
```

### Run (LLM Mode - With Ollama)

```bash
# First, install and start Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull llama3.2:1b

# Launch with LLM
ros2 launch jarvis_agent jarvis_llm.launch.py

# Now you can use natural language!
ros2 topic pub --once /jarvis/nl_raw std_msgs/String "data: 'hey jarvis go forward a bit'"
ros2 topic pub --once /jarvis/nl_raw std_msgs/String "data: 'can you spin around twice'"
```

### Run (Full System with MQTT)

```bash
# Terminal 1: Start MQTT broker
mosquitto -v

# Terminal 2: Launch Jarvis
ros2 launch jarvis_agent jarvis_full.launch.py

# Terminal 3: Send commands via MQTT
mosquitto_pub -t jarvis/voice -m "move forward 3"
mosquitto_pub -t jarvis/voice -m "turn right 2"
mosquitto_pub -t jarvis/voice -m "do a circle"

# Terminal 4: Monitor status
mosquitto_sub -t jarvis/status
```

---

## 📋 Supported Commands

### Movement
| Command | Example |
|---------|---------|
| Move forward | "move forward", "go ahead 3 seconds" |
| Move backward | "move back", "go backward 2" |
| Turn left | "turn left", "rotate left 1.5" |
| Turn right | "turn right 90 degrees" |
| Circle | "do a circle", "circle left for 5 seconds" |
| Stop | "stop", "halt", "freeze" |

### Speech (Placeholder)
| Command | Example |
|---------|---------|
| Say | "say hello world" |

### With LLM, you can also use:
- "hey jarvis, go forward a little bit"
- "can you spin around twice?"
- "move backwards for a couple seconds"
- "please stop now"

---

## 📁 Project Structure

```
jarvis_agent/
├── jarvis_agent/
│   ├── __init__.py
│   ├── agent_node.py       # Robot execution brain
│   ├── nlp_node.py         # Rule-based NLP (fallback)
│   ├── llm_nlp_node.py     # LLM-powered NLP (Ollama)
│   ├── mqtt_bridge.py      # MQTT ↔ ROS bridge
│   └── telemetry_logger.py # Debug monitoring
├── launch/
│   ├── jarvis_sim.launch.py   # Simple simulation
│   ├── jarvis_llm.launch.py   # With LLM
│   └── jarvis_full.launch.py  # Full system + MQTT
├── config/
├── resource/
├── package.xml
├── setup.py
└── setup.cfg
```

---

## 🔧 ROS 2 Topics

| Topic | Type | Direction | Description |
|-------|------|-----------|-------------|
| `/jarvis/nl_raw` | String | IN | Raw natural language input |
| `/jarvis/intent` | String | IN | Structured JSON intent |
| `/jarvis/telemetry` | String | OUT | Robot state (JSON) |
| `/jarvis/status` | String | OUT | Human-readable status |
| `/turtle1/cmd_vel` | Twist | OUT | Velocity commands |
| `/turtle1/pose` | Pose | IN | Robot pose |

---

## 📡 Intent Schema

The NLP layer outputs structured JSON intents:

```json
{"action": "move", "direction": "forward", "duration": 2.0}
{"action": "turn", "direction": "left", "duration": 1.5}
{"action": "circle", "direction": "right", "duration": 3.0}
{"action": "stop"}
{"action": "say", "text": "Hello, world!"}
```

---

## 🖥️ Jetson Deployment (Future)

For NVIDIA Jetson Orin Nano:

1. Install JetPack 6.x with ROS 2 Humble
2. Install Ollama for ARM64
3. Use NVIDIA NIM for optimized inference
4. Replace TurtleSim with real motor drivers

---

## 🧪 Testing

```bash
# Run all tests
colcon test --packages-select jarvis_agent

# Test individual nodes
ros2 run jarvis_agent agent_node
ros2 run jarvis_agent nlp_node
ros2 run jarvis_agent llm_nlp_node
```

---

## 📚 References

- [ROS 2 Humble Documentation](https://docs.ros.org/en/humble/)
- [Ollama](https://ollama.com/)
- [MQTT / Mosquitto](https://mosquitto.org/)
- [TurtleSim](https://docs.ros.org/en/humble/Tutorials/Beginner-CLI-Tools/Introducing-Turtlesim/Introducing-Turtlesim.html)

---

## 👤 Author

**Chris** - Senior Design Project

---

## 📄 License

MIT License
