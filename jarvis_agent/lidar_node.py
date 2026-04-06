#!/usr/bin/env python3
"""
JARVIS LiDAR Node - RPLIDAR A1 Obstacle Detection
==================================================
360° obstacle detection with safety zones and avoidance.
"""

from rplidar import RPLidar
import numpy as np
import time
import threading

try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
    from geometry_msgs.msg import Twist
    import json
    ROS_AVAILABLE = True
except:
    ROS_AVAILABLE = False
    print("ROS not available - running standalone")


class LidarScanner:
    def __init__(self, port='/dev/ttyUSB0'):
        self.port = port
        self.lidar = None
        self.is_running = False
        
        # Scan data
        self.scan_data = {}  # angle: distance (mm)
        self.zones = {
            'front': {'min': 337.5, 'max': 22.5, 'distance': float('inf')},
            'front_right': {'min': 22.5, 'max': 67.5, 'distance': float('inf')},
            'right': {'min': 67.5, 'max': 112.5, 'distance': float('inf')},
            'back_right': {'min': 112.5, 'max': 157.5, 'distance': float('inf')},
            'back': {'min': 157.5, 'max': 202.5, 'distance': float('inf')},
            'back_left': {'min': 202.5, 'max': 247.5, 'distance': float('inf')},
            'left': {'min': 247.5, 'max': 292.5, 'distance': float('inf')},
            'front_left': {'min': 292.5, 'max': 337.5, 'distance': float('inf')},
        }
        
        # Safety thresholds (in mm)
        self.DANGER_DISTANCE = 300    # 30cm - STOP!
        self.WARNING_DISTANCE = 500   # 50cm - Slow down
        self.CAUTION_DISTANCE = 800   # 80cm - Be careful
        
    def start(self):
        try:
            self.lidar = RPLidar(self.port)
            info = self.lidar.get_info()
            health = self.lidar.get_health()
            print(f"RPLIDAR Connected: {info}")
            print(f"Health: {health}")
            self.is_running = True
            
            # Start scanning thread
            self.scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
            self.scan_thread.start()
            return True
        except Exception as e:
            print(f"Failed to start RPLIDAR: {e}")
            return False
    
    def _scan_loop(self):
        try:
            for scan in self.lidar.iter_scans():
                if not self.is_running:
                    break
                
                # Store scan data
                self.scan_data = {}
                for (quality, angle, distance) in scan:
                    if quality > 0 and distance > 0:
                        self.scan_data[angle] = distance
                
                # Update zone distances
                self._update_zones()
                
        except Exception as e:
            print(f"Scan error: {e}")
            self.is_running = False
    
    def _update_zones(self):
        """Calculate minimum distance in each zone."""
        for zone_name, zone in self.zones.items():
            min_dist = float('inf')
            
            for angle, distance in self.scan_data.items():
                # Check if angle is in this zone
                if zone['min'] > zone['max']:  # Crosses 0° (front zone)
                    in_zone = angle >= zone['min'] or angle <= zone['max']
                else:
                    in_zone = zone['min'] <= angle <= zone['max']
                
                if in_zone and distance < min_dist:
                    min_dist = distance
            
            zone['distance'] = min_dist
    
    def get_zone_status(self):
        """Get status of all zones."""
        status = {}
        for zone_name, zone in self.zones.items():
            dist = zone['distance']
            if dist < self.DANGER_DISTANCE:
                level = 'DANGER'
            elif dist < self.WARNING_DISTANCE:
                level = 'WARNING'
            elif dist < self.CAUTION_DISTANCE:
                level = 'CAUTION'
            else:
                level = 'CLEAR'
            
            status[zone_name] = {
                'distance': dist if dist != float('inf') else -1,
                'level': level
            }
        return status
    
    def get_closest_obstacle(self):
        """Get the closest obstacle overall."""
        min_dist = float('inf')
        closest_zone = None
        
        for zone_name, zone in self.zones.items():
            if zone['distance'] < min_dist:
                min_dist = zone['distance']
                closest_zone = zone_name
        
        return closest_zone, min_dist
    
    def is_safe_to_move(self, direction):
        """Check if it's safe to move in a direction."""
        if direction == 'forward':
            zones_to_check = ['front', 'front_left', 'front_right']
        elif direction == 'backward':
            zones_to_check = ['back', 'back_left', 'back_right']
        elif direction == 'left':
            zones_to_check = ['left', 'front_left', 'back_left']
        elif direction == 'right':
            zones_to_check = ['right', 'front_right', 'back_right']
        else:
            return True, "Unknown direction"
        
        for zone_name in zones_to_check:
            dist = self.zones[zone_name]['distance']
            if dist < self.DANGER_DISTANCE:
                return False, f"DANGER: Obstacle {dist:.0f}mm in {zone_name}"
            elif dist < self.WARNING_DISTANCE:
                return True, f"WARNING: Obstacle {dist:.0f}mm in {zone_name}"
        
        return True, "Clear"
    
    def get_avoidance_suggestion(self):
        """Suggest which way to turn to avoid obstacles."""
        left_avg = np.mean([
            self.zones['left']['distance'],
            self.zones['front_left']['distance']
        ])
        right_avg = np.mean([
            self.zones['right']['distance'],
            self.zones['front_right']['distance']
        ])
        
        if left_avg > right_avg:
            return 'left', left_avg
        else:
            return 'right', right_avg
    
    def stop(self):
        self.is_running = False
        if self.lidar:
            try:
                self.lidar.stop()
                self.lidar.disconnect()
            except:
                pass
        print("RPLIDAR stopped")


