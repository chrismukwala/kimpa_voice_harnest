# Environment Setup

## Prerequisites

| Dependency | Required Version | Install |
|---|---|---|
| Python | 3.11.x (NOT 3.12+) | [python.org](https://www.python.org/downloads/release/python-31111/) |
| CUDA Toolkit | 12.1+ | [nvidia.com](https://developer.nvidia.com/cuda-downloads) |
| Ollama | ≤0.19.x (avoid 0.20.x VRAM regression) | [ollama.com](https://ollama.com/download) |
| espeak-ng | Latest | [github.com/espeak-ng](https://github.com/espeak-ng/espeak-ng/releases) — add to PATH |
| Git | Any recent | [git-scm.com](https://git-scm.com/download/win) |
| Node.js/npm | Any (dev tooling only) | Only needed if re-downloading Monaco |

## First-Time Setup

```bash
# 1. Clone the repo
git clone <repo_url>
cd voice_harnest

# 2. Run the install wizard (creates venv, installs everything in correct order)
python setup/install.py
```

The wizard performs these steps in order:
1. Assert Python 3.11.x — aborts if version mismatch
2. Assert `nvcc`, Ollama, espeak-ng on PATH
3. Create `.venv` and activate
4. Install CUDA PyTorch FIRST: `pip install torch==2.3.0+cu121 torchaudio --extra-index-url https://download.pytorch.org/whl/cu121`
5. Pin `ctranslate2==4.4.0` (before RealtimeSTT)
6. Install `requirements.txt`
7. Pull Ollama model: `ollama pull qwen2.5-coder:14b` (~8GB download)
8. Validation suite: torch CUDA check, import all key modules, synthesize 1 word, transcribe 1s silence, Ollama connectivity

## Running the App

```bash
# Activate venv first
.venv\Scripts\activate    # Windows
source .venv/bin/activate # Linux/Mac

# Start Ollama (if not already running as a service)
ollama serve

# Run
python main.py
```

## Known Issues & Workarounds

### Razer Blade 16 dual-GPU (Intel iGPU + RTX 4080 Optimus)

**Problem**: `Failed to create shared context for virtualization` — Chromium GPU process crashes when QWebEngineView tries to use the Intel iGPU instead of the NVIDIA GPU.

**Solution** (both required):
1. **Windows Graphics Settings**: Settings → Display → Graphics → Add `python.exe` → set to "High Performance (NVIDIA)"
2. **Chromium flag**: Set `QTWEBENGINE_CHROMIUM_FLAGS="--in-process-gpu"` before any Qt imports. This is done in `main.py`.

**Flags that DON'T work**: `--disable-gpu`, `--disable-gpu-compositing`, `--use-gl=swiftshader`, `--no-sandbox`

### QtWebEngine sandbox

**Problem**: QtWebEngine sandbox fails on some Windows configurations.

**Solution**: Set `QTWEBENGINE_DISABLE_SANDBOX=1` before any Qt imports. Already done in `main.py`.

### KMP duplicate library

**Problem**: `OMP: Error #15: Initializing libiomp5md.dll, but found libiomp5md.dll already initialized` — multiple copies of OpenMP loaded by torch + other deps.

**Solution**: Set `KMP_DUPLICATE_LIB_OK=TRUE` before imports. Already done in `main.py`.

### Monaco Web Workers

**Problem**: Monaco's language services use Web Workers, which are blocked by `file://` same-origin policy.

**Solution**: Serve Monaco via localhost HTTP server, NOT `file://`. The asset server binds to `127.0.0.1:<random_port>` in a daemon thread.

### CPU-only PyTorch

**Problem**: If `pip install -r requirements.txt` runs before CUDA PyTorch is installed, pip resolves `torch` as CPU-only.

**Solution**: Always install PyTorch from CUDA index URL FIRST: `pip install torch==2.3.0+cu121 --extra-index-url https://download.pytorch.org/whl/cu121`. The install wizard handles this.

### ctranslate2 version conflict

**Problem**: ctranslate2 ≥4.5.0 requires cuDNN 9.2, which conflicts with the RTX 4080 laptop CUDA setup.

**Solution**: Pin `ctranslate2==4.4.0`. Install it before RealtimeSTT to prevent RealtimeSTT from pulling a newer version.

## Dev Tools

### Audio smoke test

Use the full application environment for audio diagnostics. `.venv-poc` is only for the Monaco
POC and may not include audio dependencies such as `sounddevice`.

```bash
# Activate the full app environment first
.venv\Scripts\activate

# List output devices without attempting playback
python tools/test_audio.py --list-only

# Run the sine-wave probe and Kokoro probe on the default output device
python tools/test_audio.py

# Target a specific output device index if needed
python tools/test_audio.py --device 3
```

The tool warns if it is run outside Python 3.11.x because the real audio stack is only supported
there.
The `--device` index matches the value consumed by `TtsNavigator.set_output_device()` in the app.

### Microphone smoke test

Use the full application environment for microphone diagnostics as well.

```bash
# Activate the full app environment first
.venv\Scripts\activate

# List input devices without recording
python tools/test_mic.py --list-only

# Record a short sample and print amplitude stats
python tools/test_mic.py

# Target a specific microphone and attempt one RealtimeSTT transcription
python tools/test_mic.py --device 2 --transcribe
```

The `--device` index matches the value consumed by the coordinator-owned microphone
configuration path.

### Phase 0 POC (standalone Monaco test)

```bash
# Uses .venv-poc (PyQt6 only, no voice/LLM deps)
.venv-poc\Scripts\activate
python phase0_poc/monaco_poc.py
```

Expected output: "PASS — ROUND-TRIP OK" in both the console and the window status bar.
