<?php

use PHPUnit\Framework\TestCase;

require_once __DIR__ . '/../x_token.php';
require_once __DIR__ . '/../save.php';

/** Unit tests for the pure helper functions in save.php (not handle_save_request itself). */
final class SaveTest extends TestCase
{
    private string $tmpDir;

    protected function setUp(): void
    {
        $this->tmpDir = sys_get_temp_dir() . '/lar_save_test_' . uniqid();
        mkdir($this->tmpDir, 0777, true);
    }

    protected function tearDown(): void
    {
        $this->rrmdir($this->tmpDir);
    }

    private function rrmdir(string $dir): void
    {
        if (!is_dir($dir)) {
            return;
        }
        foreach (scandir($dir) as $entry) {
            if ($entry === '.' || $entry === '..') {
                continue;
            }
            $path = $dir . '/' . $entry;
            is_dir($path) ? $this->rrmdir($path) : unlink($path);
        }
        rmdir($dir);
    }

    // -- is_valid_id ------------------------------------------------------

    public function testIsValidIdAcceptsDotsHyphensUnderscores(): void
    {
        $this->assertTrue(is_valid_id('a.b-c_d'));
        $this->assertTrue(is_valid_id('config.mos'));
    }

    public function testIsValidIdRejectsPathSeparatorsAndSpaces(): void
    {
        $this->assertFalse(is_valid_id('a/b/c'));
        $this->assertFalse(is_valid_id('a\\b'));
        $this->assertFalse(is_valid_id('my config'));
        $this->assertFalse(is_valid_id(''));
    }

    public function testIsValidIdRejectsDirectoryReferences(): void
    {
        // The dot is allowed, so these two need excluding by name.
        $this->assertFalse(is_valid_id('.'));
        $this->assertFalse(is_valid_id('..'));
    }

    public function testIsValidIdRejectsNonAsciiPerCharacterNotPerByte(): void
    {
        // Without the /u modifier the class would be applied per byte; this
        // must agree with listen_and_rate/ids.py, which works per character.
        $this->assertFalse(is_valid_id("\u{5b9f}\u{9a13}1"));
    }

    // -- detect_server_timezone -------------------------------------------

    public function testDetectServerTimezoneReadsTimezoneFile(): void
    {
        $tzFile = $this->tmpDir . '/timezone';
        file_put_contents($tzFile, "Asia/Tokyo\n");
        $result = detect_server_timezone('UTC', $tzFile, $this->tmpDir . '/localtime-missing');
        $this->assertSame('Asia/Tokyo', $result);
    }

    public function testDetectServerTimezoneFallsBackToLocaltimeSymlink(): void
    {
        $localtimeLink = $this->tmpDir . '/localtime';
        symlink('/usr/share/zoneinfo/America/New_York', $localtimeLink);
        $result = detect_server_timezone('UTC', $this->tmpDir . '/timezone-missing', $localtimeLink);
        $this->assertSame('America/New_York', $result);
    }

    public function testDetectServerTimezoneRejectsInvalidContentAndUsesFallback(): void
    {
        $tzFile = $this->tmpDir . '/timezone';
        file_put_contents($tzFile, "not-a-real-timezone\n");
        $result = detect_server_timezone('UTC', $tzFile, $this->tmpDir . '/localtime-missing');
        $this->assertSame('UTC', $result);
    }

    public function testDetectServerTimezoneUsesGivenFallbackWhenNeitherSourceIsAvailable(): void
    {
        $missingFiles = [$this->tmpDir . '/timezone-missing', $this->tmpDir . '/localtime-missing'];
        $this->assertSame('UTC', detect_server_timezone('UTC', ...$missingFiles));
        $this->assertSame('Etc/UTC', detect_server_timezone('Etc/UTC', ...$missingFiles));
    }

    // -- validate_submission_shape ----------------------------------------

    public function testValidateSubmissionShapeAcceptsMosWithRatings(): void
    {
        $this->expectNotToPerformAssertions();
        validate_submission_shape('mos', ['ratings' => [['stimulus_id' => 'a1', 'rating' => 4]]]);
    }

    public function testValidateSubmissionShapeRejectsMosWithMissingRatings(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_submission_shape('mos', []);
    }

    public function testValidateSubmissionShapeRejectsMosWithEmptyRatings(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_submission_shape('mos', ['ratings' => []]);
    }

    public function testValidateSubmissionShapeAcceptsAbWithChoices(): void
    {
        $this->expectNotToPerformAssertions();
        validate_submission_shape('ab', ['choices' => [['stimulus_ids' => ['a1', 'b1']]]]);
    }

    public function testValidateSubmissionShapeRejectsAbWithMissingChoices(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_submission_shape('ab', []);
    }

    public function testValidateSubmissionShapeRejectsAbxWithEmptyChoices(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_submission_shape('abx', ['choices' => []]);
    }

    public function testValidateSubmissionShapeAcceptsCmosWithChoices(): void
    {
        $this->expectNotToPerformAssertions();
        validate_submission_shape('cmos', ['choices' => [['stimulus_ids' => ['a1', 'b1'], 'rating' => 1]]]);
    }

    public function testValidateSubmissionShapeRejectsCmosWithEmptyChoices(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_submission_shape('cmos', ['choices' => []]);
    }

    public function testValidateSubmissionShapeErrorHasStatus400(): void
    {
        try {
            validate_submission_shape('mos', []);
            $this->fail('Expected SaveRequestError');
        } catch (SaveRequestError $e) {
            $this->assertSame(400, $e->status);
        }
    }

    // -- validate_rating_range --------------------------------------------

