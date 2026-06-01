#!/data/data/com.termux/files/usr/bin/bash
#
# install_termux.sh — one-command Pip-on-phone installer.
#
# Turns an Android phone into Pip's whole brain: a local, offline LLM served
# over an OpenAI-compatible API, with Pip's package pointed at it. No root,
# no paid API, no cloud. Inspired by orailnoor/termux-llm and DroidDesk.
#
# Usage (inside Termux):
#     bash install_termux.sh
#
# Re-running is safe: existing packages and models are skipped.
set -euo pipefail

say() { printf '\n\033[1;35m✦ %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$1"; }

if [ -z "${PREFIX:-}" ] || [ "${PREFIX#*com.termux}" = "$PREFIX" ]; then
  warn "This script is for Termux on Android. On a laptop, use Ollama or LM Studio instead."
  warn "See TERMUX_PHONE_SETUP.md for the desktop path."
fi

# ── 1. Base packages ────────────────────────────────────────────────────────
say "Updating Termux packages (this is the slow part on a phone)…"
pkg update -y && pkg upgrade -y
pkg install -y python git cmake clang wget

# ── 2. Pick a model sized to the phone's RAM ────────────────────────────────
TOTAL_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
TOTAL_GB=$(( TOTAL_KB / 1024 / 1024 ))
say "Detected ~${TOTAL_GB} GB RAM."

# Q4_K_M GGUFs — the quality/speed sweet spot on CPU.
if   [ "$TOTAL_GB" -lt 4 ]; then
  MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"
  MODEL_FILE="qwen2.5-0.5b-instruct-q4_k_m.gguf"
elif [ "$TOTAL_GB" -lt 6 ]; then
  MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
  MODEL_FILE="qwen2.5-1.5b-instruct-q4_k_m.gguf"
else
  MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
  MODEL_FILE="qwen2.5-3b-instruct-q4_k_m.gguf"
fi
say "Selected model: ${MODEL_FILE}"

MODEL_DIR="$HOME/pip-models"
mkdir -p "$MODEL_DIR"
if [ ! -f "$MODEL_DIR/$MODEL_FILE" ]; then
  say "Downloading model (one time)…"
  wget -O "$MODEL_DIR/$MODEL_FILE" "$MODEL_URL"
else
  say "Model already present — skipping download."
fi

# ── 3. Build llama.cpp (provides the OpenAI-compatible llama-server) ────────
LLAMA_DIR="$HOME/llama.cpp"
if [ ! -d "$LLAMA_DIR" ]; then
  say "Cloning and building llama.cpp…"
  git clone --depth 1 https://github.com/ggerganov/llama.cpp "$LLAMA_DIR"
  ( cd "$LLAMA_DIR" && cmake -B build && cmake --build build --config Release -j"$(nproc)" )
else
  say "llama.cpp already built — skipping."
fi

SERVER_BIN="$LLAMA_DIR/build/bin/llama-server"
[ -x "$SERVER_BIN" ] || SERVER_BIN="$LLAMA_DIR/build/bin/server"

# ── 4. Start script + Pip env wiring ────────────────────────────────────────
START="$HOME/start-pip-brain.sh"
cat > "$START" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
# Start the local model server (OpenAI-compatible API on :8080), then Pip.
"$SERVER_BIN" -m "$MODEL_DIR/$MODEL_FILE" --host 127.0.0.1 --port 8080 &
sleep 4
export PIP_LLM_BACKEND=openai_compat
export PIP_LLM_BASE_URL=http://127.0.0.1:8080/v1
export PIP_LLM_MODEL=local
echo "Pip's local brain is live at http://127.0.0.1:8080/v1"
echo "Now run Pip, e.g.:  python -m pip_v0.pip_control_panel"
EOF
chmod +x "$START"

say "Done. Start everything with:  bash ~/start-pip-brain.sh"
say "Pip will use the on-phone model automatically — fully offline, no API keys."
