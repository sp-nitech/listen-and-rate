"""Tests for the lar-export-php-deploy CLI."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from ._helpers import _write_config_yaml


def _run_export(
    config_yaml: Path, outdir: Path, monkeypatch, overwrite: bool = False
) -> None:
    """Run `lar-export-php-deploy --config config_yaml --outdir outdir`."""
    argv = [
        "lar-export-php-deploy",
        "--config",
        str(config_yaml),
        "--outdir",
        str(outdir),
    ]
    if overwrite:
        argv.append("--overwrite")
    monkeypatch.setattr("sys.argv", argv)
    from listen_and_rate.cli.export_php_deploy import main

    main()


def _config_with_systems(tmp_path, test_audio_file) -> Path:
    return _write_config_yaml(
        tmp_path,
        {
            "test_type": "mos",
            "title": "T",
            "instructions": "I",
            "stimuli": {
                "items": [
                    {
                        "id": "s001",
                        "path": str(test_audio_file),
                        "system": "System A",
                        "utterance": "utt1",
                    },
                    {
                        "id": "s002",
                        "path": str(test_audio_file),
                        "system": "System B",
                        "utterance": "utt1",
                    },
                ]
            },
        },
    )


def test_php_value_renders_python_values_as_php_literals():
    from listen_and_rate.cli.export_php_deploy import _php_value

    assert _php_value(None) == "null"
    assert _php_value(True) == "true"
    assert _php_value(False) == "false"
    assert _php_value(3) == "3"
    assert _php_value("a'b") == "'a\\'b'"
    assert _php_value([1, 2]) == "[1, 2]"
    assert _php_value({"a": 1, "b": None}) == "['a' => 1, 'b' => null]"


@pytest.mark.parametrize(
    ("mutation", "expected_substring"),
    [
        ({"test_type": "mos2"}, "test_type"),
        ({"bogus_key": 1}, "bogus_key"),
    ],
)
def test_export_invalid_config_exits_without_pydantic_url(
    tmp_path, monkeypatch, mutation, expected_substring
):
    """An invalid config exits cleanly at the CLI boundary (no traceback/URL)."""
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli": {"items": [{"id": "s001", "path": "/tmp/nonexistent.wav"}]},
        **mutation,
    }
    config_yaml = _write_config_yaml(tmp_path, config)
    with pytest.raises(SystemExit) as excinfo:
        _run_export(config_yaml, tmp_path / "deploy", monkeypatch)
    message = str(excinfo.value)
    assert "errors.pydantic.dev" not in message
    assert expected_substring in message


def test_export_php_deploy_writes_valid_config_data_php(
    config_yaml, tmp_path, monkeypatch
):
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert text.startswith("<?php")
    assert "'test_type' => 'mos'" in text
    assert "'stimuli' => [" in text
    assert "'shortcuts' => [" in text


def test_export_deploy_hint_is_logged_not_printed(
    config_yaml, tmp_path, monkeypatch, capsys, caplog
):
    """The 'copy to public_html' hint goes through logging.info, so it stays
    out of stdout and off-screen in tests (which don't emit INFO logs)."""
    import logging

    outdir = tmp_path / "deploy"
    with caplog.at_level(logging.INFO, logger="listen_and_rate"):
        _run_export(config_yaml, outdir, monkeypatch)

    assert any("public_html" in record.message for record in caplog.records)
    assert "public_html" not in capsys.readouterr().out


def test_export_php_deploy_audio_url_is_cwd_relative(
    config_yaml, tmp_path, monkeypatch
):
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    urls = re.findall(r"'audio_url' => '([^']*)'", text)
    assert urls
    cwd = Path.cwd()
    for u in urls:
        assert (cwd / u).exists()


def test_export_php_deploy_config_data_excludes_system(
    tmp_path, test_audio_file, monkeypatch
):
    config_yaml = _config_with_systems(tmp_path, test_audio_file)
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    # Per-stimulus system identity must not leak (reference_system, a
    # separate top-level field with a non-sensitive system name, is fine).
    assert "System A" not in text
    assert "System B" not in text


def test_export_php_deploy_config_data_includes_session_sampling_params(
    tmp_path, test_audio_file, monkeypatch
):
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli_dirs": {
            "utterances_per_session": 1,
            "systems": [{"path": "placeholder"}],
        },
    }
    d = tmp_path / "sys_a"
    d.mkdir()
    shutil.copy(test_audio_file, d / "utt1.wav")
    shutil.copy(test_audio_file, d / "utt2.wav")
    config["stimuli_dirs"]["systems"] = [{"path": str(d)}]
    config_yaml = _write_config_yaml(tmp_path, config)
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'utterances_per_session' => 1" in text
    assert "'stimuli_per_session' => null" in text


