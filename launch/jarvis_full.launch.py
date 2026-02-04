#!/usr/bin/env python3
"""
Full system launch with MQTT bridge for external control.

Prerequisites:
    1. Install Mosquitto: sudo apt install mosquitto mosquitto-clients
    2. Start broker: mosquitto -v

Usage:
    ros2 launch jarvis_agent jarvis_full.launch.py

Test with:
    mosquitto_pub -t jarvis/voice -m "move forward 2"
    mosquitto_sub -t jarvis/status
"""

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import LogInfo, DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    use_llm_arg = DeclareLaunchArgument(
        'use_llm',
        default_value='false',
        description='Use LLM for NLP (requires Ollama)'
    )

    model_arg = DeclareLaunchArgument(
        'model',
        default_value='llama3.2:1b',
        description='Ollama model (if use_llm=true)'
    )

    return LaunchDescription([
        use_llm_arg,
        model_arg,

        LogInfo(msg="=" * 60),
        LogInfo(msg="  JARVIS-BOT FULL SYSTEM"),
        LogInfo(msg="  With MQTT Bridge for External Control"),
        LogInfo(msg="=" * 60),

        # TurtleSim
        Node(
            package='turtlesim',
            executable='turtlesim_node',
            name='turtlesim',
            output='screen'
        ),

        # MQTT Bridge
        Node(
            package='jarvis_agent',
            executable='mqtt_bridge',
            name='mqtt_bridge',
            output='screen',
            parameters=[{
                'mqtt_host': 'localhost',
                'mqtt_port': 1883,
                'mqtt_topic_voice': 'jarvis/voice',
                'mqtt_topic_telemetry': 'jarvis/telemetry',
                'mqtt_topic_status': 'jarvis/status'
            }]
        ),

        # NLP Node (rule-based - swap for llm_nlp_node if using LLM)
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
                'linear_speed': 1.5,
                'angular_speed': 1.5,
                'telemetry_rate': 2.0
            }]
        ),

        # Telemetry Logger
        Node(
            package='jarvis_agent',
            executable='telemetry_logger',
            name='telemetry_logger',
            output='screen',
            parameters=[{'verbose': False}]
        ),
    ])
