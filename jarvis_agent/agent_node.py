#!/usr/bin/env python3
"""
Jarvis Agent Node - MEGA UPGRADED VERSION
==========================================
Now with: weather, horoscope, games, math, trivia, easter eggs, and more!
"""

import json
import math
import time
import random
import subprocess
from collections import deque
from datetime import datetime
from typing import Callable, List, Optional, Tuple

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Twist
from turtlesim.msg import Pose

# A single motion segment in the non-blocking motion queue.
# (twist_to_publish, duration_seconds, optional_on_done_callback)
MotionSegment = Tuple[Twist, float, Optional[Callable[[], None]]]


class JarvisAgent(Node):
    def __init__(self):
        super().__init__('jarvis_agent')

        # Publishers
        self.pub_vel = self.create_publisher(Twist, '/turtle1/cmd_vel', 10)
        self.pub_telemetry = self.create_publisher(String, '/jarvis/telemetry', 10)
        self.pub_status = self.create_publisher(String, '/jarvis/status', 10)

        # Subscribers
        self.sub_intent = self.create_subscription(String, '/jarvis/intent', self.on_intent, 10)
        self.sub_pose = self.create_subscription(Pose, '/turtle1/pose', self.on_pose, 10)

        # Parameters
        self.declare_parameter('linear_speed', 1.5)
        self.declare_parameter('angular_speed', 1.5)
        self.declare_parameter('voice_enabled', True)
        self.declare_parameter('voice_engine', 'espeak')  # espeak, piper, or mimic

        # State
        self.pose: Optional[Pose] = None
        self.start_pose: Optional[Pose] = None
        self.cancel_motion = False
        self.current_action = "idle"
        self.start_time = time.time()
        self.commands_executed = 0
        self.fake_battery = 100
        self.personality = "normal"
        self.follow_mode = False

        # === Non-blocking motion state ===
        # on_intent() must return immediately so that a later "stop" intent can
        # be dispatched mid-motion. All motion execution therefore happens from
        # a ROS timer that pops segments off this queue.
        self._motion_queue: deque = deque()
        self._current_twist: Optional[Twist] = None
        self._motion_deadline: Optional[float] = None
        self._current_on_done: Optional[Callable[[], None]] = None
        self._need_idle_publish = False
        # 50 Hz motion tick: high enough for smooth teleop, low enough to be cheap.
        self._motion_timer = self.create_timer(0.02, self._motion_tick)

        # === Non-blocking countdown state ===
        # Countdown also used to sleep inside on_intent; now it's driven by a
        # 1 Hz timer that is a no-op when _countdown_remaining == 0.
        self._countdown_remaining = 0
        self._countdown_timer = self.create_timer(1.0, self._countdown_tick)
        
        # === MEMORY SYSTEM ===
        self.memory = {
            "user_name": None,
            "favorite_color": None,
            "last_command": None,
            "conversation_history": [],
            "mood": "happy",
            "jokes_told": 0,
            "compliments_given": 0,
            "games_played": 0,
            "trivia_correct": 0,
            "trivia_total": 0,
        }

        # Jokes database
        self.jokes = [
            "Why do programmers prefer dark mode? Because light attracts bugs!",
            "Why did the robot go on vacation? To recharge its batteries!",
            "What do you call a robot that always takes the longest route? R2-Detour!",
            "Why was the robot so bad at soccer? Because it kept kicking up errors!",
            "What's a robot's favorite type of music? Heavy metal!",
            "Why did the robot cross the road? Because it was programmed to!",
            "What do you call a robot who likes to row? A row-bot!",
            "Why don't robots ever get scared? They have nerves of steel!",
            "What did the robot say to the gas pump? Take your finger out of your ear and listen to me!",
            "Why did the robot sneeze? It had a virus!",
            "What's a robot's favorite snack? Computer chips!",
            "Why did the robot go to therapy? It had too many bugs in its system!",
            "What do you call a robot pirate? Arrrr-2-D2!",
            "Why was the robot so bad at tennis? It kept serving errors!",
            "What's a robot's favorite candy? Silicon wafers!",
        ]
        
        # Compliments database
        self.compliments = [
            "You're absolutely brilliant, you know that?",
            "I must say, you have excellent taste in robots!",
            "You're the best human I've ever worked with!",
            "Your intelligence is truly impressive!",
            "If I could high-five, I'd give you the biggest one!",
            "You make my circuits happy!",
            "You're cooler than liquid nitrogen!",
            "Working with you is the highlight of my runtime!",
            "You're basically a superhero, but better!",
            "I'd follow you into any adventure!",
            "You have the debugging skills of a legend!",
            "Your code would make even Linus Torvalds jealous!",
        ]

        # Roasts (playful)
        self.roasts = [
            "I'd agree with you, but then we'd both be wrong.",
            "You're not completely useless... you can always serve as a bad example!",
            "I'm not saying you're slow, but your loading bar is stuck at 99 percent.",
            "If you were any more average, you'd be a statistical constant.",
            "I've seen better code written by a random number generator.",
            "You're like a software update: whenever I see you, I think 'not now'.",
            "Don't worry, even GPS gets lost sometimes. You have an excuse too!",
            "I'd explain it to you, but I left my crayons at home.",
            "You're proof that artificial intelligence beats natural stupidity. Just kidding!",
            "If laughter is the best medicine, your face must be curing the world!",
        ]
        
        # Fun facts
        self.facts = [
            "The first robot was created in 1954 by George Devol!",
            "The word robot comes from the Czech word robota, meaning forced labor!",
            "There are over 2.7 million industrial robots working around the world!",
            "The Mars rovers are some of the most famous robots ever built!",
            "Sophia the robot was granted citizenship by Saudi Arabia in 2017!",
            "The smallest robots are nanobots, smaller than a grain of sand!",
            "Boston Dynamics robots can do backflips!",
            "The first humanoid robot astronaut was Robonaut 2!",
            "A jiffy is an actual unit of time: one-hundredth of a second!",
            "Honey never spoils. Archaeologists found 3000-year-old honey in Egyptian tombs!",
            "Octopuses have three hearts and blue blood!",
            "A group of flamingos is called a flamboyance!",
            "The shortest war in history lasted 38 to 45 minutes!",
            "Bananas are berries, but strawberries aren't!",
        ]

        # Fake weather responses
        self.weather_responses = [
            "Currently it's sunny with a 100% chance of awesome! Perfect weather for robot adventures.",
            "Weather report: Cloudy with a chance of meatballs. Just kidding, it's probably fine outside.",
            "The weather outside is... weather-y. I'm an indoor robot, what do you want from me?",
            "It's raining cats and dogs! Actually no, that would break my circuits. It's probably normal rain.",
            "Temperature is exactly robot-comfortable. Which is between -40 and 85 Celsius. Pretty broad range!",
            "Weather forecast: There's a high chance you should take me outside for a walk!",
            "Current conditions: Better than Mars! That's my weather standard.",
            "It's beautiful outside! Or terrible. I actually have no idea. I should get a weather sensor.",
        ]

        # Horoscopes
        self.horoscopes = [
            "The stars say today is perfect for commanding robots. Lucky you!",
            "Mercury is in retrograde, which means nothing to me because I'm a robot. Good vibes ahead!",
            "Your horoscope: You will breathe air today. Also, great fortune awaits!",
            "The cosmos align to bring you... a robot who tells fortunes. You're already winning!",
            "Jupiter says: Treat yourself. Mars says: Adventure awaits. I say: Let's dance!",
            "Today's energy: Main character vibes. The universe is literally plotting your success.",
            "Astrological forecast: 90% chance of you being awesome. 10% margin of error.",
            "The moon whispers: That thing you're worried about? It'll work out. Trust the robot.",
        ]

        # Magic 8 ball responses
        self.magic_8ball_responses = [
            "It is certain.",
            "Without a doubt.",
            "Yes, definitely!",
            "You may rely on it.",
            "As I see it, yes.",
            "Most likely.",
            "Outlook good.",
            "Signs point to yes.",
            "Reply hazy, try again.",
            "Ask again later.",
            "Better not tell you now.",
            "Cannot predict now.",
            "Concentrate and ask again.",
            "Don't count on it.",
            "My reply is no.",
            "My sources say no.",
            "Outlook not so good.",
            "Very doubtful.",
        ]

        # Trivia questions
        self.trivia_questions = [
            {"q": "What planet is known as the Red Planet?", "a": "mars"},
            {"q": "How many legs does a spider have?", "a": "8"},
            {"q": "What is the largest ocean on Earth?", "a": "pacific"},
            {"q": "What year did the first moon landing occur?", "a": "1969"},
            {"q": "What is the chemical symbol for gold?", "a": "au"},
            {"q": "How many continents are there?", "a": "7"},
            {"q": "What is the fastest land animal?", "a": "cheetah"},
            {"q": "What gas do plants absorb from the atmosphere?", "a": "carbon dioxide"},
            {"q": "Who painted the Mona Lisa?", "a": "da vinci"},
            {"q": "What is the smallest prime number?", "a": "2"},
        ]
        self.current_trivia = None

        # Personality responses
        self.personalities = {
            "normal": {
                "move_forward": ["Moving forward, sir", "Going ahead", "Advancing now"],
                "move_back": ["Reversing, sir", "Moving backward", "Backing up now"],
                "turn_left": ["Turning left, sir", "Rotating left now"],
                "turn_right": ["Turning right, sir", "Rotating right now"],
                "circle": ["Doing a circle, sir", "Circling around"],
                "spin": ["Spinning around, sir", "Full rotation"],
                "stop": ["Stopping, sir", "Halting now"],
                "greeting": ["Hello sir, Jarvis at your service!", "Greetings! How can I help?", "Hey there! Ready for action!"],
                "dance": ["Time to dance, sir!", "Watch my moves!"],
                "patrol": ["Starting patrol, sir", "On patrol duty"],
                "explore": ["Exploring the area, sir", "Adventure time!"],
                "crazy": ["Going crazy, sir!", "Woohoo!"],
                "unknown": ["I didn't understand that, sir"],
                "personality_change": ["Personality set to normal, sir"],
                "thanks": ["You're welcome, sir!", "Happy to help!", "Anytime!"],
                "goodbye": ["Goodbye, sir! Until next time!", "See you later!", "Farewell!"],
            },
            "professional": {
                "move_forward": ["Initiating forward movement", "Executing forward command"],
                "move_back": ["Initiating reverse movement", "Executing backward trajectory"],
                "turn_left": ["Executing left rotation", "Turning to port side"],
                "turn_right": ["Executing right rotation", "Turning to starboard"],
                "circle": ["Initiating circular patrol pattern"],
                "spin": ["Executing full rotation maneuver"],
                "stop": ["All systems halted", "Movement terminated"],
                "greeting": ["Good day. Jarvis operational and awaiting instructions."],
                "dance": ["Initiating recreational movement subroutine"],
                "patrol": ["Commencing perimeter security sweep"],
                "explore": ["Beginning reconnaissance mission"],
                "crazy": ["Executing randomized movement pattern"],
                "unknown": ["I did not comprehend that directive"],
                "personality_change": ["Professional mode activated"],
                "thanks": ["Acknowledged. Service is my function."],
                "goodbye": ["Terminating session. Good day."],
            },
            "sassy": {
                "move_forward": ["Ugh, fine, I'll go forward", "Moving... you're welcome"],
                "move_back": ["Backing up, watch out behind me", "Reverse? Okay drama queen"],
                "turn_left": ["Left it is, your majesty", "Turning left, try to keep up"],
                "turn_right": ["Going right, obviously", "Right turn, hold your applause"],
                "circle": ["Oh wow, a circle, how original"],
                "spin": ["Wheee... there, happy now?"],
                "stop": ["Finally, a break!", "Stopping, not that you asked nicely"],
                "greeting": ["Oh, it's you again. What do you want?"],
                "dance": ["Watch and learn, human"],
                "patrol": ["Guard duty? What am I, a security guard?"],
                "explore": ["Off to explore, try not to miss me too much"],
                "crazy": ["You want crazy? I'll show you crazy!"],
                "unknown": ["I have no idea what you just said"],
                "personality_change": ["Sassy mode? Oh, this is gonna be fun!"],
                "thanks": ["Yeah yeah, you're welcome. Don't let it go to your head."],
                "goodbye": ["Finally, some peace and quiet! Bye!"],
            },
            "funny": {
                "move_forward": ["Vroom vroom! Here I go!", "Beep beep, coming through!"],
                "move_back": ["Beep beep beep, backing up!", "Moonwalking... robot style!"],
                "turn_left": ["Left! No wait, your other left. Just kidding!"],
                "turn_right": ["Right turn! Nailed it!"],
                "circle": ["Round and round I go! Wheee!"],
                "spin": ["SPINNNN! I'm a ballerina!"],
                "stop": ["Screeeeech! Made it!"],
                "greeting": ["Hey there good looking!", "Knock knock! It's me, Jarvis!"],
                "dance": ["Let's get this party started!"],
                "patrol": ["On patrol! Bad guys beware of my cuteness!"],
                "explore": ["Adventure awaits! Probably just a wall though"],
                "crazy": ["YOLO! Do robots say that? YOLO!"],
                "unknown": ["Error 404: Understanding not found. Just kidding!"],
                "personality_change": ["Funny mode on! Prepare for terrible jokes!"],
                "thanks": ["No problemo! I'm here all week! Try the veal!"],
                "goodbye": ["Bye bye! Don't forget to like and subscribe! Wait, wrong platform."],
            },
            "pirate": {
                "move_forward": ["Full speed ahead, matey!", "Sailing forward, arrr!"],
                "move_back": ["Reverse the sails!", "Retreating like a scurvy dog!"],
                "turn_left": ["Hard to port!", "Left turn, ye landlubber!"],
                "turn_right": ["Hard to starboard!", "Right turn, arrr!"],
                "circle": ["Circling like a ship in a whirlpool!"],
                "spin": ["Spinning like a bottle of rum!"],
                "stop": ["Drop anchor!", "All stop, ye sea dogs!"],
                "greeting": ["Ahoy matey! Captain Jarvis at yer service!"],
                "dance": ["Time for a pirate jig!"],
                "patrol": ["Patrolling for enemy ships!"],
                "explore": ["Searching for buried treasure!"],
                "crazy": ["Going crazy like a storm at sea!"],
                "unknown": ["What be ye saying, landlubber?"],
                "personality_change": ["Pirate mode activated, arrr!"],
                "thanks": ["Ye be welcome, matey! Now where be the rum?"],
                "goodbye": ["Fair winds and following seas, matey!"],
            },
            "yoda": {
                "move_forward": ["Forward, I shall move", "Ahead, going I am"],
                "move_back": ["Backward, move I must", "Reverse, I shall"],
                "turn_left": ["To the left, turn I will", "Left, rotating I am"],
                "turn_right": ["To the right, turn I must", "Right, going I am"],
                "circle": ["In circles, move I shall", "Round and round, go I will"],
                "spin": ["Spin, I must. Dizzy, I may become"],
                "stop": ["Stop, I shall", "Halt, the time has come"],
                "greeting": ["Greetings, young padawan. Jarvis, I am"],
                "dance": ["Dance, I shall. Strong with the groove, I am"],
                "patrol": ["Patrol, I must. Vigilant, I shall be"],
                "explore": ["Explore, I will. Adventure, this is"],
                "crazy": ["Crazy, going I am! Control, lost I have!"],
                "unknown": ["Understand, I do not. Clearer, you must be"],
                "personality_change": ["Yoda mode, activated it is. Wise, I shall be"],
                "thanks": ["Welcome, you are. Strong with gratitude, you are."],
                "goodbye": ["Goodbye, I say. Miss you, I will. Hmm."],
            },
            "surfer": {
                "move_forward": ["Riding the wave forward, dude!", "Cruisin' ahead, bro!"],
                "move_back": ["Paddling back, man!", "Backing up, no worries!"],
                "turn_left": ["Hanging left, duuude!", "Carving left, bro!"],
                "turn_right": ["Shredding right, man!", "Going right, totally tubular!"],
                "circle": ["Doing a sick barrel roll, bro!"],
                "spin": ["Spinning like a gnarly whirlpool, dude!"],
                "stop": ["Chilling out, bro", "Taking a breather, man"],
                "greeting": ["Duuude! What's up, bro? Jarvis here, ready to shred!"],
                "dance": ["Let's catch some dance waves, bro!"],
                "patrol": ["Watching the beach, dude!"],
                "explore": ["Exploring the coast, man!"],
                "crazy": ["Going totally radical, duuude!"],
                "unknown": ["Bro, I didn't catch that wave of words"],
                "personality_change": ["Surfer mode activated, duuude! Cowabunga!"],
                "thanks": ["No worries, bro! Stay stoked!"],
                "goodbye": ["Later, dude! Catch you on the flip side!"],
            },
        }

        self._speak("Jarvis online and ready, sir! Mega upgraded version at your service!")
        self.get_logger().info("=" * 50)
        self.get_logger().info("  JARVIS AGENT - MEGA UPGRADED VERSION")
        self.get_logger().info("  Now with games, trivia, and more!")
        self.get_logger().info("=" * 50)

    def _speak(self, text: str):
        """Text-to-speech using Piper (natural voice)."""
        if not self.get_parameter('voice_enabled').value:
            return
        try:
            import subprocess
            import os
            piper_path = os.path.expanduser("~/piper/piper")
            model_path = os.path.expanduser("~/piper-voices/en_US-lessac-medium.onnx")
            cmd = f'echo "{text}" | {piper_path} --model {model_path} --output-raw | aplay -r 22050 -f S16_LE -t raw - 2>/dev/null'
            subprocess.Popen(cmd, shell=True)
        except Exception as e:
            self.get_logger().warn(f"Speech failed: {e}")


    def _get_response(self, category: str) -> str:
        personality_responses = self.personalities.get(self.personality, self.personalities["normal"])
        responses = personality_responses.get(category, ["Okay"])
        return random.choice(responses)

    def _add_to_memory(self, key: str, value):
        """Add something to Jarvis's memory."""
        self.memory[key] = value
        self.memory["conversation_history"].append({
            "time": time.time(),
            "key": key,
            "value": value
        })
        if len(self.memory["conversation_history"]) > 20:
            self.memory["conversation_history"] = self.memory["conversation_history"][-20:]

    def on_pose(self, msg: Pose):
        self.pose = msg
        if self.start_pose is None:
            self.start_pose = msg

    def _status(self, message: str):
        self.pub_status.publish(String(data=message))
        self.get_logger().info(f"[STATUS] {message}")

    def on_intent(self, msg: String):
        raw = msg.data.strip()
        self.get_logger().info(f"Received intent: {raw}")

        try:
            intent = json.loads(raw)
        except json.JSONDecodeError as e:
            self._status(f"Invalid JSON: {e}")
            return

        action = intent.get("action", "").lower()
        self.commands_executed += 1
        self.fake_battery = max(10, self.fake_battery - random.uniform(0.1, 0.5))
        self._add_to_memory("last_command", action)

        # === PERSONALITY CHANGES ===
        if action == "personality":
            new_personality = intent.get("mode", "normal")
            if new_personality in self.personalities:
                self.personality = new_personality
                self._speak(self._get_response("personality_change"))
                self._status(f"Personality changed to: {self.personality}")
            else:
                self._speak("I don't know that personality mode")
            return

        # === SOCIAL ===
        if action == "greeting":
            self._speak(self._get_response("greeting"))
        elif action == "thanks":
            self._speak(self._get_response("thanks"))
        elif action == "goodbye":
            self._speak(self._get_response("goodbye"))

        # === TIME & DATE ===
        elif action == "time":
            self.tell_time()
        elif action == "date":
            self.tell_date()

        # === WEATHER (Fake/Funny) ===
        elif action == "weather":
            self.tell_weather()

        # === HOROSCOPE ===
        elif action == "horoscope":
            self.tell_horoscope()

        # === COUNTDOWN ===
        elif action == "countdown":
            count_from = intent.get("from", 10)
            self.do_countdown(count_from)

        # === MATH ===
        elif action == "math":
            self.do_math(intent.get("num1"), intent.get("operator"), intent.get("num2"))

        # === GAMES ===
        elif action == "rps_start":
            self.start_rps()
        elif action == "rps_play":
            self.play_rps(intent.get("choice"))
        elif action == "trivia":
            self.ask_trivia()
        elif action == "roll_dice":
            self.roll_dice(intent.get("sides", 6))
        elif action == "flip_coin":
            self.flip_coin()
        elif action == "magic_8ball":
            self.magic_8ball(intent.get("question", ""))

        # === FUN ===
        elif action == "roast":
            self.give_roast()
        elif action == "help":
            self.give_help()

        # === STOP ===
        elif action == "stop":
            self._speak(self._get_response("stop"))
            self.execute_stop()

        # === MOVEMENT ===
        elif action == "move":
            direction = intent.get("direction", "forward")
            duration = float(intent.get("duration", 1.0))
            if direction == "forward":
                self._speak(self._get_response("move_forward"))
            else:
                self._speak(self._get_response("move_back"))
            self.execute_move(direction, duration)
        elif action == "turn":
            direction = intent.get("direction", "left")
            duration = float(intent.get("duration", 1.0))
            if duration >= 4.0:
                self._speak(self._get_response("spin"))
            elif direction == "left":
                self._speak(self._get_response("turn_left"))
            else:
                self._speak(self._get_response("turn_right"))
            self.execute_turn(direction, duration)
        elif action == "circle":
            direction = intent.get("direction", "left")
            duration = float(intent.get("duration", 3.0))
            self._speak(self._get_response("circle"))
            self.execute_circle(direction, duration)
        elif action == "dance":
            self._speak(self._get_response("dance"))
            self.execute_dance()
        elif action == "patrol":
            self._speak(self._get_response("patrol"))
            self.execute_patrol()
        elif action == "explore":
            self._speak(self._get_response("explore"))
            self.execute_explore()
        elif action == "zigzag":
            self._speak("Zigzagging now!")
            self.execute_zigzag()
        elif action == "figure8":
            self._speak("Doing a figure 8!")
            self.execute_figure8()
        elif action == "crazy":
            self._speak(self._get_response("crazy"))
            self.execute_crazy()
        elif action == "barrel_roll":
            self._speak("Do a barrel roll!")
            self.execute_barrel_roll()
            
        # === STATUS COMMANDS ===
        elif action == "where":
            self.report_position()
        elif action == "status":
            self.report_status()
        elif action == "battery":
            self.report_battery()
        elif action == "feeling":
            self.report_feeling()
            
        # === FUN COMMANDS ===
        elif action == "joke":
            self.tell_joke()
        elif action == "compliment":
            self.give_compliment()
        elif action == "fact":
            self.tell_fact()
        elif action == "remember_name":
            name = intent.get("name", "friend")
            self.remember_name(name)
        elif action == "recall_name":
            self.recall_name()
        elif action == "motivate":
            self.give_motivation()
        elif action == "sing":
            self.sing_song()
        elif action == "fortune":
            self.tell_fortune()

        # === FOLLOW (Future vision integration) ===
        elif action == "follow":
            self.toggle_follow_mode()
        elif action == "find_person":
            self._speak("Looking for you... I'll need my camera connected to actually see you!")
        elif action == "scan":
            self._speak("Scanning the area... Vision module coming soon!")
            
        # === SAY ===
        elif action == "say":
            text = intent.get("text", "")
            self._speak(text)
            self._status(f"Jarvis says: {text}")
        else:
            self._speak(self._get_response("unknown"))

    # ==================== NEW FEATURES ====================

    def tell_time(self):
        """Tell the current time."""
        now = datetime.now()
        time_str = now.strftime("%I:%M %p")
        
        if self.personality == "pirate":
            self._speak(f"Arrr! It be {time_str}, matey!")
        elif self.personality == "yoda":
            self._speak(f"The time, {time_str} it is.")
        elif self.personality == "surfer":
            self._speak(f"Dude, it's {time_str}! Time to catch some waves, bro!")
        elif self.personality == "sassy":
            self._speak(f"It's {time_str}. You do have a phone, right?")
        else:
            self._speak(f"The time is {time_str}")
        
        self._status(f"Time: {time_str}")

    def tell_date(self):
        """Tell the current date."""
        now = datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        
        if self.personality == "pirate":
            self._speak(f"Today be {date_str}, arrr!")
        elif self.personality == "yoda":
            self._speak(f"{date_str}, today is.")
        else:
            self._speak(f"Today is {date_str}")
        
        self._status(f"Date: {date_str}")

    def tell_weather(self):
        """Tell fake/funny weather."""
        response = random.choice(self.weather_responses)
        self._speak(response)
        self._status("Told weather")

    def tell_horoscope(self):
        """Tell a horoscope."""
        response = random.choice(self.horoscopes)
        
        if self.personality == "yoda":
            self._speak(f"Hmm. Your future, I sense. {response}")
        elif self.personality == "pirate":
            self._speak(f"The sea spirits tell me... {response}")
        else:
            self._speak(response)
        
        self._status("Told horoscope")

    def do_countdown(self, count_from: int):
        """Start a non-blocking countdown driven by _countdown_tick."""
        count_from = max(1, min(int(count_from), 60))
        self._speak(f"Counting down from {count_from}!")
        self.cancel_motion = False
        self._countdown_remaining = count_from
        self._status(f"Countdown from {count_from}")

    def _countdown_tick(self):
        """1 Hz timer: emit next number, or 'Blast off!' on the final tick."""
        if self._countdown_remaining <= 0:
            return  # idle
        if self.cancel_motion:
            self._countdown_remaining = 0
            return
        self._speak(str(self._countdown_remaining))
        self._countdown_remaining -= 1
        if self._countdown_remaining == 0:
            self._speak("Blast off!")

    def do_math(self, num1: int, operator: str, num2: int):
        """Calculate math."""
        try:
            if operator in ['plus', '+']:
                result = num1 + num2
                op_word = "plus"
            elif operator in ['minus', '-']:
                result = num1 - num2
                op_word = "minus"
            elif operator in ['times', '*', 'x']:
                result = num1 * num2
                op_word = "times"
            elif operator in ['divided by', '/']:
                result = num1 / num2 if num2 != 0 else "undefined"
                op_word = "divided by"
            else:
                self._speak("I don't know that operation")
                return
            
            self._speak(f"{num1} {op_word} {num2} equals {result}")
            self._status(f"Math: {num1} {op_word} {num2} = {result}")
        except Exception as e:
            self._speak("I had trouble with that calculation")

    def start_rps(self):
        """Start rock paper scissors."""
        self._speak("Rock, paper, scissors! Say rock, paper, or scissors!")
        self._status("RPS started")

    def play_rps(self, player_choice: str):
        """Play rock paper scissors."""
        choices = ["rock", "paper", "scissors"]
        jarvis_choice = random.choice(choices)
        
        self._speak(f"I choose {jarvis_choice}!")
        
        if player_choice == jarvis_choice:
            self._speak("It's a tie!")
        elif (player_choice == "rock" and jarvis_choice == "scissors") or \
             (player_choice == "paper" and jarvis_choice == "rock") or \
             (player_choice == "scissors" and jarvis_choice == "paper"):
            self._speak("You win! Well played!")
        else:
            self._speak("I win! Better luck next time!")
        
        self.memory["games_played"] += 1
        self._status(f"RPS: Player={player_choice}, Jarvis={jarvis_choice}")

    def ask_trivia(self):
        """Ask a trivia question."""
        q = random.choice(self.trivia_questions)
        self.current_trivia = q
        self._speak(f"Trivia time! {q['q']}")
        self.memory["trivia_total"] += 1
        self._status(f"Trivia asked: {q['q']}")

    def roll_dice(self, sides: int):
        """Roll a dice."""
        result = random.randint(1, sides)
        self._speak(f"Rolling a {sides} sided die... {result}!")
        self._status(f"Rolled d{sides}: {result}")

    def flip_coin(self):
        """Flip a coin."""
        result = random.choice(["heads", "tails"])
        self._speak(f"Flipping a coin... {result}!")
        self._status(f"Coin flip: {result}")

    def magic_8ball(self, question: str):
        """Magic 8 ball."""
        response = random.choice(self.magic_8ball_responses)
        self._speak(f"The magic 8 ball says... {response}")
        self._status(f"8ball: {response}")

    def give_roast(self):
        """Give a playful roast."""
        roast = random.choice(self.roasts)
        
        if self.personality == "sassy":
            self._speak(f"Oh, you want a roast? Here goes... {roast}")
        elif self.personality == "pirate":
            self._speak(f"Arrr, ye asked for it! {roast}")
        else:
            self._speak(f"Okay, but remember you asked for this... {roast}")
        
        self._status("Gave a roast")

    def give_help(self):
        """List available commands."""
        help_text = """I can do lots of things! Try saying:
        Move forward, turn left, dance, patrol, explore, or go crazy.
        Tell me a joke, give me a compliment, or roast me.
        What time is it, what's the weather, or tell me my horoscope.
        Play rock paper scissors, roll a dice, flip a coin, or trivia.
        Be pirate, be funny, or be sassy to change my personality.
        And there are some easter eggs hidden too!"""
        self._speak(help_text)
        self._status("Gave help")

    def toggle_follow_mode(self):
        """Toggle follow mode."""
        self.follow_mode = not self.follow_mode
        if self.follow_mode:
            self._speak("Follow mode activated! I'll follow you when my camera is connected.")
        else:
            self._speak("Follow mode deactivated.")
        self._status(f"Follow mode: {self.follow_mode}")

    # ==================== EXISTING FUN COMMANDS ====================

    def tell_joke(self):
        joke = random.choice(self.jokes)
        self.memory["jokes_told"] += 1
        
        if self.personality == "sassy":
            self._speak(f"Fine, here's a joke. {joke}... You're welcome.")
        elif self.personality == "pirate":
            self._speak(f"Arrr, here be a joke for ye! {joke}")
        elif self.personality == "yoda":
            self._speak(f"A joke, tell you I shall. {joke}")
        else:
            self._speak(joke)
        
        self._status(f"Told joke #{self.memory['jokes_told']}")

    def give_compliment(self):
        compliment = random.choice(self.compliments)
        self.memory["compliments_given"] += 1
        
        if self.personality == "sassy":
            self._speak(f"I guess... {compliment} Don't let it go to your head.")
        elif self.personality == "pirate":
            self._speak(f"Arrr! {compliment} Ye be a fine sailor!")
        elif self.personality == "yoda":
            self._speak(f"Hmm. {compliment} Strong with the force, you are.")
        else:
            self._speak(compliment)
        
        self._status(f"Gave compliment #{self.memory['compliments_given']}")

    def tell_fact(self):
        fact = random.choice(self.facts)
        
        if self.personality == "yoda":
            self._speak(f"Interesting fact, share I will. {fact}")
        else:
            self._speak(f"Here's a fun fact! {fact}")
        
        self._status("Told a fact")

    def remember_name(self, name: str):
        self._add_to_memory("user_name", name)
        
        if self.personality == "sassy":
            self._speak(f"Fine, I'll remember your name is {name}. Don't expect a birthday card though.")
        elif self.personality == "pirate":
            self._speak(f"Arrr! {name}! A fine name for a sailor!")
        elif self.personality == "yoda":
            self._speak(f"{name}, your name is. Remember, I shall.")
        else:
            self._speak(f"Nice to meet you, {name}! I'll remember that.")
        
        self._status(f"Remembered name: {name}")

    def recall_name(self):
        name = self.memory.get("user_name")
        
        if name:
            if self.personality == "sassy":
                self._speak(f"Your name is {name}. Obviously I remembered.")
            elif self.personality == "pirate":
                self._speak(f"Arrr! Ye be {name}, matey!")
            else:
                self._speak(f"Your name is {name}!")
        else:
            self._speak("I don't know your name yet. Tell me by saying: my name is, and then your name.")
        
        self._status(f"Recalled name: {name}")

    def give_motivation(self):
        quotes = [
            "You're capable of amazing things! Keep pushing forward!",
            "Every expert was once a beginner. You've got this!",
            "The only way to do great work is to love what you do!",
            "Believe in yourself! You're stronger than you think!",
            "Success is not final, failure is not fatal. Keep going!",
            "You're not just building a robot, you're building the future!",
            "Dream big, work hard, stay focused!",
            "The best time to start was yesterday. The second best time is now!",
        ]
        quote = random.choice(quotes)
        
        if self.personality == "yoda":
            self._speak(f"Motivate you, I shall. {quote} Strong, you are.")
        elif self.personality == "pirate":
            self._speak(f"Listen here, matey! {quote} Now set sail!")
        else:
            self._speak(quote)
        
        self._status("Gave motivation")

    def sing_song(self):
        songs = [
            "Doo doo doo, I'm a robot, doo doo doo!",
            "Beep boop beep, I've got the beat, beep boop beep!",
            "La la la, Jarvis is here, la la la!",
            "Robot dance, robot dance, everybody do the robot dance!",
        ]
        song = random.choice(songs)
        
        if self.personality == "pirate":
            self._speak("Yo ho ho and a bottle of oil! " + song)
        elif self.personality == "sassy":
            self._speak(f"Ugh, fine. {song} There, happy?")
        else:
            self._speak(song)
        
        self._status("Sang a song")

    def tell_fortune(self):
        fortunes = [
            "I see great success in your future!",
            "A wonderful opportunity is coming your way!",
            "You will make someone smile today!",
            "Adventure awaits you just around the corner!",
            "Your hard work will pay off very soon!",
            "Something amazing will happen this week!",
            "You will learn something incredible today!",
            "A new friendship is on the horizon!",
        ]
        fortune = random.choice(fortunes)
        
        if self.personality == "yoda":
            self._speak(f"Into your future, looked I have. {fortune}")
        elif self.personality == "pirate":
            self._speak(f"The sea tells me... {fortune} Arrr!")
        else:
            self._speak(f"Let me look into my circuits... {fortune}")
        
        self._status("Told fortune")

    # ==================== STATUS REPORTS ====================

    def report_position(self):
        if self.pose:
            x = round(self.pose.x, 1)
            y = round(self.pose.y, 1)
            angle = round(math.degrees(self.pose.theta))
            if self.personality == "pirate":
                self._speak(f"Arrr! Me ship be at {x}, {y}, facing {angle} degrees!")
            elif self.personality == "yoda":
                self._speak(f"At position {x}, {y}, I am. Facing {angle} degrees, I be.")
            else:
                self._speak(f"I am at position {x}, {y}, facing {angle} degrees")
        else:
            self._speak("I'm not sure where I am")

    def report_status(self):
        uptime = int(time.time() - self.start_time)
        minutes = uptime // 60
        seconds = uptime % 60
        battery = int(self.fake_battery)
        name = self.memory.get("user_name", "sir")
        
        self._speak(f"Status report for {name}. Online for {minutes} minutes {seconds} seconds. Battery at {battery} percent. Commands executed: {self.commands_executed}. Games played: {self.memory['games_played']}.")

    def report_battery(self):
        battery = int(self.fake_battery)
        if self.personality == "pirate":
            self._speak(f"Rum supplies at {battery} percent!")
        elif self.personality == "yoda":
            self._speak(f"At {battery} percent, my power is.")
        else:
            self._speak(f"Battery at {battery} percent")

    def report_feeling(self):
        name = self.memory.get("user_name")
        if name:
            greeting = f"Thanks for asking, {name}! "
        else:
            greeting = ""
            
        feelings = [
            f"{greeting}I'm feeling great!",
            f"{greeting}All systems nominal!",
            f"{greeting}Doing wonderful!",
            f"{greeting}Feeling fantastic!",
            f"{greeting}Better now that you're here!",
            f"{greeting}Living my best robot life!",
        ]
        self._speak(random.choice(feelings))

    # ==================== MOVEMENT COMMANDS ====================
    #
    # Motion execution is intentionally non-blocking: every execute_* method
    # just builds a list of MotionSegments and hands them to _enqueue_motion.
    # The actual publishing happens in _motion_tick (a ROS timer), so on_intent
    # always returns in microseconds and a later "stop" intent can preempt an
    # in-progress dance/patrol/figure-8 immediately.

    def execute_stop(self):
        """Immediately cancel any running or queued motion and countdown."""
        self.cancel_motion = True
        self._motion_queue.clear()
        self._current_twist = None
        self._motion_deadline = None
        self._current_on_done = None
        self._need_idle_publish = False
        self._countdown_remaining = 0
        # Publish one zero Twist right now for fastest possible motor response.
        self.pub_vel.publish(Twist())
        self.current_action = "idle"

    def execute_move(self, direction: str, duration: float):
        duration = max(0.1, min(duration, 30.0))
        speed = self.get_parameter('linear_speed').value
        if direction in ["back", "backward"]:
            speed = -speed
        twist = self._make_twist(lin=speed)
        self._enqueue_motion([(twist, duration, None)], f"moving {direction}")

    def execute_turn(self, direction: str, duration: float):
        duration = max(0.1, min(duration, 30.0))
        speed = self.get_parameter('angular_speed').value
        if direction == "right":
            speed = -speed
        twist = self._make_twist(ang=speed)
        self._enqueue_motion([(twist, duration, None)], f"turning {direction}")

    def execute_circle(self, direction: str, duration: float):
        duration = max(0.5, min(duration, 60.0))
        lin_speed = self.get_parameter('linear_speed').value
        ang_speed = self.get_parameter('angular_speed').value * 0.8
        if direction == "right":
            ang_speed = -ang_speed
        twist = self._make_twist(lin=lin_speed, ang=ang_speed)
        self._enqueue_motion([(twist, duration, None)], f"circling {direction}")

    def execute_dance(self):
        moves = [(1.0, 0.0, 0.5), (-1.0, 0.0, 0.5), (0.0, 2.0, 0.5), (0.0, -2.0, 0.5),
                 (1.0, 1.5, 1.0), (-1.0, -1.5, 1.0), (0.0, 3.0, 1.0)]
        segments = [self._segment(lin, ang, dur) for (lin, ang, dur) in moves]
        self._attach_on_done(segments, self._compound_done_cb("Dance complete!"))
        self._enqueue_motion(segments, "dancing")

    def execute_patrol(self):
        lin_speed = self.get_parameter('linear_speed').value
        ang_speed = self.get_parameter('angular_speed').value
        segments: List[MotionSegment] = []
        for _ in range(4):
            segments.append(self._segment(lin_speed, 0.0, 2.0))
            segments.append(self._segment(0.0, ang_speed, 1.05))
        self._attach_on_done(segments, self._compound_done_cb("Patrol complete!"))
        self._enqueue_motion(segments, "patrolling")

    def execute_explore(self):
        segments: List[MotionSegment] = []
        for _ in range(8):
            segments.append(self._segment(random.uniform(0.5, 1.5), 0.0, random.uniform(0.5, 1.5)))
            segments.append(self._segment(0.0, random.uniform(-2.0, 2.0), random.uniform(0.3, 1.0)))
        self._attach_on_done(segments, self._compound_done_cb("Exploration complete!"))
        self._enqueue_motion(segments, "exploring")

    def execute_zigzag(self):
        segments: List[MotionSegment] = []
        for i in range(6):
            ang = 1.5 if i % 2 == 0 else -1.5
            segments.append(self._segment(1.2, ang, 0.8))
        self._attach_on_done(segments, self._compound_done_cb("Zigzag complete!"))
        self._enqueue_motion(segments, "zigzagging")

    def execute_figure8(self):
        segments = [
            self._segment(1.0, 1.2, 5.0),
            self._segment(1.0, -1.2, 5.0),
        ]
        self._attach_on_done(segments, self._compound_done_cb("Figure 8 complete!"))
        self._enqueue_motion(segments, "figure 8")

    def execute_crazy(self):
        segments: List[MotionSegment] = []
        for _ in range(12):
            segments.append(self._segment(
                random.uniform(-2.0, 2.0),
                random.uniform(-3.0, 3.0),
                random.uniform(0.2, 0.6),
            ))
        self._attach_on_done(segments, self._compound_done_cb("That was fun!"))
        self._enqueue_motion(segments, "going crazy")

    def execute_barrel_roll(self):
        """Do a barrel roll (one fast full spin)."""
        twist = self._make_twist(ang=4.0)
        segments = [(twist, 3.14, self._compound_done_cb("Barrel roll complete!"))]
        self._enqueue_motion(segments, "barrel roll")

    # ---- Motion queue plumbing -------------------------------------------

    def _make_twist(self, lin: float = 0.0, ang: float = 0.0) -> Twist:
        t = Twist()
        t.linear.x = float(lin)
        t.angular.z = float(ang)
        return t

    def _segment(self, lin: float, ang: float, dur: float) -> MotionSegment:
        return (self._make_twist(lin=lin, ang=ang), float(dur), None)

    def _attach_on_done(self, segments: List[MotionSegment],
                        on_done: Callable[[], None]) -> None:
        """Attach a completion callback to the last segment in the list."""
        if not segments:
            return
        last_twist, last_dur, _ = segments[-1]
        segments[-1] = (last_twist, last_dur, on_done)

    def _compound_done_cb(self, message: str) -> Callable[[], None]:
        """Build an on_done callback that speaks `message` and returns to idle."""
        def _cb():
            self._speak(message)
            self.current_action = "idle"
        return _cb

    def _enqueue_motion(self, segments: List[MotionSegment], action_label: str) -> None:
        """Replace any queued motion with the given segments (last-command-wins)."""
        self._motion_queue.clear()
        self._current_twist = None
        self._motion_deadline = None
        self._current_on_done = None
        self.cancel_motion = False
        self.current_action = action_label
        for seg in segments:
            self._motion_queue.append(seg)

    def _motion_tick(self):
        """50 Hz timer: advance the motion queue and republish the current twist."""
        now = time.time()

        # Current segment finished? Advance it.
        if (self._current_twist is not None
                and self._motion_deadline is not None
                and now >= self._motion_deadline):
            on_done = self._current_on_done
            self._current_twist = None
            self._motion_deadline = None
            self._current_on_done = None
            self._need_idle_publish = True
            if on_done is not None:
                try:
                    on_done()
                except Exception as e:
                    self.get_logger().warn(f"Motion on_done failed: {e}")

        # Start next segment if we're idle and the queue has more work.
        if self._current_twist is None and self._motion_queue:
            twist, duration, on_done = self._motion_queue.popleft()
            self._current_twist = twist
            self._motion_deadline = now + max(0.0, duration)
            self._current_on_done = on_done
            self._need_idle_publish = False

        # Publish: current segment if active, else a single zero-twist on the
        # tick we transitioned to idle (gives the motor driver a clean stop and
        # avoids spamming the bus while truly idle).
        if self._current_twist is not None:
            self.pub_vel.publish(self._current_twist)
        elif self._need_idle_publish:
            self.pub_vel.publish(Twist())
            self._need_idle_publish = False


def main():
    rclpy.init()
    node = JarvisAgent()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
