#!/usr/bin/env python3
"""
JARVIS Vision Node - MediaPipe + RealSense Person Detection.

Runs the pose detector in a background thread and publishes the latest
person pose to a ROS topic at a steady rate. Downstream nodes (notably
``agent_node``) subscribe to this topic to drive follow-me behaviour.

Topics
------
Publishes:
    /jarvis/vision/person  (std_msgs/String JSON)
        {
          "stamp": float,          # monotonic seconds
          "detected": bool,
          "x":  float,              # -1.0 (left)  .. 1.0 (right)
          "y":  float,              # -1.0 (up)    .. 1.0 (down)
          "distance": float,        # metres (0 if depth invalid)
          "shoulder_width_px": int,
          "follow_cmd": {"linear": float, "angular": float}
        }

The standalone matplotlib/OpenCV viewer (``main_standalone``) is kept so
you can still debug the camera on a dev machine without ROS; ``main``
prefers the ROS node when ``rclpy`` is importable.
"""

import json
import threading
import time

import numpy as np

try:
    import pyrealsense2 as rs
    REALSENSE_AVAILABLE = True
except ImportError:
    REALSENSE_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False

try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
    ROS_AVAILABLE = True
except ImportError:
    ROS_AVAILABLE = False


# ---------------------------------------------------------------------------
# PersonDetector - hardware-facing class (ROS-free, reusable)
# ---------------------------------------------------------------------------


