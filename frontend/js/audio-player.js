/**
 * Custom audio player: a play/pause button and a (non-seekable) progress bar
 * wrapped around a bare <audio> element (no `controls` attribute).
 *
 * Using a bare <audio> instead of the native control means:
 *   - swapping the src per trial no longer re-renders a native shadow-DOM
 *     control, so there's no flicker on prev/next; and
 *   - there is no visible native control to right-click, so the browser's
 *     "Save Audio As" context-menu entry never appears (network/cache access
 *     is still possible - see the README's blinding threat model).
 *
 * Each test type still drives the <audio> directly (play shortcut) and binds
 * its `ended`/`error` events for playback gating; this module only owns the
 * button icon and the progress readout.
 */

// Inline SVG (not Unicode glyphs) so the icons are crisp and perfectly
// centered in the round button regardless of the platform font - the ▶/⏸
// glyphs' asymmetric side bearings made them look off-center.
// Exported so MUSHRA's own play buttons (mushra.js) can share the same icons.
export const PLAY_SVG =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>';
export const PAUSE_SVG =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>';

/**
 * Markup for one player. `localIndex` identifies the clip within a trial
 * (a number, or 'x' for ABX/XAB's reference); the test types read it back off
 * the <audio> via dataset.localIndex.
 */
export function audioPlayerHtml(localIndex, preload) {
  return `
    <div class="audio-player">
      <button class="audio-play-btn" type="button" aria-label="Play">${PLAY_SVG}</button>
      <div class="audio-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
        <div class="audio-progress-fill"></div>
      </div>
      <span class="audio-time">0.0 / --</span>
      <audio data-local-index="${localIndex}" preload="${preload}"></audio>
    </div>
  `;
}

// Listening-test clips are short, so the readout is seconds (one decimal),
// e.g. "3.4 / 5.3" - never M:SS. The total is '--' until the clip's metadata
// has loaded (which, with preload="none", is only once it's first played).
function formatSec(seconds) {
  return Number.isFinite(seconds) ? seconds.toFixed(1) : '--';
}

function timeText(audio) {
  return `${formatSec(audio.currentTime)} / ${formatSec(audio.duration)}`;
}

function playerParts(audio) {
  const player = audio.closest('.audio-player');
  return {
    player,
    btn: player.querySelector('.audio-play-btn'),
    bar: player.querySelector('.audio-progress'),
    fill: player.querySelector('.audio-progress-fill'),
    time: player.querySelector('.audio-time'),
  };
}

/** Wire the play button, play/pause icon, and progress bar for one <audio>. */
export function bindAudioPlayer(audio) {
  const { btn, bar, fill, time } = playerParts(audio);

  btn.addEventListener('click', () => {
    audio.paused ? audio.play() : audio.pause();
    // Drop focus so a later Enter reaches the document-level confirm shortcut
    // (advance/submit) instead of re-toggling this button.
    btn.blur();
  });

  const setPlaying = (playing) => {
    btn.innerHTML = playing ? PAUSE_SVG : PLAY_SVG;
    btn.setAttribute('aria-label', playing ? 'Pause' : 'Play');
  };

  const renderBar = () => {
    const pct = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0;
    fill.style.width = `${pct}%`;
    bar.setAttribute('aria-valuenow', String(Math.round(pct)));
  };

  // Drive the progress bar off requestAnimationFrame (~60fps) while playing,
  // not the `timeupdate` event (which only fires ~4x/second and made the bar
  // move in visible steps). The loop stops itself as soon as playback halts.
  // The numeric readout is throttled to ~12Hz so its digit stays legible
  // rather than churning every frame.
  let rafId = 0;
  let lastTextAt = 0;
  const tick = (now) => {
    renderBar();
    if (now - lastTextAt >= 80) {
      time.textContent = timeText(audio);
      lastTextAt = now;
    }
    rafId = audio.paused || audio.ended ? 0 : requestAnimationFrame(tick);
  };
  audio.addEventListener('play', () => {
    setPlaying(true);
    if (!rafId) rafId = requestAnimationFrame(tick);
  });
  const stop = () => {
    setPlaying(false);
    if (rafId) cancelAnimationFrame(rafId);
    rafId = 0;
    renderBar();
    time.textContent = timeText(audio);
  };
  audio.addEventListener('pause', stop);
  audio.addEventListener('ended', stop);
  audio.addEventListener('loadedmetadata', () => {
    renderBar();
    time.textContent = timeText(audio);
  });
}

/** Reset a player's UI to the start (used when its <audio> is rewound on navigation). */
export function resetAudioPlayer(audio) {
  const { player, btn, bar, fill, time } = playerParts(audio);
  if (!player) return;
  btn.innerHTML = PLAY_SVG;
  btn.setAttribute('aria-label', 'Play');
  fill.style.width = '0%';
  bar.setAttribute('aria-valuenow', '0');
  time.textContent = `0.0 / ${formatSec(audio.duration)}`;
}
