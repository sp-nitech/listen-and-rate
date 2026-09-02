<?php

use PHPUnit\Framework\TestCase;

require_once __DIR__ . '/../x_token.php';
require_once __DIR__ . '/../config.php';

/** Unit tests for the pure helper functions in config.php (not the HTTP entry point). */
final class ConfigTest extends TestCase
{
    // -- sample_keep_order -------------------------------------------------

    public function testSampleKeepOrderReturnsRequestedCount(): void
    {
        $result = sample_keep_order(['a', 'b', 'c', 'd', 'e'], 2);
        $this->assertCount(2, $result);
    }

    public function testSampleKeepOrderContainsOnlyOriginalElementsNoDuplicates(): void
    {
        $arr = ['a', 'b', 'c', 'd', 'e'];
        $result = sample_keep_order($arr, 3);
        foreach ($result as $item) {
            $this->assertContains($item, $arr);
        }
        $this->assertSame(array_unique($result), $result);
    }

    public function testSampleKeepOrderPreservesRelativeOrderWhenSelectingAll(): void
    {
        $arr = ['a', 'b', 'c', 'd', 'e'];
        $this->assertSame($arr, sample_keep_order($arr, 5));
    }

    // -- shuffle_stimuli ----------------------------------------------------

    public function testShuffleStimuliReturnsSameElementsAsMultiset(): void
    {
        $arr = ['a', 'b', 'c', 'd'];
        $result = shuffle_stimuli($arr);
        sort($result);
        $sortedArr = $arr;
        sort($sortedArr);
        $this->assertSame($sortedArr, $result);
    }

    // -- sample_stimuli -----------------------------------------------------

