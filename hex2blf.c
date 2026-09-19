/*  Copyright (c) 2015 Ryan Castellucci, All Rights Reserved */
#include <unistd.h>
#include <assert.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#include <fcntl.h>

#include <sys/stat.h>
#include <sys/types.h>

#include <arpa/inet.h> /*  for ntohl/htonl */

#include <math.h> /* pow/exp */

#include "hex.h"
#include "bloom.h"
#include "hash160.h"
#include "lineread.h"

const double k_hashes = 20;
const double m_bits   = 4294967296;

int main(int argc, char **argv) {
  hash160_t hash;
  int i;
  double pct;
  struct stat sb;
  unsigned char *bloom, *hashfile, *bloomfile;
  FILE *b;
  size_t line_ct = 0;
  lineread_t lr;
  const char *line;
  size_t linelen;
  double err_rate;
  int lrret;

  if (argc != 3) {
    fprintf(stderr, "[!] Usage: %s hashfile.hex bloomfile.blf\n", argv[0]);
    exit(1);
  }

  hashfile = argv[1];
  bloomfile = argv[2];

  lrret = lineread_open_path(&lr, (const char *)hashfile);
  if (lrret != 0) {
    fprintf(stderr, "[!] Failed to open hash160 file '%s': %s\n",
            hashfile, strerror(-lrret));
    exit(1);
  }

  if ((bloom = malloc(BLOOM_SIZE)) == NULL) {
    fprintf(stderr, "[!] malloc failed (bloom filter)\n");
    exit(1);
  }

  if (stat(bloomfile, &sb) == 0) {
    if (!S_ISREG(sb.st_mode) || sb.st_size != BLOOM_SIZE) {
      fprintf(stderr, "[!] Bloom filter file '%s' is not the correct size (%ju != %d)\n", bloomfile, sb.st_size, BLOOM_SIZE);
      exit(1);
    }
    if ((b = fopen(bloomfile, "r+")) == NULL) {
      fprintf(stderr, "[!] Failed to open bloom filter file '%s' for read/write\n", bloomfile);
      exit(1);
    }
    fprintf(stderr, "[*] Reading existing bloom filter from '%s'...\n", bloomfile);
    if ((fread(bloom, BLOOM_SIZE, 1, b)) != 1 || (fseek(b, 0, SEEK_SET)) != 0) {
      fprintf(stderr, "[!] Failed to read existing boom filter from '%s'\n", bloomfile);
      exit(1);
    }
  } else {
    /*  Assume the file didn't exist - yes there is a race condition */
    if ((b = fopen(bloomfile, "w+")) == NULL) {
      fprintf(stderr, "[!] Failed to create bloom filter file '%s'\n", bloomfile);
      exit(1);
    }
    fprintf(stderr, "[*] Initializing bloom filter...\n");
    memset(bloom, 0, BLOOM_SIZE);
  }

  i = 0;
  fprintf(stderr, "[*] Loading hash160s from '%s' \033[s  0.0%%", hashfile);
  while (lineread_next(&lr, &line, &linelen)) {
    if (linelen < 40) {
      continue;
    }
    ++line_ct;
    unhex((unsigned char *)line, 40, hash.uc, sizeof(hash.uc));
    bloom_set_hash160(bloom, hash.ul);

    if ((++i & 0x3ffff) == 0) {
      pct = lr.map_sz ? (100.0 * lr.map_off / lr.map_sz) : 100.0;
      fprintf(stderr, "\033[u%5.1f%%", pct);
      fflush(stderr);
    }
  }
  fprintf(stderr, "\033[u 100.0%%\n");
  lineread_close(&lr);

  err_rate = pow(1 - exp(-k_hashes * line_ct / m_bits), k_hashes);
  fprintf(stderr, "[*] Loaded %zu hashes, false positive rate: ~%.3e (1 in ~%.3e)\n", line_ct, err_rate, 1/err_rate);

  fprintf(stderr, "[*] Writing bloom filter to '%s'...\n", bloomfile);
  if ((fwrite(bloom, BLOOM_SIZE, 1, b)) != 1) {
    fprintf(stderr, "[!] Failed to write bloom filter file '%s'\n", bloomfile);
    exit(1);
  }

  fprintf(stderr, "[+] Success!\n");
  return 0;
}

/*  vim: set ts=2 sw=2 et ai si: */
