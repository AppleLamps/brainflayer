/* Sequential line reader: mmap for regular files, buffered fread for streams. */
#ifndef __BRAINFLAYER_LINEREAD_H_
#define __BRAINFLAYER_LINEREAD_H_

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

typedef struct lineread_s {
  const char *map;
  size_t map_sz;
  size_t map_off;
  size_t map_end;
  int fd;

  FILE *fp;
  char *rbuf;
  size_t rcap;
  size_t rlen;
  size_t roff;
  int eof;
} lineread_t;

int lineread_open_path(lineread_t *lr, const char *path);
void lineread_open_fp(lineread_t *lr, FILE *fp);
/* Split an mmap'd file across workers after skipping skip_lines.
   Each worker reads a disjoint newline-aligned byte span. */
void lineread_partition(lineread_t *lr, int worker, int nworkers, uint64_t skip_lines);
int lineread_next(lineread_t *lr, const char **line, size_t *len);
void lineread_close(lineread_t *lr);

#endif /* __BRAINFLAYER_LINEREAD_H_ */
