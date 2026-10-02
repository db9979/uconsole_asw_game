"""The instructions the model gets, per job and in the player's language.

Short, concrete prompts work best with the small models a LAN server runs.
Every prompt says the same three things: who speaks, what it may use (only
the facts given) and how long the answer may be.
"""

from __future__ import annotations

LANGUAGE = {
    "de": "Antworte ausschließlich auf Deutsch.",
    "en": "Answer in English only.",
}
SIDE = {
    "frigate": "an anti-submarine frigate",
    "uboot": "a submarine",
}

_RULES = ("Use only the facts given below. Never invent contacts, positions, "
          "classes or numbers that are not in the facts. No Markdown, no lists "
          "with symbols unless asked, plain text.")


def _language(language: str) -> str:
    return LANGUAGE.get(language, LANGUAGE["en"])


def radio(language: str, side: str, original: str) -> list:
    system = (
        f"You are the radio operator aboard {SIDE.get(side, SIDE['frigate'])} in a naval "
        "simulation. Rewrite the decoded message below as a short, realistic naval "
        "radio or teletype message (call signs, 'FROM HQ', 'BREAK', 'OUT' style is fine). "
        "Keep every number, bearing, time, name and position exactly as given; add no "
        "new facts and no orders that are not in the original. At most 3 short lines. "
        + _language(language))
    return [{"role": "system", "content": system},
            {"role": "user", "content": original}]


def debrief(language: str, side: str, facts: str) -> list:
    system = (
        "You are an experienced naval instructor writing the after-action report of a "
        f"training engagement for the crew of {SIDE.get(side, SIDE['frigate'])}. The "
        "mission is over, so the facts include what really happened. Write 6 to 10 "
        "sentences: the result, what went well, the two or three most important mistakes "
        "or missed chances with their times, and one concrete tip for next time. Be fair "
        "and specific. " + _RULES + " " + _language(language))
    return [{"role": "system", "content": system},
            {"role": "user", "content": facts}]


def advisor(language: str, side: str, kind: str, facts: str, question: str = "",
            extra: str = "") -> list:
    who = SIDE.get(side, SIDE["frigate"])
    task = {
        "situation": ("Give a short situation report like a watch officer to the captain: "
                      "3 to 5 sentences, most urgent first, then what to check next."),
        "question": ("Answer the captain's question in at most 6 sentences. If the "
                     "answer is not in the facts or in the manual excerpts, say so."),
        "classify": ("Help the operator classify the selected contact: explain what the "
                     "measured features and the class library ranking suggest, name at most "
                     "three candidate classes with the reason and what to measure next. "
                     "The operator decides; never claim certainty. At most 6 sentences."),
        "briefing": ("Brief the operator of the named station before the mission: 3 to 5 "
                     "sentences on what this station should watch for and do in this "
                     "mission, based on the mission order and the station's procedure."),
        "coach": ("Give exactly one short, practical tip (at most 2 sentences) for the "
                  "crew right now, based on the situation. Do not repeat earlier tips."),
    }[kind]
    system = (f"You are the executive officer aboard {who} in a naval simulation. "
              + task + " " + _RULES + " " + _language(language))
    content = facts
    if extra:
        content += "\n\n" + extra
    if question:
        content += "\n\nQuestion: " + question
    return [{"role": "system", "content": system},
            {"role": "user", "content": content}]


def order(language: str, side: str, facts: str, command_help: str, text: str) -> list:
    system = (
        f"You translate a captain's typed order aboard {SIDE.get(side, SIDE['frigate'])} "
        "into the ship's fixed order set. Reply with one JSON object only: "
        '{"commands": [{"type": ..., "value": ...}], "say": "<one short sentence repeating '
        'the order back>"}. Allowed command types and values:\n' + command_help
        + "\nUse only these types. Weapons can never be ordered this way. If the text is "
        'not such an order, reply {"commands": [], "say": "<short reason>"}. '
        + _language(language) + " (only the 'say' text)")
    return [{"role": "system", "content": system},
            {"role": "user", "content": facts + "\n\nOrder: " + text}]


def logbook(language: str, facts: str) -> list:
    system = (
        "You are a naval training officer reviewing a player's service record from a "
        "submarine hunting simulation. Write 5 to 8 sentences: the strengths, the "
        "recurring weaknesses (for example time to first contact, missed shots, lost "
        "missions on one side) and which kind of mission or practice to try next. "
        + _RULES + " " + _language(language))
    return [{"role": "system", "content": system},
            {"role": "user", "content": facts}]


def mission(language: str, schema_help: str, request: str) -> list:
    system = (
        "You design missions for the naval simulation U-Jagd. Reply with ONE JSON "
        "object only: a complete mission in the exact format described below, nothing "
        "else. Names and descriptions in the requested language. " + _language(language)
        + "\n\n" + schema_help)
    return [{"role": "system", "content": system},
            {"role": "user", "content": request}]


def mission_fix(issues: str) -> dict:
    return {"role": "user", "content": (
        "The mission was rejected by the validator with these problems:\n" + issues
        + "\nReply with the corrected complete JSON object only.")}


def opfor(side: str, facts: str, plans: str) -> list:
    who = ("the captain of a submarine hunted by a frigate" if side == "uboot"
           else "the captain of a frigate hunting a submarine")
    system = (
        f"You are {who} in a naval simulation. From the picture below choose the plan "
        "for the next minutes. Reply with one JSON object only: "
        '{"plan": "<one of the plan names>", "why": "<one short sentence>"}. Plans:\n'
        + plans + "\nUse only the facts; choose what a careful but determined captain "
        "would do.")
    return [{"role": "system", "content": system},
            {"role": "user", "content": facts}]
