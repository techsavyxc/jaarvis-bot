#!/usr/bin/env python3
"""JARVIS Vision Node - MediaPipe Person Detection with RealSense"""

import pyrealsense2 as rs
import numpy as np
import cv2
import mediapipe as mp
import time

class PersonDetector:
    def __init__(self):
        # RealSense setup
        self.pipeline = rs.pipeline()
        self.config = rs.config()
        self.config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
        self.config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
        
        # MediaPipe pose detection (full body tracking)
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            model_complexity=0  # 0=lite, 1=full, 2=heavy (0 is fastest for Jetson)
        )
        self.mp_draw = mp.solutions.drawing_utils
        
        # Detection state
        self.person_detected = False
        self.person_x = 0  # -1 (left) to 1 (right)
        self.person_y = 0  # -1 (up) to 1 (down)
        self.person_distance = 0
        self.shoulder_width = 0
        
        # Frame dimensions
        self.width = 640
        self.height = 480
        
    def start(self):
        self.pipeline.start(self.config)
        print("RealSense + MediaPipe started!")
        
    def stop(self):
        self.pipeline.stop()
        self.pose.close()
        
    def get_frame(self):
        frames = self.pipeline.wait_for_frames()
        depth_frame = frames.get_depth_frame()
        color_frame = frames.get_color_frame()
        
        if not depth_frame or not color_frame:
            return None, None, None
            
        depth_image = np.asanyarray(depth_frame.get_data())
        color_image = np.asanyarray(color_frame.get_data())
        
        return color_image, depth_image, depth_frame
    
    def detect_person(self, color_image, depth_frame):
        # Convert to RGB for MediaPipe
        rgb_image = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb_image)
        
        if not results.pose_landmarks:
            self.person_detected = False
            return None
        
        landmarks = results.pose_landmarks.landmark
        
        # Get key body points
        nose = landmarks[self.mp_pose.PoseLandmark.NOSE]
        left_shoulder = landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER]
        right_shoulder = landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER]
        
        # Calculate center of body (between shoulders)
        center_x = int((left_shoulder.x + right_shoulder.x) / 2 * self.width)
        center_y = int((left_shoulder.y + right_shoulder.y) / 2 * self.height)
        
        # Normalize position to -1 to 1
        self.person_x = (center_x - self.width // 2) / (self.width // 2)
        self.person_y = (center_y - self.height // 2) / (self.height // 2)
        
        # Get distance from depth
        try:
            self.person_distance = depth_frame.get_distance(center_x, center_y)
            if self.person_distance == 0:
                # Try nose position if center fails
                nose_x = int(nose.x * self.width)
                nose_y = int(nose.y * self.height)
                self.person_distance = depth_frame.get_distance(nose_x, nose_y)
        except:
            self.person_distance = 0
        
        # Calculate shoulder width (useful for size estimation)
        self.shoulder_width = abs(left_shoulder.x - right_shoulder.x) * self.width
        
        self.person_detected = True
        return results.pose_landmarks
    
    def get_follow_command(self):
        """Calculate velocity commands to follow the person."""
        if not self.person_detected:
            return 0.0, 0.0
        
        # Angular velocity - turn toward person
        # Deadzone in center to prevent jittering
        if abs(self.person_x) < 0.1:
            angular = 0.0
        else:
            angular = -self.person_x * 1.2
        
        # Linear velocity - maintain ~1m distance
        target_distance = 1.0
        
        if self.person_distance == 0:
            linear = 0.0  # No valid depth
        elif self.person_distance > target_distance + 0.3:
            linear = min(0.4, (self.person_distance - target_distance) * 0.5)
        elif self.person_distance < target_distance - 0.3:
            linear = max(-0.3, (self.person_distance - target_distance) * 0.5)
        else:
            linear = 0.0  # In sweet spot
        
        return linear, angular
    
    def draw_landmarks(self, image, landmarks):
        """Draw pose landmarks on image."""
        if landmarks:
            self.mp_draw.draw_landmarks(
                image, 
                landmarks, 
                self.mp_pose.POSE_CONNECTIONS,
                self.mp_draw.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
                self.mp_draw.DrawingSpec(color=(0, 255, 255), thickness=2)
            )


def main():
    detector = PersonDetector()
    detector.start()
    
    print("\n" + "="*50)
    print("JARVIS Vision System - MediaPipe Edition")
    print("="*50)
    print("Controls:")
    print("  F - Toggle follow mode")
    print("  Q - Quit")
    print("="*50 + "\n")
    
    follow_mode = False
    fps_time = time.time()
    fps = 0
    
    try:
        while True:
            color_image, depth_image, depth_frame = detector.get_frame()
            if color_image is None:
                continue
            
            # Calculate FPS
            fps = 1.0 / (time.time() - fps_time)
            fps_time = time.time()
            
            # Detect person
            landmarks = detector.detect_person(color_image, depth_frame)
            
            # Draw skeleton
            if landmarks:
                detector.draw_landmarks(color_image, landmarks)
                
                # Draw info box
                cv2.rectangle(color_image, (5, 5), (250, 100), (0, 0, 0), -1)
                cv2.rectangle(color_image, (5, 5), (250, 100), (0, 255, 0), 2)
                
                cv2.putText(color_image, f"Distance: {detector.person_distance:.2f}m", 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.putText(color_image, f"Position X: {detector.person_x:.2f}", 
                           (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.putText(color_image, f"Position Y: {detector.person_y:.2f}", 
                           (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            # Follow mode indicator
            if follow_mode:
                cv2.rectangle(color_image, (5, 110), (200, 160), (0, 100, 0), -1)
                cv2.putText(color_image, "FOLLOW MODE: ON", (10, 140),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                if detector.person_detected:
                    linear, angular = detector.get_follow_command()
                    cv2.putText(color_image, f"Cmd: L={linear:.2f} A={angular:.2f}", 
                               (10, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
                    
                    # Draw direction arrow
                    arrow_x = int(320 + angular * 100)
                    cv2.arrowedLine(color_image, (320, 450), (arrow_x, 400), (0, 255, 255), 3)
            else:
                cv2.putText(color_image, "FOLLOW MODE: OFF", (10, 140),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
            
            # FPS counter
            cv2.putText(color_image, f"FPS: {fps:.1f}", (550, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # Status indicator
            status = "PERSON DETECTED" if detector.person_detected else "SEARCHING..."
            color = (0, 255, 0) if detector.person_detected else (0, 0, 255)
            cv2.putText(color_image, status, (400, 470),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            
            # Display
            cv2.imshow('JARVIS Vision', color_image)
            
            # Depth visualization
            depth_colormap = cv2.applyColorMap(
                cv2.convertScaleAbs(depth_image, alpha=0.03), 
                cv2.COLORMAP_JET
            )
            cv2.imshow('Depth Map', depth_colormap)
            
            # Handle keys
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('f'):
                follow_mode = not follow_mode
                print(f"Follow mode: {'ON' if follow_mode else 'OFF'}")
                
    finally:
        detector.stop()
        cv2.destroyAllWindows()
        print("Vision node stopped.")


if __name__ == '__main__':
    main()
