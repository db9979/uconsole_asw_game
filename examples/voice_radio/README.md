# Browser voice radio demo

This is a standalone prototype from the earlier example. The integrated
multiplayer radio is started in the game's `/admin` **Server options** page;
run the game with `--web-host` for that version. Do not run this demo server
on the same port as the game.

Start from the repository root:

```sh
.venv/bin/python examples/voice_radio/server.py
```

Open `http://127.0.0.1:8765/` in two Chrome tabs, choose different stations,
and enter the printed radio code in each. Permit microphone access. Hold the
button or **F** to speak. Headphones prevent acoustic feedback.

The browser captures 48 kHz mono PCM with an AudioWorklet, applies 300 Hz
high-pass and 3400 Hz low-pass Biquad filters, mild saturation and noise, then
sends 20 ms frames over a WebSocket. The server admits one connection per
station and one active speaker, verifies the code and Origin, bounds clients,
frames and outgoing queues, and forwards audio to the other stations. PTT up,
focus loss and disconnect end transmission. Voice is transient and never enters
save data or simulation updates.

To show the current speaker in Pygame when embedding the hub in the same
process, read `hub.talker` from the Pygame thread:

```python
speaker = hub.talker  # None or a station key such as "sonar"
label = f"Funk: {speaker}" if speaker else "Funk frei"
```

`hub.talker` is protected by a lock; the game thread must only read it. The
separate demo process does not expose this value to an existing game process.

The default binding is loopback only. For clients on other computers, serve
the page and WebSocket through a reviewed HTTPS/WSS reverse proxy and set
`VOICE_HOST`, `VOICE_ORIGIN`, and ports for that deployment. Browser microphone
capture requires a secure context. This standalone demo has its own radio code;
it does not grant or inherit Remote Crew station leases.
