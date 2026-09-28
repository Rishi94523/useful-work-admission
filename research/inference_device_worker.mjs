// Amendment 14 device worker: exact integer inference for the exported models,
// SHA-256 hashcash rate, and scrypt (RFC 7914) rate. Timing only; no verifier
// secrets. Inference arithmetic follows research/inference/quantized_net.py.
import { sha256Fallback } from '/sha.mjs';
import { scrypt } from '/scrypt.mjs';

async function bin(url, Type) { return new Type(await (await fetch(url, { cache: 'no-store' })).arrayBuffer()); }

function affine(op, x) {
  const z = new Int32Array(op.output_shape.reduce((a, b) => a * b, 1));
  if (op.conv) {
    const [channels, height, width] = op.input_shape, plane = height * width;
    for (let out = 0; out < op.output_shape[0]; out++) {
      z.fill(op.bias[out], out * plane, (out + 1) * plane);
      for (let c = 0; c < channels; c++) for (let ky = 0; ky < 3; ky++) for (let kx = 0; kx < 3; kx++) {
        const w = op.weight[((out * channels + c) * 3 + ky) * 3 + kx];
        const y0 = Math.max(0, 1 - ky), y1 = Math.min(height, height + 1 - ky), x0 = Math.max(0, 1 - kx), x1 = Math.min(width, width + 1 - kx);
        for (let y = y0; y < y1; y++) {
          const from = c * plane + (y + ky - 1) * width + kx - 1, to = out * plane + y * width;
          for (let p = x0; p < x1; p++) z[to + p] += x[from + p] * w;
        }
      }
    }
  } else {
    for (let o = 0; o < z.length; o++) {
      let sum = op.bias[o]; const base = o * x.length;
      for (let j = 0; j < x.length; j++) sum += x[j] * op.weight[base + j];
      z[o] = sum;
    }
  }
  return z;
}

function post(op, z) {
  if (!op.multiplier) return null;
  const plane = op.conv ? op.output_shape[1] * op.output_shape[2] : 1;
  const x = Int8Array.from(z, (v, i) => Math.min(127, Math.floor((Math.max(0, v) * op.multiplier[Math.floor(i / plane)] + 2 ** 23) / 2 ** 24)));
  if (!op.pool) return x;
  const [channels, h, w] = op.output_shape, hh = h / 2, ww = w / 2, pooled = new Int8Array(channels * hh * ww);
  for (let c = 0; c < channels; c++) for (let y = 0; y < hh; y++) for (let p = 0; p < ww; p++) {
    const idx = c * h * w + 2 * y * w + 2 * p;
    pooled[c * hh * ww + y * ww + p] = Math.max(x[idx], x[idx + 1], x[idx + w], x[idx + w + 1]);
  }
  return pooled;
}

async function digest(parts) {
  const total = parts.reduce((s, z) => s + z.length, 0), all = new Int32Array(total); let off = 0;
  for (const z of parts) { all.set(z, off); off += z.length; }
  const bytes = new Uint8Array(all.buffer); // little-endian int32, as the server packs
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(b => b.toString(16).padStart(2, '0')).join('');
}

async function runModel(name, repeats) {
  const t0 = performance.now(), m = await (await fetch(`/inference/${name}/model.json`, { cache: 'no-store' })).json();
  const ops = await Promise.all(m.operators.map(async (op, i) => ({ ...op, weight: await bin(`/inference/${name}/w${i}.bin`, Int8Array), bias: await bin(`/inference/${name}/b${i}.bin`, Int32Array) })));
  const load_ms = performance.now() - t0, runs = [];
  for (const input of m.inputs) {
    const x0 = await bin(`/inference/${name}/${input.file}`, Int8Array);
    for (let rep = 0; rep < repeats; rep++) {
      const begin = performance.now(); let x = x0; const trace = [];
      for (const op of ops) { const z = affine(op, x); trace.push(z); x = post(op, z); }
      const ms = performance.now() - begin, hash = await digest(trace);
      runs.push({ input: input.file, rep, ms, trace_sha256: hash, exact: hash === input.trace_sha256 });
    }
  }
  return { name, load_ms, weight_bytes: ops.reduce((s, o) => s + o.weight.byteLength + o.bias.byteLength, 0), runs };
}

function shaRate(seconds) {
  const buf = new Uint8Array(24), view = new DataView(buf.buffer); buf.set(crypto.getRandomValues(new Uint8Array(16)));
  const spin = ms => { let n = 0; const end = performance.now() + ms; while (performance.now() < end) { view.setUint32(16, n, true); sha256Fallback(buf); n++; } return n; };
  spin(1000); return spin(seconds * 1000) / seconds;
}

async function scryptTimes(count) {
  const enc = new TextEncoder(), times = [];
  await scrypt(enc.encode('warm'), enc.encode('up'), 1024, 8, 1, 32);
  for (let i = 0; i < count; i++) {
    const t = performance.now(); await scrypt(enc.encode('pleaseletmein'), enc.encode('salt' + i + Math.random()), 16384, 8, 1, 64); times.push(performance.now() - t);
  }
  return times;
}

onmessage = async ({ data }) => {
  try {
    if (data.op === 'model') postMessage(await runModel(data.name, data.repeats));
    else if (data.op === 'sha') postMessage({ rate: shaRate(data.seconds) });
    else if (data.op === 'scrypt') postMessage({ times: await scryptTimes(data.count) });
    else throw Error('Unknown op');
  } catch (e) { postMessage({ error: String(e) }); }
};
