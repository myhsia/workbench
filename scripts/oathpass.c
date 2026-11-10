/*
 * oathpass -- answer an SSH OATH/TOTP prompt from a local seed.
 *
 * Some SSH gateways authenticate with a single one-time code and nothing else:
 *
 *      One-time password (OATH) for `user':
 *
 * This tool answers that prompt itself, so logging in needs no phone, no
 * typing of the host or port, and no second terminal.  The code is an RFC 6238
 * TOTP (SHA-1/256/512, 6-10 digits, configurable period) computed in plain C.
 *
 * Configuration is a JSON object in ~/.config/oathpass/config.json (mode 600).
 *
 *   "oathpass": {
 *     "host": "<IP address or name>",
 *     "ports": [2201, 2202, 2203],
 *     "user": "<username>",
 *     "otp": {
 *       "uri": "<otpauth://totp/...?secret=...&algorithm=SHA512&digits=8&period=30>"
 *     }
 *   }
 *
 * `otp.uri` is what an authenticator app exports; its algorithm/digits/period
 * win.  A bare `otp.secret` (base32) is accepted too, defaulting to SHA512/8/30.
 * `lock=true` is an authenticator UI flag and is ignored here.  An optional
 * `password` is answered only if ssh asks for one.
 *
 * Build and install:
 *   make install            (see the Makefile; PREFIX defaults to ~/.local)
 *
 * Usage:
 *   oathpass                 log in
 *   oathpass <ssh args...>   log in, forwarding the arguments to ssh
 *   oathpass --node N        pin one login node by index
 *   oathpass --port P        pin one login port by number
 *   oathpass check           dry run: target, node, code, no ssh
 *   oathpass otp [--at EPOCH] print the current code
 *   oathpass port            print the login port that would be used
 *   oathpass target          print user@host, for rsync/scp
 *   oathpass wrap <cmd...>   run any command with the askpass exported
 *   oathpass doctor          diagnose a code that does not match the phone
 *   oathpass --selftest      replay the RFC 6238 vectors, no config needed
 *
 * The configured ports are equivalent entry points: the listed order is tried
 * and a dead one falls through to the next.  Authentication is different -- a
 * rejected code never moves to another node, because every node shares the
 * same account backend and a retry only spends a lockout budget.
 *
 * License: MIT (see LICENSE at the repository root).
 */

#include <arpa/inet.h>
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <poll.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif

#define CONFIG_RELATIVE "/.config/oathpass/config.json"
#define PROBE_MS 1500            /* whole preflight budget */
#define MIN_REMAINING 4.0        /* answer only this far into a window */
#define MAX_AUTH_ATTEMPTS 3      /* lockout budget, global across ports */
#define MAX_SSH_RUNS 6           /* hard ceiling on invocations */
#define TAIL_MAX 8192

/* Any HTTPS host returns a Date header; override with "time_url" in the config. */
static char g_time_url[256] = "https://1.1.1.1";

/* ------------------------------------------------------------------ output */

static void die(const char *fmt, ...) {
    va_list ap;
    fputs("oathpass: ", stderr);
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fputc('\n', stderr);
    exit(1);
}

static void note(const char *fmt, ...) {
    va_list ap;
    fputs("oathpass: ", stderr);
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fputc('\n', stderr);
}

/* -------------------------------------------------------------------- JSON */

typedef enum { J_NULL, J_BOOL, J_NUM, J_STR, J_ARR, J_OBJ } JType;

typedef struct JVal {
    JType type;
    char *str;        /* J_STR */
    double num;       /* J_NUM */
    int boolean;      /* J_BOOL */
    size_t count;     /* J_ARR, J_OBJ */
    struct JVal **items;
    char **keys;      /* J_OBJ */
} JVal;

typedef struct {
    const char *p;
    const char *base;
} JParser;

static JVal *jparse_value(JParser *jp);

static JVal *jnew(JType type) {
    JVal *v = calloc(1, sizeof *v);
    if (!v) die("out of memory");
    v->type = type;
    return v;
}

static void jskip(JParser *jp) {
    while (*jp->p && isspace((unsigned char)*jp->p)) jp->p++;
}

static void jexpect(JParser *jp, char want) {
    jskip(jp);
    if (*jp->p != want) die("invalid JSON at offset %ld (expected '%c')", (long)(jp->p - jp->base), want);
    jp->p++;
}

static void jpad(char **buf, size_t *len, size_t *cap, char c) {
    if (*len + 2 > *cap) {
        *cap = *cap ? *cap * 2 : 32;
        *buf = realloc(*buf, *cap);
        if (!*buf) die("out of memory");
    }
    (*buf)[(*len)++] = c;
    (*buf)[*len] = '\0';
}

static void jutf8(char **buf, size_t *len, size_t *cap, unsigned cp) {
    if (cp < 0x80) {
        jpad(buf, len, cap, (char)cp);
    } else if (cp < 0x800) {
        jpad(buf, len, cap, (char)(0xC0 | (cp >> 6)));
        jpad(buf, len, cap, (char)(0x80 | (cp & 0x3F)));
    } else if (cp < 0x10000) {
        jpad(buf, len, cap, (char)(0xE0 | (cp >> 12)));
        jpad(buf, len, cap, (char)(0x80 | ((cp >> 6) & 0x3F)));
        jpad(buf, len, cap, (char)(0x80 | (cp & 0x3F)));
    } else {
        jpad(buf, len, cap, (char)(0xF0 | (cp >> 18)));
        jpad(buf, len, cap, (char)(0x80 | ((cp >> 12) & 0x3F)));
        jpad(buf, len, cap, (char)(0x80 | ((cp >> 6) & 0x3F)));
        jpad(buf, len, cap, (char)(0x80 | (cp & 0x3F)));
    }
}

static unsigned jhex4(JParser *jp) {
    unsigned value = 0;
    for (int i = 0; i < 4; i++) {
        char c = *jp->p++;
        value <<= 4;
        if (c >= '0' && c <= '9') value |= (unsigned)(c - '0');
        else if (c >= 'a' && c <= 'f') value |= (unsigned)(c - 'a' + 10);
        else if (c >= 'A' && c <= 'F') value |= (unsigned)(c - 'A' + 10);
        else die("invalid \\u escape in JSON");
    }
    return value;
}

static char *jparse_string(JParser *jp) {
    char *buf = NULL;
    size_t len = 0, cap = 0;
    jexpect(jp, '"');
    while (*jp->p && *jp->p != '"') {
        char c = *jp->p++;
        if (c != '\\') {
            jpad(&buf, &len, &cap, c);
            continue;
        }
        char esc = *jp->p++;
        switch (esc) {
        case '"': jpad(&buf, &len, &cap, '"'); break;
        case '\\': jpad(&buf, &len, &cap, '\\'); break;
        case '/': jpad(&buf, &len, &cap, '/'); break;
        case 'b': jpad(&buf, &len, &cap, '\b'); break;
        case 'f': jpad(&buf, &len, &cap, '\f'); break;
        case 'n': jpad(&buf, &len, &cap, '\n'); break;
        case 'r': jpad(&buf, &len, &cap, '\r'); break;
        case 't': jpad(&buf, &len, &cap, '\t'); break;
        case 'u': {
            unsigned cp = jhex4(jp);
            if (cp >= 0xD800 && cp <= 0xDBFF && jp->p[0] == '\\' && jp->p[1] == 'u') {
                jp->p += 2;
                unsigned low = jhex4(jp);
                if (low >= 0xDC00 && low <= 0xDFFF)
                    cp = 0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00);
            }
            jutf8(&buf, &len, &cap, cp);
            break;
        }
        default: die("invalid escape in JSON string");
        }
    }
    if (*jp->p != '"') die("unterminated JSON string");
    jp->p++;
    if (!buf) {
        buf = malloc(1);
        if (!buf) die("out of memory");
        buf[0] = '\0';
    }
    return buf;
}

