"""Optional language-model link (OpenAI-compatible chat completions).

Everything here is an optional extra: with the link off, unreachable or slow
the game plays exactly as without it.  The model only writes text; the only
place where an answer touches the simulation is the explicitly experimental
opponent advisor (``opfor.py``), which picks among the computer opponent's
own fixed plans and keeps every pick in the save.
"""
