# Data files (generated artifacts are not stored in git)

## Bloom filter

Download the private [AppleLampsX/brain](https://huggingface.co/datasets/AppleLampsX/brain) dataset:

```
export HF_TOKEN=...   # read access to AppleLampsX/brain
./scripts/fetch_hf_brain.sh
```

That writes `keys.blf.gz` and the uncompressed 512 MiB `keys.blf` used with `brainflayer -b`.

## Wordlist

`seeds.txt` is the curated high-value phrase list (bitcoin culture, public-domain
quotes, common passphrases). The full candidate list is generated:

```
python3 ../scripts/make_wordlist.py -o wordlist.txt
# or from the repo root: make wordlist
```

That downloads password/dictionary sources into `wordlist-src/` (cached) and
writes unique printable-ASCII phrases to `wordlist.txt` (about 3 million
lines). Use it as:

```
brainflayer -v -b keys.blf -m /tmp/ecmult.w16.tab -i wordlist.txt
```

Do not feed this file through `case_variants.py`; the generator already emits
title/upper/first-cap forms. Full 2^n case permutation is only for tiny lists.
