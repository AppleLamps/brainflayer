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
#include <inttypes.h>

#include <openssl/sha.h>

#include <openssl/sha.h>

#include <pthread.h>

#include <sys/time.h>
#include <sys/wait.h>
#include <sys/types.h>
#include <sys/sysinfo.h>

#include "ripemd160_256.h"
#include "sha256_fast.h"
#include "lineread.h"

#include "ec_pubkey_fast.h"

#include "hex.h"
#include "bloom.h"
#include "mmapf.h"
#include "hash160.h"
#include "hsearchf.h"

#include "algo/brainv2.h"
#include "algo/warpwallet.h"
#include "algo/brainwalletio.h"
#include "algo/sha3.h"

// raise this if you really want, but quickly diminishing returns
#define BATCH_MAX 4096

static int brainflayer_is_init = 0;

typedef struct pubhashfn_s {
   void (*fn)(hash160_t *, const unsigned char *);
   char id;
} pubhashfn_t;

static unsigned char *mem;

static mmapf_ctx bloom_mmapf;
static unsigned char *bloom = NULL;

static unsigned char *unhexed = NULL;
static size_t unhexed_sz = 4096;

#define bail(code, ...) \
do { \
  fprintf(stderr, __VA_ARGS__); \
  exit(code); \
} while (0)

#define chkmalloc(S) _chkmalloc(S, __FILE__, __LINE__)
static void * _chkmalloc(size_t size, const char *file, unsigned int line) {
  void *ptr = malloc(size);
  if (ptr == NULL) {
    bail(1, "malloc(%zu) failed at %s:%u: %s\n", size, file, line, strerror(errno));
  }
  return ptr;
}

#define chkrealloc(P, S) _chkrealloc(P, S, __FILE__, __LINE__)
__attribute__((unused))
static void * _chkrealloc(void *ptr, size_t size, const char *file, unsigned int line) {
  void *ptr2 = realloc(ptr, size);
  if (ptr2 == NULL) {
    bail(1, "realloc(%p, %zu) failed at %s:%u: %s\n", ptr, size, file, line, strerror(errno));
  }
  return ptr2;
}

uint64_t getns() {
  uint64_t ns;
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  ns  = ts.tv_nsec;
  ns += ts.tv_sec * 1000000000ULL;
  return ns;
}

static inline void brainflayer_init_globals() {
  /* only initialize stuff once */
  if (!brainflayer_is_init) {
    /* initialize buffers */
    mem = chkmalloc(4096);
    unhexed = chkmalloc(unhexed_sz);
    sha256_fast_init();

    /* set the flag */
    brainflayer_is_init = 1;
  }
}

// function pointers
static int (*input2priv)(unsigned char *, unsigned char *, size_t);

/* bitcoin uncompressed address */
static void uhash160(hash160_t *h, const unsigned char *upub) {
  unsigned char hash[SHA256_DIGEST_LENGTH];
  sha256_fast(upub, 65, hash);
  ripemd160_256(hash, h->uc);
}

/* bitcoin compressed address */
static void chash160(hash160_t *h, const unsigned char *upub) {
  unsigned char cpub[33];
  unsigned char hash[SHA256_DIGEST_LENGTH];

  /* quick and dirty public key compression */
  cpub[0] = 0x02 | (upub[64] & 0x01);
  memcpy(cpub + 1, upub + 1, 32);
  sha256_fast(cpub, 33, hash);
  ripemd160_256(hash, h->uc);
}

/* ethereum address */
static void ehash160(hash160_t *h, const unsigned char *upub) {
  SHA3_256_CTX ctx;
  unsigned char hash[SHA256_DIGEST_LENGTH];

  /* compute hash160 for uncompressed public key */
  /* keccak_256_last160(pub) */
  KECCAK_256_Init(&ctx);
  KECCAK_256_Update(&ctx, upub+1, 64);
  KECCAK_256_Final(hash, &ctx);
  memcpy(h->uc, hash+12, 20);
}

/* msb of x coordinate of public key */
static void xhash160(hash160_t *h, const unsigned char *upub) {
  memcpy(h->uc, upub+1, 20);
}



static int pass2priv(unsigned char *priv, unsigned char *pass, size_t pass_sz) {
  sha256_fast(pass, pass_sz, priv);
  return 0;
}

static int keccak2priv(unsigned char *priv, unsigned char *pass, size_t pass_sz) {
  SHA3_256_CTX ctx;

  KECCAK_256_Init(&ctx);
  KECCAK_256_Update(&ctx, pass, pass_sz);
  KECCAK_256_Final(priv, &ctx);

  return 0;
}

/* ether.camp "2031 passes of SHA-3 (Keccak)" */
static int camp2priv(unsigned char *priv, unsigned char *pass, size_t pass_sz) {
  SHA3_256_CTX ctx;
  int i;

  KECCAK_256_Init(&ctx);
  KECCAK_256_Update(&ctx, pass, pass_sz);
  KECCAK_256_Final(priv, &ctx);

  for (i = 1; i < 2031; ++i) {
    KECCAK_256_Init(&ctx);
    KECCAK_256_Update(&ctx, priv, 32);
    KECCAK_256_Final(priv, &ctx);
  }

  return 0;
}

static int sha32priv(unsigned char *priv, unsigned char *pass, size_t pass_sz) {
  SHA3_256_CTX ctx;

  SHA3_256_Init(&ctx);
  SHA3_256_Update(&ctx, pass, pass_sz);
  SHA3_256_Final(priv, &ctx);

  return 0;
}

