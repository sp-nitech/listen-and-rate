<?php

use PHPUnit\Framework\TestCase;

require_once __DIR__ . '/../x_token.php';
require_once __DIR__ . '/../audio_x.php';

/** Unit tests for the pure helper functions in audio_x.php (not the HTTP entry point). */
final class AudioXTest extends TestCase
{
    public function testBuildStimulusUrlMapMapsIdToAudioUrl(): void
    {
        $map = build_stimulus_url_map([
            ['id' => 'a1', 'label' => null, 'audio_url' => 'a/u1.wav'],
            ['id' => 'b1', 'label' => null, 'audio_url' => 'b/u1.wav'],
        ]);
        $this->assertSame(['a1' => 'a/u1.wav', 'b1' => 'b/u1.wav'], $map);
    }

    // -- resolve_byte_range --------------------------------------------------

    public function testResolveByteRangeNoHeaderReturnsFullFileStatus200(): void
    {
        $this->assertSame([0, 999, 200], resolve_byte_range(null, 1000));
    }

    public function testResolveByteRangeStartEndReturnsRequestedSlice(): void
    {
        $this->assertSame([100, 199, 206], resolve_byte_range('bytes=100-199', 1000));
    }

    public function testResolveByteRangeOpenEndedReturnsFromStartToEof(): void
    {
        $this->assertSame([500, 999, 206], resolve_byte_range('bytes=500-', 1000));
    }

    public function testResolveByteRangeSuffixReturnsLastNBytes(): void
    {
        // "bytes=-500" means "the last 500 bytes", per RFC 7233 §2.1 - not
        // "bytes 0-500", which is what a naive `(int) m[2]` assignment to
        // $end would produce.
        $this->assertSame([500, 999, 206], resolve_byte_range('bytes=-500', 1000));
    }

    public function testResolveByteRangeSuffixLargerThanFileClampsToStart(): void
    {
        $this->assertSame([0, 999, 206], resolve_byte_range('bytes=-5000', 1000));
    }

    public function testResolveByteRangeClampsEndToFileSize(): void
    {
        // "bytes=0-999999" on a 1000-byte file must not declare a
        // Content-Length larger than what is actually streamed.
        $this->assertSame([0, 999, 206], resolve_byte_range('bytes=0-999999', 1000));
    }

    public function testResolveByteRangeStartBeyondEofReturns416(): void
    {
        // RFC 7233 §4.4: a start position at/past EOF is unsatisfiable.
        [, , $status] = resolve_byte_range('bytes=1000-', 1000);
        $this->assertSame(416, $status);
        [, , $status] = resolve_byte_range('bytes=5000-6000', 1000);
        $this->assertSame(416, $status);
    }

    public function testResolveByteRangeSuffixZeroReturns416(): void
    {
        // "bytes=-0" (the last 0 bytes) is unsatisfiable per RFC 7233.
        [, , $status] = resolve_byte_range('bytes=-0', 1000);
        $this->assertSame(416, $status);
    }

    public function testResolveByteRangeStartGreaterThanEndIgnoresHeader(): void
    {
        // A syntactically valid but inverted range (start > end) is treated
        // as if no Range header were sent, per RFC 7233's "ignore invalid
        // ranges" guidance - the whole file with status 200.
        $this->assertSame([0, 999, 200], resolve_byte_range('bytes=500-100', 1000));
    }
}
