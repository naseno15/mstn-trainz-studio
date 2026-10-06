"""Trainz CDP BINARY tag LZSS decompress (and level-0 store helpers).

Faithful port of emmaworley/cdptool 2.0.0 (MIT) for MSTN Trainz Studio.
See cdptool ``lzss.rs``, ``huffman.rs``, and ``bitstream.rs``.
"""

from __future__ import annotations

import struct

LENGTH_TABLE: list[tuple[int, int]] = [
    (0, 0),
    (1, 0),
    (2, 0),
    (3, 0),
    (4, 0),
    (5, 1),
    (7, 1),
    (9, 2),
    (13, 2),
    (17, 3),
    (25, 3),
    (33, 4),
    (49, 4),
    (65, 5),
    (97, 5),
    (129, 7),
]

EOF_SYMBOL = 272
NUM_LIT_SYMBOLS = 273

LEAF_FLAG = 0x8000
REBUILD_THRESHOLD = 0x7FFF
UNPROCESSED = 0xFFFFFFFE


class BitReader:
    """LSB-first bit reader; past end reads as 0."""

    __slots__ = ("_data", "len_bits", "pos")

    def __init__(self, data: bytes) -> None:
        self._data = data
        self.len_bits = len(data) * 8
        self.pos = 0

    def read_bit(self) -> int:
        if self.pos >= self.len_bits:
            return 0
        byte_idx = self.pos // 8
        bit_idx = self.pos % 8
        self.pos += 1
        return (self._data[byte_idx] >> bit_idx) & 1

    def read_bits(self, n: int) -> int:
        if n == 0:
            return 0
        available = min(self.len_bits - self.pos, n)
        self.pos += available
        if available == 0:
            return 0
        result = 0
        start = self.pos - available
        for i in range(available):
            byte_idx = (start + i) // 8
            bit_idx = (start + i) % 8
            if (self._data[byte_idx] >> bit_idx) & 1:
                result |= 1 << i
        return result


