# Bloom filter data (not stored in git)

Download the private [AppleLampsX/brain](https://huggingface.co/datasets/AppleLampsX/brain) dataset:

```
export HF_TOKEN=...   # read access to AppleLampsX/brain
./scripts/fetch_hf_brain.sh
```

That writes `keys.blf.gz` and the uncompressed 512 MiB `keys.blf` used with `brainflayer -b`.
