#!/usr/bin/env python3
"""
Launch file for Jarvis simulation with rule-based NLP.
Use this for testing without Ollama.

Usage:
    ros2 launch jarvis_agent jarvis_sim.launch.py
"""

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import LogInfo


def generate_launch_description():
    return LaunchDescription([
        LogInfo(msg="=" * 60),
        LogInfo(msg="  JARVIS-BOT SIMULATION (Rule-Based NLP)"),
        LogInfo(msg="=" * 60),

        # TurtleSim - The simulated robot
        Node(
            package='turtlesim',
            executable='turtlesim_node',
            name='turtlesim',
            output='screen'
        ),

        # NLP Node - Rule-based command parsing
        Node(
            package='jarvis_agent',
            executable='nlp_node',
            name='nlp_node',
            output='screen'
        ),

        # Agent Node - Executes intents
        Node(
            package='jarvis_agent',
            executable='agent_node',
            name='jarvis_agent',
            output='screen',
            parameters=[{
                'linear_speed': 1.5,
                'angular_speed': 1.5,
                'telemetry_rate': 2.0
            }]
        ),

        # Telemetry Logger - For monitoring
        Node(
            package='jarvis_agent',
            executable='telemetry_logger',
            name='telemetry_logger',
            output='screen',
            parameters=[{'verbose': False}]
        ),
    ])
