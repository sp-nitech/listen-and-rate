<?php

use PHPUnit\Framework\TestCase;

require_once __DIR__ . '/../stage.php';

/** Unit tests for stage.php, mirroring listen_and_rate/dependencies.py's stage lookup. */
final class StageTest extends TestCase
{
    private string $bundleDir;

    protected function setUp(): void
    {
        $this->bundleDir = sys_get_temp_dir() . '/lar_stage_test_' . uniqid();
        mkdir($this->bundleDir, 0777, true);
    }

    protected function tearDown(): void
    {
        @unlink($this->bundleDir . '/sequence.php');
        rmdir($this->bundleDir);
    }

    private function writeSequence(array $stages): void
    {
        file_put_contents(
            $this->bundleDir . '/sequence.php',
            '<?php return ' . var_export($stages, true) . ';'
        );
    }

    public function testALoneConfigIgnoresTheStageParameter(): void
    {
        // A lone config is a sequence of one: nothing to choose between.
        $this->writeSequence(['a']);
        $this->assertSame(['a'], sequence_stages($this->bundleDir));
        $this->assertSame($this->bundleDir . '/stages/a', stage_data_dir($this->bundleDir, []));
        $this->assertSame(
            $this->bundleDir . '/stages/a',
            stage_data_dir($this->bundleDir, [STAGE_PARAM => 'anything'])
        );
    }

    public function testASequenceServesTheNamedStageFromItsOwnDirectory(): void
    {
        $this->writeSequence(['a', 'b']);
        $this->assertSame(['a', 'b'], sequence_stages($this->bundleDir));
        $this->assertSame(
            $this->bundleDir . '/stages/b',
            stage_data_dir($this->bundleDir, [STAGE_PARAM => 'b'])
        );
    }

    public function testASequenceServesNoUnknownOrMissingStage(): void
    {
        $this->writeSequence(['a', 'b']);
        $this->assertNull(stage_data_dir($this->bundleDir, []));
        $this->assertNull(stage_data_dir($this->bundleDir, [STAGE_PARAM => 'c']));
        // ?stage[]=a arrives as an array; it names no stage either.
        $this->assertNull(stage_data_dir($this->bundleDir, [STAGE_PARAM => ['a']]));
    }
}