    public function testValidateRatingRangeAcceptsValidRatings(): void
    {
        $this->expectNotToPerformAssertions();
        validate_rating_range([['rating' => 1], ['rating' => 5]]);
    }

    public function testValidateRatingRangeRejectsOutOfRange(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_rating_range([['rating' => 6]]);
    }

    public function testValidateRatingRangeErrorHasStatus400(): void
    {
        try {
            validate_rating_range([['rating' => 0]]);
            $this->fail('Expected SaveRequestError');
        } catch (SaveRequestError $e) {
            $this->assertSame(400, $e->status);
        }
    }

    // -- validate_mos_ratings ---------------------------------------------

    public function testValidateMosRatingsAcceptsKnownStimulusIds(): void
    {
        $this->expectNotToPerformAssertions();
        validate_mos_ratings(
            ['a1' => ['system' => 'A', 'item' => 'u1']],
            [['stimulus_id' => 'a1', 'rating' => 4]]
        );
    }

    public function testValidateMosRatingsRejectsUnknownStimulusId(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_mos_ratings(
            ['a1' => ['system' => 'A', 'item' => 'u1']],
            [['stimulus_id' => 'unknown', 'rating' => 4]]
        );
    }

    public function testValidateMosRatingsRejectsMissingStimulusId(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_mos_ratings(
            ['a1' => ['system' => 'A', 'item' => 'u1']],
            [['rating' => 4]]
        );
    }

    public function testValidateMosRatingsErrorHasStatus400(): void
    {
        try {
            validate_mos_ratings([], [['stimulus_id' => 'x', 'rating' => 4]]);
            $this->fail('Expected SaveRequestError');
        } catch (SaveRequestError $e) {
            $this->assertSame(400, $e->status);
        }
    }

    // -- validate_submission_shape ----------------------------------------

    public function testValidateSubmissionShapeRejectsTheSameStimulusTwice(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_submission_shape('mos', ['ratings' => [
            ['stimulus_id' => 's1', 'rating' => 5],
            ['stimulus_id' => 's1', 'rating' => 1],
        ]]);
    }

    public function testValidateSubmissionShapeRejectsTheSamePairTwiceEitherOrder(): void
    {
        // The pair is the trial, so reversing the ids is the same answer.
        $this->expectException(SaveRequestError::class);
        validate_submission_shape('ab', ['choices' => [
            ['stimulus_ids' => ['a', 'b'], 'selected_stimulus_id' => 'a'],
            ['stimulus_ids' => ['b', 'a'], 'selected_stimulus_id' => 'b'],
        ]]);
    }

    public function testValidateSubmissionShapeRejectsTheSameDmosTrialTwice(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_submission_shape('dmos', ['ratings' => [
            ['stimulus_id' => 't1', 'reference_id' => 'r1', 'rating' => 4],
            ['stimulus_id' => 't1', 'reference_id' => 'r1', 'rating' => 2],
        ]]);
    }

    public function testValidateSubmissionShapeAcceptsDistinctAnswers(): void
    {
        validate_submission_shape('mos', ['ratings' => [
            ['stimulus_id' => 's1', 'rating' => 5],
            ['stimulus_id' => 's2', 'rating' => 1],
        ]]);
        // One test stimulus rated against two different references is not a
        // repeat - only the whole (stimulus, reference) trial identifies it.
        validate_submission_shape('dmos', ['ratings' => [
            ['stimulus_id' => 't1', 'reference_id' => 'r1', 'rating' => 4],
            ['stimulus_id' => 't1', 'reference_id' => 'r2', 'rating' => 2],
        ]]);
        $this->expectNotToPerformAssertions();
    }

    // -- validate_metadata ------------------------------------------------

    public function testValidateMetadataRequiresRequiredField(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_metadata(
            [['key' => 'listener', 'type' => 'text', 'required' => true]],
            []
        );
    }

    public function testValidateMetadataRejectsATrailingNewline(): void
    {
        // PCRE's $ also matches before a trailing newline; the browser's JS
        // regex does not, so the pattern is anchored with \z to agree.
        $this->expectException(SaveRequestError::class);
        validate_metadata(
            [['key' => 'listener', 'type' => 'text', 'required' => true]],
            ['listener' => "alice\n"]
        );
    }

    public function testValidateMetadataRejectsInvalidTextPattern(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_metadata(
            [['key' => 'listener', 'type' => 'text', 'required' => true]],
            ['listener' => "=cmd|'/C calc'!A1"]
        );
    }

    public function testValidateMetadataAllowsDotsInTextValue(): void
    {
        // The text allowlist includes '.' (e.g. names, version strings).
        $result = validate_metadata(
            [['key' => 'listener', 'type' => 'text', 'required' => true]],
            ['listener' => 'v1.2-beta']
        );
        $this->assertSame(['listener' => 'v1.2-beta'], $result);
    }

    public function testValidateMetadataRejectsSelectValueNotInOptions(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_metadata(
            [[
                'key'      => 'device',
                'type'     => 'select',
                'options'  => ['Headphones', 'Speakers'],
                'required' => true,
            ]],
            ['device' => 'Bone conduction']
        );
    }

    public function testValidateMetadataReturnsSanitizedValuesAndDropsUnknownKeys(): void
    {
        $result = validate_metadata(
            [['key' => 'listener', 'type' => 'text', 'required' => true]],
            ['listener' => 'Alice-01', 'unexpected' => "=cmd|'/C calc'!A1"]
        );
        $this->assertSame(['listener' => 'Alice-01'], $result);
    }

