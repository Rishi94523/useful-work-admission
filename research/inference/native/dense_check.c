/* Fused exact verification and forward pass for dense networks (amendment 15b).
 * Research prototype; the same four-projection algebra over p = 2^31 - 1 as
 * affine_check.c, applied to every layer of a network in one call. No new
 * cryptographic construction.
 *
 * Layout (all buffers concatenated over layers l = 0..L-1, in = dims[l],
 * out = dims[l+1]):
 *   w      int8   out x in, row-major        (forward and audit only)
 *   bias   int32  out
 *   s      uint32 in x 4, interleaved        (secret projections of W)
 *   r      uint32 out x 4, interleaved       (secret projection rows)
 *   rb     uint32 4 per layer
 *   bounds int64  out
 *   mult   int64  out; ignored for the last layer, whose outputs are logits
 * Inputs x0 are int8, batch x dims[0]. A trace is input-major: for each input,
 * every layer's int32 outputs in order. Metadata is checked by the Python
 * boundary; widths are limited to MAX_WIDTH.
 */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#ifdef _WIN32
#define API __declspec(dllexport)
#else
#define API
#endif
#define P UINT64_C(2147483647)
#define MAX_WIDTH 16384

static int8_t requantize(int64_t value, int64_t mult) {
    /* ReLU, then (value * mult + 2^23) >> 24 clipped to 127; the Python
     * boundary guarantees bound * mult + 2^23 < 2^53. */
    if (value < 0) value = 0;
    value = (value * mult + INT64_C(8388608)) >> 24;
    return (int8_t)(value > 127 ? 127 : value);
}

static int check_layer(const int8_t *x, const int32_t *z, const uint32_t *s, const uint32_t *r,
    const uint32_t *rb, const int64_t *bounds, size_t n, size_t m) {
    int64_t rhs[4] = {0, 0, 0, 0};
    uint64_t lhs[4] = {0, 0, 0, 0};
    uint32_t invalid = 0;
    for (size_t i = 0; i < n; ++i) {
        const int64_t a = x[i];
        invalid |= (a < -127);   /* int8 admits -128, outside the 7-bit range */
        for (size_t j = 0; j < 4; ++j) rhs[j] += a * (int64_t)s[4 * i + j];
    }
    for (size_t i = 0; i < m; ++i) {
        const int64_t value = z[i];
        invalid |= (value < -bounds[i] || value > bounds[i]);
        const uint64_t a = (uint64_t)(value < 0 ? (int64_t)P + value : value);
        for (size_t j = 0; j < 4; ++j) {
            const uint64_t product = a * (uint64_t)r[4 * i + j];
            lhs[j] += (product & P) + (product >> 31);   /* Mersenne fold, < 2^32 */
        }
    }
    for (size_t j = 0; j < 4; ++j) {
        int64_t right = rhs[j] % (int64_t)P;
        if (right < 0) right += (int64_t)P;
        invalid |= lhs[j] % P != ((uint64_t)right + rb[j]) % P;
    }
    return invalid == 0;
}

static size_t trace_width(int layers, const int32_t *dims) {
    size_t total = 0;
    for (int l = 0; l < layers; ++l) total += (size_t)dims[l + 1];
    return total;
}

static int valid_dims(int layers, const int32_t *dims) {
    if (layers < 1 || layers > 64) return 0;
    for (int l = 0; l <= layers; ++l) if (dims[l] < 1 || dims[l] > MAX_WIDTH) return 0;
    return 1;
}

/* Verify a batch of traces. Returns 1 if every input's trace is accepted, and
 * writes each input's final-layer integers to logits (batch x dims[L]). */
API int dense_verify(int layers, const int32_t *dims, const uint32_t *s, const uint32_t *r,
    const uint32_t *rb, const int64_t *bounds, const int64_t *mult,
    const int8_t *x0, const int32_t *trace, int32_t *logits, size_t batch) {
    if (!valid_dims(layers, dims)) return 0;
    int8_t buf[2][MAX_WIDTH];
    const size_t width = trace_width(layers, dims);
    for (size_t b = 0; b < batch; ++b) {
        const int8_t *x = x0 + b * (size_t)dims[0];
        const int32_t *z = trace + b * width;
        size_t so = 0, ro = 0, oo = 0;
        for (int l = 0; l < layers; ++l) {
            const size_t n = (size_t)dims[l], m = (size_t)dims[l + 1];
            if (!check_layer(x, z, s + so, r + ro, rb + 4 * l, bounds + oo, n, m)) return 0;
            if (l + 1 < layers) {
                int8_t *next = buf[l & 1];
                for (size_t i = 0; i < m; ++i) next[i] = requantize(z[i], mult[oo + i]);
                x = next;
            } else memcpy(logits + b * m, z, m * sizeof(int32_t));
            so += 4 * n; ro += 4 * m; oo += m; z += m;
        }
    }
    return 1;
}

/* Exact integer forward pass: int8 weights, 7-bit activations, int32
 * accumulation (|sum| <= MAX_WIDTH * 127 * 127 + |bias| < 2^31). Writes the
 * trace; if claimed is non-null, instead compares every layer with it and
 * returns 0 on the first difference (the audit). */
API int dense_forward(int layers, const int32_t *dims, const int8_t *w, const int32_t *bias,
    const int64_t *mult, const int8_t *x0, int32_t *trace, const int32_t *claimed, size_t batch) {
    if (!valid_dims(layers, dims)) return 0;
    int8_t buf[2][MAX_WIDTH];
    int32_t zbuf[MAX_WIDTH];
    const size_t width = trace_width(layers, dims);
    for (size_t b = 0; b < batch; ++b) {
        const int8_t *x = x0 + b * (size_t)dims[0];
        size_t wo = 0, oo = 0, zo = b * width;
        for (int l = 0; l < layers; ++l) {
            const size_t n = (size_t)dims[l], m = (size_t)dims[l + 1];
            int32_t *z = claimed ? zbuf : trace + zo;
            for (size_t o = 0; o < m; ++o) {
                const int8_t *row = w + wo + o * n;
                int32_t sum = 0;
                for (size_t i = 0; i < n; ++i) sum += (int32_t)row[i] * (int32_t)x[i];
                z[o] = sum + bias[oo + o];
            }
            if (claimed && memcmp(z, claimed + zo, m * sizeof(int32_t)) != 0) return 0;
            if (l + 1 < layers) {
                int8_t *next = buf[l & 1];
                for (size_t i = 0; i < m; ++i) next[i] = requantize(z[i], mult[oo + i]);
                x = next;
            }
            wo += m * n; oo += m; zo += m;
        }
    }
    return 1;
}
