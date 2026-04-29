#!/usr/bin/env python3
"""
Jarvis Motor Driver Node - Wave Rover Serial Version with LIDAR Obstacle Veto

- Subscribes to /jarvis/intent  : drive commands from agent
- Subscribes to /jarvis/lidar/zones : 8-zone obstacle classification
- Publishes  to /jarvis/motor/blocked : notifies agent when a move is vetoed
- Sends      to Wave Rover via /dev/ttyUSB1 as JSON

Obstacle veto rules (direction-aware):
  forward   -> blocks if any of [front, front_left, front_right] is DANGER
  backward  -> blocks if any of [back,  back_left,  back_right]  is DANGER
  left      -> blocks if any of [front_left,  left]              is DANGER
  right     -> blocks if any of [front_right, right]             is DANGER
  spin/dance-> blocks if ANY zone is DANGER (full sweep)
  WARNING level is logged but allowed.

Fail-OPEN behavior: if no LIDAR data has been received yet, or LIDAR data
is stale (>1.5s old), movement is allowed but a warning is logged. This
prevents a brief LIDAR hiccup from killing the demo.
"""
import json
import time
import serial
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


# Movement direction -> which zones must be clear of DANGER
DIRECTION_ZONES = {
    'forward':    ['front', 'front_left', 'front_right'],
    'backward':   ['back',  'back_left',  'back_right'],
    'back':       ['back',  'back_left',  'back_right'],
    'left':       ['front_left',  'left'],
    'turn left':  ['front_left',  'left'],
    'right':      ['front_right', 'right'],
    'turn right': ['front_right', 'right'],
}

ALL_ZONES = ['front', 'front_left', 'front_right', 'right',
             'back_right', 'back', 'back_left', 'left']