/*
static int dicap2hash160(unsigned char *pass, size_t pass_sz) {
  SHA3_256_CTX ctx;

  int i, ret;

  KECCAK_256_Init(&ctx);
  KECCAK_256_Update(&ctx, pass, pass_sz);
  KECCAK_256_Final(priv256, &ctx);
  for (i = 0; i < 16384; ++i) {
    KECCAK_256_Init(&ctx);
    KECCAK_256_Update(&ctx, priv256, 32);
    KECCAK_256_Final(priv256, &ctx);
  }

  for (;;) {
    ret = priv2hash160(priv256);
    if (hash160_uncmp.uc[0] == 0) { break; }
    KECCAK_256_Init(&ctx);
    KECCAK_256_Update(&ctx, priv256, 32);
    KECCAK_256_Final(priv256, &ctx);
  }
  return ret;
}
*/

static int rawpriv2priv(unsigned char *priv, unsigned char *rawpriv, size_t rawpriv_sz) {
  memcpy(priv, rawpriv, rawpriv_sz);
  return 0;
}

static unsigned char *kdfsalt;
static size_t kdfsalt_sz;

static int warppass2priv(unsigned char *priv, unsigned char *pass, size_t pass_sz) {
  int ret;
  if ((ret = warpwallet(pass, pass_sz, kdfsalt, kdfsalt_sz, priv)) != 0) return ret;
  pass[pass_sz] = 0;
  return 0;
}

static int bwiopass2priv(unsigned char *priv, unsigned char *pass, size_t pass_sz) {
  int ret;
  if ((ret = brainwalletio(pass, pass_sz, kdfsalt, kdfsalt_sz, priv)) != 0) return ret;
  pass[pass_sz] = 0;
  return 0;
}

static int brainv2pass2priv(unsigned char *priv, unsigned char *pass, size_t pass_sz) {
  unsigned char hexout[33];
  int ret;
  if ((ret = brainv2(pass, pass_sz, kdfsalt, kdfsalt_sz, hexout)) != 0) return ret;
  pass[pass_sz] = 0;
  return pass2priv(priv, hexout, sizeof(hexout)-1);
}

static unsigned char *kdfpass;
static size_t kdfpass_sz;

static int warpsalt2priv(unsigned char *priv, unsigned char *salt, size_t salt_sz) {
  int ret;
  if ((ret = warpwallet(kdfpass, kdfpass_sz, salt, salt_sz, priv)) != 0) return ret;
  salt[salt_sz] = 0;
  return 0;
}

static int bwiosalt2priv(unsigned char *priv, unsigned char *salt, size_t salt_sz) {
  int ret;
  if ((ret = brainwalletio(kdfpass, kdfpass_sz, salt, salt_sz, priv)) != 0) return ret;
  salt[salt_sz] = 0;
  return 0;
}

static int brainv2salt2priv(unsigned char *priv, unsigned char *salt, size_t salt_sz) {
  unsigned char hexout[33];
  int ret;
  if ((ret = brainv2(kdfpass, kdfpass_sz, salt, salt_sz, hexout)) != 0) return ret;
  salt[salt_sz] = 0;
  return pass2priv(priv, hexout, sizeof(hexout)-1);
}

static unsigned char rushchk[5];
static int rush2priv(unsigned char *priv, unsigned char *pass, size_t pass_sz) {
  unsigned char hash[SHA256_DIGEST_LENGTH];
  unsigned char userpasshash[SHA256_DIGEST_LENGTH*2+1];
  unsigned char stack[512];
  unsigned char *combined = stack;
  size_t combined_sz = kdfsalt_sz + 64;

  sha256_fast(pass, pass_sz, hash);
  hex_encode(hash, sizeof(hash), (char *)userpasshash);

  if (combined_sz > sizeof(stack)) {
    combined = chkmalloc(combined_sz);
  }
  memcpy(combined, kdfsalt, kdfsalt_sz);
  memcpy(combined + kdfsalt_sz, userpasshash, 64);
  sha256_fast(combined, combined_sz, priv);
  if (combined != stack) {
    free(combined);
  }

  if (memcmp(priv, rushchk, sizeof(rushchk)) != 0) { return -1; }

  return 0;
}

inline static int priv_incr(unsigned char *upub, unsigned char *priv) {
  int sz;

  secp256k1_ec_pubkey_incr(upub, &sz, priv);

  return 0;
}

inline static void priv2pub(unsigned char *upub, const unsigned char *priv) {
  int sz;

  secp256k1_ec_pubkey_create_precomp(upub, &sz, priv);
}


typedef struct priv_batch_job_s {
  int start;
  int end;
  int *batch_line_read;
  char **batch_line;
  unsigned char (*batch_priv)[32];
  int xopt;
  unsigned char *unhexed;
  size_t unhexed_sz;
  int (*input2priv_fn)(unsigned char *, unsigned char *, size_t);
} priv_batch_job_t;

static int derive_batch_priv(int idx, priv_batch_job_t *proto) {
  if (proto->xopt) {
    if (proto->batch_line_read[idx] / 2 > (int)proto->unhexed_sz) {
      return -1;
    }
    unhex((unsigned char *)proto->batch_line[idx],
          (size_t)proto->batch_line_read[idx],
          proto->unhexed,
          proto->unhexed_sz);
    if (proto->input2priv_fn(proto->batch_priv[idx],
                             proto->unhexed,
                             (size_t)proto->batch_line_read[idx] / 2) != 0) {
      return -1;
    }
  } else {
    if (proto->input2priv_fn(proto->batch_priv[idx],
                             (unsigned char *)proto->batch_line[idx],
                             (size_t)proto->batch_line_read[idx]) != 0) {
      return -1;
    }
  }
  return 0;
}

