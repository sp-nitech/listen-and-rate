/**
 * Generate a UUID v4 session identifier.
 *
 * crypto.randomUUID needs a secure context, so over plain HTTP it is missing
 * and the fallback below runs instead - which is exactly why that fallback
 * fills the bytes with crypto.getRandomValues, available in every context.
 * Math.random is the last resort, for a browser with no Web Crypto at all;
 * it is not cryptographically strong, but it still separates sessions.
 *
 * The session id names the result file, so two listeners must never collide.
 * Mirrors the randomness the backends draw from (listen_and_rate/rng.py and
 * config.php's random_int).
 *
 * @returns {string} UUID v4 string
 */
export function generateSessionId() {
  const webCrypto = globalThis.crypto;
  if (webCrypto?.randomUUID) {
    return webCrypto.randomUUID();
  }

  const bytes = new Uint8Array(16);
  if (webCrypto?.getRandomValues) {
    webCrypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i++) {
      bytes[i] = (Math.random() * 256) | 0;
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10x

  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ].join('-');
}
