"""
Voice Harness — Installation Wizard
=====================================
Run this ONCE before any other step.

Steps (in required order):
  1.  Pre-flight: Python 3.11.x, git, espeak-ng, nvcc
  2.  Create .venv
  3.  Install CUDA PyTorch FIRST (before anything else touches torch)
  4.  Pin ctranslate2==4.4.0
  5.  Install all other requirements
  6.  Validation suite — prints ✓/✗ per component

Usage:
    python setup/install.py
"""

import subprocess
import sys
import os
import shutil
import pathlib
import argparse
import platform

ROOT = pathlib.Path(__file__).parent.parent
VENV_DIR = ROOT / ".venv"

# ------------------------------------------------------------------ colours
GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW= "\033[93m"
BOLD  = "\033[1m"
RESET = "\033[0m"

def ok(msg):  print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"  {RED}✗{RESET} {msg}")
def warn(msg): print(f"  {YELLOW}!{RESET} {msg}")
def header(msg): print(f"\n{BOLD}{msg}{RESET}")


# ------------------------------------------------------------------ helpers
def run(cmd, check=True, capture=False, **kwargs):
    if capture:
        return subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    return subprocess.run(cmd, check=check, **kwargs)


def venv_python():
    """Return path to the venv python executable."""
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def venv_pip():
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"


# ------------------------------------------------------------------ steps
def step_preflight():
    header("Step 1 — Pre-flight checks")
    passed = True

    # Python version
    vi = sys.version_info
    if vi.major == 3 and vi.minor == 11:
        ok(f"Python {vi.major}.{vi.minor}.{vi.micro}")
    else:
        fail(
            f"Python {vi.major}.{vi.minor}.{vi.micro} — REQUIRES Python 3.11.x\n"
            f"    Download: https://www.python.org/downloads/release/python-31111/\n"
            f"    3.12+ breaks webrtcvad wheels and OpenWakeWord on Windows."
        )
        passed = False

    # git
    if shutil.which("git"):
        r = run(["git", "--version"], capture=True)
        ok(r.stdout.strip())
    else:
        fail(
            "git not found — install from https://git-scm.com/download/win\n"
            "    Required for gitpython auto-commit feature."
        )
        passed = False

    # espeak-ng (required by Kokoro TTS on Windows)
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        ok("espeak-ng found in PATH")
    else:
        fail(
            "espeak-ng not found — Kokoro TTS will crash without it.\n"
            "    Install: https://github.com/espeak-ng/espeak-ng/releases\n"
            "    After install, add its bin/ folder to your system PATH."
        )
        passed = False

    # nvcc (CUDA toolkit)
    if shutil.which("nvcc"):
        r = run(["nvcc", "--version"], capture=True)
        # grab the release line
        for line in r.stdout.splitlines():
            if "release" in line.lower():
                ok(f"CUDA: {line.strip()}")
                break
    else:
        warn(
            "nvcc not found — CUDA Toolkit may not be installed.\n"
            "    Install CUDA 12.1: https://developer.nvidia.com/cuda-12-1-0-download-archive\n"
            "    Install cuDNN 8.9:  https://developer.nvidia.com/cudnn (requires NVIDIA account)\n"
            "    Continuing — but GPU acceleration will not work until CUDA is installed."
        )
        # Not a hard block — we warn but continue

    if not passed:
        print(f"\n{RED}{BOLD}Pre-flight failed. Fix the issues above and re-run.{RESET}")
        sys.exit(1)

    ok("All hard pre-flight checks passed.")


def step_venv():
    header("Step 2 — Virtual environment")
    if VENV_DIR.exists():
        warn(f".venv already exists at {VENV_DIR} — skipping creation")
    else:
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
        ok(f".venv created at {VENV_DIR}")
    ok(f"Using: {venv_python()}")


def step_pytorch():
    header("Step 3 — CUDA PyTorch (must be installed before RealtimeSTT)")
    print("    Installing torch==2.3.0+cu121 and torchaudio — this may take a few minutes...")
    run([
        str(venv_pip()), "install",
        "torch==2.3.0+cu121",
        "torchaudio==2.3.0+cu121",
        "--extra-index-url", "https://download.pytorch.org/whl/cu121",
        "--quiet",
    ])
    ok("torch 2.3.0+cu121 installed")


def step_ctranslate2():
    header("Step 4 — Pin ctranslate2==4.4.0")
    print("    (>=4.5.0 needs cuDNN 9.2 which conflicts with RTX 4080 setup)")
    run([str(venv_pip()), "install", "ctranslate2==4.4.0", "--quiet"])
    ok("ctranslate2==4.4.0 installed")


def step_requirements():
    header("Step 5 — Installing requirements.txt")
    req_path = ROOT / "requirements.txt"
    run([str(venv_pip()), "install", "-r", str(req_path)])
    ok("requirements.txt installed")


def step_validate():
    header("Step 6 — Validation suite")
    py = str(venv_python())
    results = []

    checks = [
        ("torch (CUDA)", "import torch; assert torch.cuda.is_available(), 'CUDA not available'"),
        ("PyQt6",        "import PyQt6.QtWidgets"),
        ("PyQt6-WebEngine", "import PyQt6.QtWebEngineWidgets"),
        ("PyQt6-WebChannel", "import PyQt6.QtWebChannel"),
        ("RealtimeSTT",  "import RealtimeSTT"),
        ("kokoro",       "import kokoro"),
        ("openai",       "import openai"),
        ("gitpython",    "import git"),
        ("openwakeword", "import openwakeword"),
    ]

    for name, code in checks:
        r = run([py, "-c", code], check=False, capture=True)
        if r.returncode == 0:
            ok(name)
            results.append((name, True))
        else:
            fail(f"{name} — {r.stderr.strip()[:120]}")
            results.append((name, False))

    # espeak-ng runtime check
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        ok("espeak-ng in PATH (Kokoro TTS will work)")
        results.append(("espeak-ng", True))
    else:
        fail("espeak-ng not in PATH — Kokoro TTS will fail at runtime")
        results.append(("espeak-ng", False))

    # Summary
    passed = sum(1 for _, v in results if v)
    total  = len(results)
    header(f"Validation complete: {passed}/{total} passed")
    if passed == total:
        print(f"\n{GREEN}{BOLD}All checks passed. Voice Harness is ready to run.{RESET}")
        print(f"\n  Activate the environment:  .venv\\Scripts\\activate")
        print(f"  Run Phase 0 POC:           python phase0_poc\\monaco_poc.py")
    else:
        print(f"\n{YELLOW}{BOLD}Some checks failed — see above. Fix them before running.{RESET}")


# ------------------------------------------------------------------ main
def main():
    parser = argparse.ArgumentParser(description="Voice Harness setup wizard")
    args = parser.parse_args()

    print(f"\n{BOLD}Voice Harness — Installation Wizard{RESET}")
    print(f"Root: {ROOT}\n")

    # Must not be run inside a venv already
    if sys.prefix != sys.base_prefix:
        warn("You appear to already be inside a virtual environment. This wizard creates its own .venv.")
        answer = input("  Continue anyway? [y/N] ").strip().lower()
        if answer != "y":
            sys.exit(0)

    step_preflight()
    step_venv()
    step_pytorch()
    step_ctranslate2()
    step_requirements()
    step_validate()


if __name__ == "__main__":
    main()
