"""Sequential, local-only renderer experiments against saved project material.

The child invokes the real rerender CLI. Only explicit experiment settings and
official --debug/--workers/--gpu switches differ; production config is untouched.
"""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes as wt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.compare_renderers import sample_tree


class SystemLoad:
    """System CPU and physical-disk context, not per-render disk attribution."""
    def __init__(self):
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.GetSystemTimes.argtypes=[ctypes.POINTER(wt.FILETIME)]*3
        self.last=None;self.pdh=None;self.query=wt.HANDLE();self.counters={}
        try:
            self.pdh=ctypes.WinDLL('pdh')
            self.pdh.PdhOpenQueryW.argtypes=[wt.LPCWSTR,ctypes.c_size_t,ctypes.POINTER(wt.HANDLE)]
            self.pdh.PdhAddEnglishCounterW.argtypes=[wt.HANDLE,wt.LPCWSTR,ctypes.c_size_t,ctypes.POINTER(wt.HANDLE)]
            self.pdh.PdhCollectQueryData.argtypes=[wt.HANDLE]
            self.pdh.PdhGetFormattedCounterValue.argtypes=[wt.HANDLE,wt.DWORD,ctypes.c_void_p,ctypes.c_void_p]
            self.pdh.PdhCloseQuery.argtypes=[wt.HANDLE]
            if self.pdh.PdhOpenQueryW(None,0,ctypes.byref(self.query))==0:
                for key,name in [('physical_disk_read_bps','Disk Read Bytes/sec'),('physical_disk_write_bps','Disk Write Bytes/sec')]:
                    counter=wt.HANDLE()
                    if self.pdh.PdhAddEnglishCounterW(self.query,'\\PhysicalDisk(_Total)\\'+name,0,ctypes.byref(counter))==0:
                        self.counters[key]=counter
                self.pdh.PdhCollectQueryData(self.query)
        except (OSError,AttributeError):pass

    def sample(self):
        result={};values=[wt.FILETIME() for _ in range(3)]
        if self.kernel.GetSystemTimes(*(ctypes.byref(x) for x in values)):
            idle,kernel,user=[(x.dwHighDateTime<<32)+x.dwLowDateTime for x in values]
            if self.last:
                old_idle,old_total=self.last;delta=kernel+user-old_total
                if delta>0:result['system_cpu_percent']=100*(1-(idle-old_idle)/delta)
            self.last=(idle,kernel+user)
        if self.counters and self.pdh.PdhCollectQueryData(self.query)==0:
            class Value(ctypes.Structure):
                _fields_=[('status',wt.DWORD),('value',ctypes.c_double)]
            for key,counter in self.counters.items():
                value=Value()
                if self.pdh.PdhGetFormattedCounterValue(counter,0x200,None,ctypes.byref(value))==0 and value.status in (0,1):
                    result[key]=value.value
        return result

    def close(self):
        if self.query and self.pdh:self.pdh.PdhCloseQuery(self.query)


def summarize_processes(samples):
    result={}
    for sample in samples:
        for item in sample.get('instances',[]):
            key=f"{item['pid']}:{item['created']}"
            if key not in result:
                result[key]={'pid':item['pid'],'created':item['created'],'name':item['name'],
                             'first_sample_seconds':sample['elapsed_seconds'],'cpu_seconds':0,
                             'peak_working_set_bytes':0,'peak_private_bytes':0,'io':{}}
            record=result[key];record['last_sample_seconds']=sample['elapsed_seconds']
            record['cpu_seconds']=max(record['cpu_seconds'],item['cpu'])
            record['peak_working_set_bytes']=max(record['peak_working_set_bytes'],item['working'])
            record['peak_private_bytes']=max(record['peak_private_bytes'],item['private'])
            for name,value in (item.get('io') or {}).items():record['io'][name]=max(record['io'].get(name,0),value)
    return sorted(result.values(),key=lambda x:x['cpu_seconds'],reverse=True)


def child(args):
    from app.pipeline import hyperframes as hf
    from app.factory.__main__ import main
    execute=hf._execute
    timings={}
    def timed(name,begin):
        timings[name]=round(time.perf_counter()-begin,6)
        (args.report/'adapter-stages.json').write_text(json.dumps(timings,indent=2),encoding='utf-8')
    export_project=hf.export_project
    def exported(*a,**kw):
        begin=time.perf_counter()
        try:return export_project(*a,**kw)
        finally:timed('export_seconds',begin)
    hf.export_project=exported
    prepare=hf.prepare_media
    async def prepared(export,duck_bgm=False):
        begin=time.perf_counter()
        try:await prepare(export,duck_bgm)
        finally:timed('media_prepare_seconds',begin)
    hf.prepare_media=prepared
    probe=hf.probe_video
    async def probed(*a,**kw):
        begin=time.perf_counter()
        try:return await probe(*a,**kw)
        finally:timed('final_probe_seconds',begin)
    hf.probe_video=probed
    def experiment(command,cwd,env,log,timeout,cancelled=None):
        if 'render' in command and str(command[0]).endswith('node.exe'):
            command=list(command)
            env={**env,'PRODUCER_RENDERS_DIR':str(args.report/'diagnostics/renders')}
            if args.rpc_profile:
                command.insert(1,'--import='+(ROOT/'scripts/hyperframes_rpc_profile.mjs').as_uri())
                env['AI_SHORTS_RPC_PROFILE_FILE']=str(args.report/'rpc-profile.json')
            if args.debug:command+=['--debug']
            if args.gpu:command+=['--gpu']
            if args.software_browser:command+=['--no-browser-gpu']
            command[command.index('--workers')+1]=str(args.workers)
            (args.report/'command.json').write_text(json.dumps(command,indent=2),encoding='utf-8')
            (args.report/'generated-project.txt').write_text(str(cwd),encoding='utf-8')
        begin=time.perf_counter()
        try:return execute(command,cwd,env,log,timeout,cancelled)
        finally:timed('render_cli_seconds' if 'render' in command else 'lint_cli_seconds',begin)
    hf._execute=experiment
    return main(['rerender',args.project,'--renderer','hyperframes','--renderer-fallback','none'])


