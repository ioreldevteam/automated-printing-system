"""Pure-Python, zero-dependency barcode and QR code generators.

Provides:
- encode_code128(data: str) -> str: Returns binary string of bars ('1') and spaces ('0')
- generate_qr_matrix(text: str) -> list[list[bool]]: Returns 2D boolean grid of QR modules
"""
from __future__ import annotations

# Code 128 pattern table (107 patterns, 11 modules each; stop code 13 modules)
_CODE128_PATTERNS = [
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
    "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
    "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
    "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
    "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
    "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
    "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
    "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
    "114131", "311141", "411131", "211412", "211214", "211232", "2331112"
]


def encode_code128(data: str) -> str:
    """Encode ASCII data using Code 128 (Subset B). Returns a string of '1's (bars) and '0's (spaces)."""
    # Start Code B = 104
    values = [104]
    checksum = 104
    for i, ch in enumerate(data):
        val = ord(ch) - 32
        if 0 <= val <= 95:
            values.append(val)
            checksum += val * (i + 1)
        else:
            values.append(0)
    values.append(checksum % 103)
    values.append(106)  # Stop code = 106

    modules = []
    for v in values:
        pat = _CODE128_PATTERNS[v]
        is_bar = True
        for digit in pat:
            width = int(digit)
            modules.append(("1" if is_bar else "0") * width)
            is_bar = not is_bar
    return "".join(modules)


