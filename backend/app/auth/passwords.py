"""argon2id hashing, and the only place a password is ever generated.

argon2-cffi's PasswordHasher is argon2id at its defaults, which is what §4's
`password_hash -- argon2id` comment calls for. The defaults are deliberately not
tuned down: a login happens a handful of times per round, so the ~50 ms cost is
invisible to a human and expensive to an attacker holding a stolen database.
"""
from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

# No i, l, o, 0 or 1. These get read off a screen and typed by hand under time
# pressure, and a character you have to squint at is a support call.
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"

# Verified against on the username-not-found path so a failed login costs the
# same either way. Without it, "unknown user" returns in microseconds and "wrong
# password" in ~50 ms, which is a username oracle anyone can time.
_DUMMY_HASH = _hasher.hash("scavenger-no-such-user")


def hash_password(plaintext: str) -> str:
    return _hasher.hash(plaintext)


def verify_password(password_hash: str, plaintext: str) -> bool:
    try:
        _hasher.verify(password_hash, plaintext)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def burn_time() -> None:
    """Spend a verification's worth of CPU on nothing. See _DUMMY_HASH."""
    verify_password(_DUMMY_HASH, "scavenger-no-such-user-either")


def generate_password(groups: int = 3, size: int = 4) -> str:
    """`tr4m-vixu-8k2p` — the shape redesign spec §7.2's examples use.

    Twelve characters from a 31-character alphabet is about 59 bits: far more
    than a competition account behind a login form needs, and short enough to
    read aloud.
    """
    return "-".join(
        "".join(secrets.choice(_ALPHABET) for _ in range(size)) for _ in range(groups)
    )
