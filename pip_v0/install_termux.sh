#!/data/data/com.termux/files/usr/bin/bash
#
# install_termux.sh — one-command Pip-on-phone installer.
#
# Turns an Android phone into Pip's whole brain: a local, offline LLM served
# over an OpenAI-compatible API, with Pip's package pointed at it. No root,
# no paid API, no cloud. Inspired by orailnoor/termux-llm and DroidDesk.
#
# Usage (inside Termux):
#     bash install_termux.sh              # full install
#     bash install_termux.sh --dry-run    # print the plan, change nothing
#     bash install_termux.sh --engine ollama   # force the Ollama path
#     bash install_termux.sh --engine llama    # force the llama.cpp path
#
# Two engines, both serving an OpenAI-compatible /v1 API so Pip is agnostic:
#   - ollama   : simplest if `pkg install ollama` works on your device.
#   - llama    : build llama.cpp from source (the universal fallback).
# Default = auto: try Ollama first, fall back to building llama.cpp.
#
# Re-running is safe: existing packages and models are skipped.
set -euo pipefail

DRY_RUN=0
ENGINE="auto"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --engine) ENGINE="${2:-auto}"; shift ;;
    --engine=*) ENGINE="${1#*=}" ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\n\033[1;35m✦ %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$1"; }

# run CMD — execute, or just print it under --dry-run.
run() {
  if [ "$DRY_RUN" = "1" ]; then
    printf '   \033[2m$ %s\033[0m\n' "$*"
  else
    "$@"
  fi
}

have() { command -v "$1" >/dev/null 2>&1; }

# ── 0. Environment sanity ───────────────────────────────────────────────────
if [ -z "${PREFIX:-}" ] || [ "${PREFIX#*com.termux}" = "${PREFIX:-}" ]; then
  warn "This script targets Termux on Android."
  warn "On a laptop, just run Ollama or LM Studio and point Pip at its /v1 URL."
  warn "See TERMUX_PHONE_SETUP.md for the desktop path."
fi
[ "$DRY_RUN" = "1" ] && say "DRY RUN — showing the plan, changing nothing."

# ── 1. Detect RAM and pick a right-sized Q4_K_M model ───────────────────────
TOTAL_GB=0
if [ -r /proc/meminfo ]; then
  TOTAL_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
  TOTAL_GB=$(( TOTAL_KB / 1024 / 1024 ))
fi
say "Detected ~${TOTAL_GB} GB RAM."

if   [ "$TOTAL_GB" -gt 0 ] && [ "$TOTAL_GB" -lt 4 ]; then
  OLLAMA_MODEL="qwen2.5:0.5b"
  GGUF_URL="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"
elif [ "$TOTAL_GB" -lt 6 ]; then
  OLLAMA_MODEL="qwen2.5:1.5b"
  GGUF_URL="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
else
  OLLAMA_MODEL="qwen2.5:3b"
  GGUF_URL="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
fi
GGUF_FILE="$(basename "$GGUF_URL")"
say "Model: Ollama=${OLLAMA_MODEL}  |  GGUF=${GGUF_FILE} (Q4_K_M)"

# ── 2. Base packages ────────────────────────────────────────────────────────
say "Updating Termux packages…"
run pkg update -y
run pkg install -y python git wget

# ── 3. Engine selection: ollama (simple) or llama.cpp (universal) ───────────
install_ollama() {
  say "Engine: Ollama"
  if ! have ollama; then
    run pkg install -y ollama
  fi
  have ollama || { warn "Ollama not available via pkg on this device."; return 1; }
  cat > "$HOME/start-pip-brain.sh" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
ollama serve >/dev/null 2>&1 &
sleep 3
ollama pull ${OLLAMA_MODEL}
export PIP_LLM_BACKEND=openai_compat
export PIP_LLM_BASE_URL=http://127.0.0.1:11434/v1
export PIP_LLM_MODEL=${OLLAMA_MODEL}
echo "Pip's local brain (Ollama) is live at http://127.0.0.1:11434/v1"
echo "Now run Pip:  python -m pip_v0.pip_control_panel"
EOF
  return 0
}

install_llama() {
  say "Engine: llama.cpp (build from source)"
  run pkg install -y cmake clang
  LLAMA_DIR="$HOME/llama.cpp"
  if [ ! -d "$LLAMA_DIR" ]; then
    run git clone --depth 1 https://github.com/ggerganov/llama.cpp "$LLAMA_DIR"
    run bash -c "cd '$LLAMA_DIR' && cmake -B build && cmake --build build --config Release -j\"\$(nproc)\""
  else
    say "llama.cpp already present — skipping build."
  fi
  MODEL_DIR="$HOME/pip-models"
  run mkdir -p "$MODEL_DIR"
  if [ ! -f "$MODEL_DIR/$GGUF_FILE" ]; then
    run wget -O "$MODEL_DIR/$GGUF_FILE" "$GGUF_URL"
  else
    say "Model already downloaded — skipping."
  fi
  cat > "$HOME/start-pip-brain.sh" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
SERVER="$LLAMA_DIR/build/bin/llama-server"
[ -x "\$SERVER" ] || SERVER="$LLAMA_DIR/build/bin/server"
"\$SERVER" -m "$MODEL_DIR/$GGUF_FILE" --host 127.0.0.1 --port 8080 &
sleep 4
export PIP_LLM_BACKEND=openai_compat
export PIP_LLM_BASE_URL=http://127.0.0.1:8080/v1
export PIP_LLM_MODEL=local
echo "Pip's local brain (llama.cpp) is live at http://127.0.0.1:8080/v1"
echo "Now run Pip:  python -m pip_v0.pip_control_panel"
EOF
}

case "$ENGINE" in
  ollama) install_ollama || { warn "Ollama path failed."; exit 1; } ;;
  llama)  install_llama ;;
  auto)
    if install_ollama; then
      :
    else
      warn "Falling back to building llama.cpp."
      install_llama
    fi
    ;;
  *) warn "Unknown engine '$ENGINE' (use: auto | ollama | llama)"; exit 2 ;;
esac

if [ "$DRY_RUN" = "1" ]; then
  say "Dry run complete. Re-run without --dry-run to install for real."
  exit 0
fi

run chmod +x "$HOME/start-pip-brain.sh"
say "Done. Start everything with:  bash ~/start-pip-brain.sh"
say "Pip uses the on-phone model automatically — fully offline, no API keys."
