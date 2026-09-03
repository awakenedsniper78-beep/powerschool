#!/usr/bin/env bash
# Set up a local Qwen3 chat model via Ollama.
#
#   ./setup.sh                 # pick a model that fits this machine
#   ./setup.sh 14b             # force a size: 4b | 8b | 14b | 30b-a3b | 32b
#   ./setup.sh 8b --abliterated  # community "uncensored" finetune instead of the official weights
#
set -euo pipefail

SIZE="${1:-auto}"
VARIANT="official"
for arg in "$@"; do
  [ "$arg" = "--abliterated" ] && VARIANT="abliterated"
done

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- inspect host
OS="$(uname -s)"
case "$OS" in
  Darwin)
    # Apple silicon shares RAM with the GPU, so total memory is the budget.
    MEM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
    ACCEL="metal"
    ;;
  Linux)
    MEM_GB=$(awk '/MemTotal/ {print int($2/1024/1024)}' /proc/meminfo)
    if command -v nvidia-smi >/dev/null 2>&1; then
      ACCEL="cuda"
      VRAM_GB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits \
                | sort -rn | head -1 | awk '{print int($1/1024)}')
      MEM_GB="$VRAM_GB"   # budget against VRAM; spilling to RAM is painfully slow
    else
      ACCEL="cpu"
    fi
    ;;
  *) die "unsupported OS: $OS (this script handles macOS and Linux)" ;;
esac

say "host: $OS, accelerator: $ACCEL, usable memory for the model: ${MEM_GB}GB"

# ------------------------------------------------------------- choose the model
# Q4_K_M weights need roughly (params * 0.6)GB plus a couple GB for KV cache.
if [ "$SIZE" = "auto" ]; then
  if   [ "$MEM_GB" -ge 40 ]; then SIZE="32b"
  elif [ "$MEM_GB" -ge 24 ]; then SIZE="30b-a3b"
  elif [ "$MEM_GB" -ge 16 ]; then SIZE="14b"
  elif [ "$MEM_GB" -ge 10 ]; then SIZE="8b"
  else                            SIZE="4b"
  fi
  say "auto-selected qwen3:$SIZE (override by passing a size)"
fi

case "$VARIANT" in
  official)
    MODEL="qwen3:${SIZE}"
    ;;
  abliterated)
    # Community finetunes with refusal behaviour removed. Not published by
    # Alibaba, not safety-tested, and only some sizes exist.
    case "$SIZE" in
      4b|8b|14b|32b) MODEL="huihui_ai/qwen3-abliterated:${SIZE}" ;;
      *) die "no abliterated build for ${SIZE}; try 4b, 8b, 14b or 32b" ;;
    esac
    say "using a community abliterated build: $MODEL"
    ;;
esac

# ------------------------------------------------------------- install ollama
if ! command -v ollama >/dev/null 2>&1; then
  say "installing ollama"
  case "$OS" in
    Darwin)
      if command -v brew >/dev/null 2>&1; then
        brew install --cask ollama
      else
        die "install Homebrew, or grab the app from https://ollama.com/download"
      fi
      ;;
    Linux) curl -fsSL https://ollama.com/install.sh | sh ;;
  esac
else
  say "ollama already installed ($(ollama --version 2>&1 | head -1))"
fi

# --------------------------------------------------------------- start the daemon
if ! curl -fsS --max-time 3 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
  say "starting the ollama server in the background"
  if [ "$OS" = "Darwin" ] && [ -d /Applications/Ollama.app ]; then
    open -a Ollama
  else
    nohup ollama serve >"${TMPDIR:-/tmp}/ollama.log" 2>&1 &
  fi
  for _ in $(seq 30); do
    curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && break
    sleep 1
  done
  curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1 \
    || die "ollama did not come up; check ${TMPDIR:-/tmp}/ollama.log"
fi
say "ollama is listening on http://127.0.0.1:11434"

# ------------------------------------------------------------------ pull + smoke
say "pulling $MODEL (several GB — this is the slow part)"
ollama pull "$MODEL"

say "smoke test"
ollama run "$MODEL" "Reply with exactly: local model online." --hidethinking 2>/dev/null \
  || ollama run "$MODEL" "Reply with exactly: local model online."

cat <<MSG

Done. $MODEL is installed and served locally.

  Chat:        ollama run $MODEL
  HTTP API:    curl http://127.0.0.1:11434/api/chat -d '{
                 "model": "$MODEL",
                 "messages": [{"role": "user", "content": "hello"}],
                 "stream": false
               }'
  OpenAI-compatible base URL: http://127.0.0.1:11434/v1  (any api key string)
  List / remove:  ollama list   |   ollama rm $MODEL

Qwen3 is a hybrid reasoning model: append /no_think to a prompt to skip the
thinking block, or /think to force it.
MSG
