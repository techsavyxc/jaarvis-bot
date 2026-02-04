#!/usr/bin/env python3
"""
Jarvis Voice Input Node
=======================
Listens to your microphone and converts speech to text.
Sends commands to Jarvis when you speak!

Usage:
    ros2 run jarvis_agent voice_node

Say things like:
    "Hey Jarvis move forward"
    "Dance"
    "Be pirate"
    "How are you"
"""

import json
import queue
import sys

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

try:
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except:
    AUDIO_AVAILABLE = False
    print("WARNING: sounddevice not available")

try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except:
    VOSK_AVAILABLE = False
    print("WARNING: vosk not available")


class VoiceNode(Node):
    def __init__(self):
        super().__init__('voice_node')
        
        # Publisher
        self.pub_nl = self.create_publisher(String, '/jarvis/nl_raw', 10)
        
        # Audio queue
        self.audio_queue = queue.Queue()
        
        # Parameters
        self.declare_parameter('model_path', '/home/chris/vosk-model')
        self.declare_parameter('sample_rate', 16000)
        self.declare_parameter('wake_word', 'jarvis')
        self.declare_parameter('always_listen', True)  # If False, needs wake word
        
        self.model_path = self.get_parameter('model_path').value
        self.sample_rate = self.get_parameter('sample_rate').value
        self.wake_word = self.get_parameter('wake_word').value
        self.always_listen = self.get_parameter('always_listen').value
        
        # Load model
        if VOSK_AVAILABLE:
            try:
                self.get_logger().info(f"Loading voice model from {self.model_path}...")
                self.model = Model(self.model_path)
                self.recognizer = KaldiRecognizer(self.model, self.sample_rate)
                self.get_logger().info("Voice model loaded!")
            except Exception as e:
                self.get_logger().error(f"Failed to load voice model: {e}")
                self.model = None
        else:
            self.model = None
        
        self.get_logger().info("=" * 50)
        self.get_logger().info("  JARVIS VOICE INPUT NODE")
        self.get_logger().info("  Speak commands to control Jarvis!")
        self.get_logger().info("=" * 50)

    def audio_callback(self, indata, frames, time, status):
        """Called for each audio block."""
        if status:
            self.get_logger().warn(f"Audio status: {status}")
        self.audio_queue.put(bytes(indata))

    def run(self):
        """Main loop - listen and recognize speech."""
        if not AUDIO_AVAILABLE or not VOSK_AVAILABLE or not self.model:
            self.get_logger().error("Voice recognition not available!")
            self.get_logger().error("Make sure vosk and sounddevice are installed.")
            self.get_logger().error("And the model exists at: " + self.model_path)
            return
        
        try:
            # List audio devices
            self.get_logger().info("Available audio devices:")
            self.get_logger().info(str(sd.query_devices()))
            
            # Start listening
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=8000,
                dtype='int16',
                channels=1,
                callback=self.audio_callback
            ):
                self.get_logger().info("")
                self.get_logger().info("🎤 LISTENING... Speak now!")
                self.get_logger().info("   Say: 'move forward', 'dance', 'be pirate', etc.")
                self.get_logger().info("")
                
                while rclpy.ok():
                    data = self.audio_queue.get()
                    
                    if self.recognizer.AcceptWaveform(data):
                        result = json.loads(self.recognizer.Result())
                        text = result.get('text', '').strip()
                        
                        if text:
                            self.get_logger().info(f"🗣️  Heard: '{text}'")
                            self.process_command(text)
                    
                    # Process ROS callbacks
                    rclpy.spin_once(self, timeout_sec=0)
                    
        except KeyboardInterrupt:
            self.get_logger().info("Voice node stopped.")
        except Exception as e:
            self.get_logger().error(f"Audio error: {e}")
            self.get_logger().error("Make sure a microphone is connected!")

    def process_command(self, text: str):
        """Process recognized speech and send to Jarvis."""
        text = text.lower().strip()
        
        # Check for wake word if required
        if not self.always_listen:
            if self.wake_word not in text:
                return
        
        # Send to Jarvis NLP
        self.get_logger().info(f"📤 Sending to Jarvis: '{text}'")
        self.pub_nl.publish(String(data=text))


def main():
    rclpy.init()
    node = VoiceNode()
    
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
