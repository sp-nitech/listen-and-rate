<?php

/**
 * Generates and verifies the opaque token that hides which stimulus ABX's
 * hidden "X" reference actually is. Pure PHP mirror of
 * listen_and_rate/x_token.py - see that file for the full rationale
 * (blinding X's identity without server-side session state, defeating
 * casual inspection of URLs/JSON, not a listener deliberately dumping page
 * JS state).
 */

/** Compute the opaque token asserting that X actually matches $matchedId. */
function commit_x(string $idA, string $idB, string $matchedId, string $secret): string
{
    $sorted = [$idA, $idB];
    sort($sorted, SORT_STRING);
    $msg = $sorted[0] . '|' . $sorted[1] . '|' . $matchedId;
    return substr(hash_hmac('sha256', $msg, $secret), 0, 20);
}

/** Return whichever of $idA/$idB $xToken asserts, or null if neither matches. */
function resolve_x(string $idA, string $idB, string $xToken, string $secret): ?string
{
    if (hash_equals(commit_x($idA, $idB, $idA, $secret), $xToken)) {
        return $idA;
    }
    if (hash_equals(commit_x($idA, $idB, $idB, $secret), $xToken)) {
        return $idB;
    }
    return null;
}
