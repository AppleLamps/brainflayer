/* Sequential line reader: mmap for regular files, buffered fread for streams. */
#ifndef __BRAINFLAYER_LINEREAD_H_
#define __BRAINFLAYER_LINEREAD_H_

#include <stddef.h>
#include <stdio.h>

typedef struct lineread_s {
  const char *map;
  size_t map_sz;
  size_t map_off;
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
int lineread_next(lineread_t *lr, const char **line, size_t *len);
void lineread_close(lineread_t *lr);

#endif /* __BRAINFLAYER_LINEREAD_H_ */