def test_export_php_deploy_config_data_includes_practice_params(
    tmp_path, test_audio_file, monkeypatch
):
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "practice": {"count": 2, "instructions": "Warm-up."},
        "stimuli": {
            "items": [
                {"id": f"s{i:03d}", "path": str(test_audio_file)} for i in range(3)
            ]
        },
    }
    config_yaml = _write_config_yaml(tmp_path, config)
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'practice_count' => 2" in text
    assert "'practice_instructions' => 'Warm-up.'" in text


def test_export_php_deploy_config_data_practice_defaults_when_unset(
    config_yaml, tmp_path, monkeypatch
):
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'practice_count' => 0" in text
    assert "'practice_instructions' => null" in text


def test_export_php_deploy_config_data_includes_practice_for_trial_types(
    tmp_path, test_audio_file, monkeypatch
):
    da = tmp_path / "sys_a"
    db = tmp_path / "sys_b"
    for d in (da, db):
        d.mkdir()
        shutil.copy(test_audio_file, d / "utt1.wav")
    config = {
        "test_type": "ab",
        "title": "T",
        "instructions": "I",
        "practice": {"count": 1, "instructions": "Warm-up."},
        "stimuli_dirs": {"systems": [{"path": str(da)}, {"path": str(db)}]},
    }
    config_yaml = _write_config_yaml(tmp_path, config)
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'practice_count' => 1" in text
    assert "'practice_instructions' => 'Warm-up.'" in text


def test_export_php_deploy_config_data_includes_reference_system_for_dmos(
    tmp_path, test_audio_file, monkeypatch
):
    da = tmp_path / "sys_ref"
    db = tmp_path / "sys_test"
    da.mkdir()
    db.mkdir()
    shutil.copy(test_audio_file, da / "utt1.wav")
    shutil.copy(test_audio_file, db / "utt1.wav")
    config = {
        "test_type": "dmos",
        "title": "T",
        "instructions": "I",
        "stimuli_dirs": {
            "systems": [
                {"path": str(da), "system": "Reference", "reference": True},
                {"path": str(db), "system": "Test"},
            ],
        },
    }
    config_yaml = _write_config_yaml(tmp_path, config)
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'reference_system' => 'Reference'" in text
    # Not leaked into the per-stimulus response-facing entries
    assert "'system'" not in text
    # A per-stimulus reference flag is fine to expose - it's not sensitive,
    # just which clip is labeled "Reference" vs "Test" in the paired UI.
    assert text.count("'reference' => true") == 1
    assert text.count("'reference' => false") == 1


def test_export_php_deploy_config_data_omits_reference_system_for_mos(
    config_yaml, tmp_path, monkeypatch
):
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'reference_system' => null" in text


def test_export_php_deploy_config_data_for_mushra_with_reference_and_anchor(
    tmp_path, test_audio_file, monkeypatch
):
    da = tmp_path / "sys_ref"
    db = tmp_path / "sys_b"
    dc = tmp_path / "sys_anchor"
    da.mkdir()
    db.mkdir()
    dc.mkdir()
    shutil.copy(test_audio_file, da / "utt1.wav")
    shutil.copy(test_audio_file, db / "utt1.wav")
    shutil.copy(test_audio_file, dc / "utt1.wav")
    config = {
        "test_type": "mushra",
        "title": "T",
        "instructions": "I",
        "stimuli_dirs": {
            "systems": [
                {"path": str(da), "system": "Reference", "reference": True},
                {"path": str(db), "system": "Test"},
                {"path": str(dc), "system": "Anchor", "anchor": True},
            ],
        },
    }
    config_yaml = _write_config_yaml(tmp_path, config)
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'reference_system' => 'Reference'" in text
    # 2 rateable systems: Test and Anchor (Reference excluded).
    assert "'mushra_rateable_system_count' => 2" in text
    # Per-stimulus reference/anchor flags are non-sensitive and fine to expose.
    assert text.count("'reference' => true") == 1
    assert text.count("'anchor' => true") == 1
    # System names themselves must not leak.
    assert "System A" not in text
    assert "'system'" not in text


