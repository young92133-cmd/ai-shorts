"""Run the existing rerender CLI sequentially, with process-tree CPU/memory samples.

Uses only a previously cloned project. No make, research, AI or TTS is invoked.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes as wt
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "renderers/hyperframes"))
# Reuse the successful PoC's Windows structures without changing that source.
from measure_render import ProcessEntry, MemoryCounters


def owned_instances(records: dict, root_pid: int) -> dict:
    """Reject stale Windows parent IDs after PID reuse, using creation clocks."""
    if root_pid not in records:
        return {}
    owned = {root_pid: records[root_pid]}
    for _ in range(16):
        added = {pid:record for pid,record in records.items()
                 if record['parent'] in owned and record['created'] >= owned[record['parent']]['created']}
        if added.keys() <= owned.keys():
            break
        owned.update(added)
    return owned


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in
                ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]


def sample_tree(root_pid: int, *, details: bool = False) -> tuple[dict, dict[tuple[int, int], float]]:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wt.HANDLE
    kernel.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel.OpenProcess.restype = wt.HANDLE
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    kernel.GetProcessTimes.argtypes = [wt.HANDLE, *([ctypes.POINTER(wt.FILETIME)] * 4)]
    kernel.GetProcessIoCounters.argtypes = [wt.HANDLE, ctypes.POINTER(IoCounters)]
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(MemoryCounters), wt.DWORD]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    entry = ProcessEntry(); entry.size = ctypes.sizeof(entry)
    parents, names = {}, {}
    found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
    while found:
        parents[entry.pid] = entry.parent
        names[entry.pid] = entry.exe
        found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    kernel.CloseHandle(snapshot)
    pids = {root_pid}
    for _ in range(16):
        added = {pid for pid, parent in parents.items() if parent in pids}
        if added <= pids:
            break
        pids |= added
    records = {}
    for pid in pids:
        handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
        if not handle:
            continue
        info = MemoryCounters(); info.cb = ctypes.sizeof(info)
        memory_ok = bool(psapi.GetProcessMemoryInfo(handle, ctypes.byref(info), info.cb))
        created, exited, system, user = (wt.FILETIME() for _ in range(4))
        io = IoCounters()
        io_ok = details and bool(kernel.GetProcessIoCounters(handle, ctypes.byref(io)))
        if kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(system), ctypes.byref(user)):
            records[pid] = {'parent':parents.get(pid), 'created':(created.dwHighDateTime << 32) + created.dwLowDateTime,
                            'cpu':((system.dwHighDateTime << 32) + system.dwLowDateTime
                                   + (user.dwHighDateTime << 32) + user.dwLowDateTime) / 10_000_000,
                            'working':info.WorkingSetSize if memory_ok else 0,
                            'private':info.PrivateUsage if memory_ok else 0,'readable':int(memory_ok),
                            'name':names.get(pid,''),
                            'io':{key:getattr(io,key) for key,_ in io._fields_} if io_ok else None}
        kernel.CloseHandle(handle)
    owned=owned_instances(records,root_pid)
    working=sum(r['working'] for r in owned.values());private=sum(r['private'] for r in owned.values())
    readable=sum(r['readable'] for r in owned.values())
    cpu={(pid,r['created']):r['cpu'] for pid,r in owned.items()}
    sample={"working_set_bytes": working, "private_bytes": private,
            "processes": len(owned), "readable_processes": readable}
    if details:
        sample['instances']=[dict(pid=pid,**record) for pid,record in owned.items()]
    return sample, cpu


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--renderer", choices=("ffmpeg", "hyperframes"), required=True)
    parser.add_argument("--project", default="20261109_hf_comparison")
    parser.add_argument("--report", default="output/hyperframes-comparison-20261109")
    args = parser.parse_args()
    report = ROOT / args.report
    report.mkdir(parents=True, exist_ok=True)
    result_file = report / f"{args.renderer}-result.json"
    if result_file.exists():
        raise FileExistsError(f"Preserve the existing comparison before repeating it: {result_file}")
    stem = args.renderer + "-" + time.strftime("%H%M%S")
    stdout, stderr = report / f"{stem}.stdout.json", report / f"{stem}.stderr.log"
    command = [sys.executable, "-B", "-m", "app.factory", "rerender", args.project,
               "--renderer", args.renderer, "--renderer-fallback", "none"]
    samples, seen_cpu = [], {}
    begin = time.perf_counter()
    print(f"Rendering {args.renderer} from saved content; AI/TTS disabled by rerender path", flush=True)
    with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
        process = subprocess.Popen(command, cwd=ROOT, stdout=out, stderr=err,
                                   env={**os.environ, "PYTHONIOENCODING":"utf-8", "PYTHONDONTWRITEBYTECODE":"1"})
        while process.poll() is None:
            sample, cpu = sample_tree(process.pid)
            for pid, elapsed in cpu.items():
                seen_cpu[pid] = max(seen_cpu.get(pid, 0), elapsed)
            sample.update(elapsed_seconds=round(time.perf_counter()-begin,3), cpu_seconds_observed=sum(seen_cpu.values()))
            samples.append(sample)
            time.sleep(0.2)
        code = process.wait()
    wall = time.perf_counter() - begin
    raw = stdout.read_text(encoding="utf-8")
    result = json.loads(raw) if raw.strip() else {"error":"CLI produced no JSON"}
    cpu_seconds = sum(seen_cpu.values())
    metrics = {"renderer":args.renderer, "exit_code":code, "wall_seconds":round(wall,3),
               "cpu_seconds_observed":round(cpu_seconds,3),
               "average_cpu_percent_one_core":round(cpu_seconds/wall*100,2),
               "average_cpu_percent_machine":round(cpu_seconds/wall*100/(os.cpu_count() or 1),2),
               "logical_processors":os.cpu_count(),
               "peak_tree_working_set_bytes":max((s['working_set_bytes'] for s in samples),default=0),
               "peak_tree_private_bytes":max((s['private_bytes'] for s in samples),default=0),
               "samples":len(samples), "stdout":str(stdout), "stderr":str(stderr),
               "measurement_note":"Process-tree sums with PID+creation-time ancestry filtering (v2); shared working sets may overlap; CPU excludes subprocesses that exit between samples."}
    if result.get("final_video") and code == 0:
        video = Path(result['final_video'])
        metrics.update(video=str(video),video_bytes=video.stat().st_size,
                       render_seconds=result.get('rendering',{}).get('elapsed_seconds'))
        result_file.write_text(json.dumps({"metrics":metrics,"result":result},ensure_ascii=False,indent=2),encoding="utf-8")
    (report / f"{stem}-metrics.json").write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding="utf-8")
    (report / f"{stem}-samples.json").write_text(json.dumps(samples),encoding="utf-8")
    print(json.dumps(metrics,ensure_ascii=False,indent=2))
    if code:
        print(raw)
        print(stderr.read_text(encoding="utf-8",errors="replace")[-3500:])
    raise SystemExit(code)


if __name__ == "__main__":
    main()