static void *priv_batch_worker(void *arg) {
  priv_batch_job_t *job = arg;
  int i;
  for (i = job->start; i < job->end; ++i) {
    if (derive_batch_priv(i, job) != 0) {
      job->batch_line_read[i] = -1;
    }
  }
  return NULL;
}

static int run_priv_batch_jobs(int count, int threads, priv_batch_job_t proto) {
  pthread_t th[64];
  priv_batch_job_t jobs[64];
  int created[64];
  int T = threads;
  int t, chunk;

  if (T < 2 || count < 16) {
    for (t = 0; t < count; ++t) {
      if (derive_batch_priv(t, &proto) != 0) {
        proto.batch_line_read[t] = -1;
      }
    }
    return count;
  }
  if (T > 64) {
    T = 64;
  }
  if (T > count) {
    T = count;
  }
  chunk = (count + T - 1) / T;
  for (t = 0; t < T; ++t) {
    created[t] = 0;
    jobs[t] = proto;
    jobs[t].start = t * chunk;
    jobs[t].end = jobs[t].start + chunk;
    if (jobs[t].end > count) {
      jobs[t].end = count;
    }
    if (jobs[t].start >= jobs[t].end) {
      T = t;
      break;
    }
    if (t == 0) {
      continue;
    }
    if (pthread_create(&th[t], NULL, priv_batch_worker, &jobs[t]) == 0) {
      created[t] = 1;
    } else {
      priv_batch_worker(&jobs[t]);
    }
  }
  priv_batch_worker(&jobs[0]);
  for (t = 1; t < T; ++t) {
    if (created[t]) {
      pthread_join(th[t], NULL);
    }
  }

  for (t = 0, chunk = 0; t < count; ++t) {
    if (proto.batch_line_read[t] > -1) {
      ++chunk;
    }
  }
  return chunk;
}

typedef struct hash_batch_job_s {
  int start;
  int end;
  int nfn;
  unsigned char (*upub)[65];
  hash160_t *hashes;
  pubhashfn_t *fns;
} hash_batch_job_t;

static void *hash_batch_worker(void *arg) {
  hash_batch_job_t *job = arg;
  int i, j;
  for (i = job->start; i < job->end; ++i) {
    for (j = 0; j < job->nfn; ++j) {
      job->fns[j].fn(&job->hashes[i * job->nfn + j], job->upub[i]);
    }
  }
  return NULL;
}

static void run_hash_batch_jobs(int count, int threads, hash_batch_job_t proto) {
  pthread_t th[64];
  hash_batch_job_t jobs[64];
  int created[64];
  int T = threads;
  int t, chunk;

  if (count <= 0 || proto.nfn <= 0) {
    return;
  }
  if (T < 2 || count < 32) {
    proto.start = 0;
    proto.end = count;
    hash_batch_worker(&proto);
    return;
  }
  if (T > 64) {
    T = 64;
  }
  if (T > count) {
    T = count;
  }
  chunk = (count + T - 1) / T;
  for (t = 0; t < T; ++t) {
    created[t] = 0;
    jobs[t] = proto;
    jobs[t].start = t * chunk;
    jobs[t].end = jobs[t].start + chunk;
    if (jobs[t].end > count) {
      jobs[t].end = count;
    }
    if (jobs[t].start >= jobs[t].end) {
      T = t;
      break;
    }
    if (t == 0) {
      continue;
    }
    if (pthread_create(&th[t], NULL, hash_batch_worker, &jobs[t]) == 0) {
      created[t] = 1;
    } else {
      hash_batch_worker(&jobs[t]);
    }
  }
  hash_batch_worker(&jobs[0]);
  for (t = 1; t < T; ++t) {
    if (created[t]) {
      pthread_join(th[t], NULL);
    }
  }
}

static int ensure_line_buf(char **line, size_t *sz, size_t need) {
  char *p;
  size_t nsz;
  if (*sz >= need) {
    return 0;
  }
  nsz = *sz ? *sz : 128;
  while (nsz < need) {
    nsz *= 2;
  }
  p = realloc(*line, nsz);
  if (p == NULL) {
    return -1;
  }
  *line = p;
  *sz = nsz;
  return 0;
}

static char *obuf;
static size_t obuf_len, obuf_cap;
static FILE *obuf_fp;
static int out_tty = 0;

static void obuf_init(FILE *fp, int is_tty) {
  obuf_fp = fp;
  out_tty = is_tty;
  obuf_cap = 1u << 20;
  obuf_len = 0;
  obuf = chkmalloc(obuf_cap);
  if (!is_tty) {
    setvbuf(fp, NULL, _IOFBF, 1u << 20);
  }
}

static void obuf_flush(void) {
  if (obuf_len) {
    fwrite(obuf, 1, obuf_len, obuf_fp);
    obuf_len = 0;
  }
}

static void obuf_write(const char *p, size_t n) {
  if (n >= obuf_cap) {
    obuf_flush();
    fwrite(p, 1, n, obuf_fp);
    return;
  }
  if (obuf_len + n > obuf_cap) {
    obuf_flush();
  }
  memcpy(obuf + obuf_len, p, n);
  obuf_len += n;
}

