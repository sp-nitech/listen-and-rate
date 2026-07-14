<?php

use PHPUnit\Framework\TestCase;

require_once __DIR__ . '/../x_token.php';

/** Unit tests for x_token.php, mirroring tests/test_x_token.py. */
final class XTokenTest extends TestCase
{
    private const SECRET = 'test-secret-32-bytes-long-enough';

    public function testCommitIsDeterministic(): void
    {
        $this->assertSame(
            commit_x('a', 'b', 'a', self::SECRET),
            commit_x('a', 'b', 'a', self::SECRET)
        );
    }

    public function testCommitDiffersForDifferentMatchedId(): void
    {
        $this->assertNotSame(
            commit_x('a', 'b', 'a', self::SECRET),
            commit_x('a', 'b', 'b', self::SECRET)
        );
    }

    public function testCommitDiffersForDifferentSecret(): void
    {
        $this->assertNotSame(
            commit_x('a', 'b', 'a', self::SECRET),
            commit_x('a', 'b', 'a', 'different-secret-value-32-bytes')
        );
    }

    public function testResolveRecoversMatchedIdA(): void
    {
        $token = commit_x('id_a', 'id_b', 'id_a', self::SECRET);
        $this->assertSame('id_a', resolve_x('id_a', 'id_b', $token, self::SECRET));
    }

    public function testResolveRecoversMatchedIdB(): void
    {
        $token = commit_x('id_a', 'id_b', 'id_b', self::SECRET);
        $this->assertSame('id_b', resolve_x('id_a', 'id_b', $token, self::SECRET));
    }

    public function testResolveReturnsNullForForgedToken(): void
    {
        $this->assertNull(resolve_x('id_a', 'id_b', 'not-a-real-token', self::SECRET));
    }

    public function testResolveReturnsNullForWrongSecret(): void
    {
        $token = commit_x('id_a', 'id_b', 'id_a', self::SECRET);
        $this->assertNull(resolve_x('id_a', 'id_b', $token, 'wrong-secret-should-not-work-32'));
    }

    public function testResolveReturnsNullWhenTokenFromDifferentPair(): void
    {
        $token = commit_x('id_x', 'id_y', 'id_x', self::SECRET);
        $this->assertNull(resolve_x('id_a', 'id_b', $token, self::SECRET));
    }

    public function testCommitIsOrderIndependent(): void
    {
        $this->assertSame(
            commit_x('id_a', 'id_b', 'id_a', self::SECRET),
            commit_x('id_b', 'id_a', 'id_a', self::SECRET)
        );
    }

    public function testResolveWorksRegardlessOfPairOrder(): void
    {
        $token = commit_x('id_a', 'id_b', 'id_b', self::SECRET);
        $this->assertSame('id_b', resolve_x('id_b', 'id_a', $token, self::SECRET));
    }
}