static void jpush(JVal *v, char *key, JVal *item) {
    v->items = realloc(v->items, (v->count + 1) * sizeof *v->items);
    if (!v->items) die("out of memory");
    if (v->type == J_OBJ) {
        v->keys = realloc(v->keys, (v->count + 1) * sizeof *v->keys);
        if (!v->keys) die("out of memory");
        v->keys[v->count] = key;
    }
    v->items[v->count++] = item;
}

static JVal *jparse_value(JParser *jp) {
    jskip(jp);
    char c = *jp->p;
    if (c == '{') {
        JVal *obj = jnew(J_OBJ);
        jp->p++;
        jskip(jp);
        if (*jp->p == '}') {
            jp->p++;
            return obj;
        }
        for (;;) {
            jskip(jp);
            char *key = jparse_string(jp);
            jexpect(jp, ':');
            jpush(obj, key, jparse_value(jp));
            jskip(jp);
            if (*jp->p == ',') {
                jp->p++;
                continue;
            }
            jexpect(jp, '}');
            return obj;
        }
    }
    if (c == '[') {
        JVal *arr = jnew(J_ARR);
        jp->p++;
        jskip(jp);
        if (*jp->p == ']') {
            jp->p++;
            return arr;
        }
        for (;;) {
            jpush(arr, NULL, jparse_value(jp));
            jskip(jp);
            if (*jp->p == ',') {
                jp->p++;
                continue;
            }
            jexpect(jp, ']');
            return arr;
        }
    }
    if (c == '"') {
        JVal *str = jnew(J_STR);
        str->str = jparse_string(jp);
        return str;
    }
    if (!strncmp(jp->p, "true", 4)) {
        jp->p += 4;
        JVal *v = jnew(J_BOOL);
        v->boolean = 1;
        return v;
    }
    if (!strncmp(jp->p, "false", 5)) {
        jp->p += 5;
        JVal *v = jnew(J_BOOL);
        return v;
    }
    if (!strncmp(jp->p, "null", 4)) {
        jp->p += 4;
        return jnew(J_NULL);
    }
    {
        char *end = NULL;
        double num = strtod(jp->p, &end);
        if (end == jp->p) die("invalid JSON value");
        jp->p = end;
        JVal *v = jnew(J_NUM);
        v->num = num;
        return v;
    }
}

static JVal *jget(const JVal *obj, const char *key) {
    if (!obj || obj->type != J_OBJ) return NULL;
    for (size_t i = 0; i < obj->count; i++)
        if (obj->keys[i] && !strcmp(obj->keys[i], key)) return obj->items[i];
    return NULL;
}

/* ------------------------------------------------------------------- hashes
 * SHA-1, SHA-256 and SHA-512 in plain C.  A cluster normally uses one of them;
 * all three exist so `doctor` can show what a mismatched token would produce.
 * Correctness is pinned by `--selftest`, which replays the RFC 6238 vectors.
 */

typedef enum { HASH_SHA1, HASH_SHA256, HASH_SHA512 } HashAlg;

static const uint64_t K512[80] = {
    0x428a2f98d728ae22, 0x7137449123ef65cd, 0xb5c0fbcfec4d3b2f, 0xe9b5dba58189dbbc,
    0x3956c25bf348b538, 0x59f111f1b605d019, 0x923f82a4af194f9b, 0xab1c5ed5da6d8118,
    0xd807aa98a3030242, 0x12835b0145706fbe, 0x243185be4ee4b28c, 0x550c7dc3d5ffb4e2,
    0x72be5d74f27b896f, 0x80deb1fe3b1696b1, 0x9bdc06a725c71235, 0xc19bf174cf692694,
    0xe49b69c19ef14ad2, 0xefbe4786384f25e3, 0x0fc19dc68b8cd5b5, 0x240ca1cc77ac9c65,
    0x2de92c6f592b0275, 0x4a7484aa6ea6e483, 0x5cb0a9dcbd41fbd4, 0x76f988da831153b5,
    0x983e5152ee66dfab, 0xa831c66d2db43210, 0xb00327c898fb213f, 0xbf597fc7beef0ee4,
    0xc6e00bf33da88fc2, 0xd5a79147930aa725, 0x06ca6351e003826f, 0x142929670a0e6e70,
    0x27b70a8546d22ffc, 0x2e1b21385c26c926, 0x4d2c6dfc5ac42aed, 0x53380d139d95b3df,
    0x650a73548baf63de, 0x766a0abb3c77b2a8, 0x81c2c92e47edaee6, 0x92722c851482353b,
    0xa2bfe8a14cf10364, 0xa81a664bbc423001, 0xc24b8b70d0f89791, 0xc76c51a30654be30,
    0xd192e819d6ef5218, 0xd69906245565a910, 0xf40e35855771202a, 0x106aa07032bbd1b8,
    0x19a4c116b8d2d0c8, 0x1e376c085141ab53, 0x2748774cdf8eeb99, 0x34b0bcb5e19b48a8,
    0x391c0cb3c5c95a63, 0x4ed8aa4ae3418acb, 0x5b9cca4f7763e373, 0x682e6ff3d6b2b8a3,
    0x748f82ee5defb2fc, 0x78a5636f43172f60, 0x84c87814a1f0ab72, 0x8cc702081a6439ec,
    0x90befffa23631e28, 0xa4506cebde82bde9, 0xbef9a3f7b2c67915, 0xc67178f2e372532b,
    0xca273eceea26619c, 0xd186b8c721c0c207, 0xeada7dd6cde0eb1e, 0xf57d4f7fee6ed178,
    0x06f067aa72176fba, 0x0a637dc5a2c898a6, 0x113f9804bef90dae, 0x1b710b35131c471b,
    0x28db77f523047d84, 0x32caab7b40c72493, 0x3c9ebe0a15c9bebc, 0x431d67c49c100d4c,
    0x4cc5d4becb3e42b6, 0x597f299cfc657e2a, 0x5fcb6fab3ad6faec, 0x6c44198c4a475817,
};

static const uint64_t H512[8] = {
    0x6a09e667f3bcc908, 0xbb67ae8584caa73b, 0x3c6ef372fe94f82b, 0xa54ff53a5f1d36f1,
    0x510e527fade682d1, 0x9b05688c2b3e6c1f, 0x1f83d9abfb41bd6b, 0x5be0cd19137e2179,
};

