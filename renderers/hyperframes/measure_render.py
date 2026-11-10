"""Measure this standalone PoC's local render; never import the Shorts pipeline."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
RENDERER = ROOT / "renderers" / "hyperframes"
TOOLS = ROOT / ".tools" / "hyperframes"
OUTPUT = ROOT / "output" / "hyperframes-poc-20261108"


def disk_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0


class ProcessEntry(ctypes.Structure):
    _fields_ = [("size", wt.DWORD), ("usage", wt.DWORD), ("pid", wt.DWORD),
                ("heap", ctypes.c_size_t), ("module", wt.DWORD), ("threads", wt.DWORD),
                ("parent", wt.DWORD), ("priority", wt.LONG), ("flags", wt.DWORD),
                ("exe", wt.WCHAR * 260)]


class MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD)] + [
        (name, ctypes.c_size_t) for name in ["PeakWorkingSetSize", "WorkingSetSize",
        "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
        "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage"]]


def memory_tree(root_pid: int) -> dict:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wt.HANDLE
    kernel.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel.OpenProcess.restype = wt.HANDLE
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(MemoryCounters), wt.DWORD]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    entry = ProcessEntry(); entry.size = ctypes.sizeof(entry)
    parents = {}
    ok = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
    while ok:
        parents[entry.pid] = entry.parent
        ok = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    kernel.CloseHandle(snapshot)
    pids = {root_pid}
    for _ in range(12):
        added = {pid for pid, parent in parents.items() if parent in pids}
        if added <= pids:
            break
        pids |= added
    working = private = readable = 0
    for pid in pids:
        handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
        if not handle:
            continue
        info = MemoryCounters(); info.cb = ctypes.sizeof(info)
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(info), info.cb):
            working += info.WorkingSetSize; private += info.PrivateUsage; readable += 1
        kernel.CloseHandle(handle)
    return {"working_set_bytes": working, "private_bytes": private,
            "processes": len(pids), "readable_processes": readable}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    temp = TOOLS / "tmp"; temp.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({"PATH": str(TOOLS) + os.pathsep + env["PATH"],
                "TEMP": str(temp), "TMP": str(temp),
                "HYPERFRAMES_CACHE_DIR": str(TOOLS / "cache"),
                "HYPERFRAMES_CONFIG_DIR": str(TOOLS / "config"),
                "HYPERFRAMES_EXTRACT_CACHE_DIR": str(TOOLS / "cache" / "extracted"),
                "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1",
                "HYPERFRAMES_SKIP_SKILLS": "1"})
    command = [str(TOOLS / "node.exe"),
               str(RENDERER / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"),
               "render", "poc", "--fps", "30", "--quality", "delivery",
               "--workers", "2", "--strict", "--output", str(OUTPUT / "hyperframes-poc-10s.mp4")]
    before = disk_bytes(TOOLS) + disk_bytes(RENDERER) + disk_bytes(OUTPUT)
    free_before = shutil.disk_usage(ROOT).free
    start = time.perf_counter()
    samples = []
    peak_disk = before
    next_disk_sample = 0.0
    with (OUTPUT / "render.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=RENDERER, env=env, stdout=log, stderr=subprocess.STDOUT)
        print(f"Rendering pid={process.pid}, workers=2", flush=True)
        while process.poll() is None:
            sample = memory_tree(process.pid)
            sample["elapsed_seconds"] = round(time.perf_counter() - start, 3)
            samples.append(sample)
            if sample["elapsed_seconds"] >= next_disk_sample:
                peak_disk = max(peak_disk, disk_bytes(TOOLS) + disk_bytes(RENDERER) + disk_bytes(OUTPUT))
                next_disk_sample += 1.0
            time.sleep(0.2)
        code = process.wait()
    elapsed = time.perf_counter() - start
    gaps = [b["elapsed_seconds"] - a["elapsed_seconds"] for a, b in zip(samples, samples[1:])]
    result = {"exit_code": code, "elapsed_seconds": round(elapsed, 3), "workers": 2,
              "memory_sample_sleep_seconds": 0.2, "memory_sample_count": len(samples),
              "observed_mean_sample_interval_seconds": round(sum(gaps) / len(gaps), 3) if gaps else None,
              "peak_tree_working_set_bytes": max((s["working_set_bytes"] for s in samples), default=0),
              "peak_tree_private_bytes": max((s["private_bytes"] for s in samples), default=0),
              "peak_process_count": max((s["processes"] for s in samples), default=0),
              "memory_note": "Sampled sum of the renderer process and its descendants; shared pages may be counted in multiple working sets.",
              "workspace_bytes_before": before, "peak_workspace_bytes_observed": peak_disk,
              "disk_free_before_bytes": free_before, "disk_free_after_bytes": shutil.disk_usage(ROOT).free,
              "disk_note": "Logical file sizes in dedicated tools, renderer and output; disk sampled every second, not allocated clusters.",
              "command": command}
    movie = OUTPUT / "hyperframes-poc-10s.mp4"
    if movie.exists():
        result.update({"video_bytes": movie.stat().st_size,
                       "video_sha256": hashlib.sha256(movie.read_bytes()).hexdigest()})
    (OUTPUT / "render-metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT / "memory-samples.json").write_text(json.dumps(samples), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if code:
        print((OUTPUT / "render.log").read_text(encoding="utf-8", errors="replace")[-6000:])
    raise SystemExit(code)


if __name__ == "__main__":
    main()