class PersonDetector:
    def __init__(self, width: int = 640, height: int = 480, fps: int = 30):
        if not REALSENSE_AVAILABLE:
            raise RuntimeError("pyrealsense2 not installed")
        if not MEDIAPIPE_AVAILABLE:
            raise RuntimeError("mediapipe not installed")
        if not CV2_AVAILABLE:
            raise RuntimeError("opencv-python not installed")

        self.pipeline = rs.pipeline()
        self.config = rs.config()
        self.config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)
        self.config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)

        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            model_complexity=0,  # 0=lite (fastest on Jetson)
        )
        self.mp_draw = mp.solutions.drawing_utils

        # Detection state (read by ROS wrapper thread)
        self.person_detected = False
        self.person_x = 0.0
        self.person_y = 0.0
        self.person_distance = 0.0
        self.shoulder_width = 0
        self._last_stamp = 0.0

        self.width = width
        self.height = height

    # ---- RealSense lifecycle ------------------------------------------------

    def start(self):
        self.pipeline.start(self.config)

    def stop(self):
        try:
            self.pipeline.stop()
        except Exception:
            pass
        try:
            self.pose.close()
        except Exception:
            pass

    def get_frame(self):
        frames = self.pipeline.wait_for_frames()
        depth_frame = frames.get_depth_frame()
        color_frame = frames.get_color_frame()
        if not depth_frame or not color_frame:
            return None, None, None
        depth_image = np.asanyarray(depth_frame.get_data())
        color_image = np.asanyarray(color_frame.get_data())
        return color_image, depth_image, depth_frame

    # ---- Detection ---------------------------------------------------------

    def detect_person(self, color_image, depth_frame):
        rgb_image = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb_image)

        if not results.pose_landmarks:
            self.person_detected = False
            self._last_stamp = time.time()
            return None

        landmarks = results.pose_landmarks.landmark
        nose = landmarks[self.mp_pose.PoseLandmark.NOSE]
        left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER]
        right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER]

        center_x = int((left_shoulder.x + right_shoulder.x) / 2 * self.width)
        center_y = int((left_shoulder.y + right_shoulder.y) / 2 * self.height)

        self.person_x = (center_x - self.width // 2) / (self.width // 2)
        self.person_y = (center_y - self.height // 2) / (self.height // 2)

        try:
            self.person_distance = depth_frame.get_distance(center_x, center_y)
            if self.person_distance == 0:
                nose_x = int(nose.x * self.width)
                nose_y = int(nose.y * self.height)
                self.person_distance = depth_frame.get_distance(nose_x, nose_y)
        except Exception:
            self.person_distance = 0.0

        self.shoulder_width = int(abs(left_shoulder.x - right_shoulder.x) * self.width)
        self.person_detected = True
        self._last_stamp = time.time()
        return results.pose_landmarks

    def get_follow_command(self) -> tuple:
        """Velocity commands to chase the detected person.

        Returns (linear, angular) in roughly m/s and rad/s. Called by both
        the ROS node (published with each pose message) and the standalone
        viewer.
        """
        if not self.person_detected:
            return 0.0, 0.0

        # Angular — steer toward the person, with a centre deadzone.
        if abs(self.person_x) < 0.1:
            angular = 0.0
        else:
            angular = -self.person_x * 1.2

        # Linear — hold ~1m standoff.
        target = 1.0
        if self.person_distance == 0:
            linear = 0.0
        elif self.person_distance > target + 0.3:
            linear = min(0.4, (self.person_distance - target) * 0.5)
        elif self.person_distance < target - 0.3:
            linear = max(-0.3, (self.person_distance - target) * 0.5)
        else:
            linear = 0.0
        return linear, angular

    def draw_landmarks(self, image, landmarks):
        if landmarks:
            self.mp_draw.draw_landmarks(
                image,
                landmarks,
                self.mp_pose.POSE_CONNECTIONS,
                self.mp_draw.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
                self.mp_draw.DrawingSpec(color=(0, 255, 255), thickness=2),
            )


# ---------------------------------------------------------------------------
# ROS 2 wrapper
# ---------------------------------------------------------------------------

if ROS_AVAILABLE:

    class VisionNode(Node):
        """ROS 2 front-end around :class:`PersonDetector`."""

        def __init__(self):
            super().__init__('vision_node')

            self.declare_parameter('publish_rate', 10.0)
            self.declare_parameter('topic', '/jarvis/vision/person')
            self.declare_parameter('width', 640)
            self.declare_parameter('height', 480)
            self.declare_parameter('camera_fps', 30)

            rate = max(1.0, float(self.get_parameter('publish_rate').value))
            topic = self.get_parameter('topic').value
            width = int(self.get_parameter('width').value)
            height = int(self.get_parameter('height').value)
            fps = int(self.get_parameter('camera_fps').value)

            self._detector = None
            self._detector_error = None
            try:
                self._detector = PersonDetector(width=width, height=height, fps=fps)
                self._detector.start()
            except Exception as e:
                self._detector_error = str(e)
                self.get_logger().error(
                    f"Vision hardware unavailable ({e}); node will publish "
                    f"'detected=false' heartbeats so downstream follow-me stays quiet."
                )

            self.pub = self.create_publisher(String, topic, 10)

            # Scan loop on a background thread so MediaPipe doesn't stall the executor.
            self._running = True
            self._scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
            self._scan_thread.start()

            self.timer = self.create_timer(1.0 / rate, self._publish_state)
            self.get_logger().info(
                f"VisionNode publishing on {topic} at {rate:.1f} Hz"
            )

        # ---- Scanning thread -------------------------------------------------

        def _scan_loop(self):
            if self._detector is None:
                return
            while self._running:
                try:
                    color, _depth, depth_frame = self._detector.get_frame()
                    if color is None:
                        continue
                    self._detector.detect_person(color, depth_frame)
                except Exception as e:
                    self.get_logger().warn(f"Vision scan error: {e}")
                    time.sleep(0.1)

        # ---- Publish ---------------------------------------------------------

        def _publish_state(self):
            if self._detector is None:
                payload = {
                    "stamp": time.time(),
                    "detected": False,
                    "x": 0.0, "y": 0.0, "distance": 0.0,
                    "shoulder_width_px": 0,
                    "follow_cmd": {"linear": 0.0, "angular": 0.0},
                    "error": self._detector_error or "detector unavailable",
                }
                self.pub.publish(String(data=json.dumps(payload)))
                return

            linear, angular = self._detector.get_follow_command()
            payload = {
                "stamp": self._detector._last_stamp,
                "detected": bool(self._detector.person_detected),
                "x": float(self._detector.person_x),
                "y": float(self._detector.person_y),
                "distance": float(self._detector.person_distance),
                "shoulder_width_px": int(self._detector.shoulder_width),
                "follow_cmd": {"linear": float(linear), "angular": float(angular)},
            }
            self.pub.publish(String(data=json.dumps(payload)))

        # ---- Shutdown --------------------------------------------------------

        def destroy(self):
            self._running = False
            if self._detector is not None:
                self._detector.stop()
            super().destroy_node()


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def main():
    """Prefer ROS node; fall back to standalone viewer on dev machines."""
    if not ROS_AVAILABLE:
        print("rclpy not available; launching standalone viewer.")
        main_standalone()
        return

    rclpy.init()
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy()
        rclpy.shutdown()


def main_standalone():
    """Interactive OpenCV viewer — no ROS, for camera bring-up/debugging."""
    if not (REALSENSE_AVAILABLE and CV2_AVAILABLE and MEDIAPIPE_AVAILABLE):
        print("Vision dependencies missing; cannot run standalone viewer.")
        return

    detector = PersonDetector()
    detector.start()
    print("=" * 50)
    print("JARVIS Vision System - MediaPipe Edition")
    print("=" * 50)
    print("Controls: F = toggle follow-mode preview | Q = quit")
    print("=" * 50)

    follow_mode = False
    fps_time = time.time()

    try:
        while True:
            color, depth_image, depth_frame = detector.get_frame()
            if color is None:
                continue
            fps = 1.0 / max(1e-6, time.time() - fps_time)
            fps_time = time.time()

            landmarks = detector.detect_person(color, depth_frame)
            if landmarks:
                detector.draw_landmarks(color, landmarks)
                cv2.rectangle(color, (5, 5), (250, 100), (0, 0, 0), -1)
                cv2.rectangle(color, (5, 5), (250, 100), (0, 255, 0), 2)
                cv2.putText(color, f"Dist: {detector.person_distance:.2f}m",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.putText(color, f"X: {detector.person_x:.2f}",
                            (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.putText(color, f"Y: {detector.person_y:.2f}",
                            (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            label = "FOLLOW MODE: ON" if follow_mode else "FOLLOW MODE: OFF"
            colour = (0, 255, 0) if follow_mode else (0, 165, 255)
            cv2.putText(color, label, (10, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2)
            if follow_mode and detector.person_detected:
                lin, ang = detector.get_follow_command()
                cv2.putText(color, f"Cmd: L={lin:.2f} A={ang:.2f}",
                            (10, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)

            cv2.putText(color, f"FPS: {fps:.1f}", (550, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            cv2.imshow('JARVIS Vision', color)
            depth_colormap = cv2.applyColorMap(
                cv2.convertScaleAbs(depth_image, alpha=0.03), cv2.COLORMAP_JET,
            )
            cv2.imshow('Depth Map', depth_colormap)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            if key == ord('f'):
                follow_mode = not follow_mode
                print(f"Follow mode: {'ON' if follow_mode else 'OFF'}")
    finally:
        detector.stop()
        cv2.destroyAllWindows()
        print("Vision node stopped.")


if __name__ == '__main__':
    main()
