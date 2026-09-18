"""Independent checks for the self-contained QR encoder in :mod:`src.ui.qr`.

The encoder has no third-party dependency; this test re-derives the relevant
QR Code facts (GF(256) arithmetic, the format-info BCH, the Reed-Solomon
generator, the de-interleaving order) and round-trips several payloads, so a
regression in the encoder is caught without a QR scanner.
"""

import pytest

from src.core.game import Game
from src.ui import qr


@pytest.fixture
def game():
    return Game(seed=1701, start_menu=False, audio_enabled=False)

# ---------------------------------------------------------------------------
# Independent GF(256) / BCH / Reed-Solomon helpers (PRIMITIVE = 0x11D).
# ---------------------------------------------------------------------------
_PRIM = 0x11D
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= _PRIM
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gmul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _gen_poly(deg):
    """Reed-Solomon generator polynomial of length ``deg`` (monic)."""
    poly = [1]
    for i in range(deg):
        nxt = [0] * (len(poly) + 1)
        for j, c in enumerate(poly):
            if c:
                nxt[j] ^= c
                nxt[j + 1] ^= _gmul(c, _EXP[i])
        poly = nxt
    return poly  # length deg+1, poly[0] == 1


def _rs_valid(block, deg):
    """True iff ``block`` is a codeword of the RS code of redundancy ``deg``."""
    gen = _gen_poly(deg)
    rem = [0] * deg
    for b in block:
        factor = b ^ rem[0]
        rem = rem[1:] + [0]
        if factor:
            for i in range(deg):
                rem[i] ^= _gmul(gen[i + 1], factor)
    return all(v == 0 for v in rem)


def _fmt_bch(ec_bits, mask):
    """Independent 15-bit format-information string (BCH + XOR mask)."""
    data = (ec_bits << 3) | mask
    rem = data << 10
    gen = 0x537
    while rem.bit_length() >= gen.bit_length():
        rem ^= gen << (rem.bit_length() - gen.bit_length())
    return ((data << 10) | rem) ^ 0x5412


# EC level M == 0b00; map the 15-bit stored format value -> mask pattern.
_MASK_BY_FORMAT = {_fmt_bch(0, m): m for m in range(8)}


def _data_cells(size, reserved):
    """Cell order of the data region (zig-zag up/down, skipping column 6)."""
    cells = []
    inc = -1
    row = size - 1
    for col in range(size - 1, 0, -2):
        if col <= 6:  # skip the vertical timing column, mirroring the spec
            col -= 1
        while True:
            for cc in (col, col - 1):
                if reserved[row][cc] is None:
                    cells.append((row, cc))
            row += inc
            if row < 0 or row >= size:
                row -= inc
                inc = -inc
                break
    return cells


def _read_format(m, size, copy):
    """Read the 15-bit format value for ``copy`` (1 or 2) from ``m``."""
    if copy == 1:
        pos = ([(i, 8) for i in range(6)] + [(7, 8), (8, 8)]
               + [(size - 15 + i, 8) for i in range(8, 15)])
    else:
        pos = ([(8, size - 1 - i) for i in range(8)] + [(8, 7)]
               + [(8, 5 - (i - 9)) for i in range(9, 15)])
    value = 0
    for i, (r, c) in enumerate(pos):
        if m[r][c]:
            value |= 1 << i
    return value