static void fprintresult(FILE *f, hash160_t *hash,
                                unsigned char compressed,
                                unsigned char *type,
                                unsigned char *input) {
  size_t inlen = strlen((char *)input);
  size_t typelen = strlen((char *)type);
  size_t need = 40 + 1 + 1 + 1 + typelen + 1 + inlen + 1;
  char stack[512];
  char *dst = stack;

  (void)f;
  if (need > sizeof(stack)) {
    dst = chkmalloc(need);
  }
  hex_encode(hash->uc, 20, dst);
  dst[40] = ':';
  dst[41] = (char)compressed;
  dst[42] = ':';
  memcpy(dst + 43, type, typelen);
  dst[43 + typelen] = ':';
  memcpy(dst + 44 + typelen, input, inlen);
  dst[44 + typelen + inlen] = '\n';
  if (out_tty) {
    obuf_write("\033[0K", 4);
  }
  obuf_write(dst, need);
  if (dst != stack) {
    free(dst);
  }
}

void usage(unsigned char *name) {
  printf("Usage: %s [OPTION]...\n\n\
 -a                          open output file in append mode\n\
 -b FILE                     check for matches against bloom filter FILE\n\
 -f FILE                     verify matches against sorted hash160s in FILE\n\
 -i FILE                     read from FILE instead of stdin\n\
 -o FILE                     write to FILE instead of stdout\n\
 -c TYPES                    use TYPES for public key to hash160 computation\n\
                             multiple can be specified, for example the default\n\
                             is 'uc', which will check for both uncompressed\n\
                             and compressed addresses using Bitcoin's algorithm\n\
                             u - uncompressed address\n\
                             c - compressed address\n\
                             e - ethereum address\n\
                             x - most signifigant bits of x coordinate\n\
 -t TYPE                     inputs are TYPE - supported types:\n\
                             sha256 (default) - classic brainwallet\n\
                             sha3   - sha3-256\n\
                             priv   - raw private keys (requires -x)\n\
                             warp   - WarpWallet (supports -s or -p)\n\
                             bwio   - brainwallet.io (supports -s or -p)\n\
                             bv2    - brainv2 (supports -s or -p) VERY SLOW\n\
                             rush   - rushwallet (requires -r) FAST\n\
                             keccak - keccak256 (ethercamp/old ethaddress)\n\
                             camp2  - keccak256 * 2031 (new ethercamp)\n\
 -x                          treat input as hex encoded\n\
 -s SALT                     use SALT for salted input types (default: none)\n\
 -p PASSPHRASE               use PASSPHRASE for salted input types, inputs\n\
                             will be treated as salts\n\
 -r FRAGMENT                 use FRAGMENT for cracking rushwallet passphrase\n\
 -I HEXPRIVKEY               incremental private key cracking mode, starting\n\
                             at HEXPRIVKEY (supports -n) FAST\n\
 -k K                        skip the first K lines of input\n\
 -N N                        stop after N input lines or keys\n\
 -n K/N                      use only the Kth of every N input lines\n\
 -B BATCH_SIZE               batch size for affine transformations\n\
                             must be a power of 2 (default/max: %d)\n\
 -j N                        worker count (default: number of CPUs)\n\
                             uses processes for files/-I, threads for stdin\n\
                             (use 1 to disable parallelism)\n\
 -w WINDOW_SIZE              window size for ecmult table (default: 16)\n\
                             uses about 3 * 2^w KiB memory on startup, but\n\
                             only about 2^w KiB once the table is built\n\
 -m FILE                     load ecmult table from FILE\n\
                             the ecmtabgen tool can build such a table\n\
 -v                          verbose - display cracking progress\n\
 -h                          show this help\n", name, BATCH_MAX);
//q, --quiet                 suppress non-error messages
  exit(1);
}