class AdaptiveHuffmanTree:
    def __init__(self, num_symbols_raw: int) -> None:
        n = (num_symbols_raw + 1) & 0xFFE
        total = n * 2 - 1
        root = total - 1
        self.num_leaves = n
        self.total_nodes = total
        self.root_idx = root
        self.freq = [0] * total
        self.parent = [0] * total
        self.child = [0] * total
        self.sym_to_node = [0] * n
        for i in range(n):
            self.freq[i] = 1
            self.child[i] = i | LEAF_FLAG
            self.sym_to_node[i] = i
        j = 0
        for k in range(n, total):
            self.freq[k] = self.freq[j] + self.freq[j + 1]
            self.child[k] = j
            self.parent[j] = k
            self.parent[j + 1] = k
            j += 2
        self.parent[root] = root

    def decode(self, br: BitReader) -> int:
        v = self.child[self.root_idx]
        depth = 0
        while (v & LEAF_FLAG) == 0:
            idx = v + br.read_bit()
            if idx >= self.total_nodes:
                raise ValueError("tree index out of bounds")
            v = self.child[idx]
            depth += 1
            if depth > 50:
                raise ValueError("tree decode depth exceeded")
        sym = v & ~LEAF_FLAG
        self.update(sym)
        return sym

    def update(self, symbol: int) -> None:
        if self.freq[self.root_idx] > REBUILD_THRESHOLD:
            self.rebuild()

        i = self.sym_to_node[symbol]

        while True:
            self.freq[i] += 1
            f = self.freq[i]

            if i + 1 < self.total_nodes and self.freq[i + 1] < f:
                j = i + 2
                while j < self.total_nodes and self.freq[j] < f:
                    j += 1
                j -= 1

                ci = self.child[i]
                cj = self.child[j]

                if (cj & LEAF_FLAG) == 0:
                    self.parent[cj] = i
                    self.parent[cj + 1] = i
                else:
                    self.sym_to_node[cj & ~LEAF_FLAG] = i

                if (ci & LEAF_FLAG) == 0:
                    self.parent[ci] = j
                    self.parent[ci + 1] = j
                else:
                    self.sym_to_node[ci & ~LEAF_FLAG] = j

                self.freq[i], self.freq[j] = self.freq[j], f
                self.child[i], self.child[j] = self.child[j], self.child[i]

                i = j

            p = self.parent[i]
            if p == i or p == self.root_idx:
                break
            i = p

        self.freq[self.root_idx] += 1

    def rebuild(self) -> None:
        root_idx = self.root_idx
        remaining_leaves = self.num_leaves

        for i in range(root_idx):
            if self.child[i] & LEAF_FLAG:
                self.freq[i] = (self.freq[i] + 1) >> 1
            self.parent[i] = UNPROCESSED
        self.parent[root_idx] = UNPROCESSED

        pair_scan = 0
        node_scan = 0

        while True:
            found = False
            while pair_scan < root_idx:
                if self.parent[pair_scan] == UNPROCESSED:
                    found = True
                    break
                pair_scan += 1
            if not found or pair_scan >= root_idx:
                self.parent[root_idx] = 0xFFFFFFFF
                return

            left = pair_scan
            right = pair_scan + 1
            pair_scan += 2

            while node_scan <= root_idx:
                if self.child[node_scan] & LEAF_FLAG:
                    remaining_leaves -= 1
                elif self.parent[node_scan] == UNPROCESSED:
                    break
                node_scan += 1

            slot = node_scan
            node_scan += 1
            next_scan = node_scan

            new_freq = self.freq[left] + self.freq[right]
            insert_at = slot

            if slot > 0 and self.freq[slot - 1] > new_freq:
                scan = slot - 1
                while scan >= 0 and self.freq[scan] > new_freq:
                    c = self.child[scan]
                    if (c & LEAF_FLAG) == 0:
                        self.parent[c] += 1
                        self.parent[c + 1] += 1
                    else:
                        self.sym_to_node[c & ~LEAF_FLAG] += 1
                    scan -= 1
                pos = scan + 1
                count = slot - pos
                if count > 0:
                    self.freq[pos + 1 : pos + 1 + count] = self.freq[pos : pos + count]
                    self.child[pos + 1 : pos + 1 + count] = self.child[pos : pos + count]
                insert_at = pos
            elif remaining_leaves > 0:
                scan_pos = next_scan
                dst = slot
                nxt = next_scan

                while True:
                    while scan_pos < root_idx:
                        if self.child[scan_pos] & LEAF_FLAG:
                            break
                        scan_pos += 1
                    if scan_pos >= root_idx or self.freq[scan_pos] >= new_freq:
                        break
                    self.freq[dst] = self.freq[scan_pos]
                    self.child[dst] = self.child[scan_pos]
                    self.parent[dst] = UNPROCESSED
                    self.sym_to_node[self.child[scan_pos] & ~LEAF_FLAG] = dst

                    dst = nxt
                    self.child[scan_pos] = 0
                    nxt += 1
                    node_scan = nxt

                    remaining_leaves -= 1
                    if remaining_leaves <= 0:
                        break
                    scan_pos += 1
                insert_at = dst

            self.freq[insert_at] = new_freq
            self.child[insert_at] = left
            self.parent[left] = insert_at
            self.parent[right] = insert_at


def mode_params(mode: int) -> tuple[int, int, int]:
    if mode == 0:
        return (8, 16, 4)
    if mode == 1:
        return (12, 64, 6)
    if mode == 2:
        return (14, 64, 8)
    raise ValueError(f"invalid compression mode {mode}")


def _copy_match(output: bytearray, distance: int, match_len: int, max_size: int) -> None:
    for _ in range(match_len):
        if len(output) >= max_size:
            break
        if distance <= len(output):
            output.append(output[len(output) - distance])
        else:
            output.append(0)


