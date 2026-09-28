/* Exact four-projection affine checker over p=2^31-1. Research prototype.
 * All inputs/model metadata are length/format checked by the Python boundary.
 * Loops evaluate all four checks; there is no first-failing-projection return.
 * No new cryptographic construction: this is a fused integer implementation.
 */
#include <stdint.h>
#include <stddef.h>
#ifdef _WIN32
#define API __declspec(dllexport)
#else
#define API
#endif
#define P UINT64_C(2147483647)

API int pouw_affine4(const int64_t *x, const int32_t *z,
    const uint32_t *s, const uint32_t *r, const uint32_t *rb,
    const int64_t *bounds, size_t n, size_t m) {
    if (!n || !m || n > 1048576 || m > 1048576) return 0;
    int64_t rhs[4] = {0,0,0,0};
    uint64_t lhs[4] = {0,0,0,0};
    uint32_t invalid = 0;
    for (size_t i=0; i<n; ++i) {
        int64_t a=x[i];
        invalid |= (a < -127 || a > 127);
        /* Clamp before multiplication to avoid UB even on malformed input. */
        if (a < -127 || a > 127) a=0;
        for (size_t j=0;j<4;++j) rhs[j] += a * (int64_t)s[4*i+j];
    }
    for (size_t i=0;i<m;++i) {
        const int64_t value=z[i];
        invalid |= (value < -bounds[i] || value > bounds[i]);
        const uint64_t a=(uint64_t)(value < 0 ? (int64_t)P+value : value);
        for (size_t j=0;j<4;++j) {
            const uint64_t product=a*(uint64_t)r[4*i+j];
            /* product < 2^62 for permitted values. One Mersenne fold is
             * congruent mod p and <2^32, hence total <2^52 for m<=2^20. */
            lhs[j] += (product & P) + (product >> 31);
        }
    }
    for (size_t j=0;j<4;++j) {
        int64_t right=rhs[j]%(int64_t)P;
        if (right<0) right+=(int64_t)P;
        invalid |= lhs[j]%P != ((uint64_t)right+rb[j])%P;
    }
    return invalid==0;
}

API void pouw_post(const int32_t *z, const int64_t *mult, int64_t *out,
    size_t channels, size_t h, size_t w, int pool) {
    const size_t oh=pool?h/2:h, ow=pool?w/2:w;
    for (size_t c=0;c<channels;++c) {
        for (size_t y=0;y<oh;++y) for (size_t x=0;x<ow;++x) {
            const size_t at=c*h*w+(pool?2*y:y)*w+(pool?2*x:x);
            int64_t value=z[at];
            if (pool) {
                if (z[at+1]>value) value=z[at+1];
                if (z[at+w]>value) value=z[at+w];
                if (z[at+w+1]>value) value=z[at+w+1];
            }
            /* max, ReLU, nonnegative requantization and clipping commute.
             * Trusted metadata bounds value*mult+half below 2^53. */
            if (value<0) value=0;
            value=(value*mult[c]+INT64_C(8388608))>>24;
            out[c*oh*ow+y*ow+x]=value>127?127:value;
        }
    }
}
