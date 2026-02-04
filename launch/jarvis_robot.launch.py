#!/usr/bin/env python3
"""
Launch file for REAL Jarvis robot on Jetson.
Use this instead of jarvis_sim.launch.py on actual hardware.

Usage:
    ros2 launch jarvis_agent jarvis_robot.launch.py
"""

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import LogInfo


def generate_launch_description():
    return LaunchDescription([
        LogInfo(msg="=" * 60),
        LogInfo(msg="  JARVIS-BOT - REAL HARDWARE MODE"),
        LogInfo(msg="=" * 60),

        # Motor Driver - Controls real motors
        Node(
            package='jarvis_agent',
            executable='motor_driver',
            name='motor_driver',
            output='screen',
            parameters=[{
                'left_forward_pin': 11,
                'left_backward_pin': 13,
                'right_forward_pin': 15,
                'right_backward_pin': 16,
                'left_pwm_pin': 32,
                'right_pwm_pin': 33,
                'max_speed': 80,  # Limit speed for safety
                'simulation_mode': False
            }],
            remappings=[
                ('/cmd_vel', '/turtle1/cmd_vel')  # Use same topic as sim
            ]
        ),

        # NLP Node - Understands commands
        Node(
            package='jarvis_agent',
            executable='nlp_node',
            name='nlp_node',
            output='screen'
        ),

        # Agent Node - Brain
        Node(
            package='jarvis_agent',
            executable='agent_node',
            name='jarvis_agent',
            output='screen',
            parameters=[{
                'linear_speed': 1.0,  # Adjust for real robot
                'angular_speed': 1.0,
                'voice_enabled': True
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
