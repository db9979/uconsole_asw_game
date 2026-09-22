"""Self-contained QR Code encoder for bounded on-screen connection helpers."""

from __future__ import annotations

import pygame

_MODE_BYTE = 4
_EC_M = 0
_G15 = 0x537
_G15_MASK = 0x5412
_G18 = 0x1F25
_PAD_A = 0xEC
_PAD_B = 0x11
_MAX_VERSION = 10

_BLOCKS = {
    1: ((1, 16, 10),),
    2: ((1, 28, 16),),
    3: ((1, 44, 26),),
    4: ((2, 32, 18),),
    5: ((2, 43, 24),),
    6: ((4, 27, 16),),
    7: ((4, 31, 18),),
    8: ((2, 38, 22), (2, 39, 22)),
    9: ((3, 36, 22), (2, 37, 22)),
    10: ((4, 43, 26), (1, 44, 26)),
}

_ALIGNMENT = {
    2: (6, 18),
    3: (6, 22),
    4: (6, 26),
    5: (6, 30),
    6: (6, 34),
    7: (6, 22, 38),
    8: (6, 24, 42),
    9: (6, 26, 46),
    10: (6, 28, 50),
}

_GF_EXP = [0] * 512
_GF_LOG = [0] * 256
_x = 1
for _i in range(255):
    _GF_EXP[_i] = _x
    _GF_LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _GF_EXP[_i] = _GF_EXP[_i - 255]


def _gmul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _poly_mul(left: list[int], right: list[int]) -> list[int]:
    result = [0] * (len(left) + len(right) - 1)
    for i, coefficient in enumerate(left):
        if coefficient == 0:
            continue
        for j, factor in enumerate(right):
            if factor:
                result[i + j] ^= _gmul(coefficient, factor)
    return result


def _rs_generator(count: int) -> list[int]:
    polynomial = [1]
    for i in range(count):
        polynomial = _poly_mul(polynomial, [1, _GF_EXP[i]])
    return polynomial


def _rs_encode(data: list[int], error_count: int) -> list[int]:
    generator = _rs_generator(error_count)
    remainder = [0] * error_count
    for byte in data:
        factor = byte ^ remainder[0]
        remainder = remainder[1:] + [0]
        for index in range(1, error_count + 1):
            remainder[index - 1] ^= _gmul(generator[index], factor)
    return remainder


def _select_version(length: int) -> int:
    for version in range(1, _MAX_VERSION + 1):
        total_data = sum(count * size for count, size, _ in _BLOCKS[version])
        header = 2 if version <= 9 else 3
        if length + header <= total_data:
            return version
    raise ValueError("QR payload too large for supported versions 1-10 at EC-M")


