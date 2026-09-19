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
writes printable-ASCII phrases to `wordlist.txt`. The default run is **over
1 billion** candidates (about 20 GiB): a ~3 million quality prefix plus
ranked two-word combinations of 36k dictionary words (space, hyphen, concat,
underscore). Use `--core-only` for the prefix alone, or pipe:

```
python3 ../scripts/make_wordlist.py -o - | brainflayer -v -b keys.blf -m /tmp/ecmult.w16.tab
```

Do not feed this file through `case_variants.py`; the generator already emits
title/upper/first-cap forms on the quality prefix. Full 2^n case permutation
is only for tiny lists.
