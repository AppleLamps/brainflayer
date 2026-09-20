HEADERS = bloom.h hash160.h warpwallet.h sha256_fast.h lineread.h hex.h
OBJ_MAIN = brainflayer.o hex2blf.o blfchk.o ecmtabgen.o hexln.o filehex.o
OBJ_UTIL = hex.o bloom.o mmapf.o hsearchf.o ec_pubkey_fast.o ripemd160_256.o \
           dldummy.o sha256_fast.o lineread.o
OBJ_ALGO = $(patsubst %.c,%.o,$(wildcard algo/*.c))
OBJECTS = $(OBJ_MAIN) $(OBJ_UTIL) $(OBJ_ALGO)
BINARIES = brainflayer hexln hex2blf blfchk ecmtabgen filehex
LIBS = -lrt -lcrypto -lgmp -pthread
# ARCH=native uses this machine's SHA-NI/AVX2/etc. Override with ARCH=x86-64-v3
# for a more portable binary.
ARCH ?= native
# Optional: make USE_BL=1 — faster EC adds on some CPUs (verify with scripts/benchmark.sh)
USE_BL ?= 0
BL_FLAGS = $(if $(filter 1,$(USE_BL)),-DUSE_BL_ARITHMETIC,)
TABLE ?= /tmp/ecmult.w16.tab
CFLAGS = -O3 -pthread -march=$(ARCH) -mtune=$(ARCH) \
         -flto=auto -fomit-frame-pointer -funsigned-char \
         -fno-math-errno \
         -falign-functions=16 -falign-loops=16 -falign-jumps=16 \
         -Wall -Wextra -Wno-pointer-sign -Wno-sign-compare \
         -Wno-deprecated-declarations \
         -pedantic -std=gnu11 -MMD -MP $(BL_FLAGS)
COMPILE = gcc $(CFLAGS)

SECP_CONFIG = --disable-shared --enable-static --with-field=64bit --with-scalar=64bit
ifneq ($(filter native x86-64 x86-64-v2 x86-64-v3 x86-64-v4,$(ARCH)),)
SECP_CONFIG += --with-asm=x86_64
endif

.PHONY: all clean test bench fetch-dataset fetch-bloom fetch-h160 fetch-eth test-dataset wordlist wordlist-core crack-wordlist crack-wordlist-eth

all: $(BINARIES)

.git:
	@echo 'This does not look like a cloned git repo. Unable to fetch submodules.'
	@false

secp256k1/include/secp256k1.h:
	git submodule update --init secp256k1

secp256k1/.libs/libsecp256k1.a: secp256k1/include/secp256k1.h
	cd secp256k1; make distclean 2>/dev/null || true
	cd secp256k1; ./autogen.sh
	cd secp256k1; ./configure $(SECP_CONFIG)
	cd secp256k1; make

scrypt-jane/scrypt-jane.h:
	git submodule update --init scrypt-jane

scrypt-jane/scrypt-jane.o: scrypt-jane/scrypt-jane.h scrypt-jane/scrypt-jane.c
	cd scrypt-jane; gcc -O3 -march=$(ARCH) -mtune=$(ARCH) -DSCRYPT_SALSA -DSCRYPT_SHA256 -c scrypt-jane.c -o scrypt-jane.o

brainflayer.o: brainflayer.c secp256k1/.libs/libsecp256k1.a

algo/warpwallet.o: algo/warpwallet.c scrypt-jane/scrypt-jane.h

algo/brainwalletio.o: algo/brainwalletio.c scrypt-jane/scrypt-jane.h

algo/brainv2.o: algo/brainv2.c scrypt-jane/scrypt-jane.h

ec_pubkey_fast.o: ec_pubkey_fast.c secp256k1/.libs/libsecp256k1.a
	$(COMPILE) -Wno-unused-function -c $< -o $@

%.o: %.c
	$(COMPILE) -c $< -o $@

hexln: hexln.o hex.o
	$(COMPILE) $^ $(LIBS) -o $@

blfchk: blfchk.o hex.o bloom.o mmapf.o hsearchf.o
	$(COMPILE) $^ $(LIBS) -o $@

hex2blf: hex2blf.o hex.o bloom.o mmapf.o lineread.o
	$(COMPILE) $^ $(LIBS) -lm -o $@

ecmtabgen: ecmtabgen.o mmapf.o ec_pubkey_fast.o
	$(COMPILE) $^ $(LIBS) -o $@

filehex: filehex.o hex.o
	$(COMPILE) $^ $(LIBS) -o $@

brainflayer: brainflayer.o $(OBJ_UTIL) $(OBJ_ALGO) \
             secp256k1/.libs/libsecp256k1.a scrypt-jane/scrypt-jane.o
	$(COMPILE) $^ $(LIBS) -o $@

tests/test_sha256: tests/test_sha256.c sha256_fast.o sha256_fast.h
	$(COMPILE) -I. tests/test_sha256.c sha256_fast.o -lcrypto -o $@

$(TABLE): ecmtabgen
	./ecmtabgen 16 "$(TABLE)"

test: all tests/test_sha256 $(TABLE)
	./tests/test_sha256
	python3 scripts/make_wordlist.py --self-test
	TABLE="$(TABLE)" ./scripts/verify_opt.sh

bench: all $(TABLE)
	TABLE="$(TABLE)" ./scripts/benchmark.sh

fetch-bloom:
	./scripts/fetch_hf_brain.sh

fetch-h160:
	./scripts/fetch_hf_h160.sh

fetch-eth:
	./scripts/fetch_hf_eth.sh

fetch-dataset: fetch-bloom fetch-h160 fetch-eth

test-dataset: all $(TABLE)
	TABLE="$(TABLE)" ./scripts/test_hf_brain.sh
	@if [ -f data/eth.blf ] && [ -f data/eth.bin ]; then TABLE="$(TABLE)" ./scripts/test_hf_eth.sh; fi

data/wordlist.txt: data/seeds.txt scripts/make_wordlist.py
	python3 scripts/make_wordlist.py -o data/wordlist.txt

wordlist: data/wordlist.txt

wordlist-core:
	python3 scripts/make_wordlist.py --core-only -o data/wordlist.txt

crack-wordlist: all $(TABLE) data/wordlist.txt
	@test -f data/keys.blf || { echo "missing data/keys.blf; run make fetch-bloom" >&2; exit 1; }
	@test -f data/h160.bin || { echo "missing data/h160.bin; run make fetch-h160" >&2; exit 1; }
	./brainflayer -v -b data/keys.blf -f data/h160.bin -m "$(TABLE)" -i data/wordlist.txt -o data/wordlist.hits

crack-wordlist-eth: all $(TABLE) data/wordlist.txt
	@test -f data/eth.blf || { echo "missing data/eth.blf; run make fetch-eth" >&2; exit 1; }
	@test -f data/eth.bin || { echo "missing data/eth.bin; run make fetch-eth" >&2; exit 1; }
	./brainflayer -v -c e -b data/eth.blf -f data/eth.bin -m "$(TABLE)" -i data/wordlist.txt -o data/wordlist.eth.hits

clean:
	rm -f $(BINARIES) $(OBJECTS) $(OBJECTS:.o=.d) tests/test_sha256 tests/test_sha256.d

-include $(OBJECTS:.o=.d)
