/* Copyright (c) 2015 Ryan Castellucci, All Rights Reserved */
#include <unistd.h>
#include <string.h>
#include <fcntl.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <errno.h>

#include <sys/types.h>
#include <sys/stat.h>
#include <sys/mman.h>

#include "hex.h"
#include "hash160.h"
#include "hsearchf.h"

#define HASHLEN RIPEMD160_DIGEST_LENGTH

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
  int64_t lo, hi;
  const unsigned char *key;

  if (ctx == NULL || ctx->data == NULL || ctx->entries == 0) {
    return 0;
  }

  key = hash->uc;
  lo = 0;
  hi = ctx->entries - 1;
  while (lo <= hi) {
    int64_t mid = lo + ((hi - lo) >> 1);
    int cmp = memcmp(ctx->data + (size_t)mid * HASHLEN, key, HASHLEN);
    if (cmp == 0) {
      return 1;
    }
    if (cmp < 0) {
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return 0;
}

/* vim: set ts=2 sw=2 et ai si: */