    public function testValidateMetadataSkipsAbsentOptionalField(): void
    {
        $result = validate_metadata(
            [['key' => 'device', 'type' => 'text', 'required' => false]],
            []
        );
        $this->assertSame([], $result);
    }

    // -- prefix_keys --------------------------------------------------------

    public function testPrefixKeysNamespacesFormAnswersForCsvColumns(): void
    {
        // Mirrors listen_and_rate/storage.py's METADATA_/SURVEY_ column
        // prefixes: CSV form columns are namespaced so they can never collide
        // with the saver-written result columns.
        $this->assertSame(
            ['metadata_device' => 'Headphones', 'metadata_system' => 'windows'],
            prefix_keys('metadata_', ['device' => 'Headphones', 'system' => 'windows'])
        );
        $this->assertSame([], prefix_keys('survey_', []));
    }

    public function testValidateMetadataRejectsNonStringTextValue(): void
    {
        // A crafted body can send an array (or other non-string) where a text
        // value is expected; that must be a clean 400, not an uncaught
        // TypeError from preg_match() (which would surface as a blank 500).
        // The FastAPI backend's Pydantic dict[str, str] typing rejects it too.
        $this->expectException(SaveRequestError::class);
        validate_metadata(
            [['key' => 'listener', 'type' => 'text', 'required' => true]],
            ['listener' => ['injected']]
        );
    }

    public function testValidateMetadataRejectsNonStringTextValueHasStatus400(): void
    {
        try {
            validate_metadata(
                [['key' => 'listener', 'type' => 'text', 'required' => true]],
                ['listener' => ['injected']]
            );
            $this->fail('Expected SaveRequestError');
        } catch (SaveRequestError $e) {
            $this->assertSame(400, $e->status);
        }
    }

    // -- resolve_results_dir ----------------------------------------------

    public function testResolveResultsDirDefaultsToResultsSubdirWhenMissing(): void
    {
        // config_data.php generated before output_path existed.
        $this->assertSame('/bundle/results', resolve_results_dir('/bundle', null));
        $this->assertSame('/bundle/results', resolve_results_dir('/bundle', ''));
    }

    public function testResolveResultsDirResolvesDefaultRelativePath(): void
    {
        // The YAML default './results/' keeps the pre-output_path location.
        $this->assertSame('/bundle/results', resolve_results_dir('/bundle', './results/'));
    }

    public function testResolveResultsDirResolvesCustomRelativePath(): void
    {
        $this->assertSame('/bundle/collected', resolve_results_dir('/bundle', './collected/'));
        $this->assertSame('/bundle/out/sub', resolve_results_dir('/bundle', 'out/sub'));
    }

    public function testResolveResultsDirKeepsAbsolutePath(): void
    {
        // e.g. deliberately outside the web root, per the README's advice.
        $this->assertSame('/var/data/results', resolve_results_dir('/bundle', '/var/data/results/'));
    }

    // -- resolve_experiment_dir -------------------------------------------

    public function testResolveExperimentDirCreatesDirectory(): void
    {
        $dir = resolve_experiment_dir($this->tmpDir, 'my-experiment');
        $this->assertDirectoryExists($dir);
        $this->assertStringEndsWith('/my-experiment', $dir);
    }

    public function testResolveExperimentDirRejectsAnEscapeAttempt(): void
    {
        // Rejected outright by the id rule now, rather than rewritten and
        // then caught by the containment check below.
        $this->expectException(SaveRequestError::class);
        resolve_experiment_dir($this->tmpDir, '../../evil');
    }

    public function testResolveExperimentDirStaysInsideResultsDir(): void
    {
        // The containment check is kept as defence in depth behind the id
        // rule: it is what guarantees the property the rule is meant to give.
        $dir = resolve_experiment_dir($this->tmpDir, 'nested.exp-1');
        $realResults = realpath($this->tmpDir);
        $this->assertStringStartsWith($realResults . '/', $dir . '/');
    }

    public function testResolveExperimentDirFallsBackToResultsWhenEmpty(): void
    {
        $dir = resolve_experiment_dir($this->tmpDir, '');
        $this->assertStringEndsWith('/results', $dir);
    }

    // -- build_json_result / build_csv_rows -------------------------------

    public function testBuildJsonResultEnrichesFromStimulusMap(): void
    {
        $data = [
            'session_id' => 's1',
            'test_type'  => 'mos',
            'ratings'    => [['stimulus_id' => 'a1', 'rating' => 4]],
        ];
        $stimulusMap = ['a1' => ['system' => 'System A', 'item' => 'utt1']];
        $result = build_json_result($data, [], $stimulusMap, '2026-01-01T00:00:00+00:00');
        $this->assertSame('System A', $result['ratings'][0]['system']);
        $this->assertSame('utt1', $result['ratings'][0]['item']);
        $this->assertSame(4, $result['ratings'][0]['rating']);
    }

    public function testBuildCsvRowsOrdersMetadataBetweenTestTypeAndSystem(): void
    {
        $data = [
            'session_id' => 's1',
            'test_type'  => 'mos',
            'ratings'    => [['stimulus_id' => 'a1', 'rating' => 4]],
        ];
        $stimulusMap = ['a1' => ['system' => 'System A', 'item' => 'utt1']];
        [$fields, $rows] = build_csv_rows(
            $data,
            ['listener' => 'Alice'],
            ['listener'],
            $stimulusMap,
            '2026-01-01'
        );
        $this->assertSame(
            ['session_id', 'timestamp', 'test_type', 'listener', 'system', 'item', 'rating'],
            $fields
        );
        $this->assertSame(['s1', '2026-01-01', 'mos', 'Alice', 'System A', 'utt1', 4], $rows[0]);
    }

