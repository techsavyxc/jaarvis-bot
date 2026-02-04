#!/usr/bin/env python3
"""
Jarvis Motor Driver Node
========================
Controls real motors on the 4WD chassis via GPIO.

This node subscribes to /cmd_vel (Twist messages) and
converts them to motor commands.

For Jetson Nano/Orin with L298N or similar motor driver:
- Uses GPIO pins for motor control
- Supports PWM for speed control

Wiring (adjust pins as needed):
    LEFT_FORWARD   = Pin 11
    LEFT_BACKWARD  = Pin 13
    RIGHT_FORWARD  = Pin 15
    RIGHT_BACKWARD = Pin 16
    LEFT_PWM       = Pin 32
    RIGHT_PWM      = Pin 33
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import String
import time

# Try to import GPIO (will only work on Jetson)
try:
    import Jetson.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("WARNING: Jetson.GPIO not available. Running in simulation mode.")


class MotorDriver(Node):
    def __init__(self):
        super().__init__('motor_driver')

        # === GPIO Pin Configuration ===
        self.declare_parameter('left_forward_pin', 11)
        self.declare_parameter('left_backward_pin', 13)
        self.declare_parameter('right_forward_pin', 15)
        self.declare_parameter('right_backward_pin', 16)
        self.declare_parameter('left_pwm_pin', 32)
        self.declare_parameter('right_pwm_pin', 33)
        self.declare_parameter('max_speed', 100)  # PWM duty cycle (0-100)
        self.declare_parameter('simulation_mode', not GPIO_AVAILABLE)

        # Get parameters
        self.LEFT_FWD = self.get_parameter('left_forward_pin').value
        self.LEFT_BWD = self.get_parameter('left_backward_pin').value
        self.RIGHT_FWD = self.get_parameter('right_forward_pin').value
        self.RIGHT_BWD = self.get_parameter('right_backward_pin').value
        self.LEFT_PWM = self.get_parameter('left_pwm_pin').value
        self.RIGHT_PWM = self.get_parameter('right_pwm_pin').value
        self.MAX_SPEED = self.get_parameter('max_speed').value
        self.simulation_mode = self.get_parameter('simulation_mode').value

        # === Setup GPIO ===
        if GPIO_AVAILABLE and not self.simulation_mode:
            self._setup_gpio()
        else:
            self.get_logger().warn("Running in SIMULATION MODE (no real motors)")

        # === Subscribers ===
        self.sub_cmd = self.create_subscription(
            Twist, '/cmd_vel', self.on_cmd_vel, 10
        )

        # === Publisher for status ===
        self.pub_status = self.create_publisher(String, '/jarvis/motor_status', 10)

        # === Safety: Stop motors if no command received ===
        self.last_cmd_time = time.time()
        self.timeout_timer = self.create_timer(0.5, self.check_timeout)

        self.get_logger().info("=" * 50)
        self.get_logger().info("  JARVIS MOTOR DRIVER INITIALIZED")
        self.get_logger().info(f"  Simulation Mode: {self.simulation_mode}")
        self.get_logger().info("=" * 50)

    def _setup_gpio(self):
        """Initialize GPIO pins."""
        GPIO.setmode(GPIO.BOARD)
        GPIO.setwarnings(False)

        # Setup direction pins
        GPIO.setup(self.LEFT_FWD, GPIO.OUT)
        GPIO.setup(self.LEFT_BWD, GPIO.OUT)
        GPIO.setup(self.RIGHT_FWD, GPIO.OUT)
        GPIO.setup(self.RIGHT_BWD, GPIO.OUT)

        # Setup PWM pins
        GPIO.setup(self.LEFT_PWM, GPIO.OUT)
        GPIO.setup(self.RIGHT_PWM, GPIO.OUT)

        # Create PWM objects (1000 Hz frequency)
        self.left_pwm = GPIO.PWM(self.LEFT_PWM, 1000)
        self.right_pwm = GPIO.PWM(self.RIGHT_PWM, 1000)
        self.left_pwm.start(0)
        self.right_pwm.start(0)

        self.get_logger().info("GPIO initialized successfully!")

    def on_cmd_vel(self, msg: Twist):
        """Handle velocity commands."""
        self.last_cmd_time = time.time()

        linear = msg.linear.x   # Forward/backward (-1 to 1 ish)
        angular = msg.angular.z  # Turn (-1 to 1 ish)

        # Convert to left/right wheel speeds (differential drive)
        left_speed = linear - angular * 0.5
        right_speed = linear + angular * 0.5

        # Normalize to -1 to 1 range
        max_val = max(abs(left_speed), abs(right_speed), 1.0)
        left_speed = left_speed / max_val
        right_speed = right_speed / max_val

        # Apply to motors
        self._set_motors(left_speed, right_speed)

    def _set_motors(self, left: float, right: float):
        """
        Set motor speeds.
        left/right: -1.0 (full reverse) to 1.0 (full forward)
        """
        if self.simulation_mode:
            self.get_logger().info(f"MOTORS: Left={left:.2f}, Right={right:.2f}")
            status = f"SIM: L={left:.2f} R={right:.2f}"
            self.pub_status.publish(String(data=status))
            return

        # Left motor
        if left > 0:
            GPIO.output(self.LEFT_FWD, GPIO.HIGH)
            GPIO.output(self.LEFT_BWD, GPIO.LOW)
            self.left_pwm.ChangeDutyCycle(abs(left) * self.MAX_SPEED)
        elif left < 0:
            GPIO.output(self.LEFT_FWD, GPIO.LOW)
            GPIO.output(self.LEFT_BWD, GPIO.HIGH)
            self.left_pwm.ChangeDutyCycle(abs(left) * self.MAX_SPEED)
        else:
            GPIO.output(self.LEFT_FWD, GPIO.LOW)
            GPIO.output(self.LEFT_BWD, GPIO.LOW)
            self.left_pwm.ChangeDutyCycle(0)

        # Right motor
        if right > 0:
            GPIO.output(self.RIGHT_FWD, GPIO.HIGH)
            GPIO.output(self.RIGHT_BWD, GPIO.LOW)
            self.right_pwm.ChangeDutyCycle(abs(right) * self.MAX_SPEED)
        elif right < 0:
            GPIO.output(self.RIGHT_FWD, GPIO.LOW)
            GPIO.output(self.RIGHT_BWD, GPIO.HIGH)
            self.right_pwm.ChangeDutyCycle(abs(right) * self.MAX_SPEED)
        else:
            GPIO.output(self.RIGHT_FWD, GPIO.LOW)
            GPIO.output(self.RIGHT_BWD, GPIO.LOW)
            self.right_pwm.ChangeDutyCycle(0)

        status = f"MOTORS: L={left:.2f} R={right:.2f}"
        self.pub_status.publish(String(data=status))

    def check_timeout(self):
        """Stop motors if no command received recently (safety feature)."""
        if time.time() - self.last_cmd_time > 1.0:
            self._set_motors(0, 0)

    def stop_motors(self):
        """Stop all motors."""
        self._set_motors(0, 0)
        if GPIO_AVAILABLE and not self.simulation_mode:
            self.left_pwm.ChangeDutyCycle(0)
            self.right_pwm.ChangeDutyCycle(0)

    def cleanup(self):
        """Clean up GPIO on shutdown."""
        self.stop_motors()
        if GPIO_AVAILABLE and not self.simulation_mode:
            self.left_pwm.stop()
            self.right_pwm.stop()
            GPIO.cleanup()
        self.get_logger().info("Motor driver shut down cleanly.")


def main():
    rclpy.init()
    node = MotorDriver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.cleanup()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