def _decompress_huffman(
    stream: bytes,
    uncomp_size: int,
    dist_bits_total: int,
    num_dist_symbols: int,
    dist_extra_bits: int,
) -> bytes:
    dist_mask = (1 << dist_bits_total) - 1
    lit_tree = AdaptiveHuffmanTree(NUM_LIT_SYMBOLS)
    dist_tree = AdaptiveHuffmanTree(num_dist_symbols)
    br = BitReader(stream)
    output = bytearray()

    while len(output) < uncomp_size:
        sym = lit_tree.decode(br)

        if sym == EOF_SYMBOL:
            break
        if sym > EOF_SYMBOL:
            raise ValueError(f"invalid symbol {sym}")

        if sym < 256:
            output.append(sym)
        else:
            base, extra = LENGTH_TABLE[sym - 256]
            extra_val = br.read_bits(extra) if extra > 0 else 0
            match_len = base + extra_val + 3

            dist_sym = dist_tree.decode(br)
            dist_extra = br.read_bits(dist_extra_bits)
            distance = ((dist_sym << dist_extra_bits) | dist_extra) & dist_mask
            distance = 1 if distance == 0 else distance

            _copy_match(output, distance, match_len, uncomp_size)

    del output[uncomp_size:]
    return bytes(output)


def _u32_shl1(mask: int) -> int:
    """``mask <<= 1`` as Rust u32 (overflow → 0). Python ints never wrap."""
    return (mask << 1) & 0xFFFFFFFF


class _FlagBits:
    """Continuous LSB-first flag stream in 32-bit words.

    Matches may span flag-word boundaries (Trainz mode-0). Aborting a match
    when ``mask==0`` desyncs payload bytes into the next flags word — that
    was garbling ``*.lm.txt`` / longer ``.gs`` after the first ~60 bytes.
    """

    __slots__ = ("_br", "flags", "mask")

    def __init__(self, br: BitReader) -> None:
        self._br = br
        self.flags = 0
        self.mask = 0

    def bit(self) -> int:
        if self.mask == 0:
            self.flags = self._br.read_bits(32)
            self.mask = 1
        bit = 1 if (self.flags & self.mask) else 0
        self.mask = _u32_shl1(self.mask)
        return bit


def _decompress_bitstream(
    stream: bytes,
    uncomp_size: int,
    dist_bits_total: int,
    dist_extra_bits: int,
) -> bytes:
    dist_mask = (1 << dist_bits_total) - 1
    if dist_bits_total < 16:
        len_overflow = (1 << (16 - dist_bits_total)) - 1
    else:
        len_overflow = 0
    offset_shift = min(dist_bits_total, 15)

    br = BitReader(stream)
    output = bytearray()
    fb = _FlagBits(br)

    # Mode 0 (8-bit distance): 1-bit flags + 3 inline length bits.
    # cdptool gates on dist_extra_bits==0 (dead — mode0 has extra=4); use
    # dist_bits_total==8. Flag bits must span words (see _FlagBits).
    if dist_bits_total == 8:
        while len(output) < uncomp_size:
            if fb.bit() == 0:
                output.append(br.read_bits(8) & 0xFF)
                continue
            len_code = 0
            for i in range(3):
                if fb.bit():
                    len_code |= 1 << i
            if len_code == 7:
                len_code = br.read_bits(8)
            distance = br.read_bits(8)
            distance = 1 if distance == 0 else distance
            _copy_match(output, distance, len_code + 3, uncomp_size)
    else:
        # Modes 1–2: 0,0 literal · 0,1 byte-run · 1 match (16-bit word)
        while len(output) < uncomp_size:
            if fb.bit() == 0:
                if fb.bit() == 0:
                    output.append(br.read_bits(8) & 0xFF)
                else:
                    run_len = (br.read_bits(8) & 0xFF) + 3
                    for _ in range(run_len):
                        if len(output) >= uncomp_size:
                            break
                        output.append(br.read_bits(8) & 0xFF)
            else:
                word = br.read_bits(16)
                distance = word & dist_mask
                len_code = (word >> offset_shift) & len_overflow
                if len_code == len_overflow:
                    len_code = br.read_bits(8)
                distance = 1 if distance == 0 else distance
                _copy_match(output, distance, len_code + 3, uncomp_size)

    del output[uncomp_size:]
    return bytes(output)


