#!/usr/bin/env python3
"""
LLM NLP Node - AI-Powered Natural Language Understanding
=========================================================
Uses a local LLM (via Ollama) to translate natural human language
into structured robot intents, with a **demo-safe fallback** that
bypasses Ollama entirely when the demo would otherwise break.

Topics
------
Subscribes:
    /jarvis/nl_raw     (String)  Raw user utterance.
    /jarvis/demo_safe  (Bool)    Runtime kill-switch for demo-safe mode.

Publishes:
    /jarvis/intent     (String)  JSON intent consumed by agent_node.
    /jarvis/status     (String)  Human-readable mode/status messages.

Demo-safe mode
--------------
When ``demo_safe_mode`` is True (either set at launch or toggled at runtime
via /jarvis/demo_safe), the node SKIPS Ollama entirely and routes user text
through the shared rule-based parser. This guarantees low-latency,
deterministic behavior during a live demo even if the LLM server has
crashed or is swapping.

The node also runs an auto-engage watchdog: after
``failure_threshold`` consecutive LLM failures (timeouts, connection
errors, or malformed outputs), demo-safe mode is enabled automatically
and the robot announces "Switching to offline mode" so judges hear why
things just got snappier.
"""

import json
import re
import time
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

from jarvis_agent.intent_parser import (
    canned_fallback,
    clean_text,
    parse_command,
)

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# =============================================================================
# SYSTEM PROMPT
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

