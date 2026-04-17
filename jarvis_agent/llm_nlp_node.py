#!/usr/bin/env python3
"""
LLM NLP Node — grammar-constrained Ollama NLU with demo-safe watchdog.

Pipeline
--------
1. Receive raw text on /jarvis/nl_raw.
2. If demo-safe mode is OFF and Ollama is reachable:
   a. Query Ollama with ``format="json"`` and an auto-generated SYSTEM_PROMPT
      built from :mod:`jarvis_agent.action_registry`.
   b. Parse + validate the response against the registry's JSON schema.
3. On LLM failure (timeout, bad JSON, schema mismatch):
   - Increment failure counter.  After ``failure_threshold`` consecutive
     failures, auto-engage demo-safe mode and announce "Switching to
     offline mode" so judges understand the snappier responses.
   - Fall back to the shared rule-based parser (:mod:`jarvis_agent.intent_parser`).
4. In demo-safe mode Ollama is skipped; the rule-based parser handles
   everything with deterministic, zero-latency responses.

Topics
------
Subscribes:
    /jarvis/nl_raw     (String)  Raw user utterance.
    /jarvis/demo_safe  (Bool)    Runtime toggle for demo-safe mode.

Publishes:
    /jarvis/intent     (String)  JSON intent consumed by agent_node.
    /jarvis/status     (String)  Human-readable mode/status messages.

Requirements:
    ollama >= 0.1.14 for ``format: "json"`` support.
"""

import json
import time
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

from jarvis_agent.intent_parser import canned_fallback, clean_text, parse_command
from jarvis_agent.llm_schema import build_system_prompt, validate_intent
from jarvis_agent.action_registry import action_names

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


SYSTEM_PROMPT = build_system_prompt()


