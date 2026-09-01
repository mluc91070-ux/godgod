"""Keccak-256, in the standard library only.

Ethereum's event topics and function selectors are Keccak-256 of a signature
string. `hashlib.sha3_256` is *not* Keccak: NIST changed the padding byte
between Keccak's submission and the SHA-3 standard, so the two differ on every
input. Using sha3 here would produce topic filters that match nothing, silently
— `eth_getLogs` would return an empty list and the collector would report a
quiet chain.

Sixty lines rather than a dependency. The alternative is pulling in a crypto
package for one hash on a service whose whole point is that it is cheap to run,
and `docs/COST_CONTROL.md` is about more than money.

Correctness is not asserted, it is tested: `tests/test_keccak.py` checks the
published vectors for the empty string and "abc", plus two real Ethereum
signatures whose hashes are matched against logs read from a live chain.
"""

from __future__ import annotations

_MASK = (1 << 64) - 1

_ROTATIONS = (
    1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 2, 14,
    27, 41, 56, 8, 25, 43, 62, 18, 39, 61, 20, 44,
)
_LANES = (
    10, 7, 11, 17, 18, 3, 5, 16, 8, 21, 24, 4,
    15, 23, 19, 13, 12, 2, 20, 14, 22, 9, 6, 1,
)
_ROUND_CONSTANTS = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)

_RATE = 136
"""Bytes absorbed per permutation for a 256-bit digest: 200 - 2 * 32."""


def _rotate(value: int, shift: int) -> int:
    return ((value << shift) | (value >> (64 - shift))) & _MASK


def _permute(state: list[int]) -> list[int]:
    for round_constant in _ROUND_CONSTANTS:
        # theta
        columns = [
            state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20]
            for x in range(5)
        ]
        diff = [
            columns[(x - 1) % 5] ^ _rotate(columns[(x + 1) % 5], 1) for x in range(5)
        ]
        for x in range(5):
            for y in range(0, 25, 5):
                state[x + y] ^= diff[x]

        # rho and pi
        carried = state[1]
        for index in range(24):
            lane = _LANES[index]
            state[lane], carried = _rotate(carried, _ROTATIONS[index]), state[lane]

        # chi
        for y in range(0, 25, 5):
            row = state[y : y + 5]
            for x in range(5):
                state[y + x] = row[x] ^ ((~row[(x + 1) % 5]) & _MASK & row[(x + 2) % 5])

        # iota
        state[0] ^= round_constant
    return state


def keccak256(data: bytes) -> bytes:
    """The original Keccak padding (0x01), not SHA-3's (0x06)."""
    state = [0] * 25
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % _RATE:
        padded.append(0x00)
    padded[-1] |= 0x80

    for offset in range(0, len(padded), _RATE):
        block = padded[offset : offset + _RATE]
        for lane in range(_RATE // 8):
            state[lane] ^= int.from_bytes(block[lane * 8 : lane * 8 + 8], "little")
        state = _permute(state)

    return b"".join(state[lane].to_bytes(8, "little") for lane in range(4))


def event_topic(signature: str) -> str:
    """`Transfer(address,address,uint256)` -> its `topics[0]`, 0x-prefixed.

    The signature is written out in full wherever it is used rather than a hash
    being pasted in, because a 32-byte constant cannot be read and cannot be
    checked. This turns it back into the constant.
    """
    return "0x" + keccak256(signature.encode()).hex()


def function_selector(signature: str) -> str:
    """`balanceOf(address)` -> the first four bytes of its hash, 0x-prefixed."""
    return "0x" + keccak256(signature.encode()).hex()[:8]
