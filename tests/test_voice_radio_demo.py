"""Protocol checks for the standalone browser voice demo."""

import asyncio
import importlib.util
from pathlib import Path

from websockets.legacy.client import connect
from websockets.legacy.server import serve


def _module():
    path = Path(__file__).resolve().parents[1] / "examples/voice_radio/server.py"
    spec = importlib.util.spec_from_file_location("voice_radio_demo", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ptt_relay_and_release():
    radio = _module()

    async def scenario():
        hub = radio.RadioHub("secret")
        async with serve(hub.handle, "127.0.0.1", 0, origins=["http://localhost"],
                         max_size=2048, compression=None) as server:
            port = server.sockets[0].getsockname()[1]
            url = f"ws://127.0.0.1:{port}"
            headers = {"Origin": "http://localhost"}
            async with connect(url, extra_headers=headers) as sender:
                await sender.send('{"type":"join","station":"sonar","code":"secret"}')
                assert '"ready"' in await sender.recv()
                async with connect(url, extra_headers=headers) as receiver:
                    await receiver.send('{"type":"join","station":"bridge","code":"secret"}')
                    assert '"ready"' in await receiver.recv()
                    frame = bytes(radio.FRAME_BYTES)
                    await sender.send(frame)  # No PTT: discard.
                    try:
                        await asyncio.wait_for(receiver.recv(), .05)
                        assert False, "idle audio was forwarded"
                    except asyncio.TimeoutError:
                        pass
                    await sender.send('"ptt_down"')
                    assert '"sonar"' in await receiver.recv()
                    assert hub.talker == "sonar"
                    await sender.send(frame)
                    assert await receiver.recv() == bytes((1,)) + frame
                    await sender.send('"ptt_up"')
                    assert '"station": null' in await receiver.recv()
                    assert hub.talker is None
                    await sender.send(frame)
                    try:
                        await asyncio.wait_for(receiver.recv(), .05)
                        assert False, "released audio was forwarded"
                    except asyncio.TimeoutError:
                        pass

    asyncio.run(scenario())
