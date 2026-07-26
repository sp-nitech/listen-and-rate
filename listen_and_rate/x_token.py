"""Generates and verifies the opaque token hiding ABX's hidden "X" reference.

X's audio is a duplicate of either stimulus_ids[0] or [1]; the client must
not be able to read off which one from the config response or the audio
URL. Rather than storing per-session state server-side (this app is
otherwise fully stateless - a "session" is just whatever the client
remembers and echoes back at submit time), the ground truth is encoded into
an HMAC-signed token the client passes through unread, and independently
re-derived at submit/audio-fetch time from the same (public) pair of ids
plus a server-side secret the client never sees.

This defeats casual inspection (identical URLs, readable JSON fields) -
the same threat model already accepted for MOS/AB's blinding - not a
listener deliberately dumping page JS state, which is out of scope.

Nor does it hide X's *size*. X is served as a byte-for-byte copy of one of
the pair, so its response length equals that stimulus's whenever the two
differ in length - as they may when two systems render the same item at
different durations. The same holds for the <audio> element's own duration
property, which the browser knows whatever the UI chooses to display (see
_syncAudioSrcs, which withholds X's length from the time bar for the
readout, not for this). Closing that would mean padding or re-encoding
every clip, which is not worth it here: the listener is assumed to be
cooperating with the experiment, not attacking it.
"""

from __future__ import annotations

import hashlib
import hmac


def commit(id_a: str, id_b: str, matched_id: str, secret: bytes) -> str:
    """Compute the opaque token asserting that X actually matches matched_id.

    id_a/id_b are sorted before hashing, so callers don't need to agree on a
    canonical order (e.g. a client echoing stimulus_ids back in the opposite
    order it received them still resolves correctly).
    """
    a, b = sorted((id_a, id_b))
    msg = f"{a}|{b}|{matched_id}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()[:20]


def resolve(id_a: str, id_b: str, x_token: str, secret: bytes) -> str | None:
    """Return whichever of id_a/id_b x_token asserts, or None if neither matches."""
    if hmac.compare_digest(commit(id_a, id_b, id_a, secret), x_token):
        return id_a
    if hmac.compare_digest(commit(id_a, id_b, id_b, secret), x_token):
        return id_b
    return None
