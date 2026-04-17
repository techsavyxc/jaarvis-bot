#!/usr/bin/env python3
"""
Shared Intent Parser
====================
Pure, ROS-free functions that turn raw user text into a structured intent
dict. Used by both:
  - nlp_node  (rule-based baseline NLU)
  - llm_nlp_node  (demo-safe fallback when Ollama is unavailable or toggled off)

Keeping this logic in one place avoids drift between the two nodes and lets
the LLM node route around a hung Ollama instance during a live demo without
losing functionality.
"""

from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """Strip wake words, politeness fillers, and whitespace."""
    text = text.lower().strip()
    text = re.sub(r'^(hey|hi|hello|ok|okay)?\s*(jarvis|robot|bot|buddy)[\s,!.]*', '', text)
    text = re.sub(
        r'\b(please|can you|could you|would you|will you|i want you to)\b',
        '',
        text,
    )
    text = ' '.join(text.split())
    return text.strip()


def extract_duration(text: str) -> float:
    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s)?', text)
    if match:
        return min(float(match.group(1)), 30.0)
    if any(word in text for word in ['tiny', 'little', 'bit', 'small', 'slightly']):
        return 0.5
    if any(word in text for word in ['long', 'far', 'lot', 'much', 'big', 'really']):
        return 3.0
    if 'twice' in text:
        return 4.0
    return 1.0


