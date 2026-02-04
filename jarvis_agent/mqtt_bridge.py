#!/usr/bin/env python3
"""
MQTT Bridge - Connects ROS 2 to the Outside World
==================================================
Bridges MQTT messaging with ROS 2 topics for external control.

MQTT Topics:
    jarvis/voice    (IN)  - Raw voice/text commands from external devices
    jarvis/telemetry (OUT) - Robot telemetry JSON
    jarvis/status   (OUT) - Human-readable status messages

ROS Topics:
    /jarvis/nl_raw     (OUT) - Raw text commands to NLP node
    /jarvis/telemetry  (IN)  - Telemetry from agent
    /jarvis/status     (IN)  - Status from agent
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    print("WARNING: paho-mqtt not installed. Run: pip install paho-mqtt")


class MqttBridge(Node):
    def __init__(self):
        super().__init__('mqtt_bridge')

        # === Parameters ===
        self.declare_parameter('mqtt_host', 'localhost')
        self.declare_parameter('mqtt_port', 1883)
        self.declare_parameter('mqtt_topic_voice', 'jarvis/voice')
        self.declare_parameter('mqtt_topic_telemetry', 'jarvis/telemetry')
        self.declare_parameter('mqtt_topic_status', 'jarvis/status')

        self.mqtt_host = self.get_parameter('mqtt_host').value
        self.mqtt_port = self.get_parameter('mqtt_port').value
        self.topic_voice = self.get_parameter('mqtt_topic_voice').value
        self.topic_telemetry = self.get_parameter('mqtt_topic_telemetry').value
        self.topic_status = self.get_parameter('mqtt_topic_status').value

        # === ROS Publishers (MQTT -> ROS) ===
        self.pub_nl_raw = self.create_publisher(String, '/jarvis/nl_raw', 10)

        # === ROS Subscribers (ROS -> MQTT) ===
        self.sub_telemetry = self.create_subscription(
            String, '/jarvis/telemetry', self.on_telemetry, 10
        )
        self.sub_status = self.create_subscription(
            String, '/jarvis/status', self.on_status, 10
        )

        # === MQTT Client ===
        self.mqtt_connected = False
        if MQTT_AVAILABLE:
            self._setup_mqtt()
        else:
            self.get_logger().error("MQTT not available - bridge disabled")

        self.get_logger().info("=" * 50)
        self.get_logger().info("  MQTT BRIDGE INITIALIZED")
        self.get_logger().info(f"  MQTT Broker: {self.mqtt_host}:{self.mqtt_port}")
        self.get_logger().info(f"  Voice Topic: {self.topic_voice}")
        self.get_logger().info("=" * 50)

    def _setup_mqtt(self):
        """Initialize MQTT client and connect."""
        # Use callback_api_version for newer paho-mqtt versions
        try:
            self.client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
                client_id='jarvis-mqtt-bridge'
            )
        except TypeError:
            # Older paho-mqtt version
            self.client = mqtt.Client(client_id='jarvis-mqtt-bridge')

        self.client.on_connect = self.on_mqtt_connect
        self.client.on_disconnect = self.on_mqtt_disconnect
        self.client.on_message = self.on_mqtt_message

        try:
            self.client.connect(self.mqtt_host, self.mqtt_port, keepalive=60)
            # Non-blocking MQTT loop via timer
            self.mqtt_timer = self.create_timer(0.01, self._mqtt_loop)
        except Exception as e:
            self.get_logger().error(f"Failed to connect to MQTT broker: {e}")
            self.get_logger().info("Start Mosquitto with: mosquitto -v")

    def _mqtt_loop(self):
        """Non-blocking MQTT network loop."""
        if MQTT_AVAILABLE:
            self.client.loop(timeout=0.001)

    # =========================================================================
    # MQTT CALLBACKS
    # =========================================================================
    def on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        """Called when connected to MQTT broker."""
        if rc == 0:
            self.mqtt_connected = True
            self.get_logger().info(f"MQTT connected! Subscribing to '{self.topic_voice}'")
            client.subscribe(self.topic_voice)
        else:
            self.get_logger().error(f"MQTT connection failed with code: {rc}")

    def on_mqtt_disconnect(self, client, userdata, rc, properties=None):
        """Called when disconnected from MQTT broker."""
        self.mqtt_connected = False
        self.get_logger().warn(f"MQTT disconnected (rc={rc}). Will attempt reconnect...")

    def on_mqtt_message(self, client, userdata, msg):
        """Called when message received from MQTT."""
        try:
            text = msg.payload.decode('utf-8', errors='ignore').strip()
            if text:
                self.get_logger().info(f"MQTT -> ROS: '{text}'")
                self.pub_nl_raw.publish(String(data=text))
        except Exception as e:
            self.get_logger().error(f"Error processing MQTT message: {e}")

    # =========================================================================
    # ROS -> MQTT
    # =========================================================================
    def on_telemetry(self, msg: String):
        """Forward telemetry from ROS to MQTT."""
        if self.mqtt_connected:
            try:
                self.client.publish(self.topic_telemetry, msg.data, qos=0)
            except Exception as e:
                self.get_logger().warn(f"Failed to publish telemetry: {e}")

    def on_status(self, msg: String):
        """Forward status messages from ROS to MQTT."""
        if self.mqtt_connected:
            try:
                self.client.publish(self.topic_status, msg.data, qos=0)
            except Exception as e:
                self.get_logger().warn(f"Failed to publish status: {e}")


def main():
    rclpy.init()
    node = MqttBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