class QRCodeGenerator:
    """Self-contained, pure-Python QR Code generator supporting Version 1-4 with Error Correction M."""

    ALIGNMENT = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26]}
    CONFIG = {
        1: (21, 26, 10, 16),
        2: (25, 44, 16, 28),
        3: (29, 70, 26, 44),
        4: (33, 100, 36, 64),
    }

    GF_EXP = [0] * 512
    GF_LOG = [0] * 256
    _initialized = False

    @classmethod
    def _init_gf(cls) -> None:
        if cls._initialized:
            return
        x = 1
        for i in range(255):
            cls.GF_EXP[i] = x
            cls.GF_LOG[x] = i
            x <<= 1
            if x >= 256:
                x ^= 0x11D
        for i in range(255, 512):
            cls.GF_EXP[i] = cls.GF_EXP[i - 255]
        cls._initialized = True

    @classmethod
    def gf_mul(cls, a: int, b: int) -> int:
        if a == 0 or b == 0:
            return 0
        return cls.GF_EXP[cls.GF_LOG[a] + cls.GF_LOG[b]]

    @classmethod
    def rs_poly(cls, n: int) -> list[int]:
        poly = [1]
        for i in range(n):
            next_poly = [0] * (len(poly) + 1)
            for j in range(len(poly)):
                next_poly[j] ^= cls.gf_mul(poly[j], cls.GF_EXP[i])
                next_poly[j + 1] ^= poly[j]
            poly = next_poly
        return poly

    @classmethod
    def rs_encode(cls, data: list[int], ec_count: int) -> list[int]:
        poly = cls.rs_poly(ec_count)
        msg = list(data) + [0] * ec_count
        for i in range(len(data)):
            coeff = msg[i]
            if coeff != 0:
                for j in range(len(poly)):
                    msg[i + j] ^= cls.gf_mul(poly[j], coeff)
        return msg[len(data):]

    @classmethod
    def generate_matrix(cls, text: str) -> list[list[bool]]:
        cls._init_gf()
        raw_bytes = text.encode("utf-8")
        version = 1
        for v in (1, 2, 3, 4):
            _size, _total_cw, _ec_cw, data_cw = cls.CONFIG[v]
            if len(raw_bytes) <= data_cw - 3:
                version = v
                break
        else:
            version = 4

        size, _total_cw, ec_cw, data_cw = cls.CONFIG[version]

        bits = "0100" + f"{len(raw_bytes):08b}"
        for b in raw_bytes:
            bits += f"{b:08b}"
        rem = (data_cw * 8) - len(bits)
        bits += "0" * min(4, rem)
        if len(bits) % 8 != 0:
            bits += "0" * (8 - (len(bits) % 8))

        pad_bytes = [0xEC, 0x11]
        pad_idx = 0
        data_bytes = [int(bits[i:i+8], 2) for i in range(0, len(bits), 8)]
        while len(data_bytes) < data_cw:
            data_bytes.append(pad_bytes[pad_idx])
            pad_idx = (pad_idx + 1) % 2

        ec_bytes = cls.rs_encode(data_bytes, ec_cw)
        all_codewords = data_bytes + ec_bytes

        matrix: list[list[bool | None]] = [[None] * size for _ in range(size)]

        # 1. Finder patterns
        def set_finder(r0: int, c0: int) -> None:
            for r in range(7):
                for c in range(7):
                    val = (r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4))
                    matrix[r0 + r][c0 + c] = val
            for i in range(8):
                if 0 <= r0 + 7 < size and 0 <= c0 + i < size: matrix[r0 + 7][c0 + i] = False
                if 0 <= r0 + i < size and 0 <= c0 + 7 < size: matrix[r0 + i][c0 + 7] = False
                if 0 <= r0 - 1 < size and 0 <= c0 + i < size: matrix[r0 - 1][c0 + i] = False
                if 0 <= r0 + i < size and 0 <= c0 - 1 < size: matrix[r0 + i][c0 - 1] = False

        set_finder(0, 0)
        set_finder(0, size - 7)
        set_finder(size - 7, 0)

        # 2. Timing patterns
        for i in range(8, size - 8):
            if matrix[6][i] is None: matrix[6][i] = (i % 2 == 0)
            if matrix[i][6] is None: matrix[i][6] = (i % 2 == 0)

        # 3. Alignment patterns for V2+
        align = cls.ALIGNMENT[version]
        for r in align:
            for c in align:
                if matrix[r][c] is not None:
                    continue
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        matrix[r + dr][c + dc] = (max(abs(dr), abs(dc)) != 1)

        # 4. Dark module
        matrix[4 * version + 9][8] = True

        # 5. Format info placeholder
        for i in range(9):
            if matrix[8][i] is None: matrix[8][i] = False
            if matrix[i][8] is None: matrix[i][8] = False
        for i in range(8):
            if matrix[8][size - 1 - i] is None: matrix[8][size - 1 - i] = False
            if matrix[size - 1 - i][8] is None: matrix[size - 1 - i][8] = False

        # 6. Place data with mask 0: (r + c) % 2 == 0
        bit_idx = 0
        all_bits = "".join(f"{b:08b}" for b in all_codewords)

        col = size - 1
        upward = True
        while col > 0:
            if col == 6:
                col -= 1
            rows = range(size - 1, -1, -1) if upward else range(size)
            for r in rows:
                for c in (col, col - 1):
                    if matrix[r][c] is None:
                        val = (all_bits[bit_idx] == "1") if bit_idx < len(all_bits) else False
                        bit_idx += 1
                        if (r + c) % 2 == 0:
                            val = not val
                        matrix[r][c] = val
            col -= 2
            upward = not upward

        # 7. Format info for Level M, Mask 0
        f_bits = [1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0]
        for i in range(6): matrix[8][i] = bool(f_bits[i])
        matrix[8][7] = bool(f_bits[6])
        matrix[8][8] = bool(f_bits[7])
        matrix[7][8] = bool(f_bits[8])
        for i in range(6): matrix[5 - i][8] = bool(f_bits[9 + i])

        for i in range(7): matrix[size - 1 - i][8] = bool(f_bits[i])
        for i in range(8): matrix[8][size - 8 + i] = bool(f_bits[7 + i])

        return [[bool(cell) for cell in row] for row in matrix]


def generate_qr_matrix(text: str) -> list[list[bool]]:
    """Return a 2D boolean matrix where True represents a dark module."""
    return QRCodeGenerator.generate_matrix(text)
