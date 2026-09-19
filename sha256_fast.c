/* Copyright (c) 2026 Brainflayer contributors
 *
 * SHA-NI round schedule follows Intel's SHA extensions programming
 * reference. Fallback uses OpenSSL when SHA-NI is unavailable.
 */
#include "sha256_fast.h"

#include <stdint.h>
#include <string.h>

#include <openssl/sha.h>

#if defined(__x86_64__) || defined(__i386__)
#include <cpuid.h>
#include <immintrin.h>
#define BF_HAVE_SHA_NI 1
#endif

typedef void (*sha256_transform_fn)(uint32_t state[8], const unsigned char block[64]);

static sha256_transform_fn g_transform;

#if BF_HAVE_SHA_NI
__attribute__((target("sha,ssse3,sse4.1")))
static void sha256_transform_shani(uint32_t state[8], const unsigned char data[64]) {
  __m128i STATE0, STATE1;
  __m128i MSG, TMP;
  __m128i MSG0, MSG1, MSG2, MSG3;
  __m128i ABEF_SAVE, CDGH_SAVE;
  const __m128i MASK = _mm_set_epi64x(0x0c0d0e0f08090a0bULL, 0x0405060700010203ULL);

  TMP = _mm_loadu_si128((const __m128i *)&state[0]);
  STATE1 = _mm_loadu_si128((const __m128i *)&state[4]);

  TMP = _mm_shuffle_epi32(TMP, 0xB1);
  STATE1 = _mm_shuffle_epi32(STATE1, 0x1B);
  STATE0 = _mm_alignr_epi8(TMP, STATE1, 8);
  STATE1 = _mm_blend_epi16(STATE1, TMP, 0xF0);

  ABEF_SAVE = STATE0;
  CDGH_SAVE = STATE1;

  MSG = _mm_loadu_si128((const __m128i *)(data + 0));
  MSG0 = _mm_shuffle_epi8(MSG, MASK);
  MSG = _mm_add_epi32(MSG0, _mm_set_epi64x(0xE9B5DBA5B5C0FBCFULL, 0x71374491428A2F98ULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);

  MSG = _mm_loadu_si128((const __m128i *)(data + 16));
  MSG1 = _mm_shuffle_epi8(MSG, MASK);
  MSG = _mm_add_epi32(MSG1, _mm_set_epi64x(0xAB1C5ED5923F82A4ULL, 0x59F111F13956C25BULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);
  MSG0 = _mm_sha256msg1_epu32(MSG0, MSG1);

  MSG = _mm_loadu_si128((const __m128i *)(data + 32));
  MSG2 = _mm_shuffle_epi8(MSG, MASK);
  MSG = _mm_add_epi32(MSG2, _mm_set_epi64x(0x550C7DC3243185BEULL, 0x12835B01D807AA98ULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);
  MSG1 = _mm_sha256msg1_epu32(MSG1, MSG2);

  MSG = _mm_loadu_si128((const __m128i *)(data + 48));
  MSG3 = _mm_shuffle_epi8(MSG, MASK);
  MSG = _mm_add_epi32(MSG3, _mm_set_epi64x(0xC19BF1749BDC06A7ULL, 0x80DEB1FE72BE5D74ULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  TMP = _mm_alignr_epi8(MSG3, MSG2, 4);
  MSG0 = _mm_add_epi32(MSG0, TMP);
  MSG0 = _mm_sha256msg2_epu32(MSG0, MSG3);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);
  MSG2 = _mm_sha256msg1_epu32(MSG2, MSG3);

  MSG = _mm_add_epi32(MSG0, _mm_set_epi64x(0x240CA1CC0FC19DC6ULL, 0xEFBE4786E49B69C1ULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  TMP = _mm_alignr_epi8(MSG0, MSG3, 4);
  MSG1 = _mm_add_epi32(MSG1, TMP);
  MSG1 = _mm_sha256msg2_epu32(MSG1, MSG0);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);
  MSG3 = _mm_sha256msg1_epu32(MSG3, MSG0);

  MSG = _mm_add_epi32(MSG1, _mm_set_epi64x(0x76F988DA5CB0A9DCULL, 0x4A7484AA2DE92C6FULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  TMP = _mm_alignr_epi8(MSG1, MSG0, 4);
  MSG2 = _mm_add_epi32(MSG2, TMP);
  MSG2 = _mm_sha256msg2_epu32(MSG2, MSG1);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);
  MSG0 = _mm_sha256msg1_epu32(MSG0, MSG1);

  MSG = _mm_add_epi32(MSG2, _mm_set_epi64x(0xBF597FC7B00327C8ULL, 0xA831C66D983E5152ULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  TMP = _mm_alignr_epi8(MSG2, MSG1, 4);
  MSG3 = _mm_add_epi32(MSG3, TMP);
  MSG3 = _mm_sha256msg2_epu32(MSG3, MSG2);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);
  MSG1 = _mm_sha256msg1_epu32(MSG1, MSG2);

  MSG = _mm_add_epi32(MSG3, _mm_set_epi64x(0x1429296706CA6351ULL, 0xD5A79147C6E00BF3ULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  TMP = _mm_alignr_epi8(MSG3, MSG2, 4);
  MSG0 = _mm_add_epi32(MSG0, TMP);
  MSG0 = _mm_sha256msg2_epu32(MSG0, MSG3);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);
  MSG2 = _mm_sha256msg1_epu32(MSG2, MSG3);

  MSG = _mm_add_epi32(MSG0, _mm_set_epi64x(0x53380D134D2C6DFCULL, 0x2E1B213827B70A85ULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  TMP = _mm_alignr_epi8(MSG0, MSG3, 4);
  MSG1 = _mm_add_epi32(MSG1, TMP);
  MSG1 = _mm_sha256msg2_epu32(MSG1, MSG0);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);
  MSG3 = _mm_sha256msg1_epu32(MSG3, MSG0);

  MSG = _mm_add_epi32(MSG1, _mm_set_epi64x(0x92722C8581C2C92EULL, 0x766A0ABB650A7354ULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  TMP = _mm_alignr_epi8(MSG1, MSG0, 4);
  MSG2 = _mm_add_epi32(MSG2, TMP);
  MSG2 = _mm_sha256msg2_epu32(MSG2, MSG1);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);
  MSG0 = _mm_sha256msg1_epu32(MSG0, MSG1);

  MSG = _mm_add_epi32(MSG2, _mm_set_epi64x(0xC76C51A3C24B8B70ULL, 0xA81A664BA2BFE8A1ULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  TMP = _mm_alignr_epi8(MSG2, MSG1, 4);
  MSG3 = _mm_add_epi32(MSG3, TMP);
  MSG3 = _mm_sha256msg2_epu32(MSG3, MSG2);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);
  MSG1 = _mm_sha256msg1_epu32(MSG1, MSG2);

  MSG = _mm_add_epi32(MSG3, _mm_set_epi64x(0x106AA070F40E3585ULL, 0xD6990624D192E819ULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  TMP = _mm_alignr_epi8(MSG3, MSG2, 4);
  MSG0 = _mm_add_epi32(MSG0, TMP);
  MSG0 = _mm_sha256msg2_epu32(MSG0, MSG3);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);
  MSG2 = _mm_sha256msg1_epu32(MSG2, MSG3);

  MSG = _mm_add_epi32(MSG0, _mm_set_epi64x(0x34B0BCB52748774CULL, 0x1E376C0819A4C116ULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  TMP = _mm_alignr_epi8(MSG0, MSG3, 4);
  MSG1 = _mm_add_epi32(MSG1, TMP);
  MSG1 = _mm_sha256msg2_epu32(MSG1, MSG0);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);
  MSG3 = _mm_sha256msg1_epu32(MSG3, MSG0);

  MSG = _mm_add_epi32(MSG1, _mm_set_epi64x(0x682E6FF35B9CCA4FULL, 0x4ED8AA4A391C0CB3ULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  TMP = _mm_alignr_epi8(MSG1, MSG0, 4);
  MSG2 = _mm_add_epi32(MSG2, TMP);
  MSG2 = _mm_sha256msg2_epu32(MSG2, MSG1);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);

  MSG = _mm_add_epi32(MSG2, _mm_set_epi64x(0x8CC7020884C87814ULL, 0x78A5636F748F82EEULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  TMP = _mm_alignr_epi8(MSG2, MSG1, 4);
  MSG3 = _mm_add_epi32(MSG3, TMP);
  MSG3 = _mm_sha256msg2_epu32(MSG3, MSG2);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);

  MSG = _mm_add_epi32(MSG3, _mm_set_epi64x(0xC67178F2BEF9A3F7ULL, 0xA4506CEB90BEFFFAULL));
  STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
  MSG = _mm_shuffle_epi32(MSG, 0x0E);
  STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, MSG);

  STATE0 = _mm_add_epi32(STATE0, ABEF_SAVE);
  STATE1 = _mm_add_epi32(STATE1, CDGH_SAVE);

  TMP = _mm_shuffle_epi32(STATE0, 0x1B);
  STATE1 = _mm_shuffle_epi32(STATE1, 0xB1);
  STATE0 = _mm_blend_epi16(TMP, STATE1, 0xF0);
  STATE1 = _mm_alignr_epi8(STATE1, TMP, 8);

  _mm_storeu_si128((__m128i *)&state[0], STATE0);
  _mm_storeu_si128((__m128i *)&state[4], STATE1);
}

static int sha_ni_available(void) {
  unsigned int eax = 0, ebx = 0, ecx = 0, edx = 0;
  if (!__get_cpuid_max(0, NULL)) {
    return 0;
  }
  if (!__get_cpuid_count(7, 0, &eax, &ebx, &ecx, &edx)) {
    return 0;
  }
  /* CPUID.7:0.EBX bit 29 = SHA */
  return (ebx >> 29) & 1;
}
#endif

static int g_use_shani = 0;

void sha256_fast_init(void) {
#if BF_HAVE_SHA_NI
  g_use_shani = sha_ni_available();
  if (g_use_shani) {
    g_transform = sha256_transform_shani;
  }
#else
  g_use_shani = 0;
  g_transform = NULL;
#endif
}

static void sha256_store_be(unsigned char out[32], const uint32_t state[8]) {
  int i;
  for (i = 0; i < 8; ++i) {
    out[i * 4 + 0] = (unsigned char)(state[i] >> 24);
    out[i * 4 + 1] = (unsigned char)(state[i] >> 16);
    out[i * 4 + 2] = (unsigned char)(state[i] >> 8);
    out[i * 4 + 3] = (unsigned char)(state[i]);
  }
}

void sha256_fast(const void *data, size_t len, unsigned char out[32]) {
  const unsigned char *p = data;

#if BF_HAVE_SHA_NI
  if (g_use_shani) {
    uint32_t state[8] = {
      0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
      0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u
    };
    unsigned char block[64];
    size_t n = len;
    uint64_t bits = (uint64_t)len << 3;

    while (n >= 64) {
      g_transform(state, p);
      p += 64;
      n -= 64;
    }
    memcpy(block, p, n);
    block[n] = 0x80;
    if (n < 56) {
      memset(block + n + 1, 0, 55 - n);
    } else {
      memset(block + n + 1, 0, 63 - n);
      g_transform(state, block);
      memset(block, 0, 56);
    }
    block[56] = (unsigned char)(bits >> 56);
    block[57] = (unsigned char)(bits >> 48);
    block[58] = (unsigned char)(bits >> 40);
    block[59] = (unsigned char)(bits >> 32);
    block[60] = (unsigned char)(bits >> 24);
    block[61] = (unsigned char)(bits >> 16);
    block[62] = (unsigned char)(bits >> 8);
    block[63] = (unsigned char)bits;
    g_transform(state, block);
    sha256_store_be(out, state);
    return;
  }
#endif

  SHA256(p, len, out);
}
