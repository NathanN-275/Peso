export const THUMBNAIL_BYTE_LIMIT = 4 * 1024 * 1024;

// Current FFmpeg thumbnails are 8-bit baseline JPEG, at most 720x720. Validate
// that bounded format before handing memory bytes to either image decoder.
export function thumbnailDataUri(bytes: Uint8Array): string {
  const deny = () => { throw new Error('Invalid video preview.'); };
  const word = (at: number) => (bytes[at] << 8) | bytes[at + 1];
  if (bytes.length < 4 || bytes.length > THUMBNAIL_BYTE_LIMIT || word(0) !== 0xffd8) deny();
  let at = 2, entropy = false, frame = false, scan = false;
  let components: number[] = [];
  while (at < bytes.length) {
    if (entropy) {
      while (at < bytes.length && bytes[at] !== 255) at++;
    }
    if (bytes[at++] !== 255) deny();
    while (bytes[at] === 255) at++;
    if (at >= bytes.length) deny();
    const marker = bytes[at++];
    if (entropy && (marker === 0 || marker >= 0xd0 && marker <= 0xd7)) continue;
    entropy = false;
    if (marker === 0xd9) {
      if (!frame || !scan || at !== bytes.length) deny();
      const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
      const chunks: string[] = []; let chunk = '';
      for (let i = 0; i < bytes.length; i += 3) {
        const value = (bytes[i] << 16) | ((bytes[i + 1] ?? 0) << 8) | (bytes[i + 2] ?? 0);
        chunk += alphabet[value >>> 18] + alphabet[(value >>> 12) & 63]
          + (i + 1 < bytes.length ? alphabet[(value >>> 6) & 63] : '=')
          + (i + 2 < bytes.length ? alphabet[value & 63] : '=');
        if (chunk.length >= 8192) { chunks.push(chunk); chunk = ''; }
      }
      chunks.push(chunk);
      return 'data:image/jpeg;base64,' + chunks.join('');
    }
    if (![0xc0, 0xc4, 0xdb, 0xdd, 0xda, 0xfe].includes(marker) && !(marker >= 0xe0 && marker <= 0xef)) deny();
    if (at + 2 > bytes.length) deny();
    const length = word(at), end = at + length;
    if (length < 2 || end > bytes.length) deny();
    if (marker === 0xc0) {
      const count = bytes[at + 7], height = word(at + 3), width = word(at + 5);
      if (frame || scan || length !== 8 + 3 * count || ![1, 3].includes(count) || bytes[at + 2] !== 8
          || width < 1 || width > 720 || height < 1 || height > 720) deny();
      components = Array.from({ length: count }, (_, i) => bytes[at + 8 + 3 * i]);
      if (new Set(components).size !== count) deny();
      frame = true;
    }
    if (marker === 0xda) {
      const count = bytes[at + 2];
      const selected = Array.from({ length: count }, (_, i) => bytes[at + 3 + 2 * i]);
      if (!frame || scan || count !== components.length || length !== 6 + 2 * count
          || new Set(selected).size !== count || selected.some(id => !components.includes(id))
          || bytes[end - 3] !== 0 || bytes[end - 2] !== 63 || bytes[end - 1] !== 0) deny();
      scan = true; entropy = true;
    }
    at = end;
  }
  return deny() as never;
}
