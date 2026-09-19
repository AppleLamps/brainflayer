/* Copyright (c) 2015 Ryan Castellucci, All Rights Reserved */
#include <unistd.h>
#include <string.h>
#include <fcntl.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <errno.h>

#include <arpa/inet.h>

#include <sys/types.h>
#include <sys/stat.h>
#include <sys/mman.h>

#include "hex.h"
#include "hash160.h"
#include "hsearchf.h"

#define HSEARCHF_DEBUG 0

#define HASHLEN RIPEMD160_DIGEST_LENGTH

#define RESULT(R) do { \
  res = R; \
  goto hsearchf_result; \
} while (0)

#define DO_MEMCMP(H) memcmp((H).uc, hash->uc, HASHLEN)

static int hsearchf_mmap_entries(const hsearchf_ctx_t *ctx, int64_t idx, hash160_t *out) {
  if (idx < 0 || idx >= ctx->entries) {
    return -1;
  }
  memcpy(out->uc, ctx->data + (size_t)idx * HASHLEN, HASHLEN);
  return 0;
}

int hsearchf_open(hsearchf_ctx_t *ctx, const char *path) {
  struct stat sb;
  int fd;

  memset(ctx, 0, sizeof(*ctx));
  ctx->fd = -1;

  if ((fd = open(path, O_RDONLY)) < 0) {
    return -errno;
  }

  if (fstat(fd, &sb) != 0) {
    close(fd);
    return -errno;
  }

  if (!S_ISREG(sb.st_mode) || sb.st_size % HASHLEN != 0) {
    close(fd);
    return -EINVAL;
  }

  ctx->mmap_sz = (size_t)sb.st_size;
  ctx->entries = (int64_t)(sb.st_size / HASHLEN);
  ctx->mmap_mem = mmap(NULL, ctx->mmap_sz, PROT_READ, MAP_SHARED, fd, 0);
  if (ctx->mmap_mem == MAP_FAILED) {
    close(fd);
    return -errno;
  }

  posix_madvise(ctx->mmap_mem, ctx->mmap_sz, POSIX_MADV_RANDOM);
#ifdef MADV_HUGEPAGE
  if (ctx->mmap_sz > (1u << 26)) {
    madvise(ctx->mmap_mem, ctx->mmap_sz, MADV_HUGEPAGE);
  }
#endif

  ctx->data = (const unsigned char *)ctx->mmap_mem;
  ctx->fd = fd;
  return 0;
}

void hsearchf_close(hsearchf_ctx_t *ctx) {
  if (ctx->mmap_mem != NULL && ctx->mmap_mem != MAP_FAILED) {
    munmap(ctx->mmap_mem, ctx->mmap_sz);
  }
  if (ctx->fd >= 0) {
    close(ctx->fd);
  }
  memset(ctx, 0, sizeof(*ctx));
  ctx->fd = -1;
}

int hsearchf(const hsearchf_ctx_t *ctx, hash160_t *hash) {
  int res = 0, i = 0;
  hash160_t low_h, mid_h, high_h;
  int64_t low_e, mid_e, high_e;
  int64_t vlow, vhigh, vtarget;

#if HSEARCHF_DEBUG > 0
  unsigned char hexed[64];
#endif

  if (ctx == NULL || ctx->data == NULL || ctx->entries == 0) {
    return 0;
  }

  low_e = 0;
  high_e = ctx->entries - 1;

  vtarget = ntohl(hash->ul[0]);
  memset(low_h.uc, 0x00, HASHLEN);
  memset(high_h.uc, 0xff, HASHLEN);

  while (low_e != high_e &&
         memcmp(hash->uc, low_h.uc, HASHLEN) > 0 &&
         memcmp(hash->uc, high_h.uc, HASHLEN) < 0) {
    vlow = ntohl(low_h.ul[0]);
    vhigh = ntohl(high_h.ul[0]);
    if (vhigh == vlow) {
      mid_e = (low_e + high_e) / 2;
    } else {
      mid_e = low_e + (vtarget - vlow) * (high_e - low_e) / (vhigh - vlow);
    }
    if (mid_e < low_e) {
      mid_e = low_e;
    }
    if (mid_e > high_e) {
      mid_e = high_e;
    }

    if (hsearchf_mmap_entries(ctx, mid_e, &mid_h) != 0) {
      return -1;
    }
    ++i;
    if (DO_MEMCMP(mid_h) == 0) {
      RESULT(1);
    } else if (DO_MEMCMP(mid_h) < 0) {
      low_e = mid_e + 1;
      if (hsearchf_mmap_entries(ctx, low_e, &low_h) != 0) {
        return -1;
      }
      if (DO_MEMCMP(low_h) == 0) {
        RESULT(1);
      }
    } else {
      high_e = mid_e - 1;
      if (hsearchf_mmap_entries(ctx, high_e, &high_h) != 0) {
        return -1;
      }
      if (DO_MEMCMP(high_h) == 0) {
        RESULT(1);
      }
    }
  }

hsearchf_result:
#if HSEARCHF_DEBUG > 0
  fprintf(stderr, "target: %s reads: %3d result: %d\n",
          hex(hash->uc, HASHLEN, hexed, sizeof(hexed)), i, res);
#endif
  return res;
}

/* vim: set ts=2 sw=2 et ai si: */
