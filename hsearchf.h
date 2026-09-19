/*  Copyright (c) 2015 Ryan Castellucci, All Rights Reserved */
#ifndef __BRAINFLAYER_HSEARCHF_H_
#define __BRAINFLAYER_HSEARCHF_H_

#include "hash160.h"

typedef struct hsearchf_ctx_s {
  const unsigned char *data;
  int64_t entries;
  void *mmap_mem;
  size_t mmap_sz;
  int fd;
} hsearchf_ctx_t;

int hsearchf_open(hsearchf_ctx_t *ctx, const char *path);
void hsearchf_close(hsearchf_ctx_t *ctx);
int hsearchf(const hsearchf_ctx_t *ctx, hash160_t *hash);

/* vim: set ts=2 sw=2 et ai si: */
#endif /* __BRAINFLAYER_HSEARCHF_H_ */