Now respond ONLY with JSON for this command:"""


class LlmNlpNode(Node):
    def __init__(self):
        super().__init__('llm_nlp_node')

        # === Parameters ===
        self.declare_parameter('ollama_host', 'http://localhost:11434')
        self.declare_parameter('model', 'llama3.2:1b')
        self.declare_parameter('timeout', 10.0)
        self.declare_parameter('demo_safe_mode', False)
        self.declare_parameter('failure_threshold', 3)
        self.declare_parameter('demo_safe_timeout', 2.0)

        self.ollama_host = self.get_parameter('ollama_host').value
        self.model = self.get_parameter('model').value
        self.timeout = float(self.get_parameter('timeout').value)
        self.demo_safe_mode = bool(self.get_parameter('demo_safe_mode').value)
        self.failure_threshold = int(self.get_parameter('failure_threshold').value)
        self.demo_safe_timeout = float(self.get_parameter('demo_safe_timeout').value)

        # === Runtime state ===
        self._consecutive_failures = 0
        self._auto_engaged = False  # True if demo-safe was auto-tripped

        # === Publishers & Subscribers ===
        self.sub_raw = self.create_subscription(
            String, '/jarvis/nl_raw', self.on_raw_text, 10
        )
        self.sub_toggle = self.create_subscription(
            Bool, '/jarvis/demo_safe', self._on_demo_safe_toggle, 10
        )
        self.pub_intent = self.create_publisher(String, '/jarvis/intent', 10)
        self.pub_status = self.create_publisher(String, '/jarvis/status', 10)

        # === Check Ollama availability (only if not already in demo-safe) ===
        if self.demo_safe_mode:
            self.ollama_available = False
        else:
            self.ollama_available = self._check_ollama()

        self.get_logger().info("=" * 50)
        self.get_logger().info("  LLM NLP NODE INITIALIZED")
        self.get_logger().info(f"  Ollama Host:       {self.ollama_host}")
        self.get_logger().info(f"  Model:             {self.model}")
        self.get_logger().info(f"  Ollama Available:  {self.ollama_available}")
        self.get_logger().info(f"  Demo-safe mode:    {self.demo_safe_mode}")
        self.get_logger().info(f"  Failure threshold: {self.failure_threshold}")
        self.get_logger().info("=" * 50)

        self._publish_status(
            f"llm_nlp_node ready (demo_safe={self.demo_safe_mode}, "
            f"ollama={self.ollama_available})"
        )

    # ------------------------------------------------------------------ Ollama

    def _check_ollama(self) -> bool:
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
                self.get_logger().warn(
                    f"Model '{self.model}' not found. Available: {models}. "
                    f"Pull it with: ollama pull {self.model}"
                )
                return False
            return False
        except requests.exceptions.ConnectionError:
            self.get_logger().warn("Ollama not running. Start with: ollama serve")
            return False
        except Exception as e:
            self.get_logger().warn(f"Ollama check failed: {e}")
            return False

    def _query_llm(self, user_text: str) -> Optional[str]:
        if not REQUESTS_AVAILABLE or not self.ollama_available:
            return None

        url = f"{self.ollama_host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": f"{SYSTEM_PROMPT}\nUser: \"{user_text}\"",
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 100,
            },
        }
        try:
            start = time.time()
            resp = requests.post(url, json=payload, timeout=self.timeout)
            elapsed = time.time() - start
            if resp.status_code == 200:
                response_text = resp.json().get('response', '').strip()
                self.get_logger().info(f"LLM response ({elapsed:.2f}s): {response_text}")
                return response_text
            self.get_logger().warn(f"Ollama error: {resp.status_code}")
            return None
        except requests.exceptions.Timeout:
            self.get_logger().warn("LLM query timed out")
            return None
        except Exception as e:
            self.get_logger().warn(f"LLM query failed: {e}")
            return None

    def _parse_llm_response(self, response: Optional[str]) -> Optional[dict]:
        if not response:
            return None
        json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if json_match:
            try:
                intent = json.loads(json_match.group())
                if 'action' in intent:
                    return intent
            except json.JSONDecodeError:
                pass
        return None

    # ------------------------------------------------------------- Demo-safe

    def _on_demo_safe_toggle(self, msg: Bool):
        """Handle runtime toggle of demo-safe mode via topic."""
        self._set_demo_safe(bool(msg.data), reason="manual toggle")

    def _set_demo_safe(self, enabled: bool, reason: str = ""):
        if enabled == self.demo_safe_mode:
            return  # no-op
        self.demo_safe_mode = enabled
        self._consecutive_failures = 0
        if enabled:
            self._auto_engaged = reason.startswith("watchdog")
            msg = f"Demo-safe mode ENABLED ({reason})"
            self.get_logger().warn(msg)
            self._publish_status(msg)
            # Announce via intent so TTS speaks it.
            self._publish_intent(
                {"action": "say", "text": "Switching to offline mode."}
            )
        else:
            self._auto_engaged = False
            msg = f"Demo-safe mode DISABLED ({reason})"
            self.get_logger().info(msg)
            self._publish_status(msg)
            # Re-probe Ollama when coming back online.
            self.ollama_available = self._check_ollama()

    def _record_failure(self):
        """Increment failure counter; auto-engage demo-safe if threshold hit."""
        self._consecutive_failures += 1
        self.get_logger().warn(
            f"LLM failure {self._consecutive_failures}/{self.failure_threshold}"
        )
        if (
            self._consecutive_failures >= self.failure_threshold
            and not self.demo_safe_mode
        ):
            self._set_demo_safe(
                True,
                reason=f"watchdog: {self._consecutive_failures} consecutive failures",
            )

    def _record_success(self):
        if self._consecutive_failures:
            self.get_logger().info("LLM recovered; resetting failure counter.")
        self._consecutive_failures = 0

    # ------------------------------------------------------------- Dispatch

    def on_raw_text(self, msg: String):
        raw = msg.data.strip()
        if not raw:
            return

        self.get_logger().info(f"Processing: '{raw}' (demo_safe={self.demo_safe_mode})")

        intent: Optional[dict] = None

        # Demo-safe path: skip Ollama entirely.
        if self.demo_safe_mode or not self.ollama_available:
            intent = parse_command(clean_text(raw))
        else:
            response = self._query_llm(raw)
            intent = self._parse_llm_response(response)
            if intent is None:
                self._record_failure()
                # Fall through to rule-based parser so the user still gets a reply.
                intent = parse_command(clean_text(raw))
            else:
                self._record_success()

        # Last-ditch canned reply so the robot is NEVER silent on stage.
        if intent is None:
            intent = canned_fallback(raw)

        self._publish_intent(intent)

    # ---------------------------------------------------------------- Publish

    def _publish_intent(self, intent: dict):
        intent_json = json.dumps(intent)
        self.pub_intent.publish(String(data=intent_json))
        self.get_logger().info(f"Published: {intent_json}")

    def _publish_status(self, text: str):
        self.pub_status.publish(String(data=text))


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