    public function testBuildJsonResultDoesNotFallBackToClientSuppliedSystemItem(): void
    {
        // A rating whose stimulus_id is missing from the stimulus map must not
        // let the client inject arbitrary system/item strings into the
        // stored result (unknown IDs are rejected upstream by
        // validate_mos_ratings; this guards the enrichment itself).
        $data = [
            'session_id' => 's1',
            'test_type'  => 'mos',
            'ratings'    => [
                ['stimulus_id' => 'unknown', 'system' => 'Injected', 'item' => 'evil', 'rating' => 4],
            ],
        ];
        $result = build_json_result($data, [], [], '2026-01-01T00:00:00+00:00');
        $this->assertSame('', $result['ratings'][0]['system']);
        $this->assertSame('', $result['ratings'][0]['item']);
    }

    public function testBuildCsvRowsDoesNotFallBackToClientSuppliedSystemItem(): void
    {
        $data = [
            'session_id' => 's1',
            'test_type'  => 'mos',
            'ratings'    => [
                ['stimulus_id' => 'unknown', 'system' => 'Injected', 'item' => 'evil', 'rating' => 4],
            ],
        ];
        [, $rows] = build_csv_rows($data, [], [], [], '2026-01-01');
        $this->assertSame(['s1', '2026-01-01', 'mos', '', '', 4], $rows[0]);
    }

    // -- validate_dmos_rating ---------------------------------------------

    private function dmosStimulusMap(): array
    {
        return [
            'ref1'  => ['system' => 'Reference', 'item' => 'u1'],
            'test1' => ['system' => 'Test', 'item' => 'u1'],
            'ref2'  => ['system' => 'Reference', 'item' => 'u2'],
            'test2' => ['system' => 'Test', 'item' => 'u2'],
        ];
    }

    public function testValidateDmosRatingAcceptsValidPair(): void
    {
        $meta = validate_dmos_rating(
            $this->dmosStimulusMap(),
            ['stimulus_id' => 'test1', 'reference_id' => 'ref1', 'rating' => 4],
            'Reference'
        );
        $this->assertSame('Test', $meta['system']);
        $this->assertSame('u1', $meta['item']);
    }

    public function testValidateDmosRatingRejectsMissingReferenceId(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_dmos_rating(
            $this->dmosStimulusMap(),
            ['stimulus_id' => 'test1', 'rating' => 4],
            'Reference'
        );
    }

    public function testValidateDmosRatingRejectsUnknownId(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_dmos_rating(
            $this->dmosStimulusMap(),
            ['stimulus_id' => 'unknown', 'reference_id' => 'ref1', 'rating' => 4],
            'Reference'
        );
    }

    public function testValidateDmosRatingRejectsMismatchedItem(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_dmos_rating(
            $this->dmosStimulusMap(),
            ['stimulus_id' => 'test1', 'reference_id' => 'ref2', 'rating' => 4],
            'Reference'
        );
    }

    public function testValidateDmosRatingRejectsReferenceIdNotActuallyReference(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_dmos_rating(
            $this->dmosStimulusMap(),
            ['stimulus_id' => 'ref1', 'reference_id' => 'test1', 'rating' => 4],
            'Reference'
        );
    }

    public function testValidateDmosRatingRejectsStimulusIdIsReference(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_dmos_rating(
            $this->dmosStimulusMap(),
            ['stimulus_id' => 'ref1', 'reference_id' => 'ref1', 'rating' => 4],
            'Reference'
        );
    }

    // -- build_json_result / build_csv_rows reused unchanged for DMOS -----

    public function testBuildJsonResultEnrichesDmosRatingFromStimulusMap(): void
    {
        $data = [
            'session_id' => 's1',
            'test_type'  => 'dmos',
            'ratings'    => [
                ['stimulus_id' => 'test1', 'reference_id' => 'ref1', 'rating' => 4],
            ],
        ];
        $result = build_json_result($data, [], $this->dmosStimulusMap(), '2026-01-01T00:00:00+00:00');
        $row = $result['ratings'][0];
        $this->assertSame('Test', $row['system']);
        $this->assertSame('u1', $row['item']);
        $this->assertSame(4, $row['rating']);
    }

    public function testBuildCsvRowsProducesDmosShapedRow(): void
    {
        $data = [
            'session_id' => 's1',
            'test_type'  => 'dmos',
            'ratings'    => [
                ['stimulus_id' => 'test1', 'reference_id' => 'ref1', 'rating' => 4],
            ],
        ];
        [$fields, $rows] = build_csv_rows($data, [], [], $this->dmosStimulusMap(), '2026-01-01');
        $this->assertSame(['session_id', 'timestamp', 'test_type', 'system', 'item', 'rating'], $fields);
        $this->assertSame(['s1', '2026-01-01', 'dmos', 'Test', 'u1', 4], $rows[0]);
    }

    // -- validate_mushra_rating / validate_mushra_ratings_complete ---------

    private function mushraStimulusMap(): array
    {
        return [
            'ref1' => ['system' => 'Reference', 'item' => 'u1'],
            'b1'   => ['system' => 'B', 'item' => 'u1'],
            'c1'   => ['system' => 'C', 'item' => 'u1'],
        ];
    }

    public function testValidateMushraRatingAcceptsValidStimulus(): void
    {
        $meta = validate_mushra_rating($this->mushraStimulusMap(), ['stimulus_id' => 'b1', 'rating' => 70], 'Reference');
        $this->assertSame('B', $meta['system']);
        $this->assertSame('u1', $meta['item']);
    }

