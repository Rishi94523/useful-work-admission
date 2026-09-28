// Checks research/scrypt_device.mjs against the RFC 7914 section 12 vectors.
import { scrypt } from '../research/scrypt_device.mjs';
const hex = b => Buffer.from(b).toString('hex');
const enc = s => new TextEncoder().encode(s);
const vectors = [
  ['', '', 16, 1, 1, '77d6576238657b203b19ca42c18a0497f16b4844e3074ae8dfdffa3fede21442fcd0069ded0948f8326a753a0fc81f17e8d3e0fb2e0d3628cf35e20c38d18906'],
  ['password', 'NaCl', 1024, 8, 16, 'fdbabe1c9d3472007856e7190d01e9fe7c6ad7cbc8237830e77376634b3731622eaf30d92e22a3886ff109279d9830dac727afb94a83ee6d8360cbdfa2cc0640'],
  ['pleaseletmein', 'SodiumChloride', 16384, 8, 1, '7023bdcb3afd7348461c06cd81fd38ebfda8fbba904f8e3ea9b543f6545da1f2d5432955613f0fcf62d49705242a9af9e61e85dc0d651e40dfcf017b45575887'],
];
let ok = true;
for (const [pw, salt, N, r, p, want] of vectors) {
  const t = performance.now(); const got = hex(await scrypt(enc(pw), enc(salt), N, r, p, 64));
  const pass = got === want; ok &&= pass;
  console.log(`N=${N} r=${r} p=${p}: ${pass ? 'PASS' : 'FAIL'} (${(performance.now() - t).toFixed(0)} ms)`);
}
process.exit(ok ? 0 : 1);