class MotorDriver(Node):
    def __init__(self):
        super().__init__('motor_driver')

        # ----- Parameters -----
        self.declare_parameter('port', '/dev/ttyUSB1')
        self.declare_parameter('baudrate', 115200)
        self.declare_parameter('simulation_mode', False)
        self.declare_parameter('obstacle_check_enabled', True)
        self.declare_parameter('zones_stale_timeout_s', 1.5)

        self.sim_mode = self.get_parameter('simulation_mode').value
        port = self.get_parameter('port').value
        baudrate = self.get_parameter('baudrate').value
        self.obstacle_check_enabled = self.get_parameter('obstacle_check_enabled').value
        self.zones_stale_timeout = self.get_parameter('zones_stale_timeout_s').value

        # ----- Serial connection to Wave Rover -----
        self.ser = None
        if not self.sim_mode:
            try:
                self.ser = serial.Serial(port, baudrate, timeout=1)
                time.sleep(2)
                self.get_logger().info(f'✅ Connected to Wave Rover on {port}')
            except Exception as e:
                self.get_logger().error(f'❌ Serial connection failed: {e}')
                self.sim_mode = True

        if self.sim_mode:
            self.get_logger().warn('⚠️  Running in simulation mode - no serial')

        # ----- LIDAR zones cache -----
        self.latest_zones = None
        self.latest_zones_time = 0.0

        # ----- Subscriptions -----
        self.intent_sub = self.create_subscription(
            String, '/jarvis/intent', self.intent_callback, 10)

        self.zones_sub = self.create_subscription(
            String, '/jarvis/lidar/zones', self.zones_callback, 10)

        # ----- Publisher: notify agent on vetoed movement -----
        self.blocked_pub = self.create_publisher(
            String, '/jarvis/motor/blocked', 10)

        veto_state = 'ENABLED' if self.obstacle_check_enabled else 'DISABLED'
        self.get_logger().info(
            f'🚗 Motor Driver ready - obstacle veto: {veto_state}'
        )
        self.get_logger().info('   Listening on /jarvis/intent')
        self.get_logger().info('   Listening on /jarvis/lidar/zones')

    # ---------- LIDAR ----------
    def zones_callback(self, msg):
        try:
            data = json.loads(msg.data)
            self.latest_zones = data.get('zones', {})
            self.latest_zones_time = time.time()
        except Exception as e:
            self.get_logger().warn(f'Bad zones msg: {e}')

    def is_path_clear(self, direction):
        """Returns (clear: bool, reason: str). Fail-OPEN on missing/stale data."""
        if not self.obstacle_check_enabled:
            return True, ''

        if direction == 'all':
            zones_to_check = ALL_ZONES
        else:
            zones_to_check = DIRECTION_ZONES.get(direction)
            if zones_to_check is None:
                return True, ''  # unknown direction, no veto

        # No data yet -> fail open with warning
        if self.latest_zones is None:
            self.get_logger().warn(
                '⚠️  No LIDAR data yet — moving without obstacle check'
            )
            return True, ''

        # Stale data -> fail open with warning
        age = time.time() - self.latest_zones_time
        if age > self.zones_stale_timeout:
            self.get_logger().warn(
                f'⚠️  LIDAR data stale ({age:.1f}s) — moving without obstacle check'
            )
            return True, ''

        # Check zones for DANGER
        blocked = []
        warnings = []
        for zone in zones_to_check:
            zd = self.latest_zones.get(zone, {})
            level = zd.get('level', 'CLEAR')
            dist = zd.get('distance_mm', -1)
            if level == 'DANGER':
                blocked.append(f'{zone}({dist:.0f}mm)')
            elif level == 'WARNING':
                warnings.append(f'{zone}({dist:.0f}mm)')

        if warnings:
            self.get_logger().info(f'⚠️  Caution — close: {", ".join(warnings)}')

        if blocked:
            return False, f'obstacle in {", ".join(blocked)}'
        return True, ''

    def publish_blocked(self, direction, reason):
        msg = String()
        msg.data = json.dumps({
            'direction': direction,
            'reason': reason,
            'stamp': time.time(),
        })
        self.blocked_pub.publish(msg)
        self.get_logger().warn(f'🛑 BLOCKED {direction}: {reason}')

    # ---------- Motor primitives ----------
    def send_command(self, L, R):
        cmd = json.dumps({"T": 1, "L": L, "R": R}) + "\n"
        if self.sim_mode:
            self.get_logger().info(f'[SIM] Motor cmd: L={L} R={R}')
            return
        try:
            self.ser.write(cmd.encode())
            self.get_logger().info(f'🚗 Motor cmd: L={L} R={R}')
        except Exception as e:
            self.get_logger().error(f'Serial write error: {e}')

    def stop(self):
        self.send_command(0, 0)

    def execute_move(self, direction, L, R, duration):
        """Veto-checked movement primitive."""
        clear, reason = self.is_path_clear(direction)
        if not clear:
            self.publish_blocked(direction, reason)
            self.stop()
            return
        self.send_command(L, R)
        time.sleep(duration)
        self.stop()

    # ---------- Intent handler ----------
    def intent_callback(self, msg):
        try:
            intent = json.loads(msg.data)
        except Exception:
            return

        action = intent.get('action', '')
        direction = intent.get('direction', '')
        duration = float(intent.get('duration', 1.0))

        self.get_logger().info(f'📨 Intent: action={action} direction={direction}')

        if action in ('move', 'turn'):
            if direction == 'forward':
                self.execute_move('forward', 0.3, 0.3, duration)
            elif direction in ('backward', 'back'):
                self.execute_move('backward', -0.3, -0.3, duration)
            elif direction in ('left', 'turn left'):
                self.execute_move('left', -0.25, 0.25, duration)
            elif direction in ('right', 'turn right'):
                self.execute_move('right', 0.25, -0.25, duration)

        elif action == 'stop':
            self.stop()

        elif action == 'dance':
            clear, reason = self.is_path_clear('all')
            if not clear:
                self.publish_blocked('dance', reason)
                return
            for _ in range(3):
                self.send_command(0.3, -0.3)
                time.sleep(0.4)
                self.send_command(-0.3, 0.3)
                time.sleep(0.4)
            self.stop()

        elif action == 'spin':
            clear, reason = self.is_path_clear('all')
            if not clear:
                self.publish_blocked('spin', reason)
                return
            self.send_command(0.3, -0.3)
            time.sleep(duration)
            self.stop()

    def destroy_node(self):
        self.stop()
        if self.ser:
            self.ser.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MotorDriver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
