/* Copyright (c) 2015 Ryan Castellucci, All Rights Reserved */
#include <stdint.h>
#include <stddef.h>

#include "hex.h"

unsigned char *
hex(unsigned char *buf, size_t buf_sz,
    unsigned char *hexed, size_t hexed_sz) {
  size_t n;
  if (hexed_sz == 0) {
    return hexed;
  }
  n = (hexed_sz - 1) / 2;
  if (n > buf_sz) {
    n = buf_sz;
  }
  hex_encode(buf, n, (char *)hexed);
  return hexed;
}

/*  vim: set ts=2 sw=2 et ai si: */