def parent(args):
    report=args.report;report.mkdir(parents=True,exist_ok=False)
    flags=[]
    for flag in ['debug','gpu','software_browser','rpc_profile']:
        if getattr(args,flag):flags+=['--'+flag.replace('_','-')]
    command=[sys.executable,'-B',str(Path(__file__).resolve()),'--child','--project',args.project,
             '--report',str(report),'--workers',str(args.workers),*flags]
    begin=time.perf_counter();samples=[];system=SystemLoad()
    print(f'Experiment {report.name}: workers={args.workers}, debug={args.debug}, GPU encoder={args.gpu}',flush=True)
    try:
        with (report/'stdout.json').open('w',encoding='utf-8') as out,(report/'stderr.log').open('w',encoding='utf-8') as err:
            proc=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1'})
            while proc.poll() is None:
                sample,_=sample_tree(proc.pid,details=True)
                sample.update(elapsed_seconds=round(time.perf_counter()-begin,4),**system.sample())
                samples.append(sample);time.sleep(.2)
            code=proc.wait()
    finally:system.close()
    wall=time.perf_counter()-begin
    (report/'samples.json').write_text(json.dumps(samples),encoding='utf-8')
    processes=summarize_processes(samples)
    (report/'processes.json').write_text(json.dumps(processes,indent=2),encoding='utf-8')
    cpu=sum(p['cpu_seconds'] for p in processes)
    load=[s['system_cpu_percent'] for s in samples if 'system_cpu_percent' in s]
    metrics={'exit_code':code,'wall_seconds':round(wall,3),'workers':args.workers,'debug':args.debug,'gpu_encoder_requested':args.gpu,
             'cpu_seconds_observed':round(cpu,3),'machine_cpu_percent':round(cpu/wall*100/(os.cpu_count() or 1),2),
             'system_cpu_mean_percent':round(sum(load)/len(load),2) if load else None,
             'peak_tree_working_set_bytes':max((s['working_set_bytes'] for s in samples),default=0),
             'peak_tree_private_bytes':max((s['private_bytes'] for s in samples),default=0),
             'io_note':'GetProcessIoCounters includes files, pipes and other I/O; PDH physical-disk rates are whole-system context, not process-attributed disk bytes.',
             'sampling_note':'PID+creation-time ancestry; ~0.2s intervals. Short-lived processes/peaks can be missed; shared working-set pages can overlap.'}
    result=json.loads((report/'stdout.json').read_text('utf-8'))
    if code==0:
        video=Path(result['final_video']);metrics.update(video=str(video),video_bytes=video.stat().st_size,render_seconds=result['rendering']['elapsed_seconds'])
        project=Path((report/'generated-project.txt').read_text('utf-8').strip())
        trace=[]
        for line in (project/'render.log').read_text('utf-8').splitlines():
            found=re.search(r'\[Render:trace\] (\{.*\})',line)
            if found:trace.append(json.loads(found[1]))
        (report/'stages.json').write_text(json.dumps(trace,indent=2),encoding='utf-8')
        if args.debug and trace:
            perf=report/'diagnostics/.debug'/trace[0]['renderJobId']/'perf-summary.json'
            if perf.is_file():shutil.copyfile(perf,report/'perf-summary.json')
    (report/'result.json').write_text(json.dumps({'metrics':metrics,'result':result},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(metrics,ensure_ascii=False,indent=2),flush=True)
    if code:print((report/'stdout.json').read_text('utf-8')[-1800:])
    return code


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--child',action='store_true')
    parser.add_argument('--project',default='20261109_hf_comparison')
    parser.add_argument('--report',required=True,type=lambda p:Path(p).resolve())
    parser.add_argument('--workers',type=int,choices=(1,2),default=1)
    parser.add_argument('--debug',action='store_true');parser.add_argument('--gpu',action='store_true')
    parser.add_argument('--software-browser',action='store_true')
    parser.add_argument('--rpc-profile',action='store_true')
    args=parser.parse_args();return child(args) if args.child else parent(args)


if __name__=='__main__':raise SystemExit(main())
