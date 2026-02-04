#!/usr/bin/env python3
"""
LLM NLP Node - AI-Powered Natural Language Understanding
=========================================================
Uses a local LLM (via Ollama) to translate natural human language
into structured robot intents.

This is the "AI Agent" component - it reasons about user commands
and produces safe, structured JSON intents.

Subscribes: /jarvis/nl_raw (String - raw human text)
Publishes:  /jarvis/intent (String - JSON intent)

Requirements:
    - Ollama installed: curl -fsSL https://ollama.com/install.sh | sh
    - Model pulled: ollama pull llama3.2:1b  (or mistral, phi3, etc.)

Example inputs -> outputs:
    "hey jarvis go forward a bit" -> {"action": "move", "direction": "forward", "duration": 1.0}
    "can you spin around twice" -> {"action": "turn", "direction": "left", "duration": 4.0}
    "please stop" -> {"action": "stop"}
"""

import json
import re
import time
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# =============================================================================
# SYSTEM PROMPT - This is the "brain" of Jarvis
# =============================================================================
SYSTEM_PROMPT = """You are Jarvis, an AI assistant controlling a mobile robot.
Your job is to translate natural language commands into structured JSON intents.

AVAILABLE ACTIONS:
1. move - Move the robot forward or backward
   Format: {"action": "move", "direction": "forward"|"back", "duration": <seconds>}
   
2. turn - Rotate the robot in place
   Format: {"action": "turn", "direction": "left"|"right", "duration": <seconds>}
   
3. circle - Drive in a circle
   Format: {"action": "circle", "direction": "left"|"right", "duration": <seconds>}
   
4. stop - Immediately stop all motion
   Format: {"action": "stop"}
   
5. say - Speak a message
   Format: {"action": "say", "text": "<message>"}

RULES:
- Default duration is 1.0 seconds for move/turn, 3.0 for circle
- "a bit" or "a little" = 0.5-1.0 seconds
- "a lot" or "far" = 3.0-5.0 seconds  
- "twice" for turning = multiply duration by 2
- If the command is unclear, use action "say" to ask for clarification
- ONLY output valid JSON, nothing else
- Never output actions not in the list above

EXAMPLES:
User: "go forward"
{"action": "move", "direction": "forward", "duration": 1.0}

User: "move back 3 seconds"
{"action": "move", "direction": "back", "duration": 3.0}

User: "turn left a little bit"
{"action": "turn", "direction": "left", "duration": 0.5}

User: "spin around"
{"action": "turn", "direction": "left", "duration": 4.0}

User: "do a circle"
{"action": "circle", "direction": "left", "duration": 3.0}

User: "stop"
{"action": "stop"}

User: "say hello world"
{"action": "say", "text": "hello world"}

User: "what's the weather?"
{"action": "say", "text": "I can only control movement. Try: move, turn, circle, or stop."}

Now respond ONLY with JSON for this command:"""


