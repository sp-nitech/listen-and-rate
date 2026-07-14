<?php

/**
 * audio_x.php - streams ABX's hidden "X" reference, resolving its opaque
 * commitment token server-side. Mirrors listen_and_rate/routers/audio.py's
 * GET /audio/x/{token} route and x_token.py's scheme.
 *
 * A/B's own audio is served as plain static files (this is a static PHP
 * deployment - no dynamic backend for regular playback). X can't work that
 * way: its underlying file is identical to whichever of a/b it matches, so
 * it must be resolved dynamically per request, and the response must not
 * reveal which one - a redirect to the real static URL would leak it via
 * the Location header/final URL, so the file is streamed directly instead.
 *
 * Like save.php/config.php, the functions below are pure (no superglobals,
 * no output) so PHPUnit can exercise them directly; only the bottom guard
 * touches superglobals/output, and only when this file is executed directly.
 */

require_once __DIR__ . '/x_token.php';

/** Build id => audio_url from config_data.php's stimuli list. */
function build_stimulus_url_map(array $stimuli): array
{
    $map = [];
    foreach ($stimuli as $s) {
        $map[$s['id']] = $s['audio_url'];
    }
    return $map;
}

const ABX_AUDIO_MEDIA_TYPES = [
    'wav' => 'audio/wav',
    'mp3' => 'audio/mpeg',
    'flac' => 'audio/flac',
    'ogg' => 'audio/ogg',
    'm4a' => 'audio/mp4',
];

/**
 * Parse an HTTP Range header into [start, end, status], matching RFC 7233's
 * three range forms: "bytes=start-end", "bytes=start-" (start to EOF), and
 * "bytes=-N" (suffix: the last N bytes) - matching the semantics Starlette's
 * FileResponse gives the dynamic backend's equivalent route. A missing/empty
 * header, one that doesn't match, or an inverted range (start > end) means
 * "the whole file" (status 200); a range starting at/past EOF or an empty
 * suffix ("bytes=-0") is unsatisfiable (status 416, per RFC 7233 §4.4);
 * an end past EOF is clamped to the last byte.
 *
 * @return array{0: int, 1: int, 2: int} [$start, $end, $status]
 */
function resolve_byte_range(?string $rangeHeader, int $size): array
{
    if (empty($rangeHeader) || !preg_match('/bytes=(\d*)-(\d*)/', $rangeHeader, $m)) {
        return [0, $size - 1, 200];
    }

    if ($m[1] === '' && $m[2] !== '') {
        // Suffix form: "bytes=-N" means the last N bytes of the file.
        $suffixLength = (int) $m[2];
        if ($suffixLength === 0) {
            return [0, $size - 1, 416];
        }
        return [max(0, $size - $suffixLength), $size - 1, 206];
    }

    $start = $m[1] !== '' ? (int) $m[1] : 0;
    $end = $m[2] !== '' ? min((int) $m[2], $size - 1) : $size - 1;
    if ($start >= $size) {
        return [0, $size - 1, 416];
    }
    if ($start > $end) {
        return [0, $size - 1, 200];
    }
    return [$start, $end, 206];
}

/**
 * Stream $path to the client with HTTP Range support, matching the
 * seek-ahead behavior FastAPI's FileResponse gives the dynamic backend's
 * equivalent /audio/x/{token} route.
 */
function stream_audio_with_range(string $path): void
{
    $size = filesize($path);
    [$start, $end, $status] = resolve_byte_range($_SERVER['HTTP_RANGE'] ?? null, $size);

    if ($status === 416) {
        // Unsatisfiable range: report the actual size, send no body (RFC 7233 §4.4).
        http_response_code(416);
        header("Content-Range: bytes */{$size}");
        return;
    }

    if ($status === 206) {
        header("Content-Range: bytes {$start}-{$end}/{$size}");
    }

    $ext = strtolower(pathinfo($path, PATHINFO_EXTENSION));
    $mediaType = ABX_AUDIO_MEDIA_TYPES[$ext] ?? 'audio/wav';

    http_response_code($status);
    header("Content-Type: {$mediaType}");
    header('Accept-Ranges: bytes');
    header('Content-Length: ' . ($end - $start + 1));

    $fp = fopen($path, 'rb');
    fseek($fp, $start);
    $remaining = $end - $start + 1;
    while ($remaining > 0 && !feof($fp)) {
        $chunk = fread($fp, min(8192, $remaining));
        echo $chunk;
        $remaining -= strlen($chunk);
    }
    fclose($fp);
}

// Only run when this file is executed directly as an HTTP entry point (see
// save.php for the same guard and rationale).
if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) {
    $data = include __DIR__ . '/config_data.php';
    $secret = hex2bin($data['x_secret'] ?? '');

    $token = $_GET['token'] ?? '';
    $a = $_GET['a'] ?? '';
    $b = $_GET['b'] ?? '';

    $stimulusId = resolve_x($a, $b, $token, $secret);
    if ($stimulusId === null) {
        http_response_code(404);
        exit;
    }

    $urlMap = build_stimulus_url_map($data['stimuli']);
    $audioUrl = $urlMap[$stimulusId] ?? null;
    $path = $audioUrl !== null ? __DIR__ . '/' . $audioUrl : null;
    if ($path === null || !is_file($path)) {
        http_response_code(404);
        exit;
    }

    stream_audio_with_range($path);
}