    public function testValidateMushraRatingRejectsUnknownId(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_mushra_rating($this->mushraStimulusMap(), ['stimulus_id' => 'unknown', 'rating' => 50], 'Reference');
    }

    public function testValidateMushraRatingRejectsReferenceStimulus(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_mushra_rating($this->mushraStimulusMap(), ['stimulus_id' => 'ref1', 'rating' => 90], 'Reference');
    }

    public function testValidateMushraRatingAllowsNullReferenceSystem(): void
    {
        $meta = validate_mushra_rating($this->mushraStimulusMap(), ['stimulus_id' => 'b1', 'rating' => 50], null);
        $this->assertSame('B', $meta['system']);
    }

    public function testValidateMushraRatingRejectsNonNumericRating(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_mushra_rating($this->mushraStimulusMap(), ['stimulus_id' => 'b1', 'rating' => 'abc'], 'Reference');
    }

    public function testValidateMushraRatingRejectsMissingRating(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_mushra_rating($this->mushraStimulusMap(), ['stimulus_id' => 'b1'], 'Reference');
    }

    public function testValidateMushraRatingRejectsNegativeRating(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_mushra_rating($this->mushraStimulusMap(), ['stimulus_id' => 'b1', 'rating' => -1], 'Reference');
    }

    public function testValidateMushraRatingRejectsRatingAbove100(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_mushra_rating($this->mushraStimulusMap(), ['stimulus_id' => 'b1', 'rating' => 101], 'Reference');
    }

    public function testValidateMushraRatingsCompleteAcceptsFullCoverage(): void
    {
        $this->expectNotToPerformAssertions();
        validate_mushra_ratings_complete(
            $this->mushraStimulusMap(),
            [
                ['stimulus_id' => 'b1', 'rating' => 70],
                ['stimulus_id' => 'c1', 'rating' => 20],
            ],
            'Reference'
        );
    }

    public function testValidateMushraRatingsCompleteRejectsMissingSystem(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_mushra_ratings_complete(
            $this->mushraStimulusMap(),
            [['stimulus_id' => 'b1', 'rating' => 70]],
            'Reference'
        );
    }

    // -- build_json_result / build_csv_rows reused unchanged for MUSHRA ---

    public function testBuildJsonResultEnrichesMushraRatingFromStimulusMap(): void
    {
        $data = [
            'session_id' => 's1',
            'test_type'  => 'mushra',
            'ratings'    => [
                ['stimulus_id' => 'b1', 'rating' => 70],
            ],
        ];
        $result = build_json_result($data, [], $this->mushraStimulusMap(), '2026-01-01T00:00:00+00:00');
        $row = $result['ratings'][0];
        $this->assertSame('B', $row['system']);
        $this->assertSame('u1', $row['item']);
        $this->assertSame(70, $row['rating']);
    }

    public function testBuildCsvRowsProducesMushraShapedRow(): void
    {
        $data = [
            'session_id' => 's1',
            'test_type'  => 'mushra',
            'ratings'    => [
                ['stimulus_id' => 'b1', 'rating' => 70],
            ],
        ];
        [$fields, $rows] = build_csv_rows($data, [], [], $this->mushraStimulusMap(), '2026-01-01');
        $this->assertSame(['session_id', 'timestamp', 'test_type', 'system', 'item', 'rating'], $fields);
        $this->assertSame(['s1', '2026-01-01', 'mushra', 'B', 'u1', 70], $rows[0]);
    }

    // -- validate_cmos_choice -----------------------------------------------

    private function abStimulusMap(): array
    {
        return [
            'a1' => ['system' => 'A', 'item' => 'u1'],
            'b1' => ['system' => 'B', 'item' => 'u1'],
            'a2' => ['system' => 'A', 'item' => 'u2'],
        ];
    }

    public function testValidateCmosChoiceAcceptsValidChoice(): void
    {
        [$meta1, $meta2] = validate_cmos_choice(
            $this->abStimulusMap(),
            ['stimulus_ids' => ['a1', 'b1'], 'rating' => 2]
        );
        $this->assertSame('A', $meta1['system']);
        $this->assertSame('B', $meta2['system']);
    }

    public function testValidateCmosChoiceRejectsMissingRating(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_cmos_choice($this->abStimulusMap(), ['stimulus_ids' => ['a1', 'b1']]);
    }

    public function testValidateCmosChoiceRejectsOutOfRangeRating(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_cmos_choice($this->abStimulusMap(), ['stimulus_ids' => ['a1', 'b1'], 'rating' => 4]);
    }

    public function testValidateCmosChoiceRejectsInvalidPair(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_cmos_choice($this->abStimulusMap(), ['stimulus_ids' => ['a1', 'a2'], 'rating' => 1]);
    }

    // -- build_cmos_json_result / build_cmos_csv_rows -----------------------

    public function testBuildCmosJsonResultProducesItemSystemASystemBRating(): void
    {
        $data = [
            'session_id' => 's1',
            'test_type'  => 'cmos',
            'choices'    => [['stimulus_ids' => ['a1', 'b1'], 'rating' => 2]],
        ];
        $result = build_cmos_json_result($data, [], $this->abStimulusMap(), '2026-01-01T00:00:00+00:00');
        $row = $result['ratings'][0];
        $this->assertSame('u1', $row['item']);
        $this->assertSame('A', $row['system_a']);
        $this->assertSame('B', $row['system_b']);
        $this->assertSame(2, $row['rating']);
    }

