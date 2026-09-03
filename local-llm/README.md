# Running Qwen3 locally

`./setup.sh` installs [Ollama](https://ollama.com), picks a Qwen3 size that fits
the machine, pulls the weights, and runs a smoke test. Run it on your own
computer — it needs to download several GB and wants a GPU (or Apple silicon)
to be pleasant.

```sh
cd local-llm
./setup.sh                  # auto-pick a size
./setup.sh 14b              # force a size
./setup.sh 8b --abliterated # community "uncensored" finetune
```

## Which size

Qwen3 ships at 0.6B, 1.7B, 4B, 8B, 14B, 32B, plus the 30B-A3B and 235B-A22B
mixture-of-experts models. There is no 27B Qwen3 — that size belongs to Gemma 3,
which blog posts sometimes conflate with it.

At the default Q4_K_M quantization, budget roughly `params × 0.6 GB` of weights
plus ~2 GB of KV cache, and keep it all in VRAM (or unified memory on a Mac);
once layers spill to system RAM, throughput drops by an order of magnitude.

| Model | Needs about | Notes |
|---|---|---|
| `qwen3:4b` | 5 GB | fine on a laptop iGPU or CPU |
| `qwen3:8b` | 8 GB | the usual sweet spot on a 12–16 GB card |
| `qwen3:14b` | 12 GB | wants 16 GB |
| `qwen3:30b-a3b` | 20 GB | MoE: 30B of weights, only ~3B active, so it is fast |
| `qwen3:32b` | 22 GB | dense, slowest of these, strongest |

## Using it

The daemon exposes both its native API and an OpenAI-compatible one:

```sh
ollama run qwen3:8b                       # interactive

curl http://127.0.0.1:11434/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"hi"}]}'
```

Point any OpenAI SDK at `http://127.0.0.1:11434/v1` with any non-empty API key.

Qwen3 is a hybrid reasoning model: it emits a `<think>` block by default.
Append `/no_think` to a prompt to suppress it, `/think` to force it.

## The "uncensored" builds

`--abliterated` pulls a community finetune (`huihui_ai/qwen3-abliterated`) whose
refusal directions have been ablated from the weights. These are third-party
uploads, not Alibaba releases: nobody has evaluated them, quality regresses
measurably against the official weights on reasoning benchmarks, and you own
whatever comes out. Prefer the official weights unless you specifically need
this.

## Uninstalling

```sh
ollama rm qwen3:8b        # drop one model
rm -rf ~/.ollama          # drop every model and all config
```

macOS: quit the Ollama app and `brew uninstall --cask ollama`.
Linux: `sudo systemctl disable --now ollama && sudo rm /usr/local/bin/ollama`.
