/* Copyright (c) 2015 Ryan Castellucci, All Rights Reserved */
#include <time.h>
#include <unistd.h>
#include <assert.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <signal.h>
#include <stdio.h>
#include <fcntl.h>
#include <errno.h>

#include <arpa/inet.h> /* for ntohl/htonl */

#include <sys/time.h>
#include <sys/wait.h>
#include <sys/types.h>

#include "hex.h"
#include "bloom.h"
#include "mmapf.h"
#include "hash160.h"
#include "hsearchf.h"

int main(int argc, char **argv) {
  int ret;
  hash160_t hash;
  char *line = NULL;
  size_t line_sz = 0;
  unsigned char *bloom, *bloomfile, *hashfile;
  FILE *ifile = stdin, *ofile = stdout;
  hsearchf_ctx_t hctx;
  memset(&hctx, 0, sizeof(hctx));
  hctx.fd = -1;
  mmapf_ctx bloom_mmapf;

  if (argc < 2 || argc > 3) {
    fprintf(stderr, "Usage: %s BLOOM_FILTER_FILE HASH_FILE\n", argv[0]);
    return 1;
  }

  bloomfile = argv[1];

  if ((ret = mmapf(&bloom_mmapf, bloomfile, BLOOM_SIZE, MMAPF_RNDRD)) != MMAPF_OKAY) {
    fprintf(stderr, "failed to open bloom filter '%s': %s\n", bloomfile, mmapf_strerror(ret));
    return 1;
  } else if (bloom_mmapf.mem == NULL) {
    fprintf(stderr, "got NULL pointer trying to set up bloom filter\n");
    return 1;
  }

  bloom = bloom_mmapf.mem;

  if (argc == 3) {
    int hsret;
    hashfile = argv[2];
    hsret = hsearchf_open(&hctx, hashfile);
    if (hsret != 0) {
      fprintf(stderr, "failed to open hash file '%s': %s\n", hashfile, strerror(hsret < 0 ? -hsret : hsret));
      return 1;
    }
  }

  while (getline(&line, &line_sz, ifile) > 0) {
    unhex((unsigned char *)line, 40, hash.uc, sizeof(hash.uc));

    if (!bloom_chk_hash160(bloom, hash.ul)) {
      continue;
    }

    if (hctx.data && !hsearchf(&hctx, &hash)) {
      //fprintf(ofile, "%s (false positive)\n", hex(hash.uc, sizeof(hash.uc), buf, sizeof(buf)));
      continue;
    }
    //fprintf(ofile, "%s\n", hex(hash.uc, sizeof(hash.uc), buf, sizeof(buf)));
    fprintf(ofile, "%s", line);
  }

  hsearchf_close(&hctx);
  return 0;
}

/*  vim: set ts=2 sw=2 et ai si: */