    public function testBuildCmosJsonResultFlipsRatingWhenFirstStimulusIsNotSystemA(): void
    {
        $data = [
            'session_id' => 's1',
            'test_type'  => 'cmos',
            // stimulus_ids[0] = b1 (system B); rating=2 means "the 2nd clip
            // (A) is 2 better than the 1st clip (B)" as shown to the listener.
            'choices'    => [['stimulus_ids' => ['b1', 'a1'], 'rating' => 2]],
        ];
        $result = build_cmos_json_result($data, [], $this->abStimulusMap(), '2026-01-01T00:00:00+00:00');
        $row = $result['ratings'][0];
        $this->assertSame('A', $row['system_a']);
        $this->assertSame('B', $row['system_b']);
        $this->assertSame(-2, $row['rating']);
    }

    public function testBuildCmosCsvRowsOrdersMetadataBeforeCmosColumns(): void
    {
        $data = [
            'session_id' => 's1',
            'test_type'  => 'cmos',
            'choices'    => [['stimulus_ids' => ['a1', 'b1'], 'rating' => -1]],
        ];
        [$fields, $rows] = build_cmos_csv_rows(
            $data,
            ['listener' => 'Alice'],
            ['listener'],
            $this->abStimulusMap(),
            '2026-01-01'
        );
        $this->assertSame(
            ['session_id', 'timestamp', 'test_type', 'listener', 'system_a', 'system_b', 'item', 'rating'],
            $fields
        );
        $this->assertSame(['s1', '2026-01-01', 'cmos', 'Alice', 'A', 'B', 'u1', -1], $rows[0]);
    }

    // -- validate_ab_choice_pair / validate_ab_choices ---------------------

    public function testValidateAbChoicePairAcceptsValidPair(): void
    {
        [$meta1, $meta2] = validate_ab_choice_pair($this->abStimulusMap(), ['a1', 'b1']);
        $this->assertSame('A', $meta1['system']);
        $this->assertSame('B', $meta2['system']);
    }

    public function testValidateAbChoicePairRejectsWrongCount(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_ab_choice_pair($this->abStimulusMap(), ['a1']);
    }

    public function testValidateAbChoicePairRejectsUnknownId(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_ab_choice_pair($this->abStimulusMap(), ['a1', 'unknown']);
    }

    public function testValidateAbChoicePairRejectsMismatchedItem(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_ab_choice_pair($this->abStimulusMap(), ['a1', 'a2']);
    }

    public function testValidateAbChoicePairRejectsSameSystem(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_ab_choice_pair($this->abStimulusMap(), ['a1', 'a1']);
    }

