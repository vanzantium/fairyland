import ctypes
import os
import platform
import subprocess
import json
from pathlib import Path
from . import pip_config
from . import pip_platform

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_uint),
        ("dwMemoryLoad", ctypes.c_uint),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]

def get_ram_gb() -> float:
    if not pip_platform.is_windows():
        try:
            if hasattr(os, "sysconf"):
                pages = os.sysconf("SC_PHYS_PAGES")
                page_size = os.sysconf("SC_PAGE_SIZE")
                return (pages * page_size) / (1024**3)
        except Exception:
            pass
        if pip_platform.is_macos():
            try:
                output = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
                return int(output) / (1024**3)
            except Exception:
                pass
        return 0.0

    try:
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat.ullTotalPhys / (1024**3)
    except Exception:
        return 0.0

def get_cpu_name() -> str:
    if pip_platform.is_macos():
        try:
            return subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
        except Exception:
            return platform.processor() or "Unknown CPU"
    if pip_platform.is_linux():
        try:
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return platform.processor() or "Unknown CPU"

    try:
        cpu_info = subprocess.check_output(
            "wmic cpu get Name",
            shell=True,
            text=True,
            **pip_platform.hidden_subprocess_kwargs(),
        )
        lines = [l.strip() for l in cpu_info.split('\n') if l.strip() and 'Name' not in l]
        if lines:
            return lines[0]
    except Exception:
        pass
    return "Unknown CPU"

def get_gpu_info() -> str:
    if pip_platform.is_macos():
        try:
            output = subprocess.check_output(["system_profiler", "SPDisplaysDataType"], text=True, timeout=10)
            for line in output.splitlines():
                if "Chipset Model:" in line:
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return "Unknown GPU"
    if pip_platform.is_linux():
        try:
            output = subprocess.check_output(["lspci"], text=True, timeout=5)
            for line in output.splitlines():
                if any(token in line.lower() for token in ["vga", "3d controller", "display controller"]):
                    return line.strip()
        except Exception:
            pass
        return "Unknown GPU"

    try:
        gpu_info = subprocess.check_output(
            "wmic path win32_VideoController get name,AdapterRAM",
            shell=True,
            text=True,
            **pip_platform.hidden_subprocess_kwargs(),
        )
        names = []
        for line in gpu_info.split('\n'):
            if line.strip() and 'AdapterRAM' not in line:
                names.append(line.strip())
        if names:
            return names[0]
    except Exception:
        pass
    return "Unknown GPU"