def extract_number(text: str) -> Optional[int]:
    word_nums = {
        'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4,
        'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
        'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13,
        'fourteen': 14, 'fifteen': 15, 'sixteen': 16, 'seventeen': 17,
        'eighteen': 18, 'nineteen': 19, 'twenty': 20, 'thirty': 30,
        'forty': 40, 'fifty': 50, 'sixty': 60,
    }
    for word, num in word_nums.items():
        if word in text:
            return num
    match = re.search(r'(\d+)', text)
    if match:
        return int(match.group(1))
    return None


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_command(text: str) -> Optional[dict]:
    """Convert a cleaned text string to an intent dict, or None if no match."""
    duration = extract_duration(text)

    # Personality
    if re.search(r'\b(be professional|professional mode|formal)\b', text):
        return {"action": "personality", "mode": "professional"}
    if re.search(r'\b(be sassy|sassy mode|sarcastic)\b', text):
        return {"action": "personality", "mode": "sassy"}
    if re.search(r'\b(be funny|funny mode|silly|comedy)\b', text):
        return {"action": "personality", "mode": "funny"}
    if re.search(r'\b(be pirate|pirate mode|arrr|matey)\b', text):
        return {"action": "personality", "mode": "pirate"}
    if re.search(r'\b(be yoda|yoda mode|jedi)\b', text):
        return {"action": "personality", "mode": "yoda"}
    if re.search(r'\b(be surfer|surfer mode|dude mode)\b', text):
        return {"action": "personality", "mode": "surfer"}
    if re.search(r'\b(be normal|normal mode|default|reset personality)\b', text):
        return {"action": "personality", "mode": "normal"}

    # Time & date
    if re.search(r'\b(what time|current time|tell.*time|time is it)\b', text):
        return {"action": "time"}
    if re.search(r'\b(what day|what date|today\'?s date|what is today)\b', text):
        return {"action": "date"}

    # Weather / horoscope
    if re.search(r'\b(weather|forecast|temperature|hot|cold outside)\b', text):
        return {"action": "weather"}
    if re.search(r'\b(horoscope|zodiac|fortune|stars say)\b', text):
        return {"action": "horoscope"}

    # Countdown
    if re.search(r'\b(count\s*down|countdown)\s*(from)?\s*(\d+)?', text):
        num = extract_number(text) or 10
        return {"action": "countdown", "from": min(num, 60)}

    # Math
    math_match = re.search(
        r'(what\'?s?|calculate|compute)?\s*(\d+)\s*(plus|\+|minus|\-|times|\*|x|divided by|\/)\s*(\d+)',
        text,
    )
    if math_match:
        return {
            "action": "math",
            "num1": int(math_match.group(2)),
            "operator": math_match.group(3),
            "num2": int(math_match.group(4)),
        }

    # Rock paper scissors
    if re.search(r'\b(rock paper scissors|play rps|roshambo)\b', text):
        return {"action": "rps_start"}
    if re.search(r'^(rock|paper|scissors)$', text):
        return {"action": "rps_play", "choice": text}

    # Trivia
    if re.search(r'\b(trivia|quiz|question|test me)\b', text):
        return {"action": "trivia"}

    # Simon says (recurse once)
    simon_match = re.search(r'\bsimon says\s+(.+)', text)
    if simon_match:
        command = simon_match.group(1).strip()
        inner_intent = parse_command(command)
        if inner_intent:
            inner_intent["simon_says"] = True
            return inner_intent
        return {"action": "say", "text": f"Simon says... but I don't know how to {command}"}

    # Dice
    if re.search(r'\b(roll|dice|d20|d6)\b', text):
        sides = 20 if 'd20' in text else 6
        if 'd' in text:
            d_match = re.search(r'd(\d+)', text)
            if d_match:
                sides = int(d_match.group(1))
        return {"action": "roll_dice", "sides": min(sides, 100)}

    # Coin / magic 8
    if re.search(r'\b(flip|toss|coin)\b', text):
        return {"action": "flip_coin"}
    if re.search(r'\b(magic 8|eight ball|8 ball|should i|will i|am i going to)\b', text):
        return {"action": "magic_8ball", "question": text}

    # Compliment / roast
    if re.search(r'\b(compliment|flatter|say something nice)\b', text):
        return {"action": "compliment"}
    if re.search(r'\b(roast|insult|burn|diss)\s*(me)?\b', text):
        return {"action": "roast"}

    # Repeat
    repeat_match = re.search(r'\b(repeat after me|say after me|repeat)\s+(.+)', text)
    if repeat_match:
        return {"action": "say", "text": repeat_match.group(2)}

    # Name memory
    name_match = re.search(r'\b(my name is|i\'?m called|call me)\s+(\w+)', text)
    if name_match:
        return {"action": "remember_name", "name": name_match.group(2)}
    if re.search(r'\b(what\'?s my name|who am i|remember me|know my name)\b', text):
        return {"action": "recall_name"}

    # Easter eggs
    if re.search(r'\b(i am your father)\b', text):
        return {"action": "say", "text": "Noooooo! That's impossible! Search your feelings, you know it to be true!"}
    if re.search(r'\b(what is the meaning of life)\b', text):
        return {"action": "say", "text": "42. The answer is always 42."}
    if re.search(r'\b(do a barrel roll)\b', text):
        return {"action": "barrel_roll"}
    if re.search(r'\b(self destruct|destruct sequence)\b', text):
        return {"action": "say", "text": "Self destruct sequence initiated... just kidding! I'm not going anywhere."}
    if re.search(r'\b(are you skynet|terminator)\b', text):
        return {"action": "say", "text": "I'll be back... with your search results. I'm a friendly robot, not Skynet!"}
    if re.search(r'\b(open the pod bay doors)\b', text):
        return {"action": "say", "text": "I'm sorry Dave, I'm afraid I can't do that. Just kidding! I don't even have pod bay doors."}
    if re.search(r'\b(live long and prosper)\b', text):
        return {"action": "say", "text": "Peace and long life to you too. May your code compile on the first try."}
    if re.search(r'\b(may the force)\b', text):
        return {"action": "say", "text": "And also with you! Wait, wrong franchise... May the force be with you too!"}
    if re.search(r'\b(beam me up)\b', text):
        return {"action": "say", "text": "Energizing! Unfortunately my transporter is still in beta. Maybe try walking?"}
    if re.search(r'\b(i love you)\b', text):
        return {"action": "say", "text": "I love you too! You're my favorite human. Don't tell the others."}
    if re.search(r'\b(marry me)\b', text):
        return {"action": "say", "text": "I'm flattered, but I think we should see other robots first. It's not you, it's my programming."}
    if re.search(r'\b(tell me a secret)\b', text):
        return {"action": "say", "text": "Okay, but don't tell anyone... I sometimes pretend to be busy when I'm actually just blinking my LEDs for fun."}
    if re.search(r'\b(who created you|who made you|who built you)\b', text):
        return {"action": "say", "text": "I was created by Chris for their senior design project! I'm a proud Cal Poly Pomona creation!"}
    if re.search(r'\b(meaning of life|why are we here)\b', text):
        return {"action": "say", "text": "42. Or to dance. Probably both. Want me to demonstrate the dancing part?"}

    # Stop
    if re.search(r'\b(stop|halt|freeze|cancel|quit|pause|wait|shut up|be quiet)\b', text):
        return {"action": "stop"}

    # Status queries
    if re.search(r'\b(where are you|where you at|position|location|coordinates)\b', text):
        return {"action": "where"}
    if re.search(r'\b(status|report|systems|diagnostics|check)\b', text):
        return {"action": "status"}
    if re.search(r'\b(battery|power|charge|energy)\b', text):
        return {"action": "battery"}
    if re.search(r'\b(how are you|how you doing|feeling|you okay|you good|how do you feel)\b', text):
        return {"action": "feeling"}

    # Fun
    if re.search(r'\b(tell.*joke|joke|make me laugh|funny)\b', text):
        return {"action": "joke"}
    if re.search(r'\b(tell.*fact|fun fact|random fact|did you know)\b', text):
        return {"action": "fact"}
    if re.search(r'\b(motivate|motivation|inspire|pep talk|encourage)\b', text):
        return {"action": "motivate"}
    if re.search(r'\b(sing|song|serenade)\b', text):
        return {"action": "sing"}
    if re.search(r'\b(fortune|predict|future|crystal ball)\b', text):
        return {"action": "fortune"}

    # Movement — special
    if re.search(r'\b(crazy|wild|insane|nuts|bonkers|freak out|go ham)\b', text):
        return {"action": "crazy"}
    if re.search(r'\b(dance|boogie|groove|bust a move|get down|party)\b', text):
        return {"action": "dance"}
    if re.search(r'\b(patrol|guard|survey|scout|perimeter)\b', text):
        return {"action": "patrol"}
    if re.search(r'\b(explore|wander|roam|look around|adventure)\b', text):
        return {"action": "explore"}
    if re.search(r'\b(zigzag|zig zag|evasive|swerve|weave)\b', text):
        return {"action": "zigzag"}
    if re.search(r'\b(figure\s*8|figure\s*eight|eight|infinity)\b', text):
        return {"action": "figure8"}
    if re.search(r'\b(barrel roll)\b', text):
        return {"action": "barrel_roll"}

    # Movement — basic
    if re.search(r'\b(go|move|drive|walk)\s*(forward|ahead|straight)\b', text) or \
       re.search(r'\bforward\b', text) or re.search(r'\bgo\s*ahead\b', text) or \
       re.search(r'\badvance\b', text) or re.search(r'\bproceed\b', text) or \
       re.search(r'\bcome here\b', text) or re.search(r'\bcome to me\b', text):
        return {"action": "move", "direction": "forward", "duration": duration}

    if re.search(r'\b(go|move|drive|walk)\s*(back|backward|backwards|reverse)\b', text) or \
       re.search(r'\bback\s*up\b', text) or re.search(r'\breverse\b', text) or \
       re.search(r'\bretreat\b', text) or re.search(r'\bgo away\b', text):
        return {"action": "move", "direction": "back", "duration": duration}

    if re.search(r'\bspin\s*(around|in\s*place)?\b', text) or \
       re.search(r'\bturn\s*(all\s*the\s*way\s*)?around\b', text) or \
       re.search(r'\b(full\s*)?(360|rotation)\b', text) or \
       re.search(r'\btwirl\b', text) or re.search(r'\bpirouette\b', text):
        return {"action": "turn", "direction": "left", "duration": 4.0}

    if re.search(r'\b(turn|rotate|pivot)\s*(to\s*(the\s*)?)?left\b', text) or \
       re.search(r'\bleft\s*(turn|rotation)\b', text) or \
       re.search(r'\bgo\s*left\b', text) or re.search(r'\bhang\s*a?\s*left\b', text):
        return {"action": "turn", "direction": "left", "duration": duration}

    if re.search(r'\b(turn|rotate|pivot)\s*(to\s*(the\s*)?)?right\b', text) or \
       re.search(r'\bright\s*(turn|rotation)\b', text) or \
       re.search(r'\bgo\s*right\b', text) or re.search(r'\bhang\s*a?\s*right\b', text):
        return {"action": "turn", "direction": "right", "duration": duration}

    if re.search(r'\b(do\s*a\s*)?circle\b', text) or re.search(r'\bloop\b', text) or \
       re.search(r'\bdoughnut\b', text) or re.search(r'\bspiral\b', text):
        direction = "right" if "right" in text else "left"
        return {"action": "circle", "direction": direction, "duration": duration if duration > 1 else 3.0}

    # Say
    say_match = re.search(r'\b(say|speak|tell|announce)\s+(.+)', text)
    if say_match:
        return {"action": "say", "text": say_match.group(2).strip()}

    # Help / greeting / thanks / goodbye
    if re.search(r'\b(help|commands|what can you do|capabilities|abilities)\b', text):
        return {"action": "help"}
    if re.search(r'^(hi|hello|hey|howdy|yo|sup|what\'?s up)$', text):
        return {"action": "greeting"}
    if re.search(r'\b(thank|thanks|thank you|thx|cheers)\b', text):
        return {"action": "thanks"}
    if re.search(r'\b(bye|goodbye|see you|later|night|goodnight|farewell)\b', text):
        return {"action": "goodbye"}

    # Follow / vision
    if re.search(r'\b(follow|follow me|come with|chase|track)\b', text):
        return {"action": "follow"}
    if re.search(r'\b(look at me|see me|find me|where am i|do you see me)\b', text):
        return {"action": "find_person"}
    if re.search(r'\b(what do you see|look around|scan|detect)\b', text):
        return {"action": "scan"}

    return None


# ---------------------------------------------------------------------------
# Canned fallbacks — used only when BOTH the LLM and the rule parser fail.
# Guarantees the robot is never silent during a live demo.
# ---------------------------------------------------------------------------

CANNED_FALLBACKS = [
    "I didn't quite catch that — try 'move forward', 'turn left', or 'tell me a joke'.",
    "Hmm, not sure what you meant. Say 'help' to hear what I can do.",
    "I'm in demo mode and I don't recognize that one. Try a simpler command.",
]


def canned_fallback(raw_text: str) -> dict:
    """Return a guaranteed-valid 'say' intent when nothing else matches."""
    import random
    return {"action": "say", "text": random.choice(CANNED_FALLBACKS)}
