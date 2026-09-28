// Pure-JavaScript scrypt (RFC 7914) for the device-disparity baseline: the
// memory-hard counterpart to the SHA-256 hashcash rate. PBKDF2-HMAC-SHA256 via
// WebCrypto where available, otherwise the bundled SHA-256; ROMix with
// BlockMix-Salsa20/8 in Uint32 arithmetic. Checked against the RFC 7914 test
// vectors by scripts/test_scrypt_device.mjs before any device run.

function salsa8(B) {
  const x = B.slice();
  const R = (a, b) => (a << b) | (a >>> (32 - b));
  for (let i = 0; i < 8; i += 2) {
    x[4] ^= R(x[0] + x[12], 7); x[8] ^= R(x[4] + x[0], 9); x[12] ^= R(x[8] + x[4], 13); x[0] ^= R(x[12] + x[8], 18);
    x[9] ^= R(x[5] + x[1], 7); x[13] ^= R(x[9] + x[5], 9); x[1] ^= R(x[13] + x[9], 13); x[5] ^= R(x[1] + x[13], 18);
    x[14] ^= R(x[10] + x[6], 7); x[2] ^= R(x[14] + x[10], 9); x[6] ^= R(x[2] + x[14], 13); x[10] ^= R(x[6] + x[2], 18);
    x[3] ^= R(x[15] + x[11], 7); x[7] ^= R(x[3] + x[15], 9); x[11] ^= R(x[7] + x[3], 13); x[15] ^= R(x[11] + x[7], 18);
    x[1] ^= R(x[0] + x[3], 7); x[2] ^= R(x[1] + x[0], 9); x[3] ^= R(x[2] + x[1], 13); x[0] ^= R(x[3] + x[2], 18);
    x[6] ^= R(x[5] + x[4], 7); x[7] ^= R(x[6] + x[5], 9); x[4] ^= R(x[7] + x[6], 13); x[5] ^= R(x[4] + x[7], 18);
    x[11] ^= R(x[10] + x[9], 7); x[8] ^= R(x[11] + x[10], 9); x[9] ^= R(x[8] + x[11], 13); x[10] ^= R(x[9] + x[8], 18);
    x[12] ^= R(x[15] + x[14], 7); x[13] ^= R(x[12] + x[15], 9); x[14] ^= R(x[13] + x[12], 13); x[15] ^= R(x[14] + x[13], 18);
  }
  for (let i = 0; i < 16; i++) B[i] = (B[i] + x[i]) >>> 0;
}

function blockMix(B, Y, r) {
  const X = B.subarray((2 * r - 1) * 16, 2 * r * 16).slice();
  for (let i = 0; i < 2 * r; i++) {
    for (let k = 0; k < 16; k++) X[k] ^= B[i * 16 + k];
    salsa8(X);
    const dst = (i % 2 === 0 ? i / 2 : r + (i - 1) / 2) * 16;
    Y.set(X, dst);
  }
  B.set(Y);
}

function roMix(B, r, N) {
  const len = 32 * r, V = new Uint32Array(len * N), Y = new Uint32Array(len);
  for (let i = 0; i < N; i++) { V.set(B, i * len); blockMix(B, Y, r); }
  for (let i = 0; i < N; i++) {
    const j = B[(2 * r - 1) * 16] & (N - 1);
    for (let k = 0; k < len; k++) B[k] ^= V[j * len + k];
    blockMix(B, Y, r);
  }
}

async function pbkdf2(password, salt, bytes) {
  const key = await crypto.subtle.importKey('raw', password, 'PBKDF2', false, ['deriveBits']);
  return new Uint8Array(await crypto.subtle.deriveBits({ name: 'PBKDF2', salt, iterations: 1, hash: 'SHA-256' }, key, bytes * 8));
}

export async function scrypt(password, salt, N, r, p, dkLen) {
  const B8 = await pbkdf2(password, salt, 128 * r * p);
  const B = new Uint32Array(B8.length / 4);
  for (let i = 0; i < B.length; i++) B[i] = B8[4 * i] | (B8[4 * i + 1] << 8) | (B8[4 * i + 2] << 16) | (B8[4 * i + 3] << 24);
  for (let i = 0; i < p; i++) roMix(B.subarray(i * 32 * r, (i + 1) * 32 * r), r, N);
  const out8 = new Uint8Array(B.length * 4);
  for (let i = 0; i < B.length; i++) { out8[4 * i] = B[i]; out8[4 * i + 1] = B[i] >>> 8; out8[4 * i + 2] = B[i] >>> 16; out8[4 * i + 3] = B[i] >>> 24; }
  return pbkdf2(password, out8, dkLen);
}