    public function testValidateAbChoicesRejectsTieWhenNotAllowed(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_ab_choices(
            [['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => null]],
            $this->abStimulusMap(),
            false
        );
    }

    public function testValidateAbChoicesAllowsTieWhenAllowed(): void
    {
        $this->expectNotToPerformAssertions();
        validate_ab_choices(
            [['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => null]],
            $this->abStimulusMap(),
            true
        );
    }

    public function testValidateAbChoicesRejectsPreferredNotInPair(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_ab_choices(
            [['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => 'a2']],
            $this->abStimulusMap(),
            true
        );
    }

    // -- build_ab_json_result / build_ab_csv_rows --------------------------

    public function testBuildAbJsonResultProducesItemSystemASystemBWinner(): void
    {
        $data = [
            'session_id' => 's1',
            'test_type'  => 'ab',
            'choices'    => [['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => 'a1']],
        ];
        $result = build_ab_json_result($data, [], $this->abStimulusMap(), '2026-01-01T00:00:00+00:00');
        $row = $result['ratings'][0];
        $this->assertSame('u1', $row['item']);
        $this->assertSame('A', $row['system_a']);
        $this->assertSame('B', $row['system_b']);
        $this->assertSame('a', $row['winner']);
    }

    public function testBuildAbJsonResultTieProducesTieToken(): void
    {
        $data = [
            'session_id' => 's1',
            'test_type'  => 'ab',
            'choices'    => [['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => null]],
        ];
        $result = build_ab_json_result($data, [], $this->abStimulusMap(), '2026-01-01T00:00:00+00:00');
        $this->assertSame('=', $result['ratings'][0]['winner']); // OUTCOME_TIE
    }

    public function testBuildAbJsonResultWinnerIsPositionalNotSystemName(): void
    {
        // winner records the pair SIDE (A/B/=), never a system name, so systems
        // named "tie"/"=" - which used to collide with the old "tie" sentinel -
        // are recorded unambiguously.
        $stimulusMap = [
            'a1' => ['system' => '=', 'item' => 'u1'],   // sorts before "tie"
            'b1' => ['system' => 'tie', 'item' => 'u1'],
        ];
        $data = [
            'session_id' => 's1',
            'test_type'  => 'ab',
            'choices'    => [
                ['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => 'b1'], // "tie" wins
                ['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => null], // real tie
            ],
        ];
        $result = build_ab_json_result($data, [], $stimulusMap, '2026-01-01T00:00:00+00:00');
        $this->assertSame('=', $result['ratings'][0]['system_a']);
        $this->assertSame('tie', $result['ratings'][0]['system_b']);
        $this->assertSame('b', $result['ratings'][0]['winner']); // system_b ("tie") won
        $this->assertSame('=', $result['ratings'][1]['winner']); // an actual tie
    }

    public function testBuildAbJsonResultSortsNumericSystemNamesLexicographically(): void
    {
        // PHP's sort() with the default SORT_REGULAR flag compares numeric-looking
        // strings numerically, while Python's sorted() always sorts lexicographically
        // (listen_and_rate/routers/api.py's `sorted([meta1["system"], meta2["system"]])`).
        // system_a/system_b must be assigned the same way in both deployments.
        $stimulusMap = [
            'a1' => ['system' => '128', 'item' => 'u1'],
            'b1' => ['system' => '64', 'item' => 'u1'],
        ];
        $data = [
            'session_id' => 's1',
            'test_type'  => 'ab',
            'choices'    => [['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => 'a1']],
        ];
        $result = build_ab_json_result($data, [], $stimulusMap, '2026-01-01T00:00:00+00:00');
        $row = $result['ratings'][0];
        $this->assertSame('128', $row['system_a']);
        $this->assertSame('64', $row['system_b']);
    }

    public function testBuildAbCsvRowsOrdersMetadataBeforeAbColumns(): void
    {
        $data = [
            'session_id' => 's1',
            'test_type'  => 'ab',
            'choices'    => [['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => 'b1']],
        ];
        [$fields, $rows] = build_ab_csv_rows(
            $data,
            ['listener' => 'Alice'],
            ['listener'],
            $this->abStimulusMap(),
            '2026-01-01'
        );
        $this->assertSame(
            ['session_id', 'timestamp', 'test_type', 'listener', 'system_a', 'system_b', 'item', 'winner'],
            $fields
        );
        $this->assertSame(['s1', '2026-01-01', 'ab', 'Alice', 'A', 'B', 'u1', 'b'], $rows[0]);
    }

    // -- validate_abx_choice ------------------------------------------------

    private const ABX_SECRET = 'test-secret-32-bytes-long-enough';

    public function testValidateAbxChoiceAcceptsValidCorrectGuess(): void
    {
        $token = commit_x('a1', 'b1', 'a1', self::ABX_SECRET);
        [$meta1, $meta2, $groundTruth] = validate_abx_choice(
            $this->abStimulusMap(),
            ['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => 'a1', 'x_token' => $token],
            self::ABX_SECRET
        );
        $this->assertSame('A', $meta1['system']);
        $this->assertSame('B', $meta2['system']);
        $this->assertSame('a1', $groundTruth);
    }

    public function testValidateAbxChoiceRejectsInvalidPair(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_abx_choice(
            $this->abStimulusMap(),
            ['stimulus_ids' => ['a1', 'a2'], 'selected_stimulus_id' => 'a1', 'x_token' => 'irrelevant'],
            self::ABX_SECRET
        );
    }

    public function testValidateAbxChoiceRejectsMissingSelection(): void
    {
        $token = commit_x('a1', 'b1', 'a1', self::ABX_SECRET);
        try {
            validate_abx_choice(
                $this->abStimulusMap(),
                ['stimulus_ids' => ['a1', 'b1'], 'x_token' => $token],
                self::ABX_SECRET
            );
            $this->fail('Expected SaveRequestError');
        } catch (SaveRequestError $e) {
            $this->assertSame(400, $e->status);
            $this->assertSame('selected_stimulus_id is required for ABX', $e->getMessage());
        }
    }

    public function testValidateAbxChoiceRejectsMatchedNotInPair(): void
    {
        $token = commit_x('a1', 'b1', 'a1', self::ABX_SECRET);
        $this->expectException(SaveRequestError::class);
        validate_abx_choice(
            $this->abStimulusMap(),
            ['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => 'a2', 'x_token' => $token],
            self::ABX_SECRET
        );
    }

    public function testValidateAbxChoiceRejectsForgedToken(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_abx_choice(
            $this->abStimulusMap(),
            ['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => 'a1', 'x_token' => 'forged'],
            self::ABX_SECRET
        );
    }

    // -- build_abx_json_result / build_abx_csv_rows ------------------------

    public function testBuildAbxJsonResultCorrectGuess(): void
    {
        $token = commit_x('a1', 'b1', 'a1', self::ABX_SECRET);
        $data = [
            'session_id'  => 's1',
            'test_type'   => 'abx',
            'choices' => [
                ['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => 'a1', 'x_token' => $token],
            ],
        ];
        $result = build_abx_json_result(
            $data,
            [],
            $this->abStimulusMap(),
            '2026-01-01T00:00:00+00:00',
            self::ABX_SECRET
        );
        $row = $result['ratings'][0];
        $this->assertSame('u1', $row['item']);
        $this->assertSame('A', $row['system_a']);
        $this->assertSame('B', $row['system_b']);
        $this->assertTrue($row['correct']);
    }

    public function testBuildAbxJsonResultIncorrectGuess(): void
    {
        $token = commit_x('a1', 'b1', 'a1', self::ABX_SECRET);
        $data = [
            'session_id'  => 's1',
            'test_type'   => 'abx',
            'choices' => [
                ['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => 'b1', 'x_token' => $token],
            ],
        ];
        $result = build_abx_json_result(
            $data,
            [],
            $this->abStimulusMap(),
            '2026-01-01T00:00:00+00:00',
            self::ABX_SECRET
        );
        $this->assertFalse($result['ratings'][0]['correct']);
    }

    public function testBuildAbxCsvRowsOrdersMetadataBeforeAbxColumns(): void
    {
        $token = commit_x('a1', 'b1', 'b1', self::ABX_SECRET);
        $data = [
            'session_id'  => 's1',
            'test_type'   => 'abx',
            'choices' => [
                ['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => 'b1', 'x_token' => $token],
            ],
        ];
        [$fields, $rows] = build_abx_csv_rows(
            $data,
            ['listener' => 'Alice'],
            ['listener'],
            $this->abStimulusMap(),
            '2026-01-01',
            self::ABX_SECRET
        );
        $this->assertSame(
            ['session_id', 'timestamp', 'test_type', 'listener', 'system_a', 'system_b', 'item', 'correct'],
            $fields
        );
        $this->assertSame(['s1', '2026-01-01', 'abx', 'Alice', 'A', 'B', 'u1', 'true'], $rows[0]);
    }

    // -- validate_xab_choice ------------------------------------------------

    private function xabStimulusMap(): array
    {
        return [
            'ref1' => ['system' => 'Reference', 'item' => 'u1'],
            'a1'   => ['system' => 'A', 'item' => 'u1'],
            'b1'   => ['system' => 'B', 'item' => 'u1'],
        ];
    }

    public function testValidateXabChoiceAcceptsValidChoice(): void
    {
        [$meta1, $meta2] = validate_xab_choice(
            $this->xabStimulusMap(),
            ['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => 'b1'],
            'Reference'
        );
        $this->assertSame('A', $meta1['system']);
        $this->assertSame('B', $meta2['system']);
    }

    public function testValidateXabChoiceRejectsMissingSelection(): void
    {
        // XAB is forced-choice: null (AB's tie) is not a valid response.
        $this->expectException(SaveRequestError::class);
        validate_xab_choice(
            $this->xabStimulusMap(),
            ['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => null],
            'Reference'
        );
    }

    public function testValidateXabChoiceRejectsSelectionOutsidePair(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_xab_choice(
            $this->xabStimulusMap(),
            ['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => 'ref1'],
            'Reference'
        );
    }

    public function testValidateXabChoiceRejectsReferenceInPair(): void
    {
        // ref1/a1 share an item and differ in system, so the generic
        // pair check passes - the reference-specific check must reject it.
        $this->expectException(SaveRequestError::class);
        validate_xab_choice(
            $this->xabStimulusMap(),
            ['stimulus_ids' => ['ref1', 'a1'], 'selected_stimulus_id' => 'a1'],
            'Reference'
        );
    }

    public function testValidateXabChoiceRejectsInvalidPair(): void
    {
        $this->expectException(SaveRequestError::class);
        validate_xab_choice(
            $this->xabStimulusMap(),
            ['stimulus_ids' => ['a1', 'a1'], 'selected_stimulus_id' => 'a1'],
            'Reference'
        );
    }

    // -- build_xab_json_result / build_xab_csv_rows -------------------------

    public function testBuildXabJsonResultProducesItemSystemASystemBCloser(): void
    {
        $data = [
            'session_id' => 's1',
            'test_type'  => 'xab',
            'choices'    => [['stimulus_ids' => ['b1', 'a1'], 'selected_stimulus_id' => 'b1']],
        ];
        $result = build_xab_json_result($data, [], $this->xabStimulusMap(), '2026-01-01T00:00:00+00:00', 'Reference');
        $row = $result['ratings'][0];
        $this->assertSame('u1', $row['item']);
        $this->assertSame('A', $row['system_a']);
        $this->assertSame('B', $row['system_b']);
        $this->assertSame('b', $row['closer']);
    }

    public function testBuildXabCsvRowsOrdersMetadataBeforeXabColumns(): void
    {
        $data = [
            'session_id' => 's1',
            'test_type'  => 'xab',
            'choices'    => [['stimulus_ids' => ['a1', 'b1'], 'selected_stimulus_id' => 'a1']],
        ];
        [$fields, $rows] = build_xab_csv_rows(
            $data,
            ['listener' => 'Alice'],
            ['listener'],
            $this->xabStimulusMap(),
            '2026-01-01',
            'Reference'
        );
        $this->assertSame(
            ['session_id', 'timestamp', 'test_type', 'listener', 'system_a', 'system_b', 'item', 'closer'],
            $fields
        );
        $this->assertSame(['s1', '2026-01-01', 'xab', 'Alice', 'A', 'B', 'u1', 'a'], $rows[0]);
    }

    // -- write_json_file / write_csv_file ---------------------------------

    public function testWriteJsonFileWritesValidJson(): void
    {
        $path = $this->tmpDir . '/out.json';
        write_json_file($path, ['a' => 1]);
        $this->assertSame(['a' => 1], json_decode(file_get_contents($path), true));
    }

    public function testWriteJsonFileThrowsOnUnwritablePath(): void
    {
        $this->expectException(SaveRequestError::class);
        write_json_file($this->tmpDir . '/missing-dir/out.json', ['a' => 1]);
    }

    public function testWriteCsvFileWritesHeaderAndRows(): void
    {
        $path = $this->tmpDir . '/out.csv';
        write_csv_file($path, ['a', 'b'], [['1', '2']], $this->tmpDir);
        $this->assertSame("a,b\n1,2\n", file_get_contents($path));
    }

    public function testWriteJsonFileRefusesToOverwriteExistingFileWith409(): void
    {
        $path = $this->tmpDir . '/out.json';
        write_json_file($path, ['a' => 1]);
        try {
            write_json_file($path, ['a' => 2]);
            $this->fail('Expected SaveRequestError');
        } catch (SaveRequestError $e) {
            $this->assertSame(409, $e->status);
        }
        // The collected data must be left untouched.
        $this->assertSame(['a' => 1], json_decode(file_get_contents($path), true));
    }

    public function testWriteCsvFileRefusesToOverwriteExistingFileWith409(): void
    {
        $path = $this->tmpDir . '/out.csv';
        write_csv_file($path, ['a', 'b'], [['1', '2']], $this->tmpDir);
        try {
            write_csv_file($path, ['a', 'b'], [['3', '4']], $this->tmpDir);
            $this->fail('Expected SaveRequestError');
        } catch (SaveRequestError $e) {
            $this->assertSame(409, $e->status);
        }
        $this->assertSame("a,b\n1,2\n", file_get_contents($path));
    }

}
