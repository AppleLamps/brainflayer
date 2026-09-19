/* Fast SHA-256 with SHA-NI when available, OpenSSL fallback otherwise. */
#ifndef __BRAINFLAYER_SHA256_FAST_H_
#define __BRAINFLAYER_SHA256_FAST_H_

#include <stddef.h>

void sha256_fast_init(void);
void sha256_fast(const void *data, size_t len, unsigned char out[32]);

#endif /* __BRAINFLAYER_SHA256_FAST_H_ */
