"""Self-signed certificate for the phone lookouts' HTTPS listener.

Phones only hand the gyroscope and the microphone to a page in a secure
context, and the Commander runs on a plain-HTTP LAN address.  The listener
therefore also serves HTTPS on the next port with a self-signed certificate:
the phone warns once, the player accepts it, and from then on the lookout
page is a secure context.  Nothing here makes the connection trusted beyond
that: it keeps the LAN traffic private from passive listeners only.

The certificate is made here without third-party packages: an ECDSA P-256
key (``secrets``), an X.509 v3 certificate in DER with the host's address as
subject alternative name, signed with ECDSA/SHA-256.  It is kept in
``<SAVE_DIR>/tls`` (the key readable by the user only) and made anew when
the address changes or it nears expiry, so a phone accepts it only once
per address.
"""

from __future__ import annotations

import datetime
import hashlib
import ipaddress
import json
import os
import secrets
import ssl
import tempfile

# NIST P-256 (secp256r1).
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = _P - 3
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
      0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)
VALID_DAYS = 800
RENEW_DAYS = 30
CERT_FILE, KEY_FILE, META_FILE = "cert.pem", "key.pem", "tls.json"


# --- P-256 arithmetic (Jacobian coordinates) ---------------------------------

def _double(point):
    x, y, z = point
    if y == 0:
        return (0, 1, 0)
    ysq = y * y % _P
    s = 4 * x * ysq % _P
    zz = z * z % _P
    m = 3 * (x - zz) * (x + zz) % _P       # a = -3
    nx = (m * m - 2 * s) % _P
    ny = (m * (s - nx) - 8 * ysq * ysq) % _P
    nz = 2 * y * z % _P
    return (nx, ny, nz)


def _add(p, q):
    if p[2] == 0:
        return q
    if q[2] == 0:
        return p
    x1, y1, z1 = p
    x2, y2, z2 = q
    z1z1, z2z2 = z1 * z1 % _P, z2 * z2 % _P
    u1, u2 = x1 * z2z2 % _P, x2 * z1z1 % _P
    s1, s2 = y1 * z2 * z2z2 % _P, y2 * z1 * z1z1 % _P
    if u1 == u2:
        return _double(p) if s1 == s2 else (0, 1, 0)
    h, r = (u2 - u1) % _P, (s2 - s1) % _P
    hh = h * h % _P
    hhh = h * hh % _P
    v = u1 * hh % _P
    nx = (r * r - hhh - 2 * v) % _P
    ny = (r * (v - nx) - s1 * hhh) % _P
    nz = h * z1 * z2 % _P
    return (nx, ny, nz)


def _multiply(k, point=_G):
    result, addend = (0, 1, 0), (point[0], point[1], 1)
    while k:
        if k & 1:
            result = _add(result, addend)
        addend = _double(addend)
        k >>= 1
    x, y, z = result
    if z == 0:
        raise ValueError("point at infinity")
    zinv = pow(z, -1, _P)
    return (x * zinv * zinv % _P, y * zinv * zinv * zinv % _P)


def _on_curve(point) -> bool:
    x, y = point
    return (y * y - (x * x * x + _A * x + _B)) % _P == 0


def _sign(secret, digest: bytes):
    z = int.from_bytes(digest, "big") % _N
    while True:
        k = secrets.randbelow(_N - 1) + 1
        r = _multiply(k)[0] % _N
        if r == 0:
            continue
        s = pow(k, -1, _N) * (z + r * secret) % _N
        if s:
            return r, s


def _verify(public, digest: bytes, r: int, s: int) -> bool:
    if not (0 < r < _N and 0 < s < _N):
        return False
    z = int.from_bytes(digest, "big") % _N
    w = pow(s, -1, _N)
    a = _multiply(z * w % _N)
    b = _multiply(r * w % _N, public)
    point = _add((a[0], a[1], 1), (b[0], b[1], 1))
    if point[2] == 0:
        return False
    zinv = pow(point[2], -1, _P)
    return point[0] * zinv * zinv % _P % _N == r


# --- DER -------------------------------------------------------------------

