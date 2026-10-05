# Language model (optional) {#language-model}

## Setting it up {#ref-llm}

An OpenAI-compatible language model can make the game richer. It is off by default and the game plays exactly as without it: every job falls back to the game's own texts when the server is off, slow or unreachable.

Switch it on under `F10` Options, page 2, **Language model**: on/off, the server address (for example `http://localhost:11434/v1` for Ollama in the LAN, or a cloud service), the model name, the API key, worded radio traffic, the coach (off, rare, often) and the experimental opponent; **Test connection** sends one short request and shows the answer time. The API key is kept in `~/.u-jagd/llm_key` (readable only by you) or taken from the environment variable `U_JAGD_LLM_KEY`; it never enters the settings, saves, logs or a browser.

The model runs on a server, never on the uConsole itself. The key is typed as asterisks and afterwards shown only by its last characters. The game asks for answers without a reasoning phase (understood by Qwen3 on vLLM or SGLang; a server that refuses the switch is asked without it). If a reasoning model still sends only its thinking, the test says "only reasoning, no answer": switch its thinking off on the server or choose a model without one.

## What it does {#llm-jobs}

- Radio traffic: every HQ message and the crewed submarine's radio orders are also shown worded like real traffic, beside the original. Numbers, bearings and positions stay as given; the original stays the reference.
- After-action report: when a mission ends the model writes a short report for each side from the debrief recording (now with the truth). `B` in the debrief shows it, the browser shows it in the debrief replay, and the logbook keeps it with the mission (`B` there).
- Executive officer (`F7` in a mission, the **Executive officer** button in the browser): situation report, a typed question (answered from your own picture and the manual), a typed order, help with the selected contact's classification and a briefing for your station. `Left`/`Right` or `1`-`5` choose the kind, `Enter` sends, `Up`/`Down` scroll, `Esc` closes. The officer sees only your own side's picture, like your stations.
- Typed orders: only course, speed, depth, quiet running and action stations, never weapons. The officer proposes the station commands, and nothing is given until you confirm (`Enter`; `Backspace` or `Esc` discards). In the browser the commands go only from a station allowed to give them.
- Coach: with the coach on (rare or often), a short tip from your own picture appears in the message line now and then.
- Logbook: `A` asks the model for a review of your service record, `B` shows the newest report. A mission in which situation reports, questions, orders, classification help or the coach were used is marked "with advisor" and earns no best score or award; the briefing alone does not count.
- Mission generator: `G` (frigate) or `Shift+G` (submarine) in the Mission Editor's list, and **Write mission** in the browser's Mission Planner, write a mission from a few words. The answer goes through the same check as every own mission (unknown fields dropped, a 500 NM fixed world, sink targets set to every placed hostile submarine); on problems the model gets one chance to fix them. The editor opens the mission unsaved for checking (`Ctrl+S` saves); the planner stores it as a new mission and opens it.
- Experimental opponent: every 3 min of mission time the model picks a plan for the AI side from a fixed list, from that side's own picture: for the AI submarines go deep and creep, close in, slip away or lie still (their evasion, lying in wait and attacks keep priority); for the AI hunters sprint and drift, a quiet or a fast search. It never steers, aims or fires itself. Such a mission is marked "experimental" in the logbook, earns no best score or award, and is not reproducible from its seed alone (the plan in force is saved). It never runs in the campaign, lessons or two-crew play.

## Voice {#llm-voice}

An OpenAI-compatible speech service (`/audio/speech`) gives the executive officer and the crew a natural voice. It is off by default; without it the crew keeps its `espeak-ng` voice and nothing else changes. Set it up under `F10` Options, page 2, **Language model**, page **2 Voice** (`Tab` or `PgUp`/`PgDn` switches, a click on the tab too): on/off, the server address (preset `https://api.openai.com/v1`), the speech model (preset `gpt-4o-mini-tts`; `tts-1` works as well), the voice (`Left`/`Right` cycles the OpenAI voices, `Enter` types another name), the API key, **Executive officer speaks**, **Crew reports in this voice** and **Test voice**, which says a sample sentence and shows how long it took.

- Executive officer: his answers (situation report, question, typed order, classification help, briefing) and the coach's tips are spoken on the uConsole as they arrive. Long answers are cut at a sentence end after about 700 characters.
- Crew: with **Spoken crew reports** switched on (options page 2) the crew's calls use the same voice instead of `espeak-ng`; a call the service cannot deliver is said by `espeak-ng`. Calls older than 20 s are dropped instead of said late.
- The key lives in `~/.u-jagd/tts_key` or comes from `U_JAGD_TTS_KEY`. Left empty, the language model's key is used when both addresses name the same server. Like the model's key it never enters the settings, saves, logs or a browser.
- The voice plays on its own audio channel and never cuts the sonar tone; requests and decoding run beside the game, so a slow service never stalls a frame. With the game sound off nothing is spoken.
- Remote Crew browsers keep their own voice for the crew's calls (Settings, the browser's speech synthesis); the executive officer's answers in a browser are shown, not spoken.

## Not modelled {#llm-limits}

- Not modelled: voice commands, spoken answers of the executive officer in a browser, a model on the uConsole itself, model decisions about weapons or targets, and a model that sees hidden truth during a mission.