class LlmNlpNode(Node):
    def __init__(self):
        super().__init__('llm_nlp_node')

        # === Parameters ===
        self.declare_parameter('ollama_host', 'http://localhost:11434')
        self.declare_parameter('model', 'llama3.2:1b')  # Small, fast model
        self.declare_parameter('timeout', 10.0)
        self.declare_parameter('fallback_enabled', True)

        self.ollama_host = self.get_parameter('ollama_host').value
        self.model = self.get_parameter('model').value
        self.timeout = self.get_parameter('timeout').value
        self.fallback_enabled = self.get_parameter('fallback_enabled').value

        # === Publishers & Subscribers ===
        self.sub_raw = self.create_subscription(
            String, '/jarvis/nl_raw', self.on_raw_text, 10
        )
        self.pub_intent = self.create_publisher(String, '/jarvis/intent', 10)

        # === Check Ollama availability ===
        self.ollama_available = self._check_ollama()

        self.get_logger().info("=" * 50)
        self.get_logger().info("  LLM NLP NODE INITIALIZED")
        self.get_logger().info(f"  Ollama Host: {self.ollama_host}")
        self.get_logger().info(f"  Model: {self.model}")
        self.get_logger().info(f"  Ollama Available: {self.ollama_available}")
        self.get_logger().info("=" * 50)

    def _check_ollama(self) -> bool:
        """Check if Ollama is running and model is available."""
        if not REQUESTS_AVAILABLE:
            self.get_logger().warn("requests library not available")
            return False

        try:
            resp = requests.get(f"{self.ollama_host}/api/tags", timeout=2.0)
            if resp.status_code == 200:
                models = [m['name'] for m in resp.json().get('models', [])]
                if any(self.model in m for m in models):
                    self.get_logger().info(f"Model '{self.model}' is available")
                    return True
                else:
                    self.get_logger().warn(f"Model '{self.model}' not found. Available: {models}")
                    self.get_logger().warn(f"Pull it with: ollama pull {self.model}")
                    return False
            return False
        except requests.exceptions.ConnectionError:
            self.get_logger().warn("Ollama not running. Start with: ollama serve")
            return False
        except Exception as e:
            self.get_logger().warn(f"Ollama check failed: {e}")
            return False

    def _query_llm(self, user_text: str) -> Optional[str]:
        """Send a query to Ollama and get the response."""
        if not REQUESTS_AVAILABLE or not self.ollama_available:
            return None

        url = f"{self.ollama_host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": f"{SYSTEM_PROMPT}\nUser: \"{user_text}\"",
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temp for consistent outputs
                "num_predict": 100,  # Limit output length
            }
        }

        try:
            start = time.time()
            resp = requests.post(url, json=payload, timeout=self.timeout)
            elapsed = time.time() - start

            if resp.status_code == 200:
                response_text = resp.json().get('response', '').strip()
                self.get_logger().info(f"LLM response ({elapsed:.2f}s): {response_text}")
                return response_text
            else:
                self.get_logger().warn(f"Ollama error: {resp.status_code}")
                return None
        except requests.exceptions.Timeout:
            self.get_logger().warn("LLM query timed out")
            return None
        except Exception as e:
            self.get_logger().warn(f"LLM query failed: {e}")
            return None

    def _parse_llm_response(self, response: str) -> Optional[dict]:
        """Extract JSON from LLM response."""
        if not response:
            return None

        # Try to find JSON in the response
        # Sometimes LLMs wrap JSON in markdown code blocks
        json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if json_match:
            try:
                intent = json.loads(json_match.group())
                # Validate the intent has required fields
                if 'action' in intent:
                    return intent
            except json.JSONDecodeError:
                pass

        return None

    def _fallback_parse(self, text: str) -> dict:
        """Simple rule-based fallback when LLM is unavailable."""
        text = text.lower().strip()

        # Remove wake words
        text = re.sub(r'^(hey\s+)?(jarvis|robot)[,\s]*', '', text)

        if any(word in text for word in ['stop', 'halt', 'freeze']):
            return {"action": "stop"}

        # Extract duration
        dur_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:seconds?)?', text)
        duration = float(dur_match.group(1)) if dur_match else 1.0

        if 'forward' in text or 'ahead' in text:
            return {"action": "move", "direction": "forward", "duration": duration}
        if 'back' in text:
            return {"action": "move", "direction": "back", "duration": duration}
        if 'left' in text and ('turn' in text or 'rotate' in text):
            return {"action": "turn", "direction": "left", "duration": duration}
        if 'right' in text and ('turn' in text or 'rotate' in text):
            return {"action": "turn", "direction": "right", "duration": duration}
        if 'circle' in text:
            return {"action": "circle", "direction": "left", "duration": 3.0}

        return {"action": "say", "text": f"I didn't understand: {text}"}

    def on_raw_text(self, msg: String):
        """Process raw text through LLM and emit structured intent."""
        raw = msg.data.strip()
        if not raw:
            return

        self.get_logger().info(f"Processing: '{raw}'")

        intent = None

        # Try LLM first
        if self.ollama_available:
            response = self._query_llm(raw)
            intent = self._parse_llm_response(response)

        # Fallback to rule-based if LLM failed
        if intent is None and self.fallback_enabled:
            self.get_logger().info("Using fallback parser")
            intent = self._fallback_parse(raw)

        if intent:
            self._publish_intent(intent)
        else:
            self.get_logger().error("Failed to parse command")

    def _publish_intent(self, intent: dict):
        """Publish the intent to the agent."""
        intent_json = json.dumps(intent)
        self.pub_intent.publish(String(data=intent_json))
        self.get_logger().info(f"Published: {intent_json}")


def main():
    rclpy.init()
    node = LlmNlpNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
