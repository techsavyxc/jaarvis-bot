#!/usr/bin/env python3
"""
Launch file for Jarvis simulation with LOCAL LLM (Ollama).

Prerequisites:
    1. Install Ollama: curl -fsSL https://ollama.com/install.sh | sh
    2. Start Ollama: ollama serve
    3. Pull a model: ollama pull llama3.2:1b

Usage:
    ros2 launch jarvis_agent jarvis_llm.launch.py
    
Optional parameters:
    ros2 launch jarvis_agent jarvis_llm.launch.py model:=mistral
"""

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import LogInfo, DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    # Declare launch arguments
    model_arg = DeclareLaunchArgument(
        'model',
        default_value='llama3.2:1b',
        description='Ollama model to use (e.g., llama3.2:1b, mistral, phi3)'
    )

    ollama_host_arg = DeclareLaunchArgument(
        'ollama_host',
        default_value='http://localhost:11434',
        description='Ollama API host'
    )

    return LaunchDescription([
        model_arg,
        ollama_host_arg,

        LogInfo(msg="=" * 60),
        LogInfo(msg="  JARVIS-BOT SIMULATION (LLM-Powered)"),
        LogInfo(msg="=" * 60),

        # TurtleSim - The simulated robot
        Node(
            package='turtlesim',
            executable='turtlesim_node',
            name='turtlesim',
            output='screen'
        ),

        # LLM NLP Node - AI-powered command parsing
        Node(
            package='jarvis_agent',
            executable='llm_nlp_node',
            name='llm_nlp_node',
            output='screen',
            parameters=[{
                'model': LaunchConfiguration('model'),
                'ollama_host': LaunchConfiguration('ollama_host'),
                'timeout': 10.0,
                'fallback_enabled': True  # Use rule-based if LLM fails
            }]
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
