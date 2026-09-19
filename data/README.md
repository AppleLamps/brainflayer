# Data files (generated artifacts are not stored in git)

## Bloom filter

Download the private [AppleLampsX/brain](https://huggingface.co/datasets/AppleLampsX/brain) dataset:

```
export HF_TOKEN=...   # read access to AppleLampsX/brain
./scripts/fetch_hf_brain.sh
```

That writes `keys.blf.gz` and the uncompressed 512 MiB `keys.blf` used with `brainflayer -b`.

## Exact hash160 list

Download [AppleLampsX/h160](https://huggingface.co/datasets/AppleLampsX/h160) (`all.hex.gz`) and convert it to the sorted 20-byte file brainflayer `-f` expects:

```
export HF_TOKEN=...   # read access to AppleLampsX/h160
./scripts/fetch_hf_h160.sh
```

That writes `h160.bin` (90,379,448 hash160s, ~1.7 GiB). Use it to drop bloom false positives:

```
brainflayer -v -b keys.blf -f h160.bin -m /tmp/ecmult.w16.tab -i wordlist.txt
python3 ../scripts/h160_lookup.py h160.bin 5d3a136dda11e1616e72416e7c9d7581863aecdf
```

`make fetch-dataset` fetches both files.

## Wordlist

`seeds.txt` is the curated high-value phrase list (bitcoin culture, public-domain
quotes, common passphrases). The full candidate list is generated:

```
python3 ../scripts/make_wordlist.py -o wordlist.txt
# or from the repo root: make wordlist
```

That downloads password/dictionary sources into `wordlist-src/` (cached) and
writes printable-ASCII phrases to `wordlist.txt`. The default run is **over
1 billion** candidates (about 20 GiB): a ~3 million quality prefix plus
ranked two-word combinations of 36k dictionary words (space, hyphen, concat,
underscore). Use `--core-only` for the prefix alone, or pipe:

```
python3 ../scripts/make_wordlist.py -o - | brainflayer -v -b keys.blf -f h160.bin -m /tmp/ecmult.w16.tab
```

Do not feed this file through `case_variants.py`; the generator already emits
title/upper/first-cap forms on the quality prefix. Full 2^n case permutation
is only for tiny lists.
