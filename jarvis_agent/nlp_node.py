#!/usr/bin/env python3
"""
NLP Node - rule-based baseline NLU.

The parsing logic lives in :mod:`jarvis_agent.intent_parser` so that
``llm_nlp_node`` can share the exact same rules when demo-safe mode kicks in.
"""

import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from jarvis_agent.intent_parser import clean_text, parse_command


class NlpNode(Node):
    def __init__(self):
        super().__init__('nlp_node')
        self.sub_raw = self.create_subscription(
            String, '/jarvis/nl_raw', self.on_raw_text, 10
        )
        self.pub_intent = self.create_publisher(String, '/jarvis/intent', 10)

        self.get_logger().info("=" * 50)
        self.get_logger().info("  NLP NODE - rule-based baseline")
        self.get_logger().info("=" * 50)

    def on_raw_text(self, msg: String):
        raw = msg.data.strip()
        if not raw:
            return
        text = clean_text(raw)
        self.get_logger().info(f"Received: '{raw}' -> cleaned: '{text}'")
        intent = parse_command(text)
        if intent:
            self._publish_intent(intent)
        else:
            self.get_logger().warn(f"Could not understand: '{raw}'")
            self._publish_intent({"action": "say", "text": f"Sorry, I didn't understand: {raw}"})

    def _publish_intent(self, intent: dict):
        intent_json = json.dumps(intent)
        self.pub_intent.publish(String(data=intent_json))
        self.get_logger().info(f"Published intent: {intent_json}")


def main():
    rclpy.init()
    node = NlpNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