def get_ollama_recommendation(ram_gb: float, is_phone: bool = False) -> dict:
    """
    Recommend a local model sized to available RAM.

    Tiers follow the practical RAM->parameter mapping proven by phone-side
    llama.cpp setups (see orailnoor/termux-llm): every byte counts on small
    devices. Q4_K_M quantization is named explicitly because it is the
    quality/speed sweet spot for CPU inference on phones and light laptops.
    The endpoint is OpenAI-compatible, so the same recommendation works for
    llama.cpp's llama-server, LM Studio, Jan, or Ollama.
    """
    quant = "Q4_K_M"

    if ram_gb <= 0:
        # RAM probe failed (often a locked-down phone/Termux). Stay safe.
        return {
            "model": "qwen2.5:0.5b",
            "param_size": "0.5B-1B",
            "quantization": quant,
            "tier": "Unknown / phone-safe",
            "runtime": "llama.cpp (CPU) via OpenAI-compatible /v1",
            "reason": "Could not read system RAM (common on phones/Termux). Defaulting to a sub-1B model so Pip never stalls the device.",
            "prompt_strategy": "Strict 1-step extraction prompts with <thought> scratchpads to keep a tiny model honest.",
        }

    # Granular tiers — phones live in the bottom three.
    if ram_gb < 4.0:
        tier = {
            "model": "qwen2.5:0.5b or tinyllama",
            "param_size": "up to 1B",
            "tier": "Micro",
            "reason": f"Only {ram_gb:.1f} GB RAM. Stay at/under 1B params so the device keeps breathing while Pip works.",
            "prompt_strategy": "Single-step extraction prompts, grammar-constrained JSON, no multi-hop reasoning.",
        }
    elif ram_gb < 6.0:
        tier = {
            "model": "gemma2:2b or qwen2.5:1.5b",
            "param_size": "up to 2B",
            "tier": "Ultra-light",
            "reason": f"{ram_gb:.1f} GB RAM comfortably runs a 2B model alongside other apps.",
            "prompt_strategy": "Short persona + grammar-constrained outputs; lean on Pip's strategy memory to ask well.",
        }
    elif ram_gb < 8.0:
        tier = {
            "model": "llama3.2:3b or phi3:mini",
            "param_size": "up to 3B",
            "tier": "Light",
            "reason": f"{ram_gb:.1f} GB RAM handles a 3B model — a good local default for chat + decomposition.",
            "prompt_strategy": "Decompose-then-answer; verify against checkable subgoals (BES loop).",
        }
    elif ram_gb < 16.0:
        tier = {
            "model": "phi3:mini, llama3.2:3b, or qwen2.5:7b",
            "param_size": "3B-7B",
            "tier": "Balanced",
            "reason": f"With {ram_gb:.1f} GB you can run optimized mid-tier models locally without slowing other apps.",
            "prompt_strategy": "Maintain strict persona; grammar-constrained generation for guaranteed JSON.",
        }
    else:
        tier = {
            "model": "llama3:8b or mistral",
            "param_size": "8B+",
            "tier": "Performance",
            "reason": f"Ample memory ({ram_gb:.1f} GB) — run powerful 8B models for stronger zero-shot reasoning.",
            "prompt_strategy": "Standard ReAct: large enough for multi-step agentic pipelines in one pass.",
        }

    tier["quantization"] = quant
    tier["runtime"] = "llama.cpp (CPU) via OpenAI-compatible /v1"
    if is_phone:
        tier["tier"] += " (phone)"
        tier["reason"] += " Running on-device via Termux + llama.cpp keeps everything offline and private."
    expected_tps = "2-6 tok/s on phone CPUs, faster on laptops/GPUs"
    tier["expected_speed"] = expected_tps
    return tier

def is_termux_android() -> bool:
    """Detect a Termux/Android environment (phone running Pip's brain on-device)."""
    if os.environ.get("TERMUX_VERSION"):
        return True
    prefix = os.environ.get("PREFIX", "")
    if "com.termux" in prefix:
        return True
    try:
        return Path("/system/build.prop").exists() or Path("/system/bin/getprop").exists()
    except Exception:
        return False


def optimize_system_memory() -> bool:
    if not pip_platform.is_windows():
        print("Memory optimization is currently Windows-only.")
        return False

    ps_script = """
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Diagnostics;
public class RamOptimizer {
    [DllImport("psapi.dll")]
    static extern int EmptyWorkingSet(IntPtr hwProc);
    public static void EmptyAll() {
        foreach (Process process in Process.GetProcesses()) {
            try { EmptyWorkingSet(process.Handle); } catch {}
        }
    }
}
"@ -Language CSharp
[RamOptimizer]::EmptyAll()
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            check=True,
            **pip_platform.hidden_subprocess_kwargs(),
        )
        return True
    except Exception as e:
        print(f"Memory optimization failed: {e}")
        return False

def scan_and_save(optimize: bool = False) -> dict:
    """Run hardware scan and save results to memory path.

    Memory optimization is intentionally opt-in because it touches every
    process working set and should not happen during a simple status scan.
    """
    optimized = optimize_system_memory() if optimize else False
    ram = get_ram_gb()
    phone = is_termux_android()

    report = {
        "cpu": get_cpu_name(),
        "gpu": get_gpu_info(),
        "ram_gb": round(ram, 1),
        "os": "Android (Termux)" if phone else (platform.system() or "Unknown"),
        "is_phone": phone,
        "memory_optimized": optimized,
        "memory_optimization_requested": optimize,
        "recommendation": get_ollama_recommendation(ram, is_phone=phone)
    }
    
    memory_path = pip_config.get_memory_path()
    hw_file = memory_path / "hardware.json"
    
    try:
        with open(hw_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    except Exception as e:
        print(f"Failed to save hardware report: {e}")
        
    return report

if __name__ == "__main__":
    scan_and_save(optimize=False)
