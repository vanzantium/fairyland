# Running Pip On a Phone (Termux)

Pip does not need a laptop. On Android, the phone can be her *whole brain*: a
small local model served over an OpenAI-compatible API, with Pip's package
pointed at it. Everything stays on the device — offline, private, no paid API.

This is the "works with whatever they have" path: if all someone owns is a
phone, that's enough.

> Approach inspired by [orailnoor/termux-llm](https://github.com/orailnoor/termux-llm)
> and [DroidDesk](https://github.com/orailnoor/DroidDesk): llama.cpp in Termux,
> no root, one command.

## One-command install

1. Install **Termux** (from F-Droid, not the outdated Play Store build).
2. Get Pip's files onto the phone (`git clone` your repo, or copy `pip_v0/`).
3. Run:

   ```bash
   bash pip_v0/install_termux.sh
   ```

   This updates packages, picks a model sized to your phone's RAM (Q4_K_M
   quantization), downloads it once, builds `llama.cpp`, and writes a
   `~/start-pip-brain.sh` launcher.

4. Start everything:

   ```bash
   bash ~/start-pip-brain.sh
   ```

   The local model comes up at `http://127.0.0.1:8080/v1` and Pip's env is
   wired to use it. Then run Pip, e.g. `python -m pip_v0.pip_control_panel`.

## How Pip finds the model

Pip's inference layer is **backend-agnostic** — it speaks the OpenAI
`/v1/chat/completions` shape. The installer sets three env vars:

| Variable             | Value                          | Meaning                          |
|----------------------|--------------------------------|----------------------------------|
| `PIP_LLM_BACKEND`    | `openai_compat`                | use the universal adapter        |
| `PIP_LLM_BASE_URL`   | `http://127.0.0.1:8080/v1`     | the local llama-server           |
| `PIP_LLM_MODEL`      | `local`                        | model label (llama-server is single-model) |

Because it is OpenAI-compatible, the *exact same* setup works on a laptop with
**Ollama** (`http://127.0.0.1:11434/v1`), **LM Studio**, or **Jan** — just
point `PIP_LLM_BASE_URL` at whichever is running. No code changes.

## RAM tiers (what the installer picks)

| Phone RAM | Model            | Params  |
|-----------|------------------|---------|
| < 4 GB    | Qwen2.5 0.5B     | up to 1B |
| 4–6 GB    | Qwen2.5 1.5B     | up to 2B |
| 6 GB+     | Qwen2.5 3B       | up to 3B |

All Q4_K_M. Expect ~2–6 tokens/sec on a phone CPU. Pip is built for this:
the strategy memory and BES decomposition mean a tiny model still produces
useful work by *asking better*, not by being huge.

## Fallback behavior

If no local model is running, Pip's inference router (`pip_inference.py`)
degrades gracefully:

1. **Local** model (preferred — free, private, offline)
2. **Text bridge** — type into an external tool, harvest via clipboard
   (only if the security sentinel posture is CALM/WATCH)
3. **Cloud** — opt-in only (`llm.allow_cloud = true`); never called silently
4. **Heuristics** — Pip still functions, just without a model

## Privacy

- The model and all memory live on the phone. Nothing is uploaded.
- The security sentinel's behavioral fingerprint never leaves the device.
- No raw activity logs — only compressed statistics.
