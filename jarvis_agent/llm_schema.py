#!/usr/bin/env python3
"""
Build a JSON Schema and a grammar-constrained SYSTEM_PROMPT from the
action registry.

This gives ``llm_nlp_node`` a single place to enforce the contract with
the LLM:

  1. The prompt explicitly lists every valid action + its params + an
     example, so the model knows the complete grammar.
  2. Ollama is called with ``"format": "json"`` so the output is
     guaranteed to parse as JSON (no markdown, no preamble).
  3. After parsing, we validate the object against the generated schema
     and reject any intent whose action name isn't in the registry or
     whose params don't match the declared types/enums.

Optional ``jsonschema`` is used if installed; otherwise we fall back to
a small validator that enforces the subset of features this file uses.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from jarvis_agent.action_registry import ACTIONS, find


# ---------------------------------------------------------------------------
# JSON Schema generation
# ---------------------------------------------------------------------------

def _param_to_jsonschema(p: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"type": p["type"]}
    if "enum" in p:
        out["enum"] = p["enum"]
    if "min" in p:
        out["minimum"] = p["min"]
    if "max" in p:
        out["maximum"] = p["max"]
    if "description" in p:
        out["description"] = p["description"]
    return out


def build_intent_schema() -> Dict[str, Any]:
    """JSON Schema with oneOf per action; top-level object discriminated by 'action'."""
    variants = []
    for a in ACTIONS:
        props: Dict[str, Any] = {
            "action": {"type": "string", "const": a["name"]}
        }
        for pname, pspec in a["params"].items():
            props[pname] = _param_to_jsonschema(pspec)
        required = ["action", *a["required"]]
        variants.append({
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": True,  # allow "simon_says": true etc.
        })
    return {"oneOf": variants}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    lines = [
        "You are Jarvis, an AI assistant controlling a mobile robot.",
        "Translate the user's natural language into ONE JSON intent.",
        "",
        "Rules:",
        "- Output ONE JSON object and nothing else. No prose, no markdown.",
        "- The \"action\" field MUST be one of the actions below.",
        "- Only include parameters listed for that action.",
        "- Use defaults when unsure: duration=1.0, circle duration=3.0, spin duration=4.0.",
        "- Phrases like 'a bit' -> duration 0.5; 'a lot'/'far' -> 3-5; 'twice' -> 4.",
        "- If the request is a general question or unclear, use action=\"say\".",
        "",
        "Available actions:",
    ]
    for a in ACTIONS:
        if a["params"]:
            param_blobs = []
            for pname, pspec in a["params"].items():
                desc = pspec.get("enum") or pspec["type"]
                param_blobs.append(f"{pname}:{desc}")
            sig = " {" + ", ".join(param_blobs) + "}"
        else:
            sig = ""
        lines.append(f"  - {a['name']}{sig}  — {a['description']}")

    lines.append("")
    lines.append("Examples:")
    # Pull a varied selection of examples from the registry.
    shown = 0
    for a in ACTIONS:
        for utter, intent in a["examples"]:
            lines.append(f'User: "{utter}"')
            lines.append(json.dumps(intent))
            shown += 1
            if shown >= 12:
                break
        if shown >= 12:
            break
    lines.append("")
    lines.append("Now output ONLY the JSON intent for this command:")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

try:
    import jsonschema  # type: ignore
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False


def validate_intent(intent: Any) -> bool:
    """Return True iff ``intent`` matches the registry's schema.

    Uses jsonschema when available for a full check; otherwise performs a
    focused manual check that covers the constraints this registry uses
    (action name, enum values, integer bounds, required fields).
    """
    if not isinstance(intent, dict):
        return False
    action = intent.get("action")
    if not isinstance(action, str):
        return False
    a = find(action)
    if a is None:
        return False

    if _HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=intent, schema=build_intent_schema())
            return True
        except jsonschema.ValidationError:
            return False

    # Manual validation fallback.
    for req in a["required"]:
        if req not in intent:
            return False
    for pname, pspec in a["params"].items():
        if pname not in intent:
            continue
        val = intent[pname]
        t = pspec["type"]
        if t == "number" and not isinstance(val, (int, float)):
            return False
        if t == "integer" and not isinstance(val, int):
            return False
        if t == "string" and not isinstance(val, str):
            return False
        if "enum" in pspec and val not in pspec["enum"]:
            return False
        if "min" in pspec and isinstance(val, (int, float)) and val < pspec["min"]:
            return False
        if "max" in pspec and isinstance(val, (int, float)) and val > pspec["max"]:
            return False
    return True