def _data_codewords(payload: str, version: int) -> bytes:
    data = payload.encode("ascii")
    total_cw = sum(count * size for count, size, _ in _BLOCKS[version])
    bits: list[int] = []

    def put(value: int, count: int) -> None:
        for shift in range(count - 1, -1, -1):
            bits.append((value >> shift) & 1)

    put(_MODE_BYTE, 4)
    put(len(data), 8 if version <= 9 else 16)
    for byte in data:
        put(byte, 8)
    put(0, min(4, total_cw * 8 - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    pad_index = 0
    while len(bits) < total_cw * 8:
        pad = _PAD_A if pad_index % 2 == 0 else _PAD_B
        put(pad, 8)
        pad_index += 1
    codewords = bytearray()
    for index in range(0, len(bits), 8):
        byte = 0
        for bit in bits[index:index + 8]:
            byte = (byte << 1) | bit
        codewords.append(byte)
    return bytes(codewords)


def _interleave(payload: str, version: int) -> bytes:
    codewords = _data_codewords(payload, version)
    data_blocks: list[bytes] = []
    ec_counts: list[int] = []
    offset = 0
    for count, size, error_count in _BLOCKS[version]:
        for _ in range(count):
            data_blocks.append(codewords[offset:offset + size])
            ec_counts.append(error_count)
            offset += size
    error_blocks = [_rs_encode(block, errors) for block, errors in
                    zip(data_blocks, ec_counts)]
    interleaved = bytearray()
    for index in range(max(len(block) for block in data_blocks)):
        for block in data_blocks:
            if index < len(block):
                interleaved.append(block[index])
    for index in range(max(ec_counts)):
        for block in error_blocks:
            interleaved.append(block[index])
    return bytes(interleaved)


def _mask(mask: int, row: int, col: int) -> bool:
    if mask == 0:
        return (row + col) % 2 == 0
    if mask == 1:
        return row % 2 == 0
    if mask == 2:
        return col % 3 == 0
    if mask == 3:
        return (row + col) % 3 == 0
    if mask == 4:
        return (row // 2 + col // 3) % 2 == 0
    if mask == 5:
        return (row * col) % 2 + (row * col) % 3 == 0
    if mask == 6:
        return ((row * col) % 2 + (row * col) % 3) % 2 == 0
    return ((row * col) % 3 + (row + col) % 2) % 2 == 0


def _base_matrix(version: int) -> list[list[bool | None]]:
    size = 4 * version + 17
    matrix: list[list[bool | None]] = [[None] * size for _ in range(size)]
    for top, left in ((0, 0), (0, size - 7), (size - 7, 0)):
        for row in range(-1, 8):
            for col in range(-1, 8):
                target_row = top + row
                target_col = left + col
                if not (0 <= target_row < size and 0 <= target_col < size):
                    continue
                if 0 <= row <= 6 and 0 <= col <= 6:
                    dark = (row in (0, 6) or col in (0, 6)
                            or (2 <= row <= 4 and 2 <= col <= 4))
                else:
                    dark = False
                matrix[target_row][target_col] = dark
    if version >= 2:
        positions = _ALIGNMENT[version]
        for row in positions:
            for col in positions:
                if matrix[row][col] is not None:
                    continue
                for row_offset in range(-2, 3):
                    for col_offset in range(-2, 3):
                        matrix[row + row_offset][col + col_offset] = (
                            abs(row_offset) == 2 or abs(col_offset) == 2
                            or (row_offset == 0 and col_offset == 0))
    for index in range(8, size - 8):
        if matrix[6][index] is None:
            matrix[6][index] = index % 2 == 0
        if matrix[index][6] is None:
            matrix[index][6] = index % 2 == 0
    for index in range(9):
        if matrix[index][8] is None:
            matrix[index][8] = False
        if matrix[8][index] is None:
            matrix[8][index] = False
    for index in range(8):
        if matrix[size - 1 - index][8] is None:
            matrix[size - 1 - index][8] = False
        if matrix[8][size - 8 + index] is None:
            matrix[8][size - 8 + index] = False
    if matrix[size - 8][8] is None:
        matrix[size - 8][8] = False
    if version >= 7:
        for row in range(6):
            for col in range(3):
                matrix[row][size - 11 + col] = False
                matrix[size - 11 + col][row] = False
    return matrix


def _map_data(matrix: list[list[bool | None]], data: bytes, mask: int) -> None:
    size = len(matrix)
    increment = -1
    row = size - 1
    bit_index = 7
    byte_index = 0
    data_length = len(data)
    for col in range(size - 1, 0, -2):
        if col <= 6:
            col -= 1
        column_pair = (col, col - 1)
        while True:
            for target_col in column_pair:
                if matrix[row][target_col] is None:
                    dark = False
                    if byte_index < data_length:
                        dark = ((data[byte_index] >> bit_index) & 1) == 1
                    if _mask(mask, row, target_col):
                        dark = not dark
                    matrix[row][target_col] = dark
                    bit_index -= 1
                    if bit_index == -1:
                        byte_index += 1
                        bit_index = 7
            row += increment
            if row < 0 or size <= row:
                row -= increment
                increment = -increment
                break


def _bch15(data: int) -> int:
    remainder = data << 10
    while remainder.bit_length() >= _G15.bit_length():
        remainder ^= _G15 << (remainder.bit_length() - _G15.bit_length())
    return ((data << 10) | remainder) ^ _G15_MASK


def _bch18(data: int) -> int:
    remainder = data << 12
    while remainder.bit_length() >= _G18.bit_length():
        remainder ^= _G18 << (remainder.bit_length() - _G18.bit_length())
    return (data << 12) | remainder


def _write_format_info(matrix: list[list[bool]], version: int, mask: int) -> None:
    size = len(matrix)
    value = _bch15((_EC_M << 3) | mask)
    for index in range(15):
        bit = bool((value >> index) & 1)
        if index < 6:
            matrix[index][8] = bit
        elif index < 8:
            matrix[index + 1][8] = bit
        else:
            matrix[size - 15 + index][8] = bit
        if index < 8:
            matrix[8][size - index - 1] = bit
        elif index == 8:
            matrix[8][7] = bit
        else:
            matrix[8][15 - index - 1] = bit
    matrix[size - 8][8] = True


def _write_version_info(matrix: list[list[bool]], version: int) -> None:
    if version < 7:
        return
    size = len(matrix)
    bits = _bch18(version)
    for index in range(18):
        bit = bool((bits >> index) & 1)
        matrix[index // 3][index % 3 + size - 11] = bit
        matrix[index % 3 + size - 11][index // 3] = bit


def _penalty(matrix: list[list[bool]]) -> int:
    size = len(matrix)
    score = 0
    runs = [0] * (size + 1)
    for row in range(size):
        previous = matrix[row][0]
        length = 0
        for col in range(size):
            if matrix[row][col] == previous:
                length += 1
            else:
                if length >= 5:
                    runs[length] += 1
                length = 1
                previous = matrix[row][col]
        if length >= 5:
            runs[length] += 1
    for col in range(size):
        previous = matrix[0][col]
        length = 0
        for row in range(size):
            if matrix[row][col] == previous:
                length += 1
            else:
                if length >= 5:
                    runs[length] += 1
                length = 1
                previous = matrix[row][col]
        if length >= 5:
            runs[length] += 1
    score += sum(runs[length] * (length - 2) for length in range(5, size + 1))

    for row in range(size - 1):
        for col in range(size - 1):
            value = matrix[row][col]
            if (value == matrix[row][col + 1]
                    and value == matrix[row + 1][col]
                    and value == matrix[row + 1][col + 1]):
                score += 3

    patterns = (
        (0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1),
        (1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0),
    )
    for row in range(size):
        for col in range(size - 10):
            if tuple(matrix[row][col:col + 11]) in patterns:
                score += 40
    for col in range(size):
        for row in range(size - 10):
            if tuple(matrix[row + offset][col] for offset in range(11)) in patterns:
                score += 40

    dark = sum(sum(row) for row in matrix)
    score += int(abs(dark / (size * size) * 100 - 50) / 5) * 10
    return score


def encode(payload: str) -> list[list[bool]]:
    """Encode ASCII *payload* in byte mode with EC-M and return a module matrix."""
    if not isinstance(payload, str):
        raise TypeError("QR payload must be a string")
    try:
        payload.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("QR payload must be printable ASCII") from exc
    if not payload:
        raise ValueError("QR payload must not be empty")

    version = _select_version(len(payload))
    data = _interleave(payload, version)
    best_mask = 0
    best_penalty = None
    best_matrix = None
    for mask in range(8):
        matrix = _base_matrix(version)
        _map_data(matrix, data, mask)
        penalty = _penalty(matrix)
        if best_penalty is None or penalty < best_penalty:
            best_mask = mask
            best_penalty = penalty
            best_matrix = matrix
    assert best_matrix is not None
    _write_format_info(best_matrix, version, best_mask)
    _write_version_info(best_matrix, version)
    return [[bool(module) for module in row] for row in best_matrix]


def wifi_payload(ssid: str, password: str, *, hidden: bool = False) -> str:
    """Build a scannable Wi-Fi credential payload with required escaping."""
    if not isinstance(ssid, str) or not isinstance(password, str):
        raise TypeError("SSID and password must be strings")

    def escape(value: str) -> str:
        return (value.replace("\\", "\\\\")
                   .replace(",", "\\,")
                   .replace(";", "\\;")
                   .replace(":", "\\:")
                   .replace('"', '\\"'))

    suffix = ";H:true" if hidden else ""
    return f"WIFI:T:WPA;S:{escape(ssid)};P:{escape(password)}{suffix};;"


def to_surface(matrix: list[list[bool]], module_px: int = 4, quiet: int = 2,
               dark=(0, 0, 0), light=(255, 255, 255)) -> pygame.Surface:
    """Render a QR matrix to an opaque pygame Surface."""
    if (not isinstance(matrix, list) or not matrix
            or any(len(row) != len(matrix) or not all(type(value) is bool for value in row)
                   for row in matrix)):
        raise ValueError("invalid QR module matrix")
    if (not isinstance(module_px, int) or isinstance(module_px, bool)
            or not 1 <= module_px <= 32 or quiet < 0):
        raise ValueError("invalid QR surface parameters")
    size = len(matrix)
    side = (size + 2 * quiet) * module_px
    surface = pygame.Surface((side, side))
    surface.fill(light)
    for row in range(size):
        for col in range(size):
            if matrix[row][col]:
                x = (col + quiet) * module_px
                y = (row + quiet) * module_px
                pygame.draw.rect(surface, dark, (x, y, module_px, module_px))
    return surface
