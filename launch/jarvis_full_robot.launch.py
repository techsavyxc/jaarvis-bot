#!/usr/bin/env python3
"""
FULL Jarvis robot with voice control.

Usage:
    ros2 launch jarvis_agent jarvis_full_robot.launch.py
"""

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import LogInfo


def generate_launch_description():
    return LaunchDescription([
        LogInfo(msg="=" * 60),
        LogInfo(msg="  JARVIS-BOT - FULL ROBOT WITH VOICE"),
        LogInfo(msg="=" * 60),

        # LIDAR Obstacle Detection (publishes /jarvis/lidar/zones)
        Node(
            package='jarvis_agent',
            executable='lidar_node',
            name='lidar_node',
            output='screen',
            parameters=[{
                'port': '/dev/ttyUSB0',
                'publish_rate': 10.0,
            }]
        ),

        # Motor Driver (subscribes to /jarvis/lidar/zones for safety veto)
        Node(
            package='jarvis_agent',
            executable='motor_driver',
            name='motor_driver',
            output='screen',
            parameters=[{
                'simulation_mode': False,
                'safety_enabled': True,
            }],
            remappings=[('/cmd_vel', '/turtle1/cmd_vel')]
        ),

        # NLP Node
        Node(
            package='jarvis_agent',
            executable='nlp_node',
            name='nlp_node',
            output='screen'
        ),

        # Agent Node
        Node(
            package='jarvis_agent',
            executable='agent_node',
            name='jarvis_agent',
            output='screen',
            parameters=[{
                'linear_speed': 1.0,
                'angular_speed': 1.0,
                'voice_enabled': True
            }]
        ),

        # Voice Node - Listens to microphone
        Node(
            package='jarvis_agent',
            executable='voice_node',
            name='voice_node',
            output='screen',
            parameters=[{
                'model_path': '/home/cj/vosk-model',
                'always_listen': True
            }]
        ),

        # Vision Node (publishes /jarvis/vision/person; feeds follow-me)
        Node(
            package='jarvis_agent',
            executable='vision_node',
            name='vision_node',
            output='screen',
            parameters=[{
                'publish_rate': 10.0,
            }]
        ),

        # Telemetry Logger
        Node(
            package='jarvis_agent',
            executable='telemetry_logger',
            name='telemetry_logger',
            output='screen'
        ),
    ])
