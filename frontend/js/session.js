/**
 * Generate a UUID v4 session identifier.
 *
 * Falls back to a Math.random()-based implementation when crypto.randomUUID
 * is unavailable (HTTP - non-secure contexts). The fallback is not
 * cryptographically strong but provides sufficient uniqueness for session IDs.
 *
 * @returns {string} UUID v4 string
 */
export function generateSessionId() {
  if (crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}
