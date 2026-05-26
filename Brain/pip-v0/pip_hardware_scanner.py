import ctypes
import os
import platform
import subprocess
import json
from pathlib import Path
import pip_config
import pip_platform

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

def get_ollama_recommendation(ram_gb: float) -> dict:
    if ram_gb < 8.0:
        return {
            "model": "qwen2:0.5b or gemma:2b",
            "tier": "Ultra-light",
            "reason": f"System RAM is highly constrained ({ram_gb:.1f} GB). To prevent catastrophic system stalls, Pip MUST use an ultra-light sub-3B model. She will utilize Hermes/Pi micro-pipelines and CoT scratchpads to maximize intelligence.",
            "prompt_strategy": "Hermes/Pi Strategy: Use strict 1-step extraction prompts with <thought> blocks to prevent hallucination."
        }
    elif ram_gb < 16.0:
        return {
            "model": "phi3:mini or llama3.2:3b",
            "tier": "Balanced",
            "reason": f"With {ram_gb:.1f} GB of RAM, you can comfortably run highly-optimized mid-tier models (3B-4B) locally without slowing down other apps.",
            "prompt_strategy": "Hermes/Pi Strategy: Maintain strict persona and utilize grammar-constrained generation for guaranteed JSON outputs."
        }
    else:
        return {
            "model": "llama3:8b or mistral",
            "tier": "Performance",
            "reason": f"You have ample memory ({ram_gb:.1f} GB). You can run powerful 8B parameter models for maximum zero-shot reasoning capabilities.",
            "prompt_strategy": "Standard ReAct Strategy: Model is large enough to handle multi-step agentic pipelines in a single pass."
        }

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
    
    report = {
        "cpu": get_cpu_name(),
        "gpu": get_gpu_info(),
        "ram_gb": round(ram, 1),
        "os": platform.system() or "Unknown",
        "memory_optimized": optimized,
        "memory_optimization_requested": optimize,
        "recommendation": get_ollama_recommendation(ram)
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
