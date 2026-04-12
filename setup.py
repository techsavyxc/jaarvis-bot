from setuptools import setup
import os
from glob import glob

package_name = 'jarvis_agent'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        # Package index
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        # Package manifest
        ('share/' + package_name, ['package.xml']),
        # Launch files
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        # Config files (if any)
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=[
        'setuptools',
        'paho-mqtt',
        'requests',
    ],
    zip_safe=True,
    maintainer='Chris',
    maintainer_email='chris@example.com',
    description='Jarvis-Bot: An AI-powered mobile assistant robot with local LLM',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # Core nodes
            'agent_node = jarvis_agent.agent_node:main',
            'nlp_node = jarvis_agent.nlp_node:main',
            'llm_nlp_node = jarvis_agent.llm_nlp_node:main',
            'mqtt_bridge = jarvis_agent.mqtt_bridge:main',
            'telemetry_logger = jarvis_agent.telemetry_logger:main',
            'voice_node = jarvis_agent.voice_node:main',
            'motor_driver = jarvis_agent.motor_driver:main',
            'lidar_node = jarvis_agent.lidar_node:main',
        ],
    },
)