def decode(m):
    """Independently decode a byte-mode, EC-M QR matrix -> (version, mask, text)."""
    size = len(m)
    version = (size - 17) // 4
    f1, f2 = _read_format(m, size, 1), _read_format(m, size, 2)
    assert f1 in _MASK_BY_FORMAT, f1
    assert f2 in _MASK_BY_FORMAT, f2
    assert f1 == f2, (f1, f2)
    mask = _MASK_BY_FORMAT[f1]
    base = qr._base_matrix(version)
    bits = []
    for (r, c) in _data_cells(size, base):
        b = 1 if m[r][c] else 0
        if qr._mask(mask, r, c):
            b ^= 1
        bits.append(b)
    # Some versions (e.g. 2-6) define trailing "remainder bits" after the last
    # codeword that carry no data; padding up to the next byte instead of
    # truncating to the real codeword count fabricates a bogus extra byte.
    total_cw = sum(count * (d + e) for count, d, e in qr._BLOCKS[version])
    bits = bits[:total_cw * 8]
    cw = [0] * (len(bits) // 8)
    for i in range(len(cw)):
        v = 0
        for j in range(8):
            v = (v << 1) | bits[i * 8 + j]
        cw[i] = v
    blocks = qr._BLOCKS[version]
    dsz, ecl = [], []
    for count, d, e in blocks:
        dsz += [d] * count
        ecl += [e] * count
    nblk = len(dsz)
    maxd, maxe = max(dsz), max(ecl)
    cursor = 0
    data_blocks = [[] for _ in range(nblk)]
    for p in range(maxd):
        for b in range(nblk):
            if p < dsz[b]:
                data_blocks[b].append(cw[cursor]); cursor += 1
    ec_blocks = [[] for _ in range(nblk)]
    for p in range(maxe):
        for b in range(nblk):
            if p < ecl[b]:
                ec_blocks[b].append(cw[cursor]); cursor += 1
    assert cursor == len(cw)
    for b in range(nblk):
        block = data_blocks[b] + ec_blocks[b]
        assert _rs_valid(block, ecl[b]), f"RS check failed for block {b}"
    data = bytearray()
    for b in range(nblk):
        data += bytes(data_blocks[b])
    raw = "".join(format(x, "08b") for x in data)
    assert raw[:4] == "0100", raw[:8]
    cnt_bits = 8 if version <= 9 else 16
    count = int(raw[4:4 + cnt_bits], 2)
    body = raw[4 + cnt_bits:4 + cnt_bits + count * 8]
    text = "".join(chr(int(body[i:i + 8], 2)) for i in range(0, len(body), 8))
    return version, mask, text


# ---------------------------------------------------------------------------
# wifi_payload
# ---------------------------------------------------------------------------
def test_wifi_payload_basic():
    assert qr.wifi_payload("U-Jagd-7KPX", "SecureCrewKey2345") == \
        "WIFI:T:WPA;S:U-Jagd-7KPX;P:SecureCrewKey2345;;"


def test_wifi_payload_escaping():
    assert qr.wifi_payload('A;B"C:D\\E', "p,;w") == \
        'WIFI:T:WPA;S:A\\;B\\"C\\:D\\\\E;P:p\\,\\;w;;'


def test_wifi_payload_hidden():
    assert qr.wifi_payload("net", "pw", hidden=True) == \
        "WIFI:T:WPA;S:net;P:pw;H:true;;"


def test_wifi_payload_type_errors():
    with pytest.raises(TypeError):
        qr.wifi_payload(None, "pw")
    with pytest.raises(TypeError):
        qr.wifi_payload("ssid", 1234)


# ---------------------------------------------------------------------------
# encode
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("payload, version", [
    ("A", 1),
    ("HELLO", 1),
    ("A" * 14, 1),
    ("A" * 15, 2),
    ("A" * 26, 2),
    ("A" * 27, 3),
    ("A" * 42, 3),
    ("A" * 43, 4),
    ("WIFI:T:WPA;S:U-Jagd-7KPX;P:SecureCrewKey2345;;", 4),
])
def test_encode_version_and_size(payload, version):
    matrix = qr.encode(payload)
    assert len(matrix) == 4 * version + 17
    assert all(len(row) == len(matrix) for row in matrix)
    assert all(type(cell) is bool for row in matrix for cell in row)


def test_encode_is_deterministic_and_content_sensitive():
    a = qr.encode("WIFI:T:WPA;S:net;P:secret;;")
    b = qr.encode("WIFI:T:WPA;S:net;P:secret;;")
    c = qr.encode("WIFI:T:WPA;S:net;P:secre2;;")
    assert a == b
    assert a != c


def test_encode_rejects_bad_input():
    with pytest.raises(ValueError):
        qr.encode("")
    with pytest.raises(ValueError):
        qr.encode("caf\u00e9")  # non-ASCII
    with pytest.raises(ValueError):
        qr.encode("A" * 214)  # beyond v10-M capacity (213)


def test_encode_structural_markers():
    payload = "WIFI:T:WPA;S:U-Jagd-7KPX;P:SecureCrewKey2345;;"
    m = qr.encode(payload)
    size = len(m)
    version = (size - 17) // 4

    def finder(row, col):
        return row in (0, 6) or col in (0, 6) or (2 <= row <= 4 and 2 <= col <= 4)

    # finder patterns + separators at the three corners
    for top, left in ((0, 0), (0, size - 7), (size - 7, 0)):
        for r in range(-1, 8):
            for c in range(-1, 8):
                rr, cc = top + r, left + c
                if not (0 <= rr < size and 0 <= cc < size):
                    continue
                if 0 <= r <= 6 and 0 <= c <= 6:
                    assert m[rr][cc] is finder(r, c)
                else:
                    assert m[rr][cc] is False  # separator ring

    # timing patterns
    for i in range(8, size - 8):
        assert m[6][i] is (i % 2 == 0)
        assert m[i][6] is (i % 2 == 0)

    # dark module
    assert m[size - 8][8] is True

    # alignment patterns (versions >= 2)
    alignment = {
        2: (6, 18), 3: (6, 22), 4: (6, 26), 5: (6, 30), 6: (6, 34),
        7: (6, 22, 38), 8: (6, 24, 42), 9: (6, 26, 46), 10: (6, 28, 50),
    }[version]
    if version >= 2:
        for ar in alignment:
            for ac in alignment:
                if (ar < 9 and ac < 9) or (ar < 9 and ac > size - 10) or \
                   (ar > size - 10 and ac < 9):
                    continue
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        expected = abs(dr) == 2 or abs(dc) == 2 or (dr == 0 and dc == 0)
                        assert m[ar + dr][ac + dc] is expected


def test_encode_format_info_consistent():
    for payload in ("A", "HELLO WORLD",
                    "WIFI:T:WPA;S:U-Jagd-7KPX;P:SecureCrewKey2345;;",
                    "x" * 120):
        m = qr.encode(payload)
        size = len(m)
        f1, f2 = _read_format(m, size, 1), _read_format(m, size, 2)
        assert f1 == f2
        assert f1 in _MASK_BY_FORMAT
        assert ((f1 ^ 0x5412) >> 13) & 3 == 0  # EC level M


@pytest.mark.parametrize("payload", [
    "A", "HELLO WORLD", "0123456789",
    "WIFI:T:WPA;S:U-Jagd-7KPX;P:SecureCrewKey2345;;",
    "WIFI:T:WPA;S:My Net;P:pw;H:true;;",
    "WIFI:T:WPA;S:A;B\"C\\D;P:p,q;r;;",
    "x" * 14, "x" * 27, "x" * 43, "x" * 100, "x" * 122, "x" * 213,
])
def test_encode_roundtrips_through_independent_decode(payload):
    version, mask, text = decode(qr.encode(payload))
    assert text == payload
    assert 0 <= mask <= 7


# ---------------------------------------------------------------------------
# to_surface
# ---------------------------------------------------------------------------
def test_to_surface_geometry(monkeypatch, tmp_path):
    import os
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    import pygame
    if not pygame.get_init():
        pygame.init()
    matrix = qr.encode("WIFI:T:WPA;S:net;P:secret;;")
    module_px, quiet = 4, 2
    surface = qr.to_surface(matrix, module_px=module_px, quiet=quiet,
                            dark=(1, 2, 3), light=(250, 251, 252))
    size = len(matrix)
    side = (size + 2 * quiet) * module_px
    assert surface.get_size() == (side, side)
    # quiet zone is light
    assert tuple(surface.get_at((0, 0))[:3]) == (250, 251, 252)
    # a finder corner module (0,0) is dark -> first data module is dark
    assert tuple(surface.get_at((quiet * module_px + 1, quiet * module_px + 1))[:3]) == (1, 2, 3)


@pytest.mark.parametrize("bad", [
    [],
    [[True, False]],
    [[True, False], [True, False, True]],  # ragged
    [[1, 0], [0, 1]],                       # ints, not bools
])
def test_to_surface_rejects_bad_matrix(bad):
    import pygame
    if not pygame.get_init():
        pygame.init()
    with pytest.raises(ValueError):
        qr.to_surface(bad)


def test_to_surface_rejects_bad_params():
    import pygame
    if not pygame.get_init():
        pygame.init()
    with pytest.raises(ValueError):
        qr.to_surface([[True]], module_px=0)
    with pytest.raises(ValueError):
        qr.to_surface([[True]], quiet=-1)


# ---------------------------------------------------------------------------
# integration: the hotspot screen renders a scannable QR for the credentials
# ---------------------------------------------------------------------------
def test_hotspot_screen_renders_wifi_qr(game):
    from src.commander.access_point import HotspotDetails
    console = game.commander
    console.network_mode = "hotspot"
    console.address = ("10.42.0.1", 8765)
    console.pairing_code = "123ABC"
    console.hotspot.state = "running"
    console.hotspot.details = HotspotDetails(
        ssid="U-Jagd-7KPX", password="SecureCrewKey2345",
        address="10.42.0.1", interface="wlan0")
    game.commander_open = True
    console.draw(game)

    assert console._qr_payload == qr.wifi_payload("U-Jagd-7KPX", "SecureCrewKey2345")
    assert console._qr_surface is not None
    # A second QR opens the crew page directly, so scanning it needs no manual
    # browser step once the phone has joined the Wi-Fi network.
    assert console._url_qr_payload == "http://10.42.0.1:8765/"
    assert console._url_qr_surface is not None
    # Both codes sit side by side in a 105px slot; either one sized for the
    # old single-QR 132px box would overflow into its neighbour.
    assert console._qr_surface.get_width() <= 105
    assert console._url_qr_surface.get_width() <= 105
    # The cached surface must actually decode back to the credential payload.
    version, mask, text = decode(qr.encode(console._qr_payload))
    assert text == console._qr_payload
    console.commander_open = False


def test_lan_mode_screen_renders_url_qr(game):
    console = game.commander
    console.network_mode = "lan"
    console.address = ("192.168.1.42", 8765)
    console.pairing_code = "123ABC"
    game.commander_open = True
    console.draw(game)

    assert console._url_qr_payload == "http://192.168.1.42:8765/"
    assert console._url_qr_surface is not None
    # LAN mode has no Wi-Fi to join, so only the URL QR is ever populated.
    assert console._qr_surface is None
    console.commander_open = False
