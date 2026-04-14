#!/usr/bin/env python3
"""
Canonical action/tool registry for Jarvis.

This is the single source of truth for every intent the agent understands.
Both the LLM NLU (which uses the schema to build a grammar-constrained prompt)
and anyone introspecting the robot's capabilities (e.g. a help command, a
status UI, or a future decorator-based dispatch in ``agent_node``) should
read from here.

Each entry describes:
    name          - the "action" string emitted in the intent JSON
    description   - one-line human summary (shown to the LLM)
    params        - param-name -> {"type": json_type, "enum": [...] optional,
                                   "min": N, "max": N, "description": "..."}
    examples      - tuple of (utterance, intent_dict) pairs used in the prompt
    required      - tuple of required param names (defaults to all listed)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


ActionDef = Dict[str, Any]


def _a(
    name: str,
    description: str,
    params: Optional[Dict[str, Dict[str, Any]]] = None,
    examples: Optional[Tuple[Tuple[str, dict], ...]] = None,
    required: Optional[Tuple[str, ...]] = None,
) -> ActionDef:
    params = params or {}
    if required is None:
        required = tuple(params.keys())
    return {
        "name": name,
        "description": description,
        "params": params,
        "required": required,
        "examples": examples or (),
    }


DIRECTION_LR = {"type": "string", "enum": ["left", "right"]}
DIRECTION_FB = {"type": "string", "enum": ["forward", "back"]}
DURATION = {"type": "number", "min": 0.1, "max": 30.0,
            "description": "seconds, clamped to [0.1, 30]"}


ACTIONS: List[ActionDef] = [
    # -- Movement -----------------------------------------------------------
    _a("move",
       "Drive forward or backward for a duration in seconds.",
       {"direction": DIRECTION_FB, "duration": DURATION},
       (("go forward", {"action": "move", "direction": "forward", "duration": 1.0}),
        ("back up three seconds", {"action": "move", "direction": "back", "duration": 3.0}))),
    _a("turn",
       "Rotate in place left or right for a duration in seconds.",
       {"direction": DIRECTION_LR, "duration": DURATION},
       (("turn left a little", {"action": "turn", "direction": "left", "duration": 0.5}),
        ("spin around", {"action": "turn", "direction": "left", "duration": 4.0}))),
    _a("circle",
       "Drive in a circle.",
       {"direction": DIRECTION_LR, "duration": DURATION},
       (("do a circle", {"action": "circle", "direction": "left", "duration": 3.0}),)),
    _a("stop", "Immediately stop all motion.", {}, (("stop", {"action": "stop"}),)),
    _a("crazy", "Go wild / random motion.", (), (("go crazy", {"action": "crazy"}),)),
    _a("dance", "Perform a dance routine.", (), (("dance for me", {"action": "dance"}),)),
    _a("patrol", "Drive a patrol pattern.", (), (("patrol the area", {"action": "patrol"}),)),
    _a("explore", "Drive an exploration pattern.", (), (("explore", {"action": "explore"}),)),
    _a("zigzag", "Zigzag / evasive motion.", (), (("zigzag", {"action": "zigzag"}),)),
    _a("figure8", "Drive a figure-8.", (), (("figure eight", {"action": "figure8"}),)),
    _a("barrel_roll", "Perform a barrel roll.", (),
       (("do a barrel roll", {"action": "barrel_roll"}),)),

    # -- Speech / chit-chat -------------------------------------------------
    _a("say",
       "Speak the provided text verbatim.",
       {"text": {"type": "string", "description": "text to speak"}},
       (("say hello world", {"action": "say", "text": "hello world"}),)),
    _a("greeting", "Respond to a greeting.", (), (("hello", {"action": "greeting"}),)),
    _a("thanks", "Respond to thanks.", (), (("thank you", {"action": "thanks"}),)),
    _a("goodbye", "Respond to goodbye.", (), (("bye", {"action": "goodbye"}),)),
    _a("help", "List capabilities.", (), (("help", {"action": "help"}),)),
    _a("feeling", "Describe how the robot is feeling.", (),
       (("how are you", {"action": "feeling"}),)),

    # -- Info ---------------------------------------------------------------
    _a("time", "Tell the current time.", (), (("what time is it", {"action": "time"}),)),
    _a("date", "Tell the current date.", (), (("what date is it", {"action": "date"}),)),
    _a("weather", "Tell a (fake) weather report.", (),
       (("what's the weather", {"action": "weather"}),)),
    _a("horoscope", "Tell a horoscope.", (),
       (("tell me my horoscope", {"action": "horoscope"}),)),
    _a("where", "Report the robot's position.", (),
       (("where are you", {"action": "where"}),)),
    _a("status", "Report system status.", (),
       (("status report", {"action": "status"}),)),
    _a("battery", "Report battery level.", (),
       (("battery", {"action": "battery"}),)),

    # -- Fun ----------------------------------------------------------------
    _a("joke", "Tell a joke.", (), (("tell me a joke", {"action": "joke"}),)),
    _a("fact", "Tell a fun fact.", (), (("fun fact", {"action": "fact"}),)),
    _a("motivate", "Give motivation.", (),
       (("motivate me", {"action": "motivate"}),)),
    _a("sing", "Sing.", (), (("sing me a song", {"action": "sing"}),)),
    _a("fortune", "Predict the future.", (),
       (("tell my fortune", {"action": "fortune"}),)),
    _a("compliment", "Give a compliment.", (),
       (("say something nice", {"action": "compliment"}),)),
    _a("roast", "Playfully roast the user.", (),
       (("roast me", {"action": "roast"}),)),

    # -- Games --------------------------------------------------------------
    _a("countdown",
       "Count down from N.",
       {"from": {"type": "integer", "min": 1, "max": 60}},
       (("count down from 10", {"action": "countdown", "from": 10}),)),
    _a("math",
       "Compute num1 <operator> num2.",
       {"num1": {"type": "integer"},
        "operator": {"type": "string",
                     "enum": ["plus", "+", "minus", "-", "times",
                              "*", "x", "divided by", "/"]},
        "num2": {"type": "integer"}},
       (("what's 2 plus 2",
         {"action": "math", "num1": 2, "operator": "plus", "num2": 2}),)),
    _a("rps_start", "Start a rock-paper-scissors round.", (),
       (("play rock paper scissors", {"action": "rps_start"}),)),
    _a("rps_play",
       "Play a rock-paper-scissors choice.",
       {"choice": {"type": "string", "enum": ["rock", "paper", "scissors"]}},
       (("rock", {"action": "rps_play", "choice": "rock"}),)),
    _a("trivia", "Ask a trivia question.", (),
       (("quiz me", {"action": "trivia"}),)),
    _a("roll_dice",
       "Roll a die with N sides.",
       {"sides": {"type": "integer", "min": 2, "max": 100}},
       (("roll a d20", {"action": "roll_dice", "sides": 20}),)),
    _a("flip_coin", "Flip a coin.", (),
       (("flip a coin", {"action": "flip_coin"}),)),
    _a("magic_8ball",
       "Answer a yes/no question magic-8-ball style.",
       {"question": {"type": "string"}},
       (("will it rain tomorrow",
         {"action": "magic_8ball", "question": "will it rain tomorrow"}),)),

    # -- Personality / memory ----------------------------------------------
    _a("personality",
       "Switch personality mode.",
       {"mode": {"type": "string",
                 "enum": ["professional", "sassy", "funny",
                          "pirate", "yoda", "surfer", "normal"]}},
       (("be pirate", {"action": "personality", "mode": "pirate"}),)),
    _a("remember_name",
       "Remember the user's name.",
       {"name": {"type": "string"}},
       (("my name is Chris", {"action": "remember_name", "name": "Chris"}),)),
    _a("recall_name", "Repeat the stored user name.", (),
       (("what's my name", {"action": "recall_name"}),)),

    # -- Vision / follow ----------------------------------------------------
    _a("follow", "Toggle follow-me mode.", (),
       (("follow me", {"action": "follow"}),)),
    _a("find_person", "Report whether a person is currently visible.", (),
       (("can you see me", {"action": "find_person"}),)),
    _a("scan", "Describe what the vision system currently sees.", (),
       (("scan the room", {"action": "scan"}),)),
]


# ---------------------------------------------------------------------------

def action_names() -> List[str]:
    return [a["name"] for a in ACTIONS]


def find(name: str) -> Optional[ActionDef]:
    for a in ACTIONS:
        if a["name"] == name:
            return a
    return None