def test_export_php_deploy_config_data_for_mushra_without_reference_or_anchor(
    tmp_path, test_audio_file, monkeypatch
):
    da = tmp_path / "sys_a"
    db = tmp_path / "sys_b"
    da.mkdir()
    db.mkdir()
    shutil.copy(test_audio_file, da / "utt1.wav")
    shutil.copy(test_audio_file, db / "utt1.wav")
    config = {
        "test_type": "mushra",
        "title": "T",
        "instructions": "I",
        "stimuli_dirs": {"systems": [{"path": str(da)}, {"path": str(db)}]},
    }
    config_yaml = _write_config_yaml(tmp_path, config)
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'reference_system' => null" in text
    assert "'mushra_rateable_system_count' => 2" in text
    assert "'reference' => true" not in text
    assert "'anchor' => true" not in text


def test_export_php_deploy_config_data_for_cmos(tmp_path, test_audio_file, monkeypatch):
    da = tmp_path / "sys_a"
    db = tmp_path / "sys_b"
    da.mkdir()
    db.mkdir()
    shutil.copy(test_audio_file, da / "utt1.wav")
    shutil.copy(test_audio_file, db / "utt1.wav")
    config = {
        "test_type": "cmos",
        "title": "T",
        "instructions": "I",
        "stimuli_dirs": {
            "systems": [{"path": str(da)}, {"path": str(db)}],
        },
    }
    config_yaml = _write_config_yaml(tmp_path, config)
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'test_type' => 'cmos'" in text
    # CMOS has no reference system and no allow_tie concept, like AB/ABX.
    assert "'reference_system' => null" in text
    assert "'allow_tie' => null" in text
    # No per-stimulus 'reference' flag should be true for CMOS.
    assert "'reference' => true" not in text


def test_export_php_deploy_config_data_includes_allow_tie_for_ab(
    tmp_path, test_audio_file, monkeypatch
):
    da = tmp_path / "sys_a"
    db = tmp_path / "sys_b"
    da.mkdir()
    db.mkdir()
    shutil.copy(test_audio_file, da / "utt1.wav")
    shutil.copy(test_audio_file, db / "utt1.wav")
    config = {
        "test_type": "ab",
        "title": "T",
        "instructions": "I",
        "allow_tie": False,
        "stimuli_dirs": {
            "systems": [{"path": str(da)}, {"path": str(db)}],
        },
    }
    config_yaml = _write_config_yaml(tmp_path, config)
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'test_type' => 'ab'" in text
    assert "'allow_tie' => false" in text


def test_export_php_deploy_config_data_includes_x_secret_for_abx(
    tmp_path, test_audio_file, monkeypatch
):
    da = tmp_path / "sys_a"
    db = tmp_path / "sys_b"
    da.mkdir()
    db.mkdir()
    shutil.copy(test_audio_file, da / "utt1.wav")
    shutil.copy(test_audio_file, db / "utt1.wav")
    config = {
        "test_type": "abx",
        "title": "T",
        "instructions": "I",
        "stimuli_dirs": {
            "systems": [{"path": str(da)}, {"path": str(db)}],
        },
    }
    config_yaml = _write_config_yaml(tmp_path, config)
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'test_type' => 'abx'" in text
    match = re.search(r"'x_secret' => '([0-9a-f]+)'", text)
    assert match, f"x_secret not found in {text!r}"
    assert len(match.group(1)) == 64  # secrets.token_hex(32)


