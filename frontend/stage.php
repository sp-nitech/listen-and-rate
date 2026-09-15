<?php

/**
 * stage.php - which config of the bundle a request is for.
 *
 * A bundle runs its configs back to back as a sequence - one config being a
 * sequence of one (see listen_and_rate/cli/export_php_deploy.py). It lists
 * its stage ids - the configs' experiment_ids, in the order they run - in
 * sequence.php, keeps each stage's config_data.php and stimulus_map.php under
 * stages/<id>/, and is told which stage a request is for by the `stage` query
 * parameter. Mirrors listen_and_rate/dependencies.py's get_stage_or_manifest()
 * and get_stage().
 *
 * Shared by config.php, save.php, and audio_x.php. Like them, the functions
 * below are pure (no superglobals, no output) so PHPUnit can exercise them
 * directly (see frontend/tests/StageTest.php).
 */

/** Query parameter naming the stage; mirrors Python dependencies.STAGE_PARAM. */
const STAGE_PARAM = 'stage';

/** Return the bundle's stage ids in order ([] when it has no sequence.php). */
function sequence_stages(string $bundleDir): array
{
    $path = $bundleDir . '/sequence.php';
    if (!is_file($path)) {
        return [];
    }
    $stages = include $path;
    return is_array($stages) ? $stages : [];
}

/**
 * Return the directory holding the requested config's config_data.php and
 * stimulus_map.php, or null when the bundle serves no such stage.
 *
 * The parameter chooses between the stages of a sequence, so a lone config -
 * with nothing to choose between - ignores it.
 */
function stage_data_dir(string $bundleDir, array $query): ?string
{
    $stages = sequence_stages($bundleDir);
    if (count($stages) === 1) {
        return "{$bundleDir}/stages/{$stages[0]}";
    }
    // Strict, so a non-string value (?stage[]=a arrives as an array) never
    // matches - and only a listed id ever reaches the path below.
    $stage = $query[STAGE_PARAM] ?? null;
    return in_array($stage, $stages, true) ? "{$bundleDir}/stages/{$stage}" : null;
}