class LlmNlpNode(Node):
    def __init__(self):
        super().__init__('llm_nlp_node')

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

        self._consecutive_failures = 0
        self._auto_engaged = False

        self.sub_raw = self.create_subscription(
            String, '/jarvis/nl_raw', self.on_raw_text, 10
        )
        self.sub_toggle = self.create_subscription(
            Bool, '/jarvis/demo_safe', self._on_demo_safe_toggle, 10
        )
        self.pub_intent = self.create_publisher(String, '/jarvis/intent', 10)
        self.pub_status = self.create_publisher(String, '/jarvis/status', 10)

        if self.demo_safe_mode:
            self.ollama_available = False
        else:
            self.ollama_available = self._check_ollama()

        self.get_logger().info("=" * 50)
        self.get_logger().info("  LLM NLP NODE (grammar-constrained + demo-safe)")
        self.get_logger().info(f"  Ollama Host:       {self.ollama_host}")
        self.get_logger().info(f"  Model:             {self.model}")
        self.get_logger().info(f"  Ollama Available:  {self.ollama_available}")
        self.get_logger().info(f"  Demo-safe mode:    {self.demo_safe_mode}")
        self.get_logger().info(f"  Failure threshold: {self.failure_threshold}")
        self.get_logger().info(f"  Registered actions:{len(action_names())}")
        self.get_logger().info("=" * 50)

        self._publish_status(
            f"llm_nlp_node ready (demo_safe={self.demo_safe_mode}, "
            f"ollama={self.ollama_available}, actions={len(action_names())})"
        )

    # ----- Ollama -----------------------------------------------------------

    def _check_ollama(self) -> bool:
        if not REQUESTS_AVAILABLE:
            self.get_logger().warn("requests library not available")
            return False
        try:
            resp = requests.get(f"{self.ollama_host}/api/tags", timeout=2.0)
            if resp.status_code != 200:
                return False
            models = [m['name'] for m in resp.json().get('models', [])]
            if any(self.model in m for m in models):
                self.get_logger().info(f"Model '{self.model}' is available")
                return True
            self.get_logger().warn(
                f"Model '{self.model}' not found. Available: {models}. "
                f"Pull it with: ollama pull {self.model}"
            )
            return False
        except requests.exceptions.ConnectionError:
            self.get_logger().warn("Ollama not running. Start with: ollama serve")
            return False
        except Exception as e:
            self.get_logger().warn(f"Ollama check failed: {e}")
            return False

    def _query_llm(self, user_text: str) -> Optional[str]:
        """Ask Ollama for a JSON-only response. Returns the raw text or None."""
        if not REQUESTS_AVAILABLE or not self.ollama_available:
            return None

        url = f"{self.ollama_host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": f'{SYSTEM_PROMPT}\nUser: "{user_text}"',
            "format": "json",  # Ollama structured-output: guarantees valid JSON
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 128,
            },
        }
        try:
            start = time.time()
            resp = requests.post(url, json=payload, timeout=self.timeout)
            elapsed = time.time() - start
            if resp.status_code != 200:
                self.get_logger().warn(f"Ollama error: {resp.status_code}")
                return None
            text = resp.json().get('response', '').strip()
            self.get_logger().info(f"LLM response ({elapsed:.2f}s): {text}")
            return text
        except requests.exceptions.Timeout:
            self.get_logger().warn("LLM query timed out")
            return None
        except Exception as e:
            self.get_logger().warn(f"LLM query failed: {e}")
            return None

    def _parse_and_validate(self, response: Optional[str]) -> Optional[dict]:
        """Parse Ollama JSON output and validate it against the action registry."""
        if not response:
            return None
        try:
            intent = json.loads(response)
        except json.JSONDecodeError:
            self.get_logger().warn("LLM returned non-JSON despite format=json")
            return None
        if not validate_intent(intent):
            self.get_logger().warn(f"LLM intent failed schema validation: {intent}")
            return None
        return intent

    # ----- Demo-safe watchdog -----------------------------------------------

    def _on_demo_safe_toggle(self, msg: Bool):
        self._set_demo_safe(bool(msg.data), reason="manual toggle")

    def _set_demo_safe(self, enabled: bool, reason: str = ""):
        if enabled == self.demo_safe_mode:
            return
        self.demo_safe_mode = enabled
        self._consecutive_failures = 0
        if enabled:
            self._auto_engaged = reason.startswith("watchdog")
            msg = f"Demo-safe mode ENABLED ({reason})"
            self.get_logger().warn(msg)
            self._publish_status(msg)
            self._publish_intent({"action": "say", "text": "Switching to offline mode."})
        else:
            self._auto_engaged = False
            msg = f"Demo-safe mode DISABLED ({reason})"
            self.get_logger().info(msg)
            self._publish_status(msg)
            self.ollama_available = self._check_ollama()

    def _record_failure(self):
        self._consecutive_failures += 1
        self.get_logger().warn(
            f"LLM failure {self._consecutive_failures}/{self.failure_threshold}"
        )
        if self._consecutive_failures >= self.failure_threshold and not self.demo_safe_mode:
            self._set_demo_safe(
                True,
                reason=f"watchdog: {self._consecutive_failures} consecutive failures",
            )

    def _record_success(self):
        if self._consecutive_failures:
            self.get_logger().info("LLM recovered; resetting failure counter.")
        self._consecutive_failures = 0

    # ----- Dispatch ---------------------------------------------------------

    def on_raw_text(self, msg: String):
        raw = msg.data.strip()
        if not raw:
            return
        self.get_logger().info(f"Processing: '{raw}' (demo_safe={self.demo_safe_mode})")

        intent: Optional[dict] = None

        if self.demo_safe_mode or not self.ollama_available:
            intent = parse_command(clean_text(raw))
        else:
            response = self._query_llm(raw)
            intent = self._parse_and_validate(response)
            if intent is None:
                self._record_failure()
                intent = parse_command(clean_text(raw))
            else:
                self._record_success()

        if intent is None:
            intent = canned_fallback(raw)

        self._publish_intent(intent)

    # ----- Publish ----------------------------------------------------------

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