def _tlv(tag: int, body: bytes) -> bytes:
    length = len(body)
    if length < 0x80:
        head = bytes((length,))
    else:
        size = length.to_bytes((length.bit_length() + 7) // 8, "big")
        head = bytes((0x80 | len(size),)) + size
    return bytes((tag,)) + head + body


def _int(value: int) -> bytes:
    body = value.to_bytes(max(1, (value.bit_length() + 8) // 8), "big")
    return _tlv(0x02, body)


def _oid(text: str) -> bytes:
    parts = [int(part) for part in text.split(".")]
    body = bytes((parts[0] * 40 + parts[1],))
    for part in parts[2:]:
        chunk = [part & 0x7F]
        part >>= 7
        while part:
            chunk.append(0x80 | (part & 0x7F))
            part >>= 7
        body += bytes(reversed(chunk))
    return _tlv(0x06, body)


def _seq(*items: bytes) -> bytes:
    return _tlv(0x30, b"".join(items))


def _bits(body: bytes) -> bytes:
    return _tlv(0x03, b"\x00" + body)


def _time(moment: datetime.datetime) -> bytes:
    return _tlv(0x17, moment.strftime("%y%m%d%H%M%SZ").encode("ascii"))


_EC_KEY = "1.2.840.10045.2.1"
_P256 = "1.2.840.10045.3.1.7"
_ECDSA_SHA256 = "1.2.840.10045.4.3.2"


def _pem(label: str, der: bytes) -> bytes:
    import base64
    text = base64.encodebytes(der).decode("ascii").replace("\n", "")
    lines = [text[index:index + 64] for index in range(0, len(text), 64)]
    return (f"-----BEGIN {label}-----\n" + "\n".join(lines)
            + f"\n-----END {label}-----\n").encode("ascii")


def make_certificate(addresses, *, now=None, days=VALID_DAYS):
    """``(cert_pem, key_pem)`` for a self-signed server certificate naming
    ``addresses`` (IPv4 strings) and ``localhost``."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    secret = secrets.randbelow(_N - 1) + 1
    public = _multiply(secret)
    point = b"\x04" + public[0].to_bytes(32, "big") + public[1].to_bytes(32, "big")
    name = _seq(_tlv(0x31, _seq(_oid("2.5.4.3"), _tlv(0x0C, b"U-Jagd Remote Crew"))))
    alt = b"".join(_tlv(0x87, ipaddress.IPv4Address(item).packed)
                   for item in sorted(set(addresses)))
    alt += _tlv(0x82, b"localhost")
    extensions = _seq(
        _seq(_oid("2.5.29.19"), _tlv(0x01, b"\xff"), _tlv(0x04, _seq())),
        _seq(_oid("2.5.29.37"), _tlv(0x04, _seq(_oid("1.3.6.1.5.5.7.3.1")))),
        _seq(_oid("2.5.29.17"), _tlv(0x04, _seq(alt))))
    algorithm = _seq(_oid(_ECDSA_SHA256))
    tbs = _seq(
        _tlv(0xA0, _int(2)),
        _int(secrets.randbits(127) | 1 << 126),
        algorithm, name,
        _seq(_time(now - datetime.timedelta(hours=1)),
             _time(now + datetime.timedelta(days=days))),
        name,
        _seq(_seq(_oid(_EC_KEY), _oid(_P256)), _bits(point)),
        _tlv(0xA3, extensions))
    r, s = _sign(secret, hashlib.sha256(tbs).digest())
    certificate = _seq(tbs, algorithm, _bits(_seq(_int(r), _int(s))))
    key = _seq(_int(1), _tlv(0x04, secret.to_bytes(32, "big")),
               _tlv(0xA0, _oid(_P256)), _tlv(0xA1, _bits(point)))
    return _pem("CERTIFICATE", certificate), _pem("EC PRIVATE KEY", key)


# --- storage -----------------------------------------------------------------

def _write(path: str, data: bytes, mode: int) -> None:
    directory = os.path.dirname(path)
    handle, staged = tempfile.mkstemp(prefix=".tls-", dir=directory)
    try:
        os.chmod(staged, mode)
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged, path)
    except BaseException:
        try:
            os.unlink(staged)
        except OSError:
            pass
        raise


def ensure_certificate(directory: str, address: str, *, now=None):
    """``(cert_path, key_path)`` valid for ``address``: the stored pair, or a
    fresh one when the address is new, the pair is near expiry or unreadable."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    ipaddress.IPv4Address(address)
    if os.path.islink(directory):
        raise OSError("symlinked certificate directory")
    os.makedirs(directory, mode=0o700, exist_ok=True)
    cert_path = os.path.join(directory, CERT_FILE)
    key_path = os.path.join(directory, KEY_FILE)
    meta_path = os.path.join(directory, META_FILE)
    try:
        with open(meta_path, encoding="utf-8") as stream:
            meta = json.load(stream)
        expires = datetime.datetime.fromisoformat(meta["not_after"])
        if (address in meta["addresses"] and os.path.isfile(cert_path)
                and os.path.isfile(key_path) and not os.path.islink(cert_path)
                and not os.path.islink(key_path)
                and expires - now > datetime.timedelta(days=RENEW_DAYS)):
            context(cert_path, key_path)
            return cert_path, key_path
    except (OSError, ValueError, KeyError, TypeError, ssl.SSLError):
        pass
    cert, key = make_certificate([address], now=now)
    _write(key_path, key, 0o600)
    _write(cert_path, cert, 0o644)
    _write(meta_path, json.dumps({
        "addresses": [address],
        "not_after": (now + datetime.timedelta(days=VALID_DAYS)).isoformat()},
        sort_keys=True).encode("ascii"), 0o644)
    return cert_path, key_path


def context(cert_path: str, key_path: str) -> ssl.SSLContext:
    """Server-side TLS context (TLS 1.2+) with the stored pair."""
    result = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    result.minimum_version = ssl.TLSVersion.TLSv1_2
    result.load_cert_chain(cert_path, key_path)
    return result


def fingerprint(cert_path: str) -> str:
    """SHA-256 fingerprint of the stored certificate (``AB:CD:...``), to
    compare with what the phone shows before accepting it."""
    with open(cert_path, encoding="ascii") as stream:
        der = ssl.PEM_cert_to_DER_cert(stream.read())
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[index:index + 2] for index in range(0, len(digest), 2))
