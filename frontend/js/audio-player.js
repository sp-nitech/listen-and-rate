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
// Padlock shown in place of the time readout for a blinded clip (ABX's X), so
// its intentionally hidden length reads as deliberate rather than a broken
// "-- / --". fill:currentColor keeps it monochrome (the readout's own text
// colour), never the coloured 🔒 emoji.
const LOCK_SVG =
  '<svg viewBox="0 0 24 24" width="1em" height="1em" role="img" aria-label="Length hidden" ' +
  'style="vertical-align:-0.12em;fill:currentColor">' +
  '<path d="M12 2a5 5 0 0 0-5 5v2H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2h-1V7a5 5 0 0 0-5-5zm-3 7V7a3 3 0 0 1 6 0v2H9z"/></svg>';

/**
 * Markup for one player. `localIndex` identifies the clip within a trial
 * (a number, or 'x' for ABX/XAB's reference); the test types read it back off
 * the <audio> via dataset.localIndex.
 */
export function audioPlayerHtml(localIndex, preload) {
  // The "--" total and empty data-duration are placeholders only: every test
  // type sets data-duration (the served clip length) and repaints via
  // resetAudioPlayer() in its sync step, synchronously before first paint.
  return `
    <div class="audio-player">
      <button class="audio-rewind-btn" type="button" aria-label="Rewind to start">${REWIND_SVG}</button>
      <button class="audio-play-btn" type="button" aria-label="Play">${PLAY_SVG}</button>
      <div class="audio-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
        <div class="audio-progress-fill"></div>
      </div>
      <span class="audio-time">0.0 / --</span>
      <audio data-local-index="${localIndex}" data-duration="" preload="${preload}"></audio>
    </div>
  `;
}

// Listening-test clips are short, so the readout is seconds (one decimal),
// e.g. "3.4 / 5.3" - never M:SS. The total shows '--' only if no duration is
// known at all.
function formatSec(seconds) {
  return Number.isFinite(seconds) ? seconds.toFixed(1) : '--';
}

// A blinded clip (ABX's X reference, data-duration="hidden") shows no numbers
// at all - neither a total (even from the loaded audio's own metadata) nor
// the elapsed time, since playing to the end would otherwise reveal the
// length, leaking which stimulus X duplicates. The progress bar stays
// (visual only), so listeners keep their position feedback.
function isBlinded(audio) {
  return audio.dataset.duration === 'hidden';
}

// The clip's total length. The server-provided duration (data-duration, set by
// the test type per clip) is authoritative and available on render, so the
// readout never flickers from '--'; a blinded clip has none.
function totalDuration(audio) {
  if (isBlinded(audio)) return Number.NaN;
  const served = Number(audio.dataset.duration);
  return served > 0 ? served : audio.duration;
}

// Left-pad `seconds`' integer part to `intDigits` with figure spaces (U+2007,
// one digit wide under tabular-nums). Keeps the elapsed field constant-width as
// its integer grows a digit (e.g. 9.9 -> 10.0 on a 10s+ clip), so the readout
// never widens mid-playback and shove the flex:1 progress bar's right edge in.
function padSec(seconds, intDigits) {
  const text = formatSec(seconds);
  const pad = intDigits - text.split('.')[0].length;
  return (pad > 0 ? '\u2007'.repeat(pad) : '') + text;
}

function timeText(audio) {
  const totalText = formatSec(totalDuration(audio));
  // Match the elapsed's integer width to the total's DISPLAYED digits (which
  // already account for rounding, e.g. 9.96 -> "10.0"). Clips under 10s have a
  // single integer digit, so nothing is padded and their readout is unchanged.
  const intDigits = totalText.split('.')[0].length;
  return `${padSec(audio.currentTime, intDigits)} / ${totalText}`;
}

// Paint the time readout. A blinded clip's readout is static (the lock icon,
// set once by resetAudioPlayer on trial sync), so playback/seek events leave
// it untouched; every other clip shows elapsed / total.
function renderTime(timeEl, audio) {
  if (isBlinded(audio)) return;
  timeEl.textContent = timeText(audio);
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

/**
 * Pause every other clip on the page, so only `audio` is sounding.
 *
 * A comparison test asks which of two stimuli is better; two of them playing
 * at once is a mixture of both, and a judgement made on it is not a judgement
 * of either. The play-to-completion gate would be satisfied all the same -
 * every clip reaches 'ended' - so nothing downstream would notice. Every
 * playback path enforces this: the keyboard shortcut (PairedTrialTest's
 * _handlePlayShortcut pauses whatever is playing), MUSHRA's own buttons, and
 * the card play button below.
 */
export function pauseOtherAudio(audio) {
  for (const other of document.querySelectorAll('audio')) {
    if (other !== audio && !other.paused) other.pause();
  }
}

/** Wire the play button, play/pause icon, and progress bar for one <audio>. */
export function bindAudioPlayer(audio) {
  const { playBtn, rewindBtn, bar, fill, time } = playerParts(audio);

  playBtn.addEventListener('click', () => {
    if (audio.paused) pauseOtherAudio(audio);
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
      renderTime(time, audio);
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
    renderTime(time, audio);
  };
  audio.addEventListener('pause', stop);
  audio.addEventListener('ended', stop);
  audio.addEventListener('loadedmetadata', () => {
    renderBar();
    renderTime(time, audio);
  });
  // Repaint after an external seek (the rewind button/shortcut) - while
  // paused, the rAF loop above isn't running to pick the new position up.
  audio.addEventListener('seeked', () => {
    renderBar();
    renderTime(time, audio);
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
  const blinded = isBlinded(audio);
  // Drop the numeric readout's reserved min-width for the lock so the box hugs
  // the icon and the flex:1 progress bar reclaims the slack, instead of leaving
  // a wide gap between the bar and the right-aligned lock (see .is-blinded CSS).
  time.classList.toggle('is-blinded', blinded);
  if (blinded) {
    time.innerHTML = LOCK_SVG;
  } else {
    // currentTime is 0 here (callers rewind first), so this is the padded
    // "0.0 / total" - matching the tick handler's format so the elapsed
    // field's width doesn't jump between reset and the first tick.
    time.textContent = timeText(audio);
  }
}