def test_export_php_deploy_config_data_includes_reference_system_for_xab(
    tmp_path, test_audio_file, monkeypatch
):
    dref = tmp_path / "sys_ref"
    da = tmp_path / "sys_a"
    db = tmp_path / "sys_b"
    for d in (dref, da, db):
        d.mkdir()
        shutil.copy(test_audio_file, d / "utt1.wav")
    config = {
        "test_type": "xab",
        "title": "T",
        "instructions": "I",
        "stimuli_dirs": {
            "systems": [
                {"path": str(dref), "system": "Reference", "reference": True},
                {"path": str(da), "system": "A"},
                {"path": str(db), "system": "B"},
            ],
        },
    }
    config_yaml = _write_config_yaml(tmp_path, config)
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'test_type' => 'xab'" in text
    assert "'reference_system' => 'Reference'" in text
    # XAB's X is a disclosed reference, not a hidden duplicate - no secret.
    assert "'x_secret' => null" in text
    assert text.count("'reference' => true") == 1
    assert text.count("'reference' => false") == 2


def test_export_php_deploy_config_data_omits_x_secret_for_mos(
    config_yaml, tmp_path, monkeypatch
):
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'x_secret' => null" in text


def test_export_php_deploy_config_data_includes_preload_audio(
    config_yaml, tmp_path, monkeypatch
):
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'preload_audio' => false" in text


def _config_with_output_path(tmp_path, test_audio_file, output_path=None) -> Path:
    config = {
        "test_type": "mos",
        "title": "T",
        "instructions": "I",
        "stimuli": {"items": [{"id": "s001", "path": str(test_audio_file)}]},
    }
    if output_path is not None:
        config["output"] = {"format": "csv", "path": output_path}
    return _write_config_yaml(tmp_path, config)


def test_export_php_deploy_config_data_includes_default_output_path(
    tmp_path, test_audio_file, monkeypatch
):
    """save.php resolves its results directory from output_path, so the
    exported config_data.php must carry it (default: ./results/)."""
    config_yaml = _config_with_output_path(tmp_path, test_audio_file)
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'output_path' => './results/'" in text
    # Default layout unchanged: results/ seeded with .htaccess as before.
    assert (outdir / "results" / ".htaccess").exists()


def test_export_php_deploy_seeds_custom_relative_results_dir(
    tmp_path, test_audio_file, monkeypatch
):
    """A custom relative output.path is resolved against the bundle root:
    that directory (not results/) is created and .htaccess-protected."""
    config_yaml = _config_with_output_path(
        tmp_path, test_audio_file, output_path="./collected/"
    )
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    assert "'output_path' => './collected/'" in text
    assert (outdir / "collected" / ".htaccess").exists()
    assert not (outdir / "results").exists()


def test_export_php_deploy_overwrite_preserves_custom_results_dir(
    tmp_path, test_audio_file, monkeypatch
):
    """--overwrite must preserve collected data in a CUSTOM output.path
    directory, not just the default results/."""
    config_yaml = _config_with_output_path(
        tmp_path, test_audio_file, output_path="./collected/"
    )
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    keep = outdir / "collected" / "exp" / "s1.csv"
    keep.parent.mkdir(parents=True)
    keep.write_text("precious data")
    _run_export(config_yaml, outdir, monkeypatch, overwrite=True)
    assert keep.read_text() == "precious data"


def test_export_php_deploy_writes_stimulus_map_php(
    tmp_path, test_audio_file, monkeypatch
):
    config_yaml = _config_with_systems(tmp_path, test_audio_file)
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "stimulus_map.php").read_text()
    assert text.startswith("<?php")
    assert "'s001' => ['system' => 'System A', 'utterance' => 'utt1']" in text
    assert "'s002' => ['system' => 'System B', 'utterance' => 'utt1']" in text


def test_export_php_deploy_requires_outdir_arg(config_yaml, monkeypatch):
    monkeypatch.setattr(
        "sys.argv", ["lar-export-php-deploy", "--config", str(config_yaml)]
    )
    from listen_and_rate.cli.export_php_deploy import main

    with pytest.raises(SystemExit):
        main()


def test_export_php_deploy_produces_expected_bundle_layout(
    tmp_path, test_audio_file, monkeypatch
):
    import stat

    # Default (relative) output.path - the bundle carries its own results/.
    config_yaml = _config_with_output_path(tmp_path, test_audio_file)
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    assert (outdir / "index.html").is_file()
    assert (outdir / "save.php").is_file()
    assert (outdir / "css" / "style.css").is_file()
    assert (outdir / "js" / "app.js").is_file()
    assert (outdir / "results" / ".htaccess").is_file()
    mode = stat.S_IMODE((outdir / "results").stat().st_mode)
    assert mode == 0o777
    assert (outdir / "x_token.php").is_file()
    assert (outdir / "audio_x.php").is_file()