    private function stimuliWithTwoSystemsTwoItems(): array
    {
        return [
            ['id' => 'A__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'a/u1.wav'],
            ['id' => 'A__u2', 'label' => null, 'item' => 'u2', 'audio_url' => 'a/u2.wav'],
            ['id' => 'B__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'b/u1.wav'],
            ['id' => 'B__u2', 'label' => null, 'item' => 'u2', 'audio_url' => 'b/u2.wav'],
        ];
    }

    public function testSampleStimuliWithItemsPerSessionKeepsAllSystemsForChosenItem(): void
    {
        $result = sample_stimuli($this->stimuliWithTwoSystemsTwoItems(), null, 1);
        $this->assertCount(2, $result);
        $items = array_unique(array_column($result, 'item'));
        $this->assertCount(1, $items);
    }

    public function testSampleStimuliWithStimuliPerSessionPicksExactCount(): void
    {
        $result = sample_stimuli($this->stimuliWithTwoSystemsTwoItems(), 2, null);
        $this->assertCount(2, $result);
    }

    public function testSampleStimuliReturnsAllWhenNoSamplingConfigured(): void
    {
        $stimuli = $this->stimuliWithTwoSystemsTwoItems();
        $result = sample_stimuli($stimuli, null, null);
        $this->assertSame($stimuli, $result);
    }

    // -- build_config_response ----------------------------------------------

    /** Shared fields for a fake config_data.php array; $extra overrides/adds per test type. */
    private function baseFakeConfigData(string $testType, array $extra = []): array
    {
        return array_merge(
            [
                'experiment_id' => 'config',
                'test_type' => $testType,
                'title' => 'T',
                'instructions' => 'I',
                'presentation_order' => 'random',
                'audio_preload' => 'auto',
                'durations' => ['A__u1' => 1.5, 'A__u2' => 1.5, 'B__u1' => 1.5, 'B__u2' => 1.5],
                'metadata' => ['title' => 'Listener Information', 'fields' => []],
                'survey' => ['title' => 'Questionnaire', 'fields' => []],
                'metrics' => ['response_time' => false],
                'resume' => ['max_age_ms' => 7200000],
                'stimuli_per_session' => null,
                'items_per_session' => 1,
                'stimuli' => $this->stimuliWithTwoSystemsTwoItems(),
            ],
            $extra
        );
    }

    private function fakeConfigData(): array
    {
        return $this->baseFakeConfigData('mos', [
            'shortcuts' => ['play' => 'Space'],
            'rating_labels' => null,
        ]);
    }

    public function testBuildConfigResponseAppliesItemsPerSession(): void
    {
        $response = build_config_response($this->fakeConfigData());
        $this->assertCount(2, $response['stimuli']);
    }

    public function testBuildConfigResponseStimuliOnlyExposeIdLabelAudioUrl(): void
    {
        $response = build_config_response($this->fakeConfigData());
        foreach ($response['stimuli'] as $s) {
            $this->assertSame(['id', 'label', 'audio_url'], array_keys($s));
        }
    }

    public function testBuildConfigResponsePassesThroughTopLevelFields(): void
    {
        $response = build_config_response($this->fakeConfigData());
        $this->assertSame('config', $response['experiment_id']);
        $this->assertSame('mos', $response['test_type']);
        $this->assertSame('T', $response['title']);
        $this->assertSame(['play' => 'Space'], $response['shortcuts']);
    }

    public function testBuildConfigResponsePassesThroughSurveyBlock(): void
    {
        // Each form is one {title, fields} block, passed through unchanged.
        $survey = [
            'title'  => 'アンケート',
            'fields' => [[
                'key'      => 'trial_count',
                'label'    => 'Was the number of trials appropriate?',
                'type'     => 'select',
                'options'  => ['TooFew', 'Appropriate', 'TooMany'],
                'required' => true,
            ]],
        ];
        $data = $this->baseFakeConfigData('mos', [
            'shortcuts' => ['play' => 'Space'],
            'rating_labels' => null,
            'survey' => $survey,
        ]);
        $response = build_config_response($data);
        $this->assertSame($survey, $response['survey']);
    }

    public function testBuildConfigResponseExposesWhichMetricsToCollect(): void
    {
        // The frontend measures only what this says; see listening-test.js.
        $data = $this->baseFakeConfigData('mos', [
            'shortcuts' => ['play' => 'Space'],
            'rating_labels' => null,
            'metrics' => ['response_time' => true],
        ]);
        $response = build_config_response($data);
        $this->assertSame(['response_time' => true], $response['metrics']);
    }

    public function testBuildConfigResponseExposesTheResumeWindow(): void
    {
        // Already in browser milliseconds when the bundle is exported: the
        // hours the experimenter wrote never reach the PHP host. See resume.js.
        $data = $this->baseFakeConfigData('mos', [
            'shortcuts' => ['play' => 'Space'],
            'rating_labels' => null,
            'resume' => ['max_age_ms' => 1800000],
        ]);
        $response = build_config_response($data);
        $this->assertSame(['max_age_ms' => 1800000], $response['resume']);
    }

    public function testBuildConfigResponsePassesThroughFormPageTitles(): void
    {
        $data = $this->baseFakeConfigData('mos', [
            'shortcuts' => ['play' => 'Space'],
            'rating_labels' => null,
            'metadata' => ['title' => '参加者情報', 'fields' => []],
            'survey' => ['title' => 'アンケート', 'fields' => []],
        ]);
        $response = build_config_response($data);
        $this->assertSame('参加者情報', $response['metadata']['title']);
        $this->assertSame('アンケート', $response['survey']['title']);
    }

    public function testBuildConfigResponsePassesThroughAudioPreload(): void
    {
        // The <audio preload> level is echoed to the browser unchanged.
        $response = build_config_response($this->fakeConfigData());
        $this->assertSame('auto', $response['audio_preload']);

        $data = $this->fakeConfigData();
        $data['audio_preload'] = 'none';
        $this->assertSame('none', build_config_response($data)['audio_preload']);
    }

    public function testBuildConfigResponsePassesThroughDurations(): void
    {
        // Clip lengths are echoed so the browser can show them immediately.
        $response = build_config_response($this->fakeConfigData());
        $this->assertSame(1.5, $response['durations']['A__u1']);
    }

    // -- config_version (resume fingerprint) -------------------------------

    public function testBuildConfigResponseIncludesConfigVersion(): void
    {
        $response = build_config_response($this->fakeConfigData());
        $this->assertArrayHasKey('config_version', $response);
        $this->assertIsString($response['config_version']);
        $this->assertNotSame('', $response['config_version']);
    }

    public function testConfigVersionStableForSameData(): void
    {
        $v1 = build_config_response($this->fakeConfigData())['config_version'];
        $v2 = build_config_response($this->fakeConfigData())['config_version'];
        $this->assertSame($v1, $v2);
    }

    public function testConfigVersionChangesWhenConfigChanges(): void
    {
        $v1 = build_config_response($this->fakeConfigData())['config_version'];
        $data = $this->fakeConfigData();
        $data['instructions'] = 'DIFFERENT';
        $v2 = build_config_response($data)['config_version'];
        $this->assertNotSame($v1, $v2);
    }

    // -- practice stage ---------------------------------------------------

    public function testPracticeExtrasSamplesCountItemsFromPoolWithoutDuplicates(): void
    {
        $pool = ['a', 'b', 'c', 'd'];
        $extras = practice_extras(
            ['practice_count' => 2, 'practice_instructions' => 'W.'],
            $pool,
            fn ($values) => $values
        );
        $this->assertSame('W.', $extras['practice_instructions']);
        $sampled = $extras['practice_trials'];
        $this->assertCount(2, $sampled);
        $this->assertSame(array_unique($sampled), $sampled);
        foreach ($sampled as $item) {
            $this->assertContains($item, $pool);
        }
    }

    public function testPracticeExtrasSupportsCustomKey(): void
    {
        $extras = practice_extras(
            ['practice_count' => 1, 'practice_instructions' => 'W.'],
            ['a'],
            fn ($values) => $values,
            'practice_stimuli'
        );
        $this->assertSame(['a'], $extras['practice_stimuli']);
    }

    public function testPracticeExtrasEmptyWhenCountZeroOrAbsent(): void
    {
        $this->assertSame([], practice_extras(['practice_count' => 0], ['a'], fn ($i) => $i));
        $this->assertSame([], practice_extras([], ['a'], fn ($i) => $i));
    }

    public function testBuildConfigResponseIncludesPracticeFieldsWhenCountPositive(): void
    {
        $data = $this->fakeConfigData();
        $data['practice_count'] = 2;
        $data['practice_instructions'] = 'Warm-up.';
        $response = build_config_response($data);
        $this->assertCount(2, $response['practice_stimuli']);
        foreach ($response['practice_stimuli'] as $s) {
            $this->assertSame(['id', 'label', 'audio_url'], array_keys($s));
        }
        $this->assertSame('Warm-up.', $response['practice_instructions']);
    }

    public function testBuildConfigResponseOmitsPracticeFieldsWhenCountZero(): void
    {
        $data = $this->fakeConfigData();
        $data['practice_count'] = 0;
        $data['practice_instructions'] = null;
        $response = build_config_response($data);
        $this->assertArrayNotHasKey('practice_stimuli', $response);
        $this->assertArrayNotHasKey('practice_instructions', $response);
    }

    public function testBuildConfigResponseOmitsPracticeFieldsWhenKeysAbsent(): void
    {
        // Older config_data.php bundles may predate the practice feature.
        $response = build_config_response($this->fakeConfigData());
        $this->assertArrayNotHasKey('practice_stimuli', $response);
        $this->assertArrayNotHasKey('practice_instructions', $response);
    }

    /** Enable a 1-page practice stage on a fake config_data array. */
    private function withPractice(array $data): array
    {
        $data['practice_count'] = 1;
        $data['practice_instructions'] = 'W.';
        return $data;
    }

    public function testBuildDmosConfigResponseIncludesPracticeTrials(): void
    {
        $response = build_dmos_config_response($this->withPractice($this->fakeDmosConfigData()));
        $this->assertSame('W.', $response['practice_instructions']);
        $this->assertCount(1, $response['practice_trials']);
        $trial = $response['practice_trials'][0];
        $this->assertSame(['reference', 'test'], array_keys($trial));
        $this->assertSame(['id', 'label', 'audio_url'], array_keys($trial['reference']));
        $this->assertSame(['id', 'label', 'audio_url'], array_keys($trial['test']));
    }

    public function testBuildCmosConfigResponseIncludesPracticeTrials(): void
    {
        $response = build_cmos_config_response($this->withPractice($this->fakeCmosConfigData()));
        $this->assertSame('W.', $response['practice_instructions']);
        $this->assertCount(1, $response['practice_trials']);
        $trial = $response['practice_trials'][0];
        $this->assertSame(['stimuli'], array_keys($trial));
        $this->assertCount(2, $trial['stimuli']);
    }

    public function testBuildAbConfigResponseIncludesPracticeTrials(): void
    {
        $response = build_ab_config_response($this->withPractice($this->fakeAbConfigData()));
        $this->assertSame('W.', $response['practice_instructions']);
        $this->assertCount(1, $response['practice_trials']);
        $this->assertSame(['stimuli'], array_keys($response['practice_trials'][0]));
    }

    public function testBuildAbxConfigResponseIncludesPracticeTrialsWithXToken(): void
    {
        $response = build_abx_config_response($this->withPractice($this->fakeAbxConfigData()));
        $this->assertSame('W.', $response['practice_instructions']);
        $this->assertCount(1, $response['practice_trials']);
        $trial = $response['practice_trials'][0];
        $this->assertSame(['stimuli', 'x'], array_keys($trial));
        $this->assertNotEmpty($trial['x']['token']);
    }

    public function testBuildXabConfigResponseIncludesPracticeTrials(): void
    {
        $response = build_xab_config_response($this->withPractice($this->fakeXabConfigData()));
        $this->assertSame('W.', $response['practice_instructions']);
        $this->assertCount(1, $response['practice_trials']);
        $trial = $response['practice_trials'][0];
        $this->assertSame(['reference', 'stimuli'], array_keys($trial));
        $this->assertCount(2, $trial['stimuli']);
    }

    public function testBuildMushraConfigResponseIncludesPracticeTrials(): void
    {
        $response = build_mushra_config_response($this->withPractice($this->fakeMushraConfigData()));
        $this->assertSame('W.', $response['practice_instructions']);
        $this->assertCount(1, $response['practice_trials']);
        $trial = $response['practice_trials'][0];
        $this->assertSame(['reference', 'systems', 'anchor'], array_keys($trial));
        $this->assertSame('Ref__u1', $trial['reference']['id']);
        $this->assertSame('Anchor__u1', $trial['anchor']['id']);
    }

    public function testTrialBuildersOmitPracticeFieldsWhenKeysAbsent(): void
    {
        $response = build_dmos_config_response($this->fakeDmosConfigData());
        $this->assertArrayNotHasKey('practice_trials', $response);
        $this->assertArrayNotHasKey('practice_instructions', $response);
    }

    // -- group_dmos_trials ------------------------------------------------

    private function stimuliWithReferenceAndTwoTestSystemsOneItem(): array
    {
        return [
            ['id' => 'Ref__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'ref/u1.wav', 'reference' => true],
            ['id' => 'B__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'b/u1.wav', 'reference' => false],
            ['id' => 'C__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'c/u1.wav', 'reference' => false],
        ];
    }

    public function testGroupDmosTrialsPairsReferenceWithEachTestSystem(): void
    {
        $trials = group_dmos_trials($this->stimuliWithReferenceAndTwoTestSystemsOneItem());
        $this->assertCount(2, $trials);
        foreach ($trials as $t) {
            $this->assertSame('Ref__u1', $t['reference']['id']);
        }
        $testIds = array_map(fn ($t) => $t['test']['id'], $trials);
        $this->assertContains('B__u1', $testIds);
        $this->assertContains('C__u1', $testIds);
    }

    public function testGroupDmosTrialsSkipsItemMissingReference(): void
    {
        $stimuli = [
            ['id' => 'Ref__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'ref/u1.wav', 'reference' => true],
            ['id' => 'B__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'b/u1.wav', 'reference' => false],
            ['id' => 'B__u2', 'label' => null, 'item' => 'u2', 'audio_url' => 'b/u2.wav', 'reference' => false],
        ];
        $trials = group_dmos_trials($stimuli);
        $this->assertCount(1, $trials);
        $this->assertSame('u1', $trials[0]['reference']['item']);
    }

    // -- sample_dmos_trials -----------------------------------------------

    public function testSampleDmosTrialsAppliesItemsPerSessionKeepingAllTestSystems(): void
    {
        $stimuli = [
            ['id' => 'Ref__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'ref/u1.wav', 'reference' => true],
            ['id' => 'B__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'b/u1.wav', 'reference' => false],
            ['id' => 'C__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'c/u1.wav', 'reference' => false],
            ['id' => 'Ref__u2', 'label' => null, 'item' => 'u2', 'audio_url' => 'ref/u2.wav', 'reference' => true],
            ['id' => 'B__u2', 'label' => null, 'item' => 'u2', 'audio_url' => 'b/u2.wav', 'reference' => false],
            ['id' => 'C__u2', 'label' => null, 'item' => 'u2', 'audio_url' => 'c/u2.wav', 'reference' => false],
        ];
        $trials = group_dmos_trials($stimuli);
        $result = sample_dmos_trials($trials, 1);
        $this->assertCount(2, $result); // 1 item x 2 test systems
    }

    public function testSampleDmosTrialsReturnsAllWhenNoLimit(): void
    {
        $trials = group_dmos_trials($this->stimuliWithReferenceAndTwoTestSystemsOneItem());
        $result = sample_dmos_trials($trials, null);
        $this->assertCount(2, $result);
    }

    // -- build_dmos_config_response --------------------------------------

    private function fakeDmosConfigData(): array
    {
        return $this->baseFakeConfigData('dmos', [
            'shortcuts' => ['rating' => ['1' => 1]],
            'rating_labels' => null,
            'reference_system' => 'Reference',
            'items_per_session' => null,
            'stimuli' => $this->stimuliWithReferenceAndTwoTestSystemsOneItem(),
        ]);
    }

    public function testBuildDmosConfigResponseHasReferenceAndTestPerTrial(): void
    {
        $response = build_dmos_config_response($this->fakeDmosConfigData());
        $this->assertCount(2, $response['trials']);
        foreach ($response['trials'] as $t) {
            $this->assertArrayHasKey('reference', $t);
            $this->assertArrayHasKey('test', $t);
        }
    }

    public function testBuildDmosConfigResponseStimuliOnlyExposeIdLabelAudioUrl(): void
    {
        $response = build_dmos_config_response($this->fakeDmosConfigData());
        foreach ($response['trials'] as $t) {
            $this->assertSame(['id', 'label', 'audio_url'], array_keys($t['reference']));
            $this->assertSame(['id', 'label', 'audio_url'], array_keys($t['test']));
        }
    }

    public function testBuildDmosConfigResponseHasNoAllowTie(): void
    {
        $response = build_dmos_config_response($this->fakeDmosConfigData());
        $this->assertArrayNotHasKey('allow_tie', $response);
    }

    public function testBuildConfigResponseDispatchesToDmosWhenTestTypeIsDmos(): void
    {
        $response = build_config_response($this->fakeDmosConfigData());
        $this->assertArrayHasKey('trials', $response);
        $this->assertArrayHasKey('reference', $response['trials'][0]);
        $this->assertArrayNotHasKey('stimuli', $response);
    }

    // -- group_mushra_trials ----------------------------------------------

    private function stimuliForMushra(): array
    {
        return [
            ['id' => 'Ref__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'ref/u1.wav', 'reference' => true, 'anchor' => false],
            ['id' => 'B__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'b/u1.wav', 'reference' => false, 'anchor' => false],
            ['id' => 'Anchor__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'anchor/u1.wav', 'reference' => false, 'anchor' => true],
        ];
    }

    public function testGroupMushraTrialsGroupsReferenceSystemsAndAnchor(): void
    {
        $trials = group_mushra_trials($this->stimuliForMushra(), 2);
        $this->assertCount(1, $trials);
        $this->assertSame('Ref__u1', $trials[0]['reference']['id']);
        $this->assertSame('Anchor__u1', $trials[0]['anchor']['id']);
        $this->assertSame(['B__u1'], array_column($trials[0]['systems'], 'id'));
    }

    public function testGroupMushraTrialsSkipsIncompleteItem(): void
    {
        $stimuli = [
            ...$this->stimuliForMushra(),
            ['id' => 'Ref__u2', 'label' => null, 'item' => 'u2', 'audio_url' => 'ref/u2.wav', 'reference' => true, 'anchor' => false],
            ['id' => 'B__u2', 'label' => null, 'item' => 'u2', 'audio_url' => 'b/u2.wav', 'reference' => false, 'anchor' => false],
            // u2 is missing the anchor stimulus - incomplete, must be skipped.
        ];
        $trials = group_mushra_trials($stimuli, 2);
        $this->assertCount(1, $trials);
        $this->assertSame('u1', mushra_trial_item($trials[0]));
    }

    public function testGroupMushraTrialsWithoutReference(): void
    {
        $stimuli = [
            ['id' => 'A__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'a/u1.wav', 'reference' => false, 'anchor' => false],
            ['id' => 'B__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'b/u1.wav', 'reference' => false, 'anchor' => false],
        ];
        $trials = group_mushra_trials($stimuli, 2);
        $this->assertCount(1, $trials);
        $this->assertNull($trials[0]['reference']);
        $this->assertNull($trials[0]['anchor']);
    }

    // -- sample_mushra_trials ---------------------------------------------

    public function testSampleMushraTrialsAppliesItemsPerSession(): void
    {
        $stimuli = [
            ...$this->stimuliForMushra(),
            ['id' => 'Ref__u2', 'label' => null, 'item' => 'u2', 'audio_url' => 'ref/u2.wav', 'reference' => true, 'anchor' => false],
            ['id' => 'B__u2', 'label' => null, 'item' => 'u2', 'audio_url' => 'b/u2.wav', 'reference' => false, 'anchor' => false],
            ['id' => 'Anchor__u2', 'label' => null, 'item' => 'u2', 'audio_url' => 'anchor/u2.wav', 'reference' => false, 'anchor' => true],
        ];
        $trials = group_mushra_trials($stimuli, 2);
        $result = sample_mushra_trials($trials, 1);
        $this->assertCount(1, $result);
    }

    public function testSampleMushraTrialsReturnsAllWhenNoLimit(): void
    {
        $trials = group_mushra_trials($this->stimuliForMushra(), 2);
        $result = sample_mushra_trials($trials, null);
        $this->assertCount(1, $result);
    }

    // -- build_mushra_config_response -------------------------------------

    private function fakeMushraConfigData(): array
    {
        return $this->baseFakeConfigData('mushra', [
            'shortcuts' => ['play' => 'Space'],
            'rating_labels' => null,
            'reference_system' => 'Reference',
            'mushra_rateable_system_count' => 2,
            'items_per_session' => null,
            'stimuli' => $this->stimuliForMushra(),
        ]);
    }

    public function testBuildMushraConfigResponseHasReferenceSystemsAndAnchor(): void
    {
        $response = build_mushra_config_response($this->fakeMushraConfigData());
        $this->assertCount(1, $response['trials']);
        $trial = $response['trials'][0];
        $this->assertSame('Ref__u1', $trial['reference']['id']);
        $this->assertSame('Anchor__u1', $trial['anchor']['id']);
        $this->assertSame(['B__u1'], array_column($trial['systems'], 'id'));
    }

    public function testBuildMushraConfigResponseStimuliOnlyExposeIdLabelAudioUrl(): void
    {
        $response = build_mushra_config_response($this->fakeMushraConfigData());
        foreach ($response['trials'] as $t) {
            $this->assertSame(['id', 'label', 'audio_url'], array_keys($t['reference']));
            $this->assertSame(['id', 'label', 'audio_url'], array_keys($t['anchor']));
            foreach ($t['systems'] as $s) {
                $this->assertSame(['id', 'label', 'audio_url'], array_keys($s));
            }
        }
    }

    public function testBuildMushraConfigResponseAnchorNeverInSystemsArray(): void
    {
        $response = build_mushra_config_response($this->fakeMushraConfigData());
        foreach ($response['trials'] as $t) {
            $systemIds = array_column($t['systems'], 'id');
            $this->assertNotContains($t['anchor']['id'], $systemIds);
        }
    }

    public function testBuildConfigResponseDispatchesToMushraWhenTestTypeIsMushra(): void
    {
        $response = build_config_response($this->fakeMushraConfigData());
        $this->assertArrayHasKey('trials', $response);
        $this->assertArrayHasKey('anchor', $response['trials'][0]);
        $this->assertArrayNotHasKey('stimuli', $response);
    }

    // -- build_cmos_config_response --------------------------------------

    private function fakeCmosConfigData(): array
    {
        return $this->baseFakeConfigData('cmos', [
            'shortcuts' => ['rating' => ['1' => -3]],
            'rating_labels' => null,
        ]);
    }

    public function testBuildCmosConfigResponseAppliesItemsPerSession(): void
    {
        $response = build_cmos_config_response($this->fakeCmosConfigData());
        $this->assertCount(1, $response['trials']);
        $this->assertCount(2, $response['trials'][0]['stimuli']);
    }

    public function testBuildCmosConfigResponseStimuliOnlyExposeIdLabelAudioUrl(): void
    {
        $response = build_cmos_config_response($this->fakeCmosConfigData());
        foreach ($response['trials'] as $t) {
            foreach ($t['stimuli'] as $s) {
                $this->assertSame(['id', 'label', 'audio_url'], array_keys($s));
            }
        }
    }

    public function testBuildCmosConfigResponseHasNoAllowTie(): void
    {
        $response = build_cmos_config_response($this->fakeCmosConfigData());
        $this->assertArrayNotHasKey('allow_tie', $response);
    }

    public function testBuildCmosConfigResponseIncludesRatingLabels(): void
    {
        $data = $this->baseFakeConfigData('cmos', [
            'shortcuts' => ['rating' => ['1' => -3]],
            'rating_labels' => ['-3' => 'Much worse'],
        ]);
        $response = build_cmos_config_response($data);
        $this->assertSame(['-3' => 'Much worse'], $response['rating_labels']);
    }

    public function testBuildConfigResponseDispatchesToCmosWhenTestTypeIsCmos(): void
    {
        $response = build_config_response($this->fakeCmosConfigData());
        $this->assertArrayHasKey('trials', $response);
        $this->assertArrayNotHasKey('stimuli', $response);
        $this->assertArrayNotHasKey('allow_tie', $response);
    }

    // -- group_ab_trials --------------------------------------------------

    public function testGroupAbTrialsPairsByItem(): void
    {
        $trials = group_ab_trials($this->stimuliWithTwoSystemsTwoItems());
        $this->assertCount(2, $trials);
        foreach ($trials as $t) {
            $this->assertCount(2, $t['stimuli']);
        }
    }

    public function testGroupAbTrialsDropsUnpairedItem(): void
    {
        $stimuli = $this->stimuliWithTwoSystemsTwoItems();
        $stimuli[] = ['id' => 'A__u3', 'label' => null, 'item' => 'u3', 'audio_url' => 'a/u3.wav'];
        $trials = group_ab_trials($stimuli);
        $this->assertCount(2, $trials);
        $items = array_map(fn ($t) => $t['stimuli'][0]['item'], $trials);
        $this->assertNotContains('u3', $items);
    }

    public function testGroupAbTrialsIncludesItemNamedZero(): void
    {
        // PHP's !empty("0") is true (PHP treats the string "0" as "empty"),
        // unlike Python's `if s.item:` which correctly treats "0" as a
        // non-empty item name (listen_and_rate/config.py's build_ab_trials).
        $stimuli = [
            ['id' => 'A__0', 'label' => null, 'item' => '0', 'audio_url' => 'a/0.wav'],
            ['id' => 'B__0', 'label' => null, 'item' => '0', 'audio_url' => 'b/0.wav'],
        ];
        $trials = group_ab_trials($stimuli);
        $this->assertCount(1, $trials);
    }

    // -- sample_ab_trials -------------------------------------------------

    public function testSampleAbTrialsAppliesItemsPerSession(): void
    {
        $trials = group_ab_trials($this->stimuliWithTwoSystemsTwoItems());
        $result = sample_ab_trials($trials, 1);
        $this->assertCount(1, $result);
    }

    public function testSampleAbTrialsReturnsAllWhenNoLimit(): void
    {
        $trials = group_ab_trials($this->stimuliWithTwoSystemsTwoItems());
        $result = sample_ab_trials($trials, null);
        $this->assertCount(2, $result);
    }

    // -- build_ab_config_response ----------------------------------------

    private function fakeAbConfigData(): array
    {
        return $this->baseFakeConfigData('ab', [
            'shortcuts' => ['choose_a' => '1'],
            'allow_tie' => false,
        ]);
    }

    public function testBuildAbConfigResponseAppliesItemsPerSession(): void
    {
        $response = build_ab_config_response($this->fakeAbConfigData());
        $this->assertCount(1, $response['trials']);
        $this->assertCount(2, $response['trials'][0]['stimuli']);
    }

    public function testBuildAbConfigResponseStimuliOnlyExposeIdLabelAudioUrl(): void
    {
        $response = build_ab_config_response($this->fakeAbConfigData());
        foreach ($response['trials'] as $t) {
            foreach ($t['stimuli'] as $s) {
                $this->assertSame(['id', 'label', 'audio_url'], array_keys($s));
            }
        }
    }

    public function testBuildAbConfigResponseExposesAllowTie(): void
    {
        $response = build_ab_config_response($this->fakeAbConfigData());
        $this->assertFalse($response['allow_tie']);
    }

    public function testBuildConfigResponseDispatchesToAbWhenTestTypeIsAb(): void
    {
        $response = build_config_response($this->fakeAbConfigData());
        $this->assertArrayHasKey('trials', $response);
        $this->assertArrayNotHasKey('stimuli', $response);
    }

    // -- build_abx_config_response ---------------------------------------

    private function fakeAbxConfigData(): array
    {
        return $this->baseFakeConfigData('abx', [
            'shortcuts' => ['choose_a' => '1'],
            'x_secret' => bin2hex('test-secret-32-bytes-long-enough'),
        ]);
    }

    public function testBuildAbxConfigResponseAppliesItemsPerSession(): void
    {
        $response = build_abx_config_response($this->fakeAbxConfigData());
        $this->assertCount(1, $response['trials']);
        $this->assertCount(2, $response['trials'][0]['stimuli']);
    }

    public function testBuildAbxConfigResponseStimuliOnlyExposeIdLabelAudioUrl(): void
    {
        $response = build_abx_config_response($this->fakeAbxConfigData());
        foreach ($response['trials'] as $t) {
            foreach ($t['stimuli'] as $s) {
                $this->assertSame(['id', 'label', 'audio_url'], array_keys($s));
            }
        }
    }

    public function testBuildAbxConfigResponseIncludesXToken(): void
    {
        $response = build_abx_config_response($this->fakeAbxConfigData());
        foreach ($response['trials'] as $t) {
            $this->assertArrayHasKey('x', $t);
            $this->assertArrayHasKey('token', $t['x']);
            $ids = array_column($t['stimuli'], 'id');
            $this->assertNotContains($t['x']['token'], $ids);
        }
    }

    public function testBuildAbxConfigResponseSplitsTheHiddenXBetweenBothStimuli(): void
    {
        // The X is committed behind an HMAC, so ask the token which stimulus it
        // names rather than reading the choice directly.
        $data   = $this->fakeAbxConfigData();
        $secret = hex2bin($data['x_secret']);
        $first  = 0;
        $draws  = 200;
        for ($i = 0; $i < $draws; $i++) {
            $response = build_abx_config_response($data);
            $trial    = $response['trials'][0];
            $ids      = array_column($trial['stimuli'], 'id');
            if (resolve_x($ids[0], $ids[1], $trial['x']['token'], $secret) === $ids[0]) {
                $first++;
            }
        }
        // Both sides must come up; a stuck or degenerate draw would expose the
        // answer. The bound is loose enough not to flake (p < 1e-9 when fair).
        $this->assertGreaterThan($draws * 0.25, $first);
        $this->assertLessThan($draws * 0.75, $first);
    }

    public function testBuildAbxConfigResponseHasNoAllowTie(): void
    {
        $response = build_abx_config_response($this->fakeAbxConfigData());
        $this->assertArrayNotHasKey('allow_tie', $response);
    }

    public function testBuildConfigResponseDispatchesToAbxWhenTestTypeIsAbx(): void
    {
        $response = build_config_response($this->fakeAbxConfigData());
        $this->assertArrayHasKey('trials', $response);
        $this->assertArrayHasKey('x', $response['trials'][0]);
        $this->assertArrayNotHasKey('stimuli', $response);
    }

    // -- group_xab_trials / build_xab_config_response --------------------

    private function stimuliForXab(): array
    {
        return [
            ['id' => 'Ref__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'ref/u1.wav', 'reference' => true],
            ['id' => 'A__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'a/u1.wav', 'reference' => false],
            ['id' => 'B__u1', 'label' => null, 'item' => 'u1', 'audio_url' => 'b/u1.wav', 'reference' => false],
            ['id' => 'Ref__u2', 'label' => null, 'item' => 'u2', 'audio_url' => 'ref/u2.wav', 'reference' => true],
            ['id' => 'A__u2', 'label' => null, 'item' => 'u2', 'audio_url' => 'a/u2.wav', 'reference' => false],
            ['id' => 'B__u2', 'label' => null, 'item' => 'u2', 'audio_url' => 'b/u2.wav', 'reference' => false],
        ];
    }

    public function testGroupXabTrialsGroupsReferenceWithTestPair(): void
    {
        $trials = group_xab_trials($this->stimuliForXab());
        $this->assertCount(2, $trials);
        foreach ($trials as $t) {
            $this->assertStringStartsWith('Ref__', $t['reference']['id']);
            $this->assertCount(2, $t['stimuli']);
        }
    }

    public function testGroupXabTrialsSkipsItemMissingReference(): void
    {
        $stimuli = array_filter(
            $this->stimuliForXab(),
            fn ($s) => $s['id'] !== 'Ref__u2'
        );
        $trials = group_xab_trials($stimuli);
        $this->assertCount(1, $trials);
        $this->assertSame('Ref__u1', $trials[0]['reference']['id']);
    }

    public function testGroupXabTrialsSkipsItemWithoutTwoTestStimuli(): void
    {
        $stimuli = array_filter(
            $this->stimuliForXab(),
            fn ($s) => $s['id'] !== 'B__u2'
        );
        $trials = group_xab_trials($stimuli);
        $this->assertCount(1, $trials);
    }

    private function fakeXabConfigData(): array
    {
        return $this->baseFakeConfigData('xab', [
            'shortcuts' => ['choose_a' => '1'],
            'reference_system' => 'Reference',
            'stimuli' => $this->stimuliForXab(),
        ]);
    }

    public function testBuildXabConfigResponseAppliesItemsPerSession(): void
    {
        $response = build_xab_config_response($this->fakeXabConfigData());
        $this->assertCount(1, $response['trials']);
        $this->assertCount(2, $response['trials'][0]['stimuli']);
    }

    public function testBuildXabConfigResponseStimuliOnlyExposeIdLabelAudioUrl(): void
    {
        $response = build_xab_config_response($this->fakeXabConfigData());
        foreach ($response['trials'] as $t) {
            $this->assertSame(['id', 'label', 'audio_url'], array_keys($t['reference']));
            foreach ($t['stimuli'] as $s) {
                $this->assertSame(['id', 'label', 'audio_url'], array_keys($s));
            }
        }
    }

    public function testBuildXabConfigResponseHasNoXTokenAndNoAllowTie(): void
    {
        $response = build_xab_config_response($this->fakeXabConfigData());
        $this->assertArrayNotHasKey('allow_tie', $response);
        foreach ($response['trials'] as $t) {
            $this->assertArrayNotHasKey('x', $t);
        }
    }

    public function testBuildConfigResponseDispatchesToXabWhenTestTypeIsXab(): void
    {
        $response = build_config_response($this->fakeXabConfigData());
        $this->assertArrayHasKey('trials', $response);
        $this->assertArrayHasKey('reference', $response['trials'][0]);
        $this->assertArrayNotHasKey('stimuli', $response);
    }
}
