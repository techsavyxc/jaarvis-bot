#!/usr/bin/env python3
"""
Launch RPLIDAR A1 + Intel RealSense drivers and open RViz2.

Usage:
    ros2 launch jarvis_agent sensors.launch.py
    ros2 launch jarvis_agent sensors.launch.py rviz:=false
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import os


RVIZ_CONFIG = os.path.join(
    os.path.dirname(__file__), '..', 'config', 'sensors.rviz'
)


def generate_launch_description():
    rviz_arg = DeclareLaunchArgument(
        'rviz', default_value='true',
        description='Launch RViz2 for visualization'
    )

    lidar = Node(
        package='rplidar_ros',
        executable='rplidar_node',
        name='rplidar',
        output='screen',
        parameters=[{
            'serial_port': '/dev/ttyUSB0',
            'serial_baudrate': 115200,
            'frame_id': 'laser',
            'angle_compensate': True,
            'scan_mode': 'Standard',
        }]
    )

    realsense = Node(
        package='realsense2_camera',
        executable='realsense2_camera_node',
        name='realsense',
        output='screen',
        parameters=[{
            'enable_color': True,
            'enable_depth': True,
            'enable_pointcloud': True,
            'pointcloud.enable': True,
            'align_depth.enable': True,
        }]
    )

    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        condition=IfCondition(LaunchConfiguration('rviz')),
        arguments=['-d', RVIZ_CONFIG] if os.path.isfile(RVIZ_CONFIG) else [],
    )

    return LaunchDescription([
        LogInfo(msg="Starting RPLIDAR A1 + RealSense sensors..."),
        rviz_arg,
        lidar,
        realsense,
        rviz,
    ])