def test_export_php_deploy_absolute_output_path_seeds_no_bundle_results_dir(
    config_yaml, tmp_path, monkeypatch
):
    """conftest's config_yaml uses an absolute output.path: the results live
    at that absolute location (save.php uses it as-is), so no results/ is
    seeded inside the bundle."""
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    assert not (outdir / "results").exists()


def test_export_php_deploy_creates_audio_symlinks(
    config_yaml, tmp_path, test_audio_file, monkeypatch
):
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    text = (outdir / "config_data.php").read_text()
    urls = re.findall(r"'audio_url' => '([^']*)'", text)
    assert urls
    for u in urls:
        link = outdir / u
        assert link.is_symlink()
        assert link.readlink().is_absolute()
        assert link.resolve() == test_audio_file.resolve()
        assert link.read_bytes() == test_audio_file.read_bytes()


def test_export_php_deploy_can_run_twice_with_overwrite(
    config_yaml, tmp_path, monkeypatch
):
    outdir = tmp_path / "deploy"
    _run_export(config_yaml, outdir, monkeypatch, overwrite=True)
    _run_export(config_yaml, outdir, monkeypatch, overwrite=True)
    assert (outdir / "config_data.php").is_file()


def test_export_php_deploy_does_not_overwrite_existing_outdir_by_default(
    config_yaml, tmp_path, monkeypatch
):
    outdir = tmp_path / "deploy"
    outdir.mkdir()
    (outdir / "stale.txt").write_text("leftover from a previous run")
    with pytest.raises(FileExistsError):
        _run_export(config_yaml, outdir, monkeypatch)
    assert (outdir / "stale.txt").exists()


def test_export_php_deploy_overwrite_flag_regenerates_existing_outdir(
    config_yaml, tmp_path, monkeypatch
):
    outdir = tmp_path / "deploy"
    outdir.mkdir()
    (outdir / "stale.txt").write_text("leftover from a previous run")
    _run_export(config_yaml, outdir, monkeypatch, overwrite=True)
    assert not (outdir / "stale.txt").exists()
    assert (outdir / "config_data.php").is_file()


def test_export_php_deploy_overwrite_preserves_existing_results_directory(
    tmp_path, test_audio_file, monkeypatch
):
    # Default (relative) output.path: the bundle's results/ holds collected
    # data and must survive --overwrite.
    config_yaml = _config_with_output_path(tmp_path, test_audio_file)
    outdir = tmp_path / "deploy"
    results_dir = outdir / "results" / "some-experiment"
    results_dir.mkdir(parents=True)
    collected = results_dir / "real-listener-session.csv"
    collected.write_text("session_id,timestamp,test_type,system,utterance,rating\n")
    _run_export(config_yaml, outdir, monkeypatch, overwrite=True)
    assert collected.is_file()
    assert (
        collected.read_text()
        == "session_id,timestamp,test_type,system,utterance,rating\n"
    )
    assert (outdir / "config_data.php").is_file()


def test_export_php_deploy_overwrite_clears_results_dir_when_output_path_absolute(
    config_yaml, tmp_path, monkeypatch
):
    """With an absolute output.path the results live outside the bundle, so a
    leftover results/ directory inside it is regenerable clutter - --overwrite
    clears it like everything else (no legacy-layout special case)."""
    outdir = tmp_path / "deploy"
    stale = outdir / "results" / "old-layout" / "stale.csv"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale")
    _run_export(config_yaml, outdir, monkeypatch, overwrite=True)
    assert not (outdir / "results").exists()


def test_export_php_deploy_creates_outdir_if_missing(
    config_yaml, tmp_path, monkeypatch
):
    outdir = tmp_path / "nested" / "deploy"
    _run_export(config_yaml, outdir, monkeypatch)
    assert (outdir / "config_data.php").is_file()
    assert (outdir / "stimulus_map.php").is_file()