static const uint32_t K256[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

static const uint32_t H256[8] = {
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
};

static uint32_t rotr32(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }
static uint32_t rotl32(uint32_t x, int n) { return (x << n) | (x >> (32 - n)); }
static uint64_t rotr64(uint64_t x, int n) { return (x >> n) | (x << (64 - n)); }

typedef struct {
    uint32_t h[5];
    uint64_t bytes;
    unsigned char buf[64];
    size_t used;
} Sha1Ctx;

typedef struct {
    uint32_t h[8];
    uint64_t bytes;
    unsigned char buf[64];
    size_t used;
} Sha256Ctx;

typedef struct {
    uint64_t h[8];
    uint64_t bytes;
    unsigned char buf[128];
    size_t used;
} Sha512Ctx;

typedef struct {
    HashAlg alg;
    union {
        Sha1Ctx s1;
        Sha256Ctx s256;
        Sha512Ctx s512;
    } u;
} Hasher;

static void sha1_compress(Sha1Ctx *c, const unsigned char *p) {
    uint32_t w[80];
    for (int i = 0; i < 16; i++)
        w[i] = ((uint32_t)p[i * 4] << 24) | ((uint32_t)p[i * 4 + 1] << 16) |
               ((uint32_t)p[i * 4 + 2] << 8) | (uint32_t)p[i * 4 + 3];
    for (int i = 16; i < 80; i++) w[i] = rotl32(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
    uint32_t a = c->h[0], b = c->h[1], d = c->h[3], e = c->h[4], cc = c->h[2];
    for (int i = 0; i < 80; i++) {
        uint32_t f, k;
        if (i < 20) {
            f = (b & cc) | (~b & d);
            k = 0x5A827999;
        } else if (i < 40) {
            f = b ^ cc ^ d;
            k = 0x6ED9EBA1;
        } else if (i < 60) {
            f = (b & cc) | (b & d) | (cc & d);
            k = 0x8F1BBCDC;
        } else {
            f = b ^ cc ^ d;
            k = 0xCA62C1D6;
        }
        uint32_t tmp = rotl32(a, 5) + f + e + k + w[i];
        e = d;
        d = cc;
        cc = rotl32(b, 30);
        b = a;
        a = tmp;
    }
    c->h[0] += a;
    c->h[1] += b;
    c->h[2] += cc;
    c->h[3] += d;
    c->h[4] += e;
}

static void sha256_compress(Sha256Ctx *c, const unsigned char *p) {
    uint32_t w[64];
    for (int i = 0; i < 16; i++)
        w[i] = ((uint32_t)p[i * 4] << 24) | ((uint32_t)p[i * 4 + 1] << 16) |
               ((uint32_t)p[i * 4 + 2] << 8) | (uint32_t)p[i * 4 + 3];
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = rotr32(w[i - 15], 7) ^ rotr32(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = rotr32(w[i - 2], 17) ^ rotr32(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = c->h[0], b = c->h[1], cc = c->h[2], d = c->h[3];
    uint32_t e = c->h[4], f = c->h[5], g = c->h[6], h = c->h[7];
    for (int i = 0; i < 64; i++) {
        uint32_t s1 = rotr32(e, 6) ^ rotr32(e, 11) ^ rotr32(e, 25);
        uint32_t ch = (e & f) ^ (~e & g);
        uint32_t t1 = h + s1 + ch + K256[i] + w[i];
        uint32_t s0 = rotr32(a, 2) ^ rotr32(a, 13) ^ rotr32(a, 22);
        uint32_t maj = (a & b) ^ (a & cc) ^ (b & cc);
        uint32_t t2 = s0 + maj;
        h = g;
        g = f;
        f = e;
        e = d + t1;
        d = cc;
        cc = b;
        b = a;
        a = t1 + t2;
    }
    c->h[0] += a;
    c->h[1] += b;
    c->h[2] += cc;
    c->h[3] += d;
    c->h[4] += e;
    c->h[5] += f;
    c->h[6] += g;
    c->h[7] += h;
}

static void sha512_compress(Sha512Ctx *c, const unsigned char *p) {
    uint64_t w[80];
    for (int i = 0; i < 16; i++) {
        w[i] = 0;
        for (int k = 0; k < 8; k++) w[i] = (w[i] << 8) | (uint64_t)p[i * 8 + k];
    }
    for (int i = 16; i < 80; i++) {
        uint64_t s0 = rotr64(w[i - 15], 1) ^ rotr64(w[i - 15], 8) ^ (w[i - 15] >> 7);
        uint64_t s1 = rotr64(w[i - 2], 19) ^ rotr64(w[i - 2], 61) ^ (w[i - 2] >> 6);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint64_t a = c->h[0], b = c->h[1], cc = c->h[2], d = c->h[3];
    uint64_t e = c->h[4], f = c->h[5], g = c->h[6], h = c->h[7];
    for (int i = 0; i < 80; i++) {
        uint64_t s1 = rotr64(e, 14) ^ rotr64(e, 18) ^ rotr64(e, 41);
        uint64_t ch = (e & f) ^ (~e & g);
        uint64_t t1 = h + s1 + ch + K512[i] + w[i];
        uint64_t s0 = rotr64(a, 28) ^ rotr64(a, 34) ^ rotr64(a, 39);
        uint64_t maj = (a & b) ^ (a & cc) ^ (b & cc);
        uint64_t t2 = s0 + maj;
        h = g;
        g = f;
        f = e;
        e = d + t1;
        d = cc;
        cc = b;
        b = a;
        a = t1 + t2;
    }
    c->h[0] += a;
    c->h[1] += b;
    c->h[2] += cc;
    c->h[3] += d;
    c->h[4] += e;
    c->h[5] += f;
    c->h[6] += g;
    c->h[7] += h;
}

static size_t hasher_block(HashAlg alg) { return alg == HASH_SHA512 ? 128 : 64; }
static size_t hasher_len(HashAlg alg) {
    return alg == HASH_SHA512 ? 64 : (alg == HASH_SHA256 ? 32 : 20);
}

/* The three contexts store `used`, `bytes` and `buf` at different offsets, so
   every access goes through the active union member -- never through u.s1. */
static size_t *hasher_used(Hasher *hs) {
    switch (hs->alg) {
    case HASH_SHA1: return &hs->u.s1.used;
    case HASH_SHA256: return &hs->u.s256.used;
    default: return &hs->u.s512.used;
    }
}

static uint64_t *hasher_bytes(Hasher *hs) {
    switch (hs->alg) {
    case HASH_SHA1: return &hs->u.s1.bytes;
    case HASH_SHA256: return &hs->u.s256.bytes;
    default: return &hs->u.s512.bytes;
    }
}

static unsigned char *hasher_buffer(Hasher *hs) {
    switch (hs->alg) {
    case HASH_SHA1: return hs->u.s1.buf;
    case HASH_SHA256: return hs->u.s256.buf;
    default: return hs->u.s512.buf;
    }
}

static void hasher_init(Hasher *hs, HashAlg alg) {
    hs->alg = alg;
    switch (alg) {
    case HASH_SHA1:
        hs->u.s1.h[0] = 0x67452301;
        hs->u.s1.h[1] = 0xEFCDAB89;
        hs->u.s1.h[2] = 0x98BADCFE;
        hs->u.s1.h[3] = 0x10325476;
        hs->u.s1.h[4] = 0xC3D2E1F0;
        hs->u.s1.bytes = 0;
        hs->u.s1.used = 0;
        break;
    case HASH_SHA256:
        memcpy(hs->u.s256.h, H256, sizeof H256);
        hs->u.s256.bytes = 0;
        hs->u.s256.used = 0;
        break;
    case HASH_SHA512:
        memcpy(hs->u.s512.h, H512, sizeof H512);
        hs->u.s512.bytes = 0;
        hs->u.s512.used = 0;
        break;
    }
}

static void hasher_update(Hasher *hs, const void *data, size_t len) {
    const unsigned char *p = data;
    size_t block = hasher_block(hs->alg);
    size_t *used = hasher_used(hs);
    unsigned char *buf = hasher_buffer(hs);
    *hasher_bytes(hs) += len;
    while (len) {
        size_t take = block - *used;
        if (take > len) take = len;
        memcpy(buf + *used, p, take);
        *used += take;
        p += take;
        len -= take;
        if (*used == block) {
            if (hs->alg == HASH_SHA512) sha512_compress(&hs->u.s512, buf);
            else if (hs->alg == HASH_SHA256) sha256_compress(&hs->u.s256, buf);
            else sha1_compress(&hs->u.s1, buf);
            *used = 0;
        }
    }
}

static void hasher_final(Hasher *hs, unsigned char *out) {
    size_t block = hasher_block(hs->alg);
    size_t dlen = hasher_len(hs->alg);
    int is512 = (hs->alg == HASH_SHA512);
    uint64_t bits = *hasher_bytes(hs) * 8;
    size_t used = *hasher_used(hs);
    size_t tail = is512 ? 16 : 8; /* SHA-512 carries a 128-bit length */
    unsigned char pad[128];
    unsigned char lenbuf[16];
    size_t padlen = (used < block - tail) ? (block - tail - used) : (2 * block - tail - used);
    memset(pad, 0, sizeof pad);
    pad[0] = 0x80;
    hasher_update(hs, pad, padlen);
    memset(lenbuf, 0, sizeof lenbuf);
    for (int i = 0; i < 8; i++) lenbuf[tail - 1 - i] = (unsigned char)(bits >> (8 * i));
    hasher_update(hs, lenbuf, tail);
    for (size_t i = 0; i < dlen; i++) {
        if (is512) out[i] = (unsigned char)(hs->u.s512.h[i / 8] >> (56 - 8 * (i % 8)));
        else if (hs->alg == HASH_SHA256)
            out[i] = (unsigned char)(hs->u.s256.h[i / 4] >> (24 - 8 * (i % 4)));
        else out[i] = (unsigned char)(hs->u.s1.h[i / 4] >> (24 - 8 * (i % 4)));
    }
}

static void hash_bytes(HashAlg alg, const void *data, size_t len, unsigned char *out) {
    Hasher hs;
    hasher_init(&hs, alg);
    hasher_update(&hs, data, len);
    hasher_final(&hs, out);
}

static void hmac_hash(HashAlg alg, const unsigned char *key, size_t keylen,
                      const unsigned char *msg, size_t msglen, unsigned char *out) {
    unsigned char block_key[128];
    unsigned char ipad[128], opad[128];
    unsigned char inner[64];
    size_t block = hasher_block(alg);
    Hasher hs;

    memset(block_key, 0, sizeof block_key);
    if (keylen > block) hash_bytes(alg, key, keylen, block_key);
    else memcpy(block_key, key, keylen);
    for (size_t i = 0; i < block; i++) {
        ipad[i] = (unsigned char)(block_key[i] ^ 0x36);
        opad[i] = (unsigned char)(block_key[i] ^ 0x5C);
    }
    hasher_init(&hs, alg);
    hasher_update(&hs, ipad, block);
    hasher_update(&hs, msg, msglen);
    hasher_final(&hs, inner);
    hasher_init(&hs, alg);
    hasher_update(&hs, opad, block);
    hasher_update(&hs, inner, hasher_len(alg));
    hasher_final(&hs, out);
}

/* -------------------------------------------------------------- time / TOTP */

static double monotime(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

static void sleep_seconds(double seconds) {
    struct timespec ts;
    if (seconds <= 0) return;
    ts.tv_sec = (time_t)seconds;
    ts.tv_nsec = (long)((seconds - (double)ts.tv_sec) * 1e9);
    nanosleep(&ts, NULL);
}

typedef struct {
    unsigned char key[512];
    size_t keylen;
    HashAlg alg;
    int digits;
    double period;
    char name[16];
} Token;

static int b32val(char c) {
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a';
    if (c >= '2' && c <= '7') return c - '2' + 26;
    return -1;
}

static int base32_decode(const char *text, unsigned char *out, size_t outmax, size_t *outlen) {
    uint32_t buf = 0;
    int bits = 0;
    size_t n = 0;
    for (const char *p = text; *p; p++) {
        if (*p == '=' || isspace((unsigned char)*p)) continue;
        int v = b32val(*p);
        if (v < 0) return -1;
        buf = (buf << 5) | (uint32_t)v;
        bits += 5;
        if (bits >= 8) {
            bits -= 8;
            if (n >= outmax) return -1;
            out[n++] = (unsigned char)((buf >> bits) & 0xFF);
        }
    }
    *outlen = n;
    return n > 0 ? 0 : -1;
}

static void hotp(const Token *tok, uint64_t counter, char *out, size_t outsz) {
    unsigned char msg[8];
    unsigned char mac[64];
    for (int i = 0; i < 8; i++) msg[7 - i] = (unsigned char)(counter >> (8 * i));
    hmac_hash(tok->alg, tok->key, tok->keylen, msg, sizeof msg, mac);
    int offset = mac[hasher_len(tok->alg) - 1] & 0x0F;
    uint32_t bin = ((uint32_t)(mac[offset] & 0x7F) << 24) | ((uint32_t)mac[offset + 1] << 16) |
                   ((uint32_t)mac[offset + 2] << 8) | (uint32_t)mac[offset + 3];
    uint32_t modulus = 1;
    for (int i = 0; i < tok->digits; i++) modulus *= 10;
    snprintf(out, outsz, "%0*u", tok->digits, bin % modulus);
}

static void code_at(const Token *tok, double at, char *out, size_t outsz) {
    hotp(tok, (uint64_t)(at / tok->period), out, outsz);
}

static double window_remaining(const Token *tok, double at) {
    double into = at - tok->period * (double)((uint64_t)(at / tok->period));
    return tok->period - into;
}

/* A code with enough of its window left to survive the ssh round trip. */
static void fresh_code(const Token *tok, char *out, size_t outsz) {
    double now = monotime();
    double remaining = window_remaining(tok, now);
    if (remaining < MIN_REMAINING) {
        sleep_seconds(remaining + 0.25);
        now = monotime();
    }
    code_at(tok, now, out, outsz);
}

/* ---------------------------------------------------------------- the config */

typedef struct {
    char host[256];
    char user[256];
    char password[256];
    int has_password;
    Token token;
    int ports[16];
    size_t nports;
    char ports_render[128];
} Config;

static int is_placeholder(const char *s) {
    size_t n = s ? strlen(s) : 0;
    return n >= 2 && s[0] == '<' && s[n - 1] == '>';
}

static const char *config_path(void) {
    static char chosen[4096];
    const char *home = getenv("HOME");
    if (!home) die("HOME is not set");
    snprintf(chosen, sizeof chosen, "%s%s", home, CONFIG_RELATIVE);
    return chosen;
}

static char *slurp(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) die("cannot read %s: %s", path, strerror(errno));
    if (fseek(f, 0, SEEK_END) != 0) die("cannot read %s", path);
    long size = ftell(f);
    if (size < 0) die("cannot read %s", path);
    rewind(f);
    char *buf = malloc((size_t)size + 1);
    if (!buf) die("out of memory");
    size_t got = fread(buf, 1, (size_t)size, f);
    buf[got] = '\0';
    fclose(f);
    return buf;
}

static void percent_decode(char *s) {
    char *dst = s;
    for (char *src = s; *src; src++) {
        if (*src == '%' && isxdigit((unsigned char)src[1]) && isxdigit((unsigned char)src[2])) {
            char hex[3] = {src[1], src[2], 0};
            *dst++ = (char)strtol(hex, NULL, 16);
            src += 2;
        } else {
            *dst++ = *src;
        }
    }
    *dst = '\0';
}

static void take_query_value(const char *key, const char *value, Token *tok, int *have_secret,
                             char *secret, size_t secret_sz) {
    if (!strcmp(key, "secret")) {
        snprintf(secret, secret_sz, "%s", value);
        *have_secret = 1;
    } else if (!strcmp(key, "algorithm")) {
        snprintf(tok->name, sizeof tok->name, "%s", value);
    } else if (!strcmp(key, "digits")) {
        tok->digits = atoi(value);
    } else if (!strcmp(key, "period")) {
        tok->period = atof(value);
    }
}

static void parse_otpauth(const char *uri, Token *tok, char *secret, size_t secret_sz, int *have_secret) {
    const char *query = strchr(uri, '?');
    if (!query) die("oathpass.otp.uri has no query string");
    if (strncmp(uri, "otpauth://", 10) != 0) die("oathpass.otp.uri is not an otpauth:// URI");
    char *copy = strdup(query + 1);
    if (!copy) die("out of memory");
    for (char *pair = strtok(copy, "&"); pair; pair = strtok(NULL, "&")) {
        char *eq = strchr(pair, '=');
        if (!eq) continue;
        *eq = '\0';
        char *value = eq + 1;
        percent_decode(value);
        take_query_value(pair, value, tok, have_secret, secret, secret_sz);
    }
    free(copy);
}

static void load_config(Config *cfg) {
    memset(cfg, 0, sizeof *cfg);
    cfg->token.digits = 8;
    cfg->token.period = 30.0;
    strcpy(cfg->token.name, "SHA512");

    const char *path = config_path();
    struct stat st;
    if (stat(path, &st) != 0) die("cannot read %s: %s", path, strerror(errno));
    if (st.st_mode & 0077)
        note("warning: %s is mode %03o; it holds the OATH seed -- chmod 600 it", path,
             (unsigned)(st.st_mode & 0777));

    char *text = slurp(path);
    JParser jp = {text, text};
    JVal *root = jparse_value(&jp);
    JVal *block = jget(root, "oathpass");
    if (!block) die("no \"oathpass\" object in %s", path);

    JVal *host = jget(block, "host");
    JVal *user = jget(block, "user");
    if (!host || host->type != J_STR || is_placeholder(host->str))
        die("oathpass.host is a placeholder -- fill it in %s", path);
    if (!user || user->type != J_STR || is_placeholder(user->str))
        die("oathpass.user is a placeholder -- fill it in %s", path);
    snprintf(cfg->host, sizeof cfg->host, "%s", host->str);
    snprintf(cfg->user, sizeof cfg->user, "%s", user->str);

    JVal *password = jget(block, "password");
    if (password && password->type == J_STR && !is_placeholder(password->str)) {
        snprintf(cfg->password, sizeof cfg->password, "%s", password->str);
        cfg->has_password = 1;
    }

    JVal *ports = jget(block, "ports");
    if (!ports) die("oathpass.ports is missing in %s", path);
    if (ports->type != J_ARR) {
        JVal *only[1] = {ports};
        ports = jnew(J_ARR);
        jpush(ports, NULL, only[0]);
    }
    for (size_t i = 0; i < ports->count && cfg->nports < 16; i++) {
        JVal *item = ports->items[i];
        int value = -1;
        if (item->type == J_NUM) value = (int)item->num;
        else if (item->type == J_STR && !is_placeholder(item->str)) value = atoi(item->str);
        if (value <= 0 || value > 65535)
            die("oathpass.ports entry %zu is a placeholder or not a port number -- fill it in %s", i + 1, path);
        cfg->ports[cfg->nports++] = value;
    }
    if (!cfg->nports) die("oathpass.ports is empty in %s", path);
    {
        size_t used = 0;
        for (size_t i = 0; i < cfg->nports; i++)
            used += (size_t)snprintf(cfg->ports_render + used, sizeof cfg->ports_render - used, "%s%d",
                                     i ? "," : "", cfg->ports[i]);
    }

    JVal *time_url = jget(block, "time_url");
    if (time_url && time_url->type == J_STR && time_url->str[0] && !is_placeholder(time_url->str))
        snprintf(g_time_url, sizeof g_time_url, "%s", time_url->str);

    JVal *otp = jget(block, "otp");
    if (!otp) die("oathpass.otp is missing in %s", path);
    char secret[512] = {0};
    int have_secret = 0;
    JVal *uri = jget(otp, "uri");
    if (uri && uri->type == J_STR && !is_placeholder(uri->str)) {
        parse_otpauth(uri->str, &cfg->token, secret, sizeof secret, &have_secret);
    } else {
        JVal *raw = jget(otp, "secret");
        if (!raw || raw->type != J_STR || is_placeholder(raw->str))
            die("oathpass.otp.uri (or oathpass.otp.secret) is a placeholder -- fill it in %s", path);
        snprintf(secret, sizeof secret, "%s", raw->str);
        have_secret = 1;
        JVal *algorithm = jget(otp, "algorithm");
        JVal *digits = jget(otp, "digits");
        JVal *period = jget(otp, "period");
        if (algorithm && algorithm->type == J_STR)
            snprintf(cfg->token.name, sizeof cfg->token.name, "%s", algorithm->str);
        if (digits && digits->type == J_NUM) cfg->token.digits = (int)digits->num;
        if (period && period->type == J_NUM) cfg->token.period = period->num;
    }
    if (!have_secret) die("oathpass.otp carries no secret -- fill it in %s", path);

    for (char *p = cfg->token.name; *p; p++) *p = (char)toupper((unsigned char)*p);
    if (!strcmp(cfg->token.name, "SHA512")) cfg->token.alg = HASH_SHA512;
    else if (!strcmp(cfg->token.name, "SHA256")) cfg->token.alg = HASH_SHA256;
    else if (!strcmp(cfg->token.name, "SHA1")) cfg->token.alg = HASH_SHA1;
    else die("unsupported oathpass.otp algorithm %s", cfg->token.name);
    if (cfg->token.digits < 6 || cfg->token.digits > 10) die("oathpass.otp digits out of range");
    if (cfg->token.period < 1 || cfg->token.period > 3600) die("oathpass.otp period out of range");

    if (base32_decode(secret, cfg->token.key, sizeof cfg->token.key, &cfg->token.keylen) != 0)
        die("oathpass.otp secret is not valid base32");
}

/* ------------------------------------------------------------------ askpass */

static int contains_ci(const char *haystack, const char *needle) {
    size_t n = strlen(needle);
    for (const char *p = haystack; *p; p++) {
        size_t i = 0;
        while (i < n && p[i] && tolower((unsigned char)p[i]) == tolower((unsigned char)needle[i])) i++;
        if (i == n) return 1;
    }
    return 0;
}

static int is_otp_prompt(const char *prompt) {
    return contains_ci(prompt, "one-time") || contains_ci(prompt, "one time") ||
           contains_ci(prompt, "oath") || contains_ci(prompt, "otp") ||
           contains_ci(prompt, "verification") || contains_ci(prompt, "token") ||
           contains_ci(prompt, "code") || strstr(prompt, "动态") || strstr(prompt, "口令") ||
           strstr(prompt, "验证码");
}

static int is_password_prompt(const char *prompt) {
    return contains_ci(prompt, "password") || contains_ci(prompt, "passphrase") ||
           contains_ci(prompt, "密码");
}

static int askpass(const char *prompt) {
    Config cfg;
    load_config(&cfg);
    /* OTP first: the cluster's prompt is "One-time password (OATH) ...", which
       a naive password match would answer with the wrong secret. */
    if (is_otp_prompt(prompt)) {
        char code[16];
        fresh_code(&cfg.token, code, sizeof code);
        printf("%s\n", code);
        return 0;
    }
    if (is_password_prompt(prompt)) {
        if (!cfg.has_password) die("ssh asked for a password but oathpass.password is not set");
        printf("%s\n", cfg.password);
        return 0;
    }
    {
        char code[16];
        fresh_code(&cfg.token, code, sizeof code);
        printf("%s\n", code);
        return 0;
    }
}

/* ---------------------------------------------------------------- networking */

static int resolve(const char *host, int port, struct sockaddr_storage *out, socklen_t *outlen) {
    struct addrinfo hints;
    struct addrinfo *res = NULL;
    memset(&hints, 0, sizeof hints);
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    char service[16];
    snprintf(service, sizeof service, "%d", port);
    if (getaddrinfo(host, service, &hints, &res) != 0 || !res) return -1;
    memcpy(out, res->ai_addr, res->ai_addrlen);
    *outlen = res->ai_addrlen;
    freeaddrinfo(res);
    return 0;
}

/* Probe all ports at once; return the lowest index that answers, or -1.
   `reachable`, when given, receives one flag per configured port. */
static int probe_ports(const Config *cfg, double budget_s, int *reachable) {
    struct pollfd fds[16];
    struct sockaddr_storage addr[16];
    socklen_t addrlen[16];
    int count = (int)cfg->nports;
    int started[16];
    for (int i = 0; i < count; i++) {
        started[i] = 0;
        fds[i].fd = -1;
        fds[i].events = POLLOUT;
        if (resolve(cfg->host, cfg->ports[i], &addr[i], &addrlen[i]) != 0) continue;
        int fd = socket(addr[i].ss_family, SOCK_STREAM, 0);
        if (fd < 0) continue;
        fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) | O_NONBLOCK);
        fds[i].fd = fd;
        started[i] = 1;
        if (connect(fd, (struct sockaddr *)&addr[i], addrlen[i]) == 0) {
            started[i] = 2; /* connected immediately */
        } else if (errno != EINPROGRESS) {
            started[i] = 3; /* failed immediately */
        }
    }

    struct timespec start, now;
    clock_gettime(CLOCK_MONOTONIC, &start);
    for (;;) {
        int pending = 0;
        for (int i = 0; i < count; i++)
            if (started[i] == 1) pending++;
        if (pending == 0) break;
        clock_gettime(CLOCK_MONOTONIC, &now);
        double elapsed = (double)(now.tv_sec - start.tv_sec) +
                         (double)(now.tv_nsec - start.tv_nsec) / 1e9;
        int left = (int)((budget_s - elapsed) * 1000.0);
        if (left <= 0) break;
        struct pollfd wait[16];
        int n = 0;
        int map[16];
        for (int i = 0; i < count; i++)
            if (started[i] == 1) {
                wait[n] = fds[i];
                map[n] = i;
                n++;
            }
        int ready = poll(wait, (nfds_t)n, left);
        if (ready <= 0) break;
        for (int k = 0; k < n; k++) {
            if (wait[k].revents) {
                int err = 0;
                socklen_t len = sizeof err;
                getsockopt(fds[map[k]].fd, SOL_SOCKET, SO_ERROR, &err, &len);
                started[map[k]] = (err == 0) ? 2 : 3;
            }
        }
    }

    int best = -1;
    for (int i = 0; i < count; i++) {
        if (started[i] == 2 && best < 0) best = i;
        if (started[i] == 1) started[i] = 3; /* never resolved: treat as silent */
        if (fds[i].fd >= 0) close(fds[i].fd);
        if (reachable) reachable[i] = (started[i] == 2);
    }
    return best;
}

/* ---------------------------------------------------------------- running ssh */

typedef struct {
    char text[TAIL_MAX];
    size_t len;
} Tail;

/* `n` is clamped to the source buffer, which keeps the copy provably in
   bounds and makes the contract explicit. */
static void tail_add(Tail *tail, const char *chunk, size_t chunk_len, size_t n) {
    if (n > chunk_len) n = chunk_len;
    if (n >= TAIL_MAX) {
        chunk += n - (TAIL_MAX - 1);
        n = TAIL_MAX - 1;
    }
    if (tail->len + n >= TAIL_MAX - 1) {
        size_t drop = tail->len + n - (TAIL_MAX - 1);
        memmove(tail->text, tail->text + drop, tail->len - drop);
        tail->len -= drop;
    }
    memcpy(tail->text + tail->len, chunk, n);
    tail->len += n;
    tail->text[tail->len] = '\0';
}

/* Run ssh, echoing its stderr live and keeping the tail for classification. */
static int run_command(char *const argv[], const char *askpass_path, Tail *tail) {
    int pipefd[2];
    if (pipe(pipefd) != 0) die("pipe: %s", strerror(errno));

    setenv("OATHPASS_ASKPASS", "1", 1);
    setenv("SSH_ASKPASS", askpass_path, 1);
    setenv("SSH_ASKPASS_REQUIRE", "force", 1);
    if (!getenv("DISPLAY")) setenv("DISPLAY", ":0", 1);

    pid_t pid = fork();
    if (pid < 0) die("fork: %s", strerror(errno));
    if (pid == 0) {
        dup2(pipefd[1], STDERR_FILENO);
        close(pipefd[0]);
        close(pipefd[1]);
        execvp(argv[0], argv);
        fprintf(stderr, "oathpass: cannot run %s: %s\n", argv[0], strerror(errno));
        _exit(127);
    }

    close(pipefd[1]);
    char chunk[1024];
    for (;;) {
        ssize_t got = read(pipefd[0], chunk, sizeof chunk);
        if (got > 0) {
            fwrite(chunk, 1, (size_t)got, stderr);
            fflush(stderr);
            tail_add(tail, chunk, sizeof chunk, (size_t)got);
            continue;
        }
        if (got < 0 && errno == EINTR) continue;
        break;
    }
    close(pipefd[0]);
    int status = 0;
    while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {
    }
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    return 255;
}

static const char *self_path(void) {
    static char buf[4096];
#ifdef __APPLE__
    uint32_t size = sizeof buf;
    if (_NSGetExecutablePath(buf, &size) != 0) die("cannot locate the executable");
#else
    ssize_t got = readlink("/proc/self/exe", buf, sizeof buf - 1);
    if (got <= 0) die("cannot locate the executable");
    buf[got] = '\0';
#endif
    return buf;
}

static char *const *build_ssh(char **storage, const Config *cfg, int port, char **userargs) {
    size_t i = 0;
    storage[i++] = "ssh";
    storage[i++] = "-o";
    storage[i++] = "PreferredAuthentications=keyboard-interactive";
    storage[i++] = "-o";
    storage[i++] = "PubkeyAuthentication=no";
    storage[i++] = "-o";
    storage[i++] = "StrictHostKeyChecking=accept-new";
    storage[i++] = "-o";
    storage[i++] = "ConnectTimeout=10";
    storage[i++] = "-o";
    storage[i++] = "ServerAliveInterval=60";
    storage[i++] = "-o";
    storage[i++] = "NumberOfPasswordPrompts=1";
    storage[i++] = isatty(STDIN_FILENO) ? "-t" : "-T";
    char *portbuf = malloc(16);
    char *target = malloc(600);
    if (!portbuf || !target) die("out of memory");
    snprintf(portbuf, 16, "%d", port);
    snprintf(target, 600, "%s@%s", cfg->user, cfg->host);
    storage[i++] = "-p";
    storage[i++] = portbuf;
    storage[i++] = target;
    for (char **extra = userargs; extra && *extra; extra++) storage[i++] = *extra;
    storage[i] = NULL;
    return storage;
}

/* ------------------------------------------------------------------- commands */

typedef struct {
    int index; /* 0-based into cfg->ports */
    int port;
    int reachable;
} Node;

/* Order the login candidates best-first: answering nodes in listed order, then
   the silent ones as a last resort.  Returns how many were written, or -1 when
   nothing answered at all. */
static int select_nodes(const Config *cfg, int forced_index, int forced_port, Node *out, int outmax,
                        int *reachable_count, int *n_answered) {
    int reachable[16] = {0};
    int answered = 0;
    int first = -1;

    if (forced_port > 0) {
        Config narrowed = *cfg;
        narrowed.nports = 1;
        narrowed.ports[0] = forced_port;
        first = probe_ports(&narrowed, PROBE_MS / 1000.0, NULL);
        answered = (first == 0);
        if (reachable_count) *reachable_count = answered;
        if (n_answered) *n_answered = answered;
        if (!answered) return -1;
        out[0].index = 0;
        out[0].port = forced_port;
        out[0].reachable = 1;
        return 1;
    }

    if (forced_index > 0) {
        if ((size_t)forced_index > cfg->nports) return -2;
        Config narrowed = *cfg;
        narrowed.nports = 1;
        narrowed.ports[0] = cfg->ports[forced_index - 1];
        first = probe_ports(&narrowed, PROBE_MS / 1000.0, NULL);
        answered = (first == 0);
        if (reachable_count) *reachable_count = answered;
        if (n_answered) *n_answered = answered;
        if (!answered) return -1;
        out[0].index = forced_index - 1;
        out[0].port = cfg->ports[forced_index - 1];
        out[0].reachable = 1;
        return 1;
    }

    first = probe_ports(cfg, PROBE_MS / 1000.0, reachable);
    for (int i = 0; i < (int)cfg->nports; i++)
        if (reachable[i]) answered++;
    if (reachable_count) *reachable_count = answered;
    if (n_answered) *n_answered = answered;
    if (first < 0) return -1;

    int n = 0;
    for (int i = 0; i < (int)cfg->nports && n < outmax; i++)
        if (reachable[i]) {
            out[n].index = i;
            out[n].port = cfg->ports[i];
            out[n].reachable = 1;
            n++;
        }
    for (int i = 0; i < (int)cfg->nports && n < outmax; i++)
        if (!reachable[i]) {
            out[n].index = i;
            out[n].port = cfg->ports[i];
            out[n].reachable = 0;
            n++;
        }
    return n;
}

static int report_no_network(const Config *cfg, int forced_index, int forced_port) {
    if (forced_port > 0) note("port %d does not answer", forced_port);
    else if (forced_index > 0) note("node %d (port %d) does not answer", forced_index, cfg->ports[forced_index - 1]);
    else note("no login node answered on %s (ports %s)", cfg->host, cfg->ports_render);
    note("this is almost always the network: connect to the VPN or campus network "
         "your cluster needs, then run oathpass again");
    return 3;
}

static int cmd_login(const Config *cfg, char **userargs, int forced_index, int forced_port) {
    Node nodes[16];
    int count = select_nodes(cfg, forced_index, forced_port, nodes, 16, NULL, NULL);
    if (count == -2) die("--node %d is out of range (1..%zu)", forced_index, cfg->nports);
    if (count < 0) return report_no_network(cfg, forced_index, forced_port);

    char *slots[64];
    int auth_attempts = 0;
    int ssh_runs = 0;
    const char *askpass_path = self_path();

    for (int cursor = 0; cursor < count; cursor++) {
        int port = nodes[cursor].port;

        for (;;) {
            if (ssh_runs >= MAX_SSH_RUNS) {
                note("giving up after %d ssh runs", ssh_runs);
                return 255;
            }
            memset(slots, 0, sizeof slots);
            build_ssh(slots, cfg, port, userargs);
            Tail tail;
            memset(&tail, 0, sizeof tail);
            ssh_runs++;
            int status = run_command(slots, askpass_path, &tail);
            if (status != 255) return status;

            if (contains_ci(tail.text, "locked") || contains_ci(tail.text, "too many")) {
                note("the account looks locked or rate limited -- stopping now");
                note("wait, then check the account portal; do not retry blindly");
                return 255;
            }
            int auth_failed = contains_ci(tail.text, "permission denied") ||
                              contains_ci(tail.text, "authentication failed") ||
                              contains_ci(tail.text, "no more authentication methods");
            if (auth_failed) {
                auth_attempts++;
                if (auth_attempts >= MAX_AUTH_ATTEMPTS) {
                    note("%d authentication attempts rejected -- stopping", auth_attempts);
                    note("a wrong seed and a drifting clock look identical here; run: oathpass doctor");
                    return 255;
                }
                double wait_s = window_remaining(&cfg->token, monotime()) + 0.5;
                note("code rejected (%d/%d); waiting %.0fs for a fresh window",
                     auth_attempts, MAX_AUTH_ATTEMPTS, wait_s);
                sleep_seconds(wait_s);
                continue; /* retry on the same node: the backend is shared */
            }
            int transport = contains_ci(tail.text, "connection refused") ||
                            contains_ci(tail.text, "connection timed out") ||
                            contains_ci(tail.text, "operation timed out") ||
                            contains_ci(tail.text, "no route to host") ||
                            contains_ci(tail.text, "network is unreachable") ||
                            contains_ci(tail.text, "connection reset") ||
                            contains_ci(tail.text, "connection closed by") ||
                            contains_ci(tail.text, "kex_exchange_identification") ||
                            contains_ci(tail.text, "banner exchange") ||
                            contains_ci(tail.text, "broken pipe");
            if (transport) {
                note("port %d dropped the connection, trying the next node", port);
                break;
            }
            return status;
        }
    }

    note("no login node answered after %d ssh runs", ssh_runs);
    return 255;
}

static int cmd_otp(const Config *cfg, int argc, char **argv) {
    double at = -1;
    for (int i = 0; i < argc; i++) {
        if (!strcmp(argv[i], "--at") && i + 1 < argc) {
            at = atof(argv[++i]);
        } else {
            die("otp takes only --at EPOCH");
        }
    }
    char code[16];
    if (at >= 0) code_at(&cfg->token, at, code, sizeof code);
    else code_at(&cfg->token, monotime(), code, sizeof code);
    printf("%s\n", code);
    return 0;
}

static int cmd_target(const Config *cfg) {
    printf("%s@%s\n", cfg->user, cfg->host);
    return 0;
}

static int cmd_port(const Config *cfg, int forced_index, int forced_port) {
    Node nodes[16];
    int count = select_nodes(cfg, forced_index, forced_port, nodes, 16, NULL, NULL);
    if (count == -2) die("--node %d is out of range (1..%zu)", forced_index, cfg->nports);
    if (count < 0) return report_no_network(cfg, forced_index, forced_port);
    printf("%d\n", nodes[0].port);
    return 0;
}

/* Dry run: everything the login would do, except that ssh never runs. */
static int cmd_check(const Config *cfg, int forced_index, int forced_port) {
    Node nodes[16];
    int answered = 0, answered_again = 0;
    int count = select_nodes(cfg, forced_index, forced_port, nodes, 16, &answered, &answered_again);
    if (count == -2) die("--node %d is out of range (1..%zu)", forced_index, cfg->nports);
    if (count < 0) return report_no_network(cfg, forced_index, forced_port);

    double now = monotime();
    char code[16];
    code_at(&cfg->token, now, code, sizeof code);
    double left = window_remaining(&cfg->token, now);

    char *slots[64];
    memset(slots, 0, sizeof slots);
    build_ssh(slots, cfg, nodes[0].port, NULL);

    printf("config    %s\n", config_path());
    printf("target    %s@%s\n", cfg->user, cfg->host);
    printf("ports     %zu configured; %d reachable\n", cfg->nports, answered);
    printf("node      would use %d of %zu, port %d\n", nodes[0].index + 1, cfg->nports, nodes[0].port);
    printf("token     %s/%d digits/%0.0fs; window %0.0fs left\n", cfg->token.name, cfg->token.digits,
           cfg->token.period, left);
    printf("code      %s\n", code);
    if (left < MIN_REMAINING)
        printf("caution   only %0.0fs left in this window -- run oathpass check again\n", left);
    printf("ssh      ");
    for (size_t i = 0; slots[i]; i++) printf(" %s", slots[i]);
    printf("\nverdict   ready (nothing was sent; this code is live for %0.0fs)\n", left);
    return 0;
}

static int cmd_wrap(const Config *cfg, int argc, char **argv) {
    (void)cfg;
    if (argc < 1) die("wrap needs a command, e.g. oathpass wrap rsync -av ./d/ -- target");
    setenv("OATHPASS_ASKPASS", "1", 1);
    setenv("SSH_ASKPASS", self_path(), 1);
    setenv("SSH_ASKPASS_REQUIRE", "force", 1);
    execvp(argv[0], argv);
    die("cannot run %s: %s", argv[0], strerror(errno));
    return 1;
}

/* Days from 1970-01-01 to a civil date (Howard Hinnant's algorithm).  Written
   out instead of strptime/timegm, which exist on neither all three platforms
   nor in every C library. */
static long long days_from_civil(long long y, unsigned m, unsigned d) {
    y -= (m <= 2);
    long long era = (y >= 0 ? y : y - 399) / 400;
    unsigned yoe = (unsigned)(y - era * 400);
    unsigned doy = (153 * (m + (m > 2 ? -3u : 9u)) + 2) / 5 + d - 1;
    unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + (long long)doe - 719468;
}

/* "Sun, 06 Nov 1994 08:49:37 GMT" -> seconds since the epoch, or -1. */
static long long parse_http_date(const char *text) {
    static const char *months[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
    char weekday[8], month[8];
    int day, year, hour, minute, second;
    if (sscanf(text, "%7[A-Za-z], %d %7[A-Za-z] %d %d:%d:%d", weekday, &day, month, &year,
               &hour, &minute, &second) != 7)
        return -1;
    int mon = -1;
    for (int i = 0; i < 12; i++)
        if (!strncasecmp(month, months[i], 3)) mon = i;
    if (mon < 0 || day < 1 || day > 31 || hour > 23 || minute > 59 || second > 60) return -1;
    long long days = days_from_civil(year, (unsigned)mon + 1, (unsigned)day);
    return days * 86400 + hour * 3600 + minute * 60 + second;
}

static void report_clock(void) {
    printf("\nclock\n");
    time_t now = time(NULL);
    struct tm local;
    localtime_r(&now, &local);
    char stamp[64];
    strftime(stamp, sizeof stamp, "%Y-%m-%d %H:%M:%S %Z", &local);
    printf("  local time      %s\n", stamp);

    /* Any HTTPS host answers with a Date header; `time_url` overrides the default
       for networks that block it. */
    char command[512];
    snprintf(command, sizeof command, "curl -sI --max-time 5 %s 2>/dev/null", g_time_url);
    FILE *f = popen(command, "r");
    int reported = 0;
    if (f) {
        char line[512];
        while (fgets(line, sizeof line, f)) {
            if (strncasecmp(line, "date:", 5) != 0) continue;
            char *value = line + 5;
            while (*value == ' ') value++;
            long long server_time = parse_http_date(value);
            if (server_time >= 0) {
                double offset = difftime((time_t)server_time, time(NULL));
                printf("  remote clock    %+0.0f s vs this Mac", offset);
                if (offset > 3 || offset < -3) printf("   <-- drift, codes will fail");
                printf("\n");
                reported = 1;
            }
            break;
        }
        pclose(f);
    }
    if (!reported) {
        printf("  remote clock    unreachable (%s)\n", g_time_url);
    }
}

static int cmd_doctor(const Config *cfg) {
    double now = monotime();
    char code[16];
    printf("config\n");
    printf("  file            %s\n", config_path());
    printf("  host            %s\n", cfg->host);
    printf("  user            %s\n", cfg->user);
    printf("  ports           %s\n", cfg->ports_render);
    printf("  token           %s/%d digits/%0.0fs, seed %zu bytes\n", cfg->token.name,
           cfg->token.digits, cfg->token.period, cfg->token.keylen);
    printf("  window          %.1fs left of %0.0fs\n", window_remaining(&cfg->token, now),
           cfg->token.period);

    printf("\ncodes at this second (compare with the phone)\n");
    static const struct {
        const char *name;
        HashAlg alg;
    } algorithms[] = {{"SHA1", HASH_SHA1}, {"SHA256", HASH_SHA256}, {"SHA512", HASH_SHA512}};
    for (int a = 0; a < 3; a++) {
        for (int digits = 6; digits <= 8; digits += 2) {
            Token probe = cfg->token;
            probe.alg = algorithms[a].alg;
            probe.digits = digits;
            code_at(&probe, now, code, sizeof code);
            int configured = !strcmp(algorithms[a].name, cfg->token.name) && cfg->token.digits == digits;
            printf("  %-6s %d digits  %s%s\n", algorithms[a].name, digits, code,
                   configured ? "   <-- configured" : "");
        }
    }
    report_clock();
    printf("\nif no code here matches the phone, the seed in the config is wrong;"
           "\nif the right one matches but the login fails, the clock is the problem.\n");
    return 0;
}

static int cmd_selftest(void) {
    /* RFC 6238 Appendix B.  The same base32 path the config uses is exercised. */
    static const struct {
        HashAlg alg;
        const char *b32;
        long long at;
        const char *want;
    } cases[] = {
        {HASH_SHA1, "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 59, "94287082"},
        {HASH_SHA1, "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", 1111111109LL, "07081804"},
        {HASH_SHA256, "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZA====", 59, "46119246"},
        {HASH_SHA256, "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZA====", 1111111109LL, "68084774"},
        {HASH_SHA512, "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
                      "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNA=", 59, "90693936"},
        {HASH_SHA512, "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
                      "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNA=", 1111111109LL, "25091201"},
        {HASH_SHA512, "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
                      "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNA=", 20000000000LL, "47863826"},
    };
    static const char *names[] = {"SHA1", "SHA256", "SHA512"};
    int failures = 0;
    printf("RFC 6238 vectors\n");
    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        Token tok;
        memset(&tok, 0, sizeof tok);
        tok.alg = cases[i].alg;
        tok.digits = 8;
        tok.period = 30.0;
        if (base32_decode(cases[i].b32, tok.key, sizeof tok.key, &tok.keylen) != 0) {
            printf("  %-6s T=%-12lld seed decode FAILED\n", names[cases[i].alg], cases[i].at);
            failures++;
            continue;
        }
        char code[16];
        hotp(&tok, (uint64_t)(cases[i].at / 30), code, sizeof code);
        int ok = !strcmp(code, cases[i].want);
        printf("  %-6s T=%-12lld %s %s\n", names[cases[i].alg], cases[i].at, code,
               ok ? "OK" : "MISMATCH");
        if (!ok) failures++;
    }
    printf("%s\n", failures ? "selftest FAILED" : "selftest passed");
    return failures ? 1 : 0;
}

static int usage(void) {
    printf("usage: oathpass [--node N | --port PORT] [ssh args...]\n"
           "       oathpass check              dry run: target, node, code, no ssh\n"
           "       oathpass otp [--at EPOCH]   print the current code\n"
           "       oathpass port               print the login port that would be used\n"
           "       oathpass target             print user@host\n"
           "       oathpass wrap <command...>  run a command with the askpass exported\n"
           "       oathpass doctor             why a code does not match the phone\n"
           "       oathpass --selftest         replay the RFC 6238 vectors\n"
           "\n"
           "The cluster asks one question -- One-time password (OATH) -- and this\n"
           "answers it from the seed in %s.\n",
           config_path());
    return 0;
}

int main(int argc, char **argv) {
    const char *askpass_role = getenv("OATHPASS_ASKPASS");
    if (askpass_role && !strcmp(askpass_role, "1")) return askpass(argc > 1 ? argv[1] : "");

    int forced_port = 0;
    int forced_node = 0;
    int index = 1;
    while (index < argc) {
        if (!strncmp(argv[index], "--port=", 7)) {
            forced_port = atoi(argv[index] + 7);
            index++;
            continue;
        }
        if (!strcmp(argv[index], "--port") && index + 1 < argc) {
            forced_port = atoi(argv[index + 1]);
            index += 2;
            continue;
        }
        if (!strncmp(argv[index], "--node=", 7)) {
            forced_node = atoi(argv[index] + 7);
            index++;
            continue;
        }
        if (!strcmp(argv[index], "--node") && index + 1 < argc) {
            forced_node = atoi(argv[index + 1]);
            index += 2;
            continue;
        }
        break;
    }
    if (forced_port < 0 || forced_port > 65535) die("--port needs a port number");
    if (forced_node < 0) die("--node needs a node number");
    if (forced_node && forced_port) die("use either --node or --port, not both");

    char **rest = argv + index;
    int restc = argc - index;
    const char *command = restc > 0 ? rest[0] : "";

    if (!strcmp(command, "--help") || !strcmp(command, "-h") || !strcmp(command, "help")) return usage();
    if (!strcmp(command, "--selftest") || !strcmp(command, "selftest")) return cmd_selftest();

    if (!strcmp(command, "otp") || !strcmp(command, "target") || !strcmp(command, "doctor") ||
        !strcmp(command, "wrap") || !strcmp(command, "port") || !strcmp(command, "check") ||
        !strcmp(command, "--dry-run")) {
        Config cfg;
        load_config(&cfg);
        if (!strcmp(command, "otp")) return cmd_otp(&cfg, restc - 1, rest + 1);
        if (!strcmp(command, "target")) return cmd_target(&cfg);
        if (!strcmp(command, "doctor")) return cmd_doctor(&cfg);
        if (!strcmp(command, "port")) return cmd_port(&cfg, forced_node, forced_port);
        if (!strcmp(command, "check") || !strcmp(command, "--dry-run"))
            return cmd_check(&cfg, forced_node, forced_port);
        return cmd_wrap(&cfg, restc - 1, rest + 1);
    }

    Config cfg;
    load_config(&cfg);
    return cmd_login(&cfg, rest, forced_node, forced_port);
}
