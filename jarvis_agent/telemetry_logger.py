#!/usr/bin/env python3
"""
Telemetry Logger - Debug and Monitoring Tool
=============================================
Subscribes to telemetry and status topics for monitoring.

Useful for debugging and demonstrations.
"""

import json
from datetime import datetime

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class TelemetryLogger(Node):
    def __init__(self):
        super().__init__('telemetry_logger')

        self.declare_parameter('verbose', False)
        self.verbose = self.get_parameter('verbose').value

        # Subscribe to telemetry and status
        self.sub_telemetry = self.create_subscription(
            String, '/jarvis/telemetry', self.on_telemetry, 10
        )
        self.sub_status = self.create_subscription(
            String, '/jarvis/status', self.on_status, 10
        )
        self.sub_intent = self.create_subscription(
            String, '/jarvis/intent', self.on_intent, 10
        )

        self.get_logger().info("Telemetry Logger ready")
        self.get_logger().info("  Listening: /jarvis/telemetry, /jarvis/status, /jarvis/intent")

    def on_telemetry(self, msg: String):
        """Log telemetry data."""
        if self.verbose:
            try:
                data = json.loads(msg.data)
                pose = data.get('pose', {})
                if pose:
                    self.get_logger().info(
                        f"TELE | action={data.get('action', '?'):12s} | "
                        f"x={pose.get('x', 0):5.2f} y={pose.get('y', 0):5.2f} "
                        f"θ={pose.get('theta_deg', 0):6.1f}°"
                    )
            except json.JSONDecodeError:
                self.get_logger().info(f"TELE | {msg.data}")

    def on_status(self, msg: String):
        """Log status messages."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.get_logger().info(f"[{timestamp}] STATUS: {msg.data}")

    def on_intent(self, msg: String):
        """Log intents being sent to agent."""
        self.get_logger().info(f"INTENT: {msg.data}")


def main():
    rclpy.init()
    node = TelemetryLogger()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
