/* Compare sha256_fast against OpenSSL for known vectors and random lengths. */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <openssl/sha.h>
#include "sha256_fast.h"

static int fail = 0;

static void check(const char *name, const void *data, size_t len) {
  unsigned char a[32], b[32];
  sha256_fast(data, len, a);
  SHA256(data, len, b);
  if (memcmp(a, b, 32) != 0) {
    fprintf(stderr, "mismatch: %s (len=%zu)\n", name, len);
    fail = 1;
  }
}

int main(void) {
  unsigned char buf[256];
  size_t i;

  sha256_fast_init();

  check("empty", "", 0);
  check("abc", "abc", 3);
  check("password", "password", 8);
  check("55 bytes", "1234567890123456789012345678901234567890123456789012345", 55);
  check("56 bytes", "12345678901234567890123456789012345678901234567890123456", 56);
  check("63 bytes", "123456789012345678901234567890123456789012345678901234567890123", 63);
  check("64 bytes", "1234567890123456789012345678901234567890123456789012345678901234", 64);
  check("65 bytes", "12345678901234567890123456789012345678901234567890123456789012345", 65);

  for (i = 0; i < sizeof(buf); ++i) {
    buf[i] = (unsigned char)(i * 17 + 3);
  }
  for (i = 0; i <= sizeof(buf); ++i) {
    char name[32];
    snprintf(name, sizeof(name), "buf[%zu]", i);
    check(name, buf, i);
  }

  if (fail) {
    fprintf(stderr, "sha256_fast tests failed\n");
    return 1;
  }
  printf("sha256_fast: ok\n");
  return 0;
}
