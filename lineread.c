/* Copyright (c) 2026 Brainflayer contributors */
#include "lineread.h"

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#ifndef LINEREAD_BUFSZ
#define LINEREAD_BUFSZ (1u << 20)
#endif

static void lineread_zero(lineread_t *lr) {
  memset(lr, 0, sizeof(*lr));
  lr->fd = -1;
}

int lineread_open_path(lineread_t *lr, const char *path) {
  struct stat st;
  int fd;

  lineread_zero(lr);

  fd = open(path, O_RDONLY);
  if (fd < 0) {
    return -errno;
  }
  if (fstat(fd, &st) != 0) {
    int e = errno;
    close(fd);
    return -e;
  }
  if (!S_ISREG(st.st_mode)) {
    close(fd);
    return -EINVAL;
  }

  lr->fd = fd;
  lr->map_sz = (size_t)st.st_size;
  if (lr->map_sz == 0) {
    lr->map = NULL;
    return 0;
  }

  lr->map = mmap(NULL, lr->map_sz, PROT_READ, MAP_SHARED, fd, 0);
  if (lr->map == MAP_FAILED) {
    int e = errno;
    close(fd);
    lineread_zero(lr);
    return -e;
  }

  lr->map_off = 0;
  lr->map_end = lr->map_sz;

  posix_madvise((void *)lr->map, lr->map_sz, POSIX_MADV_SEQUENTIAL);
#ifdef MADV_SEQUENTIAL
  madvise((void *)lr->map, lr->map_sz, MADV_SEQUENTIAL);
#endif
#ifdef MADV_HUGEPAGE
  if (lr->map_sz > (1u << 26)) {
    madvise((void *)lr->map, lr->map_sz, MADV_HUGEPAGE);
  }
#endif
  return 0;
}

void lineread_open_fp(lineread_t *lr, FILE *fp) {
  lineread_zero(lr);
  lr->fp = fp;
  lr->rcap = LINEREAD_BUFSZ;
  lr->rbuf = malloc(lr->rcap);
  if (lr->rbuf == NULL) {
    lr->rcap = 0;
    lr->eof = 1;
  }
}

static size_t lineread_limit(const lineread_t *lr) {
  if (lr->map_end == 0 || lr->map_end > lr->map_sz) {
    return lr->map_sz;
  }
  return lr->map_end;
}

static size_t lineread_align_nl(const lineread_t *lr, size_t off, size_t end) {
  const char *nl;
  if (off >= end) {
    return end;
  }
  nl = memchr(lr->map + off, '\n', end - off);
  return nl ? (size_t)(nl - lr->map) + 1 : end;
}

void lineread_partition(lineread_t *lr, int worker, int nworkers, uint64_t skip_lines) {
  size_t start;
  size_t end;
  size_t span;
  size_t a;
  size_t b;

  if (lr->map == NULL || nworkers < 1) {
    return;
  }
  if (worker < 0 || worker >= nworkers) {
    lr->map_off = lr->map_sz;
    lr->map_end = lr->map_sz;
    return;
  }

  start = 0;
  end = lr->map_sz;
  while (skip_lines && start < end) {
    start = lineread_align_nl(lr, start, end);
    --skip_lines;
  }

  span = end - start;
  a = start + (size_t)(((uint64_t)span * (uint64_t)worker) / (uint64_t)nworkers);
  if (worker + 1 == nworkers) {
    b = end;
  } else {
    b = start + (size_t)(((uint64_t)span * (uint64_t)(worker + 1)) / (uint64_t)nworkers);
  }
  if (worker > 0) {
    a = lineread_align_nl(lr, a, end);
  }
  if (worker + 1 < nworkers) {
    b = lineread_align_nl(lr, b, end);
  }
  if (a > b) {
    a = b;
  }

  lr->map_off = a;
  lr->map_end = b;

  if (b > a) {
    posix_madvise((void *)(lr->map + a), b - a, POSIX_MADV_SEQUENTIAL);
#ifdef MADV_SEQUENTIAL
    madvise((void *)(lr->map + a), b - a, MADV_SEQUENTIAL);
#endif
  }
}

int lineread_next(lineread_t *lr, const char **line, size_t *len) {
  if (lr->map != NULL || (lr->fd >= 0 && lr->map_sz == 0 && lr->fp == NULL)) {
    const char *start;
    const char *nl;
    size_t end = lineread_limit(lr);

    if (lr->map_off >= end) {
      return 0;
    }
    start = lr->map + lr->map_off;
    nl = memchr(start, '\n', end - lr->map_off);
    if (nl != NULL) {
      *len = (size_t)(nl - start);
      lr->map_off = (size_t)(nl - lr->map) + 1;
    } else {
      *len = end - lr->map_off;
      lr->map_off = end;
    }
    if (*len && start[*len - 1] == '\r') {
      --*len;
    }
    *line = start;
    return 1;
  }

  if (lr->fp == NULL || lr->rbuf == NULL) {
    return 0;
  }

  for (;;) {
    char *start = lr->rbuf + lr->roff;
    char *nl = memchr(start, '\n', lr->rlen - lr->roff);

    if (nl != NULL) {
      *len = (size_t)(nl - start);
      lr->roff = (size_t)(nl - lr->rbuf) + 1;
      if (*len && start[*len - 1] == '\r') {
        --*len;
      }
      *line = start;
      return 1;
    }

    if (lr->eof) {
      if (lr->roff < lr->rlen) {
        *len = lr->rlen - lr->roff;
        *line = start;
        lr->roff = lr->rlen;
        if (*len && start[*len - 1] == '\r') {
          --*len;
        }
        return 1;
      }
      return 0;
    }

    if (lr->roff > 0) {
      size_t remain = lr->rlen - lr->roff;
      if (remain) {
        memmove(lr->rbuf, start, remain);
      }
      lr->rlen = remain;
      lr->roff = 0;
    }

    if (lr->rlen == lr->rcap) {
      size_t ncap = lr->rcap * 2;
      char *nbuf = realloc(lr->rbuf, ncap);
      if (nbuf == NULL) {
        lr->eof = 1;
        continue;
      }
      lr->rbuf = nbuf;
      lr->rcap = ncap;
    }

    {
      size_t got = fread(lr->rbuf + lr->rlen, 1, lr->rcap - lr->rlen, lr->fp);
      lr->rlen += got;
      if (got == 0) {
        lr->eof = 1;
      }
    }
  }
}

void lineread_close(lineread_t *lr) {
  if (lr->map != NULL && lr->map != MAP_FAILED) {
    munmap((void *)lr->map, lr->map_sz);
  }
  if (lr->fd >= 0) {
    close(lr->fd);
  }
  free(lr->rbuf);
  lineread_zero(lr);
}
