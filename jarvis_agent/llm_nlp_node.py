#!/usr/bin/env python3
"""
LLM NLP Node — AI-powered NLU with grammar-constrained outputs.

Pipeline
--------
1. Receive raw text on /jarvis/nl_raw.
2. Query Ollama with ``format="json"`` plus an auto-generated SYSTEM_PROMPT
   built from :mod:`jarvis_agent.action_registry`.
3. Parse + validate the response against the registry's JSON schema. An
   invalid (or missing, or malformed) response is treated as an LLM
   failure.
4. On failure, fall back to the shared rule-based parser so the user
   still gets a sensible intent.

Why grammar constraints?
    The prior prompt only described 5 actions and used a fragile
    ``\\{[^}]+\\}`` regex to extract JSON. Any phrase outside that
    handful was either silently rejected or matched by the lossy fallback.
    This version advertises every action the agent supports, refuses
    anything off-menu, and guarantees valid JSON via Ollama's structured
    output mode.

Requirements:
    ollama >= 0.1.14 for ``format: "json"`` support.
"""

import json
import time
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

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
        self.declare_parameter('fallback_enabled', True)

        self.ollama_host = self.get_parameter('ollama_host').value
        self.model = self.get_parameter('model').value
        self.timeout = float(self.get_parameter('timeout').value)
        self.fallback_enabled = bool(self.get_parameter('fallback_enabled').value)

        self.sub_raw = self.create_subscription(
            String, '/jarvis/nl_raw', self.on_raw_text, 10
        )
        self.pub_intent = self.create_publisher(String, '/jarvis/intent', 10)

        self.ollama_available = self._check_ollama()

        self.get_logger().info("=" * 50)
        self.get_logger().info("  LLM NLP NODE (grammar-constrained)")
        self.get_logger().info(f"  Ollama Host:      {self.ollama_host}")
        self.get_logger().info(f"  Model:            {self.model}")
        self.get_logger().info(f"  Ollama Available: {self.ollama_available}")
        self.get_logger().info(f"  Registered actions: {len(action_names())}")
        self.get_logger().info("=" * 50)

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
            # Ollama's structured-output mode: forces valid JSON.
            "format": "json",
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
            # Ollama in format=json SHOULD never emit invalid JSON, but
            # belt-and-braces in case an older server is in use.
            self.get_logger().warn("LLM returned non-JSON despite format=json")
            return None
        if not validate_intent(intent):
            self.get_logger().warn(
                f"LLM intent failed schema validation: {intent}"
            )
            return None
        return intent

    # ----- Fallback ---------------------------------------------------------

    def _fallback(self, text: str) -> Optional[dict]:
        """Rule-based parser covering every registered action."""
        try:
            # Importing here keeps the module optional for non-ROS testing.
            from jarvis_agent.nlp_node import NlpNode  # type: ignore

            # NlpNode's parser is an instance method — we don't want to
            # spin up a full node just to parse one sentence, so we call
            # its pure helpers via a dummy binding.
            parser = NlpNode.__new__(NlpNode)  # type: ignore[misc]
            return parser._parse_command(parser._clean_text(text))  # type: ignore[attr-defined]
        except Exception as e:
            self.get_logger().warn(f"Fallback parser failed: {e}")
            return None

    # ----- Dispatch ---------------------------------------------------------

    def on_raw_text(self, msg: String):
        raw = msg.data.strip()
        if not raw:
            return
        self.get_logger().info(f"Processing: '{raw}'")

        intent: Optional[dict] = None

        if self.ollama_available:
            response = self._query_llm(raw)
            intent = self._parse_and_validate(response)

        if intent is None and self.fallback_enabled:
            self.get_logger().info("Using fallback parser")
            intent = self._fallback(raw)

        if intent is None:
            self.get_logger().error(f"Failed to parse command: {raw!r}")
            intent = {
                "action": "say",
                "text": f"Sorry, I didn't understand: {raw}",
            }

        self._publish_intent(intent)

    def _publish_intent(self, intent: dict):
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
