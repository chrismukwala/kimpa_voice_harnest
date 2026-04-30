# Environment Setup

## Prerequisites

| Dependency | Required Version | Install |
|---|---|---|
| Python | 3.11.x (NOT 3.12+) | [python.org](https://www.python.org/downloads/release/python-31111/) |
| CUDA Toolkit | 12.1+ | [nvidia.com](https://developer.nvidia.com/cuda-downloads) |
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
2. Assert `nvcc`, git, and espeak-ng on PATH
3. Create `.venv` and activate
4. Install CUDA PyTorch FIRST: `pip install torch==2.3.0+cu121 torchaudio --extra-index-url https://download.pytorch.org/whl/cu121`
5. Pin `ctranslate2==4.4.0` before installing faster-whisper
6. Install `requirements.txt`
7. Validation suite: torch CUDA check, import key modules, synthesize 1 word, and run audio diagnostics manually as needed

Note: after the Phase 5 STT rewrite, the installer validation should be checked against the
current dependency list before treating a fresh install as fully verified.

## Git hooks (Phase H1)

After the venv is set up, install the local pre-commit / pre-push hooks:

```bash
python scripts/install_hooks.py
```

This wires `.git/hooks/pre-commit` and `.git/hooks/pre-push` to:

- **pre-commit** — secret scan, forbidden-pattern scan, file-size limits, and
  `pytest tests/ -q` (skipped via `.test-passed` cache when nothing changed).
- **pre-push** — full `pytest tests/ -v` and `pip-audit -r requirements.txt`
  (audit is warn-only).

Re-run `python scripts/install_hooks.py` any time the wrapper logic changes.
The cache file `.test-passed` is gitignored.

## Running the App

```bash
# Activate venv first
.venv\Scripts\activate    # Windows
source .venv/bin/activate # Linux/Mac

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

**Solution**: Pin `ctranslate2==4.4.0` before installing faster-whisper and the rest of the audio stack.

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

# Target a specific microphone and attempt one faster-whisper transcription
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