def main_standalone():
    """Run with visualization (no ROS)."""
    import matplotlib.pyplot as plt
    
    scanner = LidarScanner('/dev/ttyUSB0')
    if not scanner.start():
        return
    
    # Setup visualization
    plt.ion()
    fig = plt.figure(figsize=(14, 6))
    
    # Radar view
    ax1 = fig.add_subplot(121, projection='polar')
    ax1.set_title("360° LIDAR View", fontsize=12, color='white')
    ax1.set_facecolor('black')
    ax1.set_ylim(0, 3000)
    
    # Zone status view
    ax2 = fig.add_subplot(122)
    ax2.set_title("Zone Status", fontsize=12)
    
    fig.patch.set_facecolor('#1a1a2e')
    
    print("\n" + "="*50)
    print("JARVIS LIDAR Obstacle Detection")
    print("="*50)
    print("Close window to stop")
    print("="*50 + "\n")
    
    try:
        while True:
            if not scanner.scan_data:
                time.sleep(0.1)
                continue
            
            # === Radar View ===
            ax1.clear()
            angles = np.radians(list(scanner.scan_data.keys()))
            distances = list(scanner.scan_data.values())
            
            # Color by distance
            colors = []
            for d in distances:
                if d < scanner.DANGER_DISTANCE:
                    colors.append('red')
                elif d < scanner.WARNING_DISTANCE:
                    colors.append('orange')
                elif d < scanner.CAUTION_DISTANCE:
                    colors.append('yellow')
                else:
                    colors.append('lime')
            
            ax1.scatter(angles, distances, s=8, c=colors)
            ax1.set_ylim(0, 3000)
            ax1.set_title("360° LIDAR View", fontsize=12, color='white')
            ax1.set_facecolor('black')
            ax1.tick_params(colors='white')
            
            # === Zone Status ===
            ax2.clear()
            status = scanner.get_zone_status()
            
            zone_names = list(status.keys())
            zone_distances = [s['distance'] if s['distance'] > 0 else 0 for s in status.values()]
            zone_colors = []
            for s in status.values():
                if s['level'] == 'DANGER':
                    zone_colors.append('red')
                elif s['level'] == 'WARNING':
                    zone_colors.append('orange')
                elif s['level'] == 'CAUTION':
                    zone_colors.append('yellow')
                else:
                    zone_colors.append('lime')
            
            bars = ax2.barh(zone_names, zone_distances, color=zone_colors)
            ax2.set_xlim(0, 2000)
            ax2.set_xlabel('Distance (mm)')
            ax2.set_title('Zone Distances', fontsize=12)
            ax2.axvline(x=scanner.DANGER_DISTANCE, color='red', linestyle='--', label='Danger')
            ax2.axvline(x=scanner.WARNING_DISTANCE, color='orange', linestyle='--', label='Warning')
            ax2.set_facecolor('#2a2a3e')
            ax2.tick_params(colors='white')
            ax2.xaxis.label.set_color('white')
            ax2.title.set_color('white')
            for label in ax2.get_yticklabels():
                label.set_color('white')
            
            # Print status
            closest_zone, closest_dist = scanner.get_closest_obstacle()
            safe, msg = scanner.is_safe_to_move('forward')
            
            # Add text status
            status_text = f"Closest: {closest_zone} @ {closest_dist:.0f}mm\n"
            status_text += f"Forward: {'SAFE' if safe else 'BLOCKED'}\n"
            if not safe:
                direction, _ = scanner.get_avoidance_suggestion()
                status_text += f"Suggestion: Turn {direction}"
            
            fig.suptitle(status_text, fontsize=10, color='cyan', y=0.02)
            
            plt.tight_layout()
            plt.pause(0.1)
            
    except KeyboardInterrupt:
        pass
    finally:
        scanner.stop()
        plt.close()


if __name__ == '__main__':
    main_standalone()