def decompress(comp_data: bytes, uncomp_size: int) -> bytes:
    """Decompress CDP LZSS; ``comp_data`` starts with mode/level header byte."""
    if not comp_data:
        raise ValueError("truncated input")

    first_byte = comp_data[0]
    mode = (first_byte >> 4) & 3
    level = first_byte & 0xF

    if level == 0:
        end = min(1 + uncomp_size, len(comp_data))
        return comp_data[1:end]

    dist_bits_total, num_dist_symbols, dist_extra_bits = mode_params(mode)

    if level < 7:
        return _decompress_bitstream(
            comp_data[1:], uncomp_size, dist_bits_total, dist_extra_bits
        )
    return _decompress_huffman(
        comp_data[1:],
        uncomp_size,
        dist_bits_total,
        num_dist_symbols,
        dist_extra_bits,
    )


def compress_stored(data: bytes, mode: int = 0) -> bytes:
    """Level 0 store: header byte (mode<<4 | 0) + raw data."""
    return bytes([(mode << 4) | 0]) + data


def make_binary_blob(data: bytes) -> bytes:
    """u32le uncompressed size + ``compress_stored(data)``."""
    return struct.pack("<I", len(data)) + compress_stored(data)


def decode_binary_blob(blob: bytes) -> bytes:
    """Read u32le size prefix and decompress the remainder."""
    if len(blob) < 4:
        raise ValueError("binary blob too short")
    uncomp_size = struct.unpack_from("<I", blob, 0)[0]
    return decompress(blob[4:], uncomp_size)


def decode_asset_text(data: bytes) -> str:
    """Decode Trainz text / .gs bytes (UTF-8, then CP932 for JP assets)."""
    if not data:
        return ""
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for enc in ("cp932", "shift_jis"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


# Mode-0 level-6 fixtures from KIHA CDPs — catch u32 mask wrap + flag-bit span.
_MODE0_GS_BLOB = bytes.fromhex(
    "450000000600000000696e636c75646520226b6968615f6d61696e2e677322"
    "0a0a636c617373206d730000ae01746e5f6c696e6b5f736372697074206973"
    "192e207b7d3b0a"
)
_MODE0_GS_TEXT = b'include "kiha_main.gs"\n\nclass mstn_link_script isclass kiha_main {};\n'
_MODE0_LM_BLOB = bytes.fromhex(
    "b4000000060000000076657273696f6e20312e300d0a6f6666736574203d2030"
    "2e30303b0d0a63616c6080002063506f696e1363656e746572156d756c746970"
    "6c6965720400dc0016311172656e6465724375744f66663c16616e696d6174f1"
    "0c105f5b081931351974746163686d4f093334010080005d6573682822312229"
    "0d0a7b0d0a20206e616d6521226361622e08000000696d22247d0d0a"
)
_MODE0_LM_TEXT = (
    b"version 1.0\r\noffset = 0.00;\r\ncalcPoint = center;\r\n"
    b"multiplier = 1;\r\nrenderCutOff = 0.01;\r\nanimationCutOff = 0.15;\r\n"
    b"attachmentCutOff = 0.001;\r\n\r\nmesh(\"1\")\r\n{\r\n  name = \"cab.im\";\r\n}\r\n"
)


def _self_check() -> None:
    sample = bytes(range(256)) * 2
    stored = compress_stored(sample, mode=2)
    assert decompress(stored, len(sample)) == sample

    blob = make_binary_blob(sample)
    assert decode_binary_blob(blob) == sample

    pattern = b"abc" * 40 + b"\x00" * 10
    blob2 = make_binary_blob(pattern)
    assert decode_binary_blob(blob2) == pattern

    assert decode_binary_blob(_MODE0_GS_BLOB) == _MODE0_GS_TEXT
    assert decode_binary_blob(_MODE0_LM_BLOB) == _MODE0_LM_TEXT
    assert decode_asset_text(_MODE0_GS_TEXT) == _MODE0_GS_TEXT.decode("utf-8")
    assert "\ufffd" not in decode_asset_text("日本語".encode("cp932"))


if __name__ == "__main__":
    _self_check()
    print("cdp_lzss self-check OK")