int main(int argc, char **argv) {
  FILE *ifile = stdin;
  FILE *ofile = stdout;
  hsearchf_ctx_t fctx;
  memset(&fctx, 0, sizeof(fctx));
  fctx.fd = -1;

  int ret, c, i, j;

  float alpha, ilines_rate, ilines_rate_avg;
  int64_t raw_lines = -1;
  uint64_t report_mask = 0;
  uint64_t time_last, time_curr, time_delta;
  uint64_t time_start, time_elapsed;
  uint64_t ilines_last, ilines_curr, ilines_delta;
  uint64_t olines;

  int skipping = 0, tty = 0;

  unsigned char modestr[64];

  int spok = 0, aopt = 0, vopt = 0, wopt = 16, xopt = 0, jopt = 0;
  int nopt_mod = 0, nopt_rem = 0, Bopt = 0, nopt_user = 0;
  uint64_t kopt = 0, Nopt = ~0ULL;
  unsigned char *bopt = NULL, *iopt = NULL, *oopt = NULL;
  unsigned char *topt = NULL, *sopt = NULL, *popt = NULL;
  unsigned char *mopt = NULL, *fopt = NULL, *ropt = NULL;
  unsigned char *Iopt = NULL, *copt = NULL;

  unsigned char priv[64];
  pubhashfn_t pubhashfn[8];
  hash160_t *batch_hash = NULL;
  int n_pubhashfn = 0;
  memset(pubhashfn, 0, sizeof(pubhashfn));

  int batch_stopped = -1;
  char *batch_line[BATCH_MAX];
  size_t batch_line_sz[BATCH_MAX];
  int batch_line_read[BATCH_MAX];
  unsigned char batch_priv[BATCH_MAX][32];
  unsigned char batch_upub[BATCH_MAX][65];
  memset(batch_line, 0, sizeof(batch_line));
  memset(batch_line_sz, 0, sizeof(batch_line_sz));

  while ((c = getopt(argc, argv, "avxb:hi:k:f:m:n:o:p:s:r:c:t:w:I:N:B:j:")) != -1) {
    switch (c) {
      case 'a':
        aopt = 1; // open output file in append mode
        break;
      case 'k':
        kopt = strtoull(optarg, NULL, 10); // skip first k lines of input
        skipping = 1;
        break;
      case 'n':
        // only try the rem'th of every mod lines (one indexed)
        nopt_user = 1;
        nopt_rem = atoi(optarg) - 1;
        optarg = strchr(optarg, '/');
        if (optarg != NULL) { nopt_mod = atoi(optarg+1); }
        skipping = 1;
        break;
      case 'B':
        Bopt = atoi(optarg);
        break;
      case 'j':
        jopt = atoi(optarg);
        if (jopt < 1) {
          bail(1, "Invalid '-j' argument, threads must be >= 1\n");
        }
        break;
      case 'N':
        Nopt = strtoull(optarg, NULL, 0); // allows 0x
        break;
      case 'w':
        if (wopt > 1) wopt = atoi(optarg);
        break;
      case 'm':
        mopt = optarg; // table file
        wopt = 1; // auto
        break;
      case 'v':
        vopt = 1; // verbose
        break;
      case 'b':
        bopt = optarg; // bloom filter file
        break;
      case 'f':
        fopt = optarg; // full filter file
        break;
      case 'i':
        iopt = optarg; // input file
        break;
      case 'o':
        oopt = optarg; // output file
        break;
      case 'x':
        xopt = 1; // input is hex encoded
        break;
      case 's':
        sopt = optarg; // salt
        break;
      case 'p':
        popt = optarg; // passphrase
        break;
      case 'r':
        ropt = optarg; // rushwallet
        break;
      case 'c':
        copt = optarg; // type of hash160
        break;
      case 't':
        topt = optarg; // type of input
        break;
      case 'I':
        Iopt = optarg; // start key for incremental
        xopt = 1; // input is hex encoded
        break;
      case 'h':
        // show help
        usage(argv[0]);
        return 0;
      case '?':
        // show error
        return 1;
      default:
        // should never be reached...
        printf("got option '%c' (%d)\n", c, c);
        return 1;
    }
  }

  if (optind < argc) {
    if (optind == 1 && argc == 2) {
      // older versions of brainflayer had the bloom filter file as a
      // single optional argument, this keeps compatibility with that
      bopt = argv[1];
    } else {
      fprintf(stderr, "Invalid arguments:\n");
      while (optind < argc) {
        fprintf(stderr, "    '%s'\n", argv[optind++]);
      }
      exit(1);
    }
  }

  if (nopt_rem != 0 || nopt_mod != 0) {
    // note that nopt_rem has had one subtracted at option parsing
    if (nopt_rem >= nopt_mod) {
      bail(1, "Invalid '-n' argument, remainder '%d' must be <= modulus '%d'\n", nopt_rem+1, nopt_mod);
    } else if (nopt_rem < 0) {
      bail(1, "Invalid '-n' argument, remainder '%d' must be > 0\n", nopt_rem+1);
    } else if (nopt_mod < 1) {
      bail(1, "Invalid '-n' argument, modulus '%d' must be > 0\n", nopt_mod);
    }
  }

  if (wopt < 1 || wopt > 28) {
    bail(1, "Invalid window size '%d' - must be >= 1 and <= 28\n", wopt);
  } else {
    // very rough sanity check of window size
    struct sysinfo info;
    sysinfo(&info);
    uint64_t sysram = info.mem_unit * info.totalram;
    if (3584LLU*(1<<wopt) > sysram) {
      bail(1, "Not enough ram for requested window size '%d'\n", wopt);
    }
  }

  if (Bopt) { // if unset, will be set later
    if (Bopt < 1 || Bopt > BATCH_MAX) {
      bail(1, "Invalid '-B' argument, batch size '%d' - must be >= 1 and <= %d\n", Bopt, BATCH_MAX);
    } else if (Bopt & (Bopt - 1)) { // https://graphics.stanford.edu/~seander/bithacks.html#DetermineIfPowerOf2
      bail(1, "Invalid '-B' argument, batch size '%d' is not a power of 2\n", Bopt);
    }
  }

  if (Iopt) {
    if (strlen(Iopt) != 64) {
      bail(1, "The starting key passed to the '-I' must be 64 hex digits exactly\n");
    }
    if (topt) {
      bail(1, "Cannot specify input type in incremental mode\n");
    }
    topt = "priv";
    // normally, getline would allocate the batch_line entries, but we need to
    // do this to give the processing loop somewhere to write to in incr mode
    for (i = 0; i < BATCH_MAX; ++i) {
      batch_line[i] = Iopt;
    }
    unhex(Iopt, sizeof(priv)*2, priv, sizeof(priv));
    skipping = 1;
    if (!nopt_mod) { nopt_mod = 1; };
  }


  /* handle copt */
  if (copt == NULL) { copt = "uc"; }
  i = 0;
  while (copt[i]) {
    switch (copt[i]) {
      case 'u':
        pubhashfn[i].fn = &uhash160;
        break;
      case 'c':
        pubhashfn[i].fn = &chash160;
        break;
      case 'e':
        pubhashfn[i].fn = &ehash160;
        break;
      case 'x':
        pubhashfn[i].fn = &xhash160;
        break;
      default:
        bail(1, "Unknown hash160 type '%c'.\n", copt[i]);
    }
    if (strchr(copt + i + 1, copt[i])) {
      bail(1, "Duplicate hash160 type '%c'.\n", copt[i]);
    }
    pubhashfn[i].id = copt[i];
    ++i;
  }
  n_pubhashfn = i;
  if (n_pubhashfn < 1) {
    bail(1, "No hash160 types specified\n");
  }
  batch_hash = chkmalloc(sizeof(hash160_t) * (size_t)BATCH_MAX * (size_t)n_pubhashfn);

  /* handle topt */
  if (topt == NULL) { topt = "sha256"; }

  if (strcmp(topt, "sha256") == 0) {
    input2priv = &pass2priv;
  } else if (strcmp(topt, "priv") == 0) {
    if (!xopt) {
      bail(1, "raw private key input requires -x");
    }
    input2priv = &rawpriv2priv;
  } else if (strcmp(topt, "warp") == 0) {
    if (!Bopt) { Bopt = 1; } // don't batch transform for slow input hashes by default
    spok = 1;
    input2priv = popt ? &warpsalt2priv : &warppass2priv;
  } else if (strcmp(topt, "bwio") == 0) {
    if (!Bopt) { Bopt = 1; } // don't batch transform for slow input hashes by default
    spok = 1;
    input2priv = popt ? &bwiosalt2priv : &bwiopass2priv;
  } else if (strcmp(topt, "bv2") == 0) {
    if (!Bopt) { Bopt = 1; } // don't batch transform for slow input hashes by default
    spok = 1;
    input2priv = popt ? &brainv2salt2priv : &brainv2pass2priv;
  } else if (strcmp(topt, "rush") == 0) {
    input2priv = &rush2priv;
  } else if (strcmp(topt, "camp2") == 0) {
    input2priv = &camp2priv;
  } else if (strcmp(topt, "keccak") == 0) {
    input2priv = &keccak2priv;
  } else if (strcmp(topt, "sha3") == 0) {
    input2priv = &sha32priv;
//  } else if (strcmp(topt, "dicap") == 0) {
//    input2priv = &dicap2priv;
  } else {
    bail(1, "Unknown input type '%s'.\n", topt);
  }

  if (spok) {
    if (sopt && popt) {
      bail(1, "Cannot specify both a salt and a passphrase\n");
    }
    if (popt) {
      kdfpass = popt;
      kdfpass_sz = strlen(popt);
    } else {
      if (sopt) {
        kdfsalt = sopt;
        kdfsalt_sz = strlen(kdfsalt);
      } else {
        kdfsalt = chkmalloc(0);
        kdfsalt_sz = 0;
      }
    }
  } else {
    if (popt) {
      bail(1, "Specifying a passphrase not supported with input type '%s'\n", topt);
    } else if (sopt) {
      bail(1, "Specifying a salt not supported with this input type '%s'\n", topt);
    }
  }

  if (ropt) {
    if (input2priv != &rush2priv) {
      bail(1, "Specifying a url fragment only supported with input type 'rush'\n");
    }
    kdfsalt = ropt;
    kdfsalt_sz = strlen(kdfsalt) - sizeof(rushchk)*2;
    if (kdfsalt[kdfsalt_sz-1] != '!') {
      bail(1, "Invalid rushwallet url fragment '%s'\n", kdfsalt);
    }
    unhex(kdfsalt+kdfsalt_sz, sizeof(rushchk)*2, rushchk, sizeof(rushchk));
    kdfsalt[kdfsalt_sz] = '\0';
  } else if (input2priv == &rush2priv) {
    bail(1, "The '-r' option is required for rushwallet.\n");
  }

  snprintf(modestr, sizeof(modestr), xopt ? "(hex)%s" : "%s", topt);

  if (bopt) {
    if ((ret = mmapf(&bloom_mmapf, bopt, BLOOM_SIZE, MMAPF_RNDRD)) != MMAPF_OKAY) {
      bail(1, "failed to open bloom filter '%s': %s\n", bopt, mmapf_strerror(ret));
    } else if (bloom_mmapf.mem == NULL) {
      bail(1, "got NULL pointer trying to set up bloom filter\n");
    }
    bloom = bloom_mmapf.mem;
  }

  if (fopt) {
    int hsret;
    if (!bopt) {
      bail(1, "The '-f' option must be used with a bloom filter\n");
    }
    hsret = hsearchf_open(&fctx, (const char *)fopt);
    if (hsret != 0) {
      bail(1, "failed to mmap hash160 file '%s': %s\n", fopt, strerror(hsret < 0 ? -hsret : hsret));
    }
  }

  lineread_t lreader;
  memset(&lreader, 0, sizeof(lreader));
  lreader.fd = -1;

  if (iopt) {
    int lrret = lineread_open_path(&lreader, (const char *)iopt);
    if (lrret != 0) {
      bail(1, "failed to open '%s' for reading: %s\n", iopt, strerror(-lrret));
    }
  } else if (!Iopt) {
    lineread_open_fp(&lreader, ifile);
  }

  if (oopt && (ofile = fopen(oopt, (aopt ? "a" : "w"))) == NULL) {
    bail(1, "failed to open '%s' for writing: %s\n", oopt, strerror(errno));
  }

  setvbuf(stderr, NULL, _IOLBF, 0);

  if (vopt && ofile == stdout && isatty(fileno(stdout))) { tty = 1; }
  obuf_init(ofile, tty);

  if (jopt < 1) {
    long ncpu = sysconf(_SC_NPROCESSORS_ONLN);
    jopt = (ncpu > 0) ? (int)ncpu : 1;
  }

  brainflayer_init_globals();

  if (secp256k1_ec_pubkey_precomp_table(wopt, mopt) != 0) {
    bail(1, "failed to initialize precomputed table\n");
  }

  if (secp256k1_ec_pubkey_batch_init(BATCH_MAX) != 0) {
    bail(1, "failed to initialize batch point conversion structures\n");
  }

  int worker_id = 0;
  int nchildren = 0;
  pid_t children[64];
  int use_processes = (jopt > 1 && !nopt_user && (Iopt != NULL || iopt != NULL));

  if (use_processes) {
    int w;
    if (jopt > 64) {
      jopt = 64;
    }
    nopt_mod = jopt;
    skipping = 1;
    if (Iopt && nopt_mod < 1) {
      nopt_mod = 1;
    }
    for (w = 1; w < jopt; ++w) {
      pid_t pid = fork();
      if (pid < 0) {
        bail(1, "fork failed: %s\n", strerror(errno));
      }
      if (pid == 0) {
        worker_id = w;
        nopt_rem = w;
        nchildren = 0;
        break;
      }
      children[nchildren++] = pid;
    }
    if (worker_id == 0) {
      nopt_rem = 0;
    }
    secp256k1_ec_pubkey_set_threads(1);
    {
      int fd = fileno(ofile);
      int flags = fcntl(fd, F_GETFL, 0);
      if (flags >= 0) {
        fcntl(fd, F_SETFL, flags | O_APPEND);
      }
    }
    if (Nopt != ~0ULL) {
      uint64_t extra = Nopt % (uint64_t)jopt;
      Nopt = Nopt / (uint64_t)jopt + (worker_id < (int)extra ? 1 : 0);
    }
    if (vopt) {
      fprintf(stderr, "[*] workers: %d processes (id %d)\n", jopt, worker_id);
    }
  } else {
    jopt = secp256k1_ec_pubkey_set_threads((unsigned int)jopt);
    if (vopt) {
      fprintf(stderr, "[*] worker threads: %d\n", jopt);
    }
  }

  ilines_curr = 0;

  if (vopt) {
    /* initialize timing data */
    time_start = time_last = getns();
    olines = ilines_last = 0;
    ilines_rate_avg = -1;
    alpha = 0.500;
  } else {
    time_start = time_last = 0; // prevent compiler warning about uninitialized use
  }

  // set default batch size
  if (!Bopt) { Bopt = BATCH_MAX; }

  for (;;) {
    uint64_t remaining = (Nopt == ~0ULL) ? (uint64_t)Bopt : (Nopt - ilines_curr);
    int this_batch = Bopt;
    if (remaining == 0) {
      batch_stopped = 0;
      break;
    }
    if (remaining < (uint64_t)Bopt) {
      this_batch = (int)remaining;
    }

    if (Iopt) {
      if (skipping) {
        priv_add_uint32(priv, nopt_rem + kopt);
        skipping = 0;
      }
      secp256k1_ec_pubkey_batch_incr(this_batch, nopt_mod, batch_upub, batch_priv, priv);
      memcpy(priv, batch_priv[this_batch-1], 32);
      priv_add_uint32(priv, nopt_mod);

      batch_stopped = this_batch;
    } else {
      priv_batch_job_t pjob;
      int filled = 0;

      for (i = 0; i < this_batch;) {
        const char *line;
        size_t linelen;
        if (!lineread_next(&lreader, &line, &linelen)) {
          break;
        }
        if (skipping) {
          ++raw_lines;
          if (kopt && raw_lines < kopt) { continue; }
          if (nopt_mod) {
            /* Stripe remaining lines after -k so worker 0 gets the first
               unskipped line. Absolute-line modulus would send -k 1 -N 1
               to line 5 instead of line 2 when -j 4. */
            uint64_t idx = (uint64_t)raw_lines - kopt;
            if (idx % (uint64_t)nopt_mod != (uint64_t)nopt_rem) { continue; }
          }
        }
        if (ensure_line_buf(&batch_line[i], &batch_line_sz[i], linelen + 1) != 0) {
          bail(1, "realloc failed while reading input\n");
        }
        memcpy(batch_line[i], line, linelen);
        batch_line[i][linelen] = 0;
        batch_line_read[i] = (int)linelen;
        ++i;
      }
      filled = i;

      if (filled > 0) {
        pjob.start = 0;
        pjob.end = filled;
        pjob.batch_line_read = batch_line_read;
        pjob.batch_line = batch_line;
        pjob.batch_priv = batch_priv;
        pjob.xopt = xopt;
        pjob.unhexed = unhexed;
        pjob.unhexed_sz = unhexed_sz;
        pjob.input2priv_fn = input2priv;

        if (!use_processes && jopt > 1 && !xopt && filled >= 512) {
          int priv_threads = jopt > 2 ? 2 : jopt;
          run_priv_batch_jobs(filled, priv_threads, pjob);
          for (i = 0, batch_stopped = 0; i < filled; ++i) {
            if (batch_line_read[i] > -1) {
              if (batch_stopped != i) {
                batch_line_read[batch_stopped] = batch_line_read[i];
                batch_line[batch_stopped] = batch_line[i];
                memcpy(batch_priv[batch_stopped], batch_priv[i], 32);
              }
              ++batch_stopped;
            }
          }
          filled = batch_stopped;
        } else {
          for (i = 0; i < filled; ++i) {
            if (derive_batch_priv(i, &pjob) != 0) {
              fprintf(stderr, "input2priv failed! continuing...\n");
              batch_line_read[i] = -1;
            }
          }
          for (i = 0, batch_stopped = 0; i < filled; ++i) {
            if (batch_line_read[i] > -1) {
              if (batch_stopped != i) {
                batch_line_read[batch_stopped] = batch_line_read[i];
                batch_line[batch_stopped] = batch_line[i];
                memcpy(batch_priv[batch_stopped], batch_priv[i], 32);
              }
              ++batch_stopped;
            }
          }
          filled = batch_stopped;
        }

        if (filled > 0) {
          secp256k1_ec_pubkey_batch_create((unsigned int)filled, batch_upub, batch_priv);
        }
      }

      batch_stopped = filled;
    }

    // hash public keys (parallel when this process has worker threads)
    if (batch_stopped > 0) {
      hash_batch_job_t hjob;
      hjob.start = 0;
      hjob.end = batch_stopped;
      hjob.nfn = n_pubhashfn;
      hjob.upub = batch_upub;
      hjob.hashes = batch_hash;
      hjob.fns = pubhashfn;
      if (!use_processes && jopt > 1) {
        run_hash_batch_jobs(batch_stopped, jopt, hjob);
      } else {
        hash_batch_worker(&hjob);
      }
    }

    if (bloom) { /* crack mode */
      for (i = 0; i < batch_stopped; ++i) {
        if (Iopt) {
          hex_encode(batch_priv[i], 32, batch_line[i]);
        }
        for (j = 0; j < n_pubhashfn; ++j) {
          hash160_t *h = &batch_hash[i * n_pubhashfn + j];
          if (!bloom_chk_hash160(bloom, h->ul)) {
            continue;
          }
          if (fopt && !hsearchf(&fctx, h)) {
            continue;
          }
          fprintresult(ofile, h, pubhashfn[j].id, modestr, (unsigned char *)batch_line[i]);
          ++olines;
        }
      }
    } else { /* generate mode */
      for (i = 0; i < batch_stopped; ++i) {
        if (Iopt) {
          hex_encode(batch_priv[i], 32, batch_line[i]);
        }
        for (j = 0; j < n_pubhashfn; ++j) {
          fprintresult(ofile, &batch_hash[i * n_pubhashfn + j],
                       pubhashfn[j].id, modestr, (unsigned char *)batch_line[i]);
        }
      }
    }
    // end public key processing loop

    ilines_curr += batch_stopped;

    // start stats
    if (vopt) {
      if (batch_stopped < Bopt || (ilines_curr & report_mask) == 0) {
        time_curr = getns();
        time_delta = time_curr - time_last;
        time_elapsed = time_curr - time_start;
        time_last = time_curr;
        ilines_delta = ilines_curr - ilines_last;
        ilines_last = ilines_curr;
        ilines_rate = (ilines_delta * 1.0e9) / (time_delta * 1.0);

        if (batch_stopped < Bopt) {
          /* report overall average on last status update */
          ilines_rate_avg = (ilines_curr * 1.0e9) / (time_elapsed * 1.0);
        } else if (ilines_rate_avg < 0) {
          ilines_rate_avg = ilines_rate;
        /* target reporting frequency to about once every five seconds */
        } else if (time_delta < 2500000000) {
          report_mask = (report_mask << 1) | 1;
          ilines_rate_avg = ilines_rate; /* reset EMA */
        } else if (time_delta > 10000000000) {
          report_mask >>= 1;
          ilines_rate_avg = ilines_rate; /* reset EMA */
        } else {
          /* exponetial moving average */
          ilines_rate_avg = alpha * ilines_rate + (1 - alpha) * ilines_rate_avg;
        }

        if (tty) {
          obuf_flush();
        }
        if (use_processes) {
          fprintf(stderr,
              "w%d rate: %9.2f p/s found: %5" PRIu64 "/%-10" PRIu64 " elapsed: %8.3f s\n",
              worker_id,
              ilines_rate_avg,
              olines,
              ilines_curr,
              time_elapsed / 1.0e9
          );
        } else {
          fprintf(stderr,
              "\033[0G\033[2K"
              " rate: %9.2f p/s"
              " found: %5" PRIu64 "/%-10" PRIu64
              " elapsed: %8.3f s"
              "\033[0G",
              ilines_rate_avg,
              olines,
              ilines_curr,
              time_elapsed / 1.0e9
          );
        }

        fflush(stderr);
      }
    }
    // end stats

    // main loop exit condition
    if (batch_stopped < Bopt || ilines_curr >= Nopt) {
      if (vopt && !use_processes) { fprintf(stderr, "\n"); }
      break;
    }
  }

  obuf_flush();
  if (worker_id == 0) {
    lineread_close(&lreader);
  }

  if (nchildren > 0) {
    int w, st, rc = 0;
    for (w = 0; w < nchildren; ++w) {
      if (waitpid(children[w], &st, 0) < 0 || !WIFEXITED(st) || WEXITSTATUS(st) != 0) {
        rc = 1;
      }
    }
    hsearchf_close(&fctx);
    return rc;
  }

  hsearchf_close(&fctx);
  return 0;
}

/*  vim: set ts=2 sw=2 et ai si: */
