"""The one random number generator the package draws from.

Every draw made here is a listener-facing randomization: which subset of the
stimuli a listener is given, what order it is presented in, which side of a
pair is shown first, and which stimulus the hidden X duplicates. The last of
those is the reason this is `SystemRandom` and not the `random` module's
default Mersenne Twister: x_token.py blinds the ABX ground truth behind an
HMAC, which buys nothing if the choice it hides comes from a stream an
observer can reconstruct from earlier trials.

The cost is one `os.urandom` read per draw - a few hundred per request here,
which does not show up next to serving the audio.

frontend/config.php is the mirror of this file: it draws only through PHP's
`random_int()`, which is the same guarantee. Both backends must randomize the
same way, or the same experiment would be blinded differently depending on
how it happens to be deployed.
"""

from __future__ import annotations

import random

rng = random.SystemRandom()
