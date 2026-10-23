"""Plain-language verdict labels.

The status codes (`VERIFIED`, `DUPLICATE`, ...) stay exactly as they are: they are
what the tests, the history rows and the API contract use. These labels are the
words a seller reads, derived from the status plus which check produced it,
because one status (`SUSPECTED_FAKE`) covers three different seller messages.

`LIKELY_EDITED` is no longer issued: since 2026-10-23 an uncalibrated image score is
a `warning` on the verdict rather than a `SUSPECTED_FAKE` of its own, so nothing in
`verify.py` passes the `forensic` reason any more. The mapping stays because rows
written before that change carry the word in `verifications.label`, and a seller
opening an older database should read what the machine said at the time.
"""
from typing import Optional

VERIFIED = "Verified"
REUSED = "Reused"
NO_MATCH = "Doesn't match"
LIKELY_EDITED = "Likely edited"
UNCONFIRMED = "Can't confirm yet"

# Reason codes the verdict engine passes for a SUSPECTED_FAKE.
MISMATCH = "mismatch"
FORENSIC = "forensic"


def label_for(status: str, reason: Optional[str] = None) -> str:
    if status == "VERIFIED":
        return VERIFIED
    if status == "DUPLICATE":
        return REUSED
    if status == "PENDING_MATCH":
        return UNCONFIRMED
    if status == "SUSPECTED_FAKE":
        if reason == MISMATCH:
            return NO_MATCH
        if reason == FORENSIC:
            return LIKELY_EDITED
        # Unreadable image or no reference to match on: nothing was contradicted,
        # so the honest word is that it is unconfirmed, not that it is fake.
        return UNCONFIRMED
    return UNCONFIRMED
