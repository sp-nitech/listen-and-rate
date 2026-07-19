/**
 * Custom audio player: rewind and play/pause buttons and a (non-seekable)
 * progress bar wrapped around a bare <audio> element (no `controls`
 * attribute). The bar stays non-seekable because seeking forward to the end
 * would fire `ended` and defeat the play-to-completion gate; rewinding
 * (rewindAudio) is the one safe seek - it can only ever add listening.
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
// Skip-to-start (bar + left-pointing triangle), the universal rewind-to-start icon.
const REWIND_SVG =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6h2v12H6zm12 0v12l-9-6z"/></svg>';

/**
 * Markup for one player. `localIndex` identifies the clip within a trial
 * (a number, or 'x' for ABX/XAB's reference); the test types read it back off
 * the <audio> via dataset.localIndex.
 */
export function audioPlayerHtml(localIndex, preload, durationSec) {
  const dur = Number.isFinite(durationSec) ? durationSec : '';
  return `
    <div class="audio-player">
      <button class="audio-rewind-btn" type="button" aria-label="Rewind to start">${REWIND_SVG}</button>
      <button class="audio-play-btn" type="button" aria-label="Play">${PLAY_SVG}</button>
      <div class="audio-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
        <div class="audio-progress-fill"></div>
      </div>
      <span class="audio-time">0.0 / ${formatSec(durationSec)}</span>
      <audio data-local-index="${localIndex}" data-duration="${dur}" preload="${preload}"></audio>
    </div>
  `;
}

// Listening-test clips are short, so the readout is seconds (one decimal),
// e.g. "3.4 / 5.3" - never M:SS. The total shows '--' only if no duration is
// known at all.
function formatSec(seconds) {
  return Number.isFinite(seconds) ? seconds.toFixed(1) : '--';
}

// The clip's total length. The server-provided duration (data-duration, set by
// the test type per clip) is authoritative and available on render, so the
// readout never flickers from '--'. A clip marked 'hidden' (ABX's X reference)
// must never reveal its length - showing it, even from the loaded audio's own
// metadata, would leak which stimulus X duplicates - so it stays '--'.
function totalDuration(audio) {
  if (audio.dataset.duration === 'hidden') return Number.NaN;
  const served = Number(audio.dataset.duration);
  return served > 0 ? served : audio.duration;
}

// A blinded clip (ABX's X) shows no numbers at all - not even elapsed, since
// playing to the end would otherwise reveal the length. The progress bar stays
// (visual only), so listeners keep their position feedback.
function isBlinded(audio) {
  return audio.dataset.duration === 'hidden';
}

function timeText(audio) {
  if (isBlinded(audio)) return '-- / --';
  return `${formatSec(audio.currentTime)} / ${formatSec(totalDuration(audio))}`;
}

function playerParts(audio) {
  const player = audio.closest('.audio-player');
  return {
    player,
    playBtn: player.querySelector('.audio-play-btn'),
    rewindBtn: player.querySelector('.audio-rewind-btn'),
    bar: player.querySelector('.audio-progress'),
    fill: player.querySelector('.audio-progress-fill'),
    time: player.querySelector('.audio-time'),
  };
}

/**
 * Rewind to the start, preserving the play/pause state. Gate-safe: unlike
 * seeking forward, jumping to 0 can never skip content, so the
 * play-to-completion gate is unaffected. The player repaints itself via its
 * own `seeked` listener (see bindAudioPlayer), so callers just seek.
 */
export function rewindAudio(audio) {
  if (audio.currentTime !== 0) audio.currentTime = 0;
}

/** Wire the play button, play/pause icon, and progress bar for one <audio>. */
export function bindAudioPlayer(audio) {
  const { playBtn, rewindBtn, bar, fill, time } = playerParts(audio);

  playBtn.addEventListener('click', () => {
    audio.paused ? audio.play() : audio.pause();
    // Drop focus so a later Enter reaches the document-level confirm shortcut
    // (advance/submit) instead of re-toggling this button.
    playBtn.blur();
  });

  rewindBtn.addEventListener('click', () => {
    rewindAudio(audio);
    rewindBtn.blur();
  });

  const setPlaying = (playing) => {
    playBtn.innerHTML = playing ? PAUSE_SVG : PLAY_SVG;
    playBtn.setAttribute('aria-label', playing ? 'Pause' : 'Play');
  };

  const renderBar = () => {
    // Prefer the real element duration once loaded (exact during playback);
    // fall back to the served duration before the first play.
    const dur = audio.duration || totalDuration(audio);
    const pct = dur ? (audio.currentTime / dur) * 100 : 0;
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
  // Repaint after an external seek (the rewind button/shortcut) - while
  // paused, the rAF loop above isn't running to pick the new position up.
  audio.addEventListener('seeked', () => {
    renderBar();
    time.textContent = timeText(audio);
  });
}

/** Reset a player's UI to the start (used when its <audio> is rewound on navigation). */
export function resetAudioPlayer(audio) {
  const { player, playBtn, bar, fill, time } = playerParts(audio);
  if (!player) return;
  playBtn.innerHTML = PLAY_SVG;
  playBtn.setAttribute('aria-label', 'Play');
  fill.style.width = '0%';
  bar.setAttribute('aria-valuenow', '0');
  time.textContent = isBlinded(audio) ? '-- / --' : `0.0 / ${formatSec(totalDuration(audio))}`;
}
