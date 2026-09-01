"""Keccak-256 against published vectors, and against a live chain's own logs.

The failure this guards against is silent. `hashlib.sha3_256` differs from
Keccak only in one padding byte, so a wrong implementation still returns a
plausible 32-byte value — it just never matches a topic, `eth_getLogs` returns
nothing, and the collector reports a chain where nothing is happening.

The last two cases are the ones that matter. They are signatures whose hashes
were matched against logs read from Robinhood Chain: the values below are what
that chain actually puts in `topics[0]`, so they check the implementation
against reality rather than against itself.
"""

from __future__ import annotations

from app.core.keccak import event_topic, function_selector, keccak256

# -- the published vectors --------------------------------------------------


def test_the_empty_string() -> None:
    assert (
        keccak256(b"").hex()
        == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    )


def test_abc() -> None:
    assert (
        keccak256(b"abc").hex()
        == "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"
    )


def test_it_is_not_sha3() -> None:
    """The one-byte padding difference, stated as a test.

    SHA-3-256 of the empty string is a7ff…; Keccak-256 is c5d2…. An
    implementation that returned the first would be wrong in a way nothing
    downstream could detect.
    """
    import hashlib

    assert keccak256(b"") != hashlib.sha3_256(b"").digest()


def test_a_message_longer_than_one_block() -> None:
    """136 bytes is the rate, so 200 bytes runs the absorb loop twice.

    This one is a regression pin, not an independent vector: the value is what
    this implementation produces, kept so a refactor of the permutation cannot
    change it quietly. The independent checks are the four around it — two
    published vectors and two topics matched against a live chain — and they
    are what establish the implementation is right in the first place.
    """
    assert (
        keccak256(b"a" * 200).hex()
        == "96ea54061def936c4be90b518992fdc6f12f535068a256229aca54267b4d084d"
    )
    assert (
        keccak256(bytes(range(256)) * 2).hex()
        == "f55ba327291604f0e5be6651752398b7be2331aad65f5763ce067df95cc13be1"
    )


# -- against a real chain ---------------------------------------------------


def test_the_erc20_transfer_topic() -> None:
    """The most-emitted topic on any EVM chain. Wrong here, wrong everywhere."""
    assert event_topic("Transfer(address,address,uint256)") == (
        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    )


def test_the_launchpad_topic_matches_the_chain() -> None:
    """Read from Robinhood Chain, not from a document.

    A chain-wide `eth_getLogs` on this topic returned launches from a contract
    that then answered `graduationStatus` for each token it named. That round
    trip is what makes this constant a measurement rather than a copy.
    """
    assert event_topic(
        "TokenLaunched(address,address,address,address,address,"
        "uint256,uint256,uint256,uint256,uint256)"
    ) == "0xdb51ea9ad51ab453a65a4cb7e60c3cb378c9501bb002609f8f97778fb6c4235a"


def test_the_graduation_selector_matches_the_chain() -> None:
    assert function_selector("graduationStatus(address)") == "0x98d652f1"
