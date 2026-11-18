"""Compare preserved stage-3 A with actual stage-3.1 B, after the common audit."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import subprocess

from PIL import Image, ImageDraw, ImageFont
from verify_renderer_comparison import ROOT, FONT


def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    report=ROOT/'output/hyperframes-stage31-20261111'
    delivery=report/'B-delivery';out=report/'comparison';out.mkdir(exist_ok=True)
    baseline=ROOT/'output/hyperframes-stage3-accepted-20261110'
    previous=load(baseline/'verification.json');actual=load(delivery/'verification.json')
    assert actual['ok'] and actual['actual_mp4_highlight']['matching_frames']==588
    a=Path(previous['metrics']['C']['video']);b=Path(actual['metrics']['C']['video'])
    assert hashlib.sha256(a.read_bytes()).hexdigest()==previous['probe']['C']['sha256']
    ga=Path(previous['generated_project']);gb=Path(actual['generated_project'])
    html_identical=all((ga/name).read_bytes()==(gb/name).read_bytes() for name in ['index.html','compositions/shorts.html','caption-map.json'])
    assert html_identical,'Changed visual HTML/caption clock'
    command=['ffmpeg','-hide_banner','-i',str(a),'-i',str(b),'-an','-filter_complex',
             '[0:v]split=2[a1][a2];[1:v]split=2[b1][b2];[a1][b1]ssim=stats_file=ssim.log[s];[a2][b2]psnr=stats_file=psnr.log[p]',
             '-map','[s]','-map','[p]','-f','null','-']
    metrics=subprocess.run(command,cwd=out,capture_output=True,encoding='utf-8',errors='replace')
    (out/'ffmpeg-quality.log').write_text(metrics.stderr,encoding='utf-8');assert metrics.returncode==0
    ssim_match=re.search(r'SSIM .* All:([\d.]+)',metrics.stderr)
    psnr_match=re.search(r'PSNR .* average:([\d.]+)',metrics.stderr)
    assert ssim_match and psnr_match
    ssim,psnr=float(ssim_match[1]),float(psnr_match[1])
    assert ssim>=.995 and psnr>=45,(ssim,psnr)
    frame_ssim=[float(x) for x in re.findall(r'All:([\d.]+)',(out/'ssim.log').read_text('utf-8'))]
    assert len(frame_ssim)==889
    saved={};times=[1,4,9,16,22,28]
    for name,source in [('A',baseline),('B',delivery)]:
        for t in times:saved[name,t]=Image.open(source/f'frames/C-{t:02}s.png').convert('RGB')
    font=ImageFont.truetype(str(FONT),26)
    for selected in ([4,9,22],[1,16,28]):
        sheet=Image.new('RGB',(1128,1400),'#f4f2e9');draw=ImageDraw.Draw(sheet)
        guide=sheet.copy();gd=ImageDraw.Draw(guide)
        for row,(name,label) in enumerate([('A','HyperFrames 3'),('B','HyperFrames 3.1')]):
            for col,t in enumerate(selected):
                x,y=8+376*col,48+700*row
                for canvas,pen in [(sheet,draw),(guide,gd)]:
                    pen.text((x,y-38),f'{name} · {label} · {t}초',font=font,fill='#101e25')
                    canvas.paste(saved[name,t].resize((360,640),Image.Resampling.LANCZOS),(x,y))
                gd.rectangle((x+72/3,y+250/3,x+930/3,y+1520/3),outline='#fb913a',width=2)
        stem='comparison-'+ '-'.join(str(t)+'s' for t in selected)
        sheet.save(out/(stem+'.png'));guide.save(out/(stem+'-safe.png'))
    summary={'ok':True,'A':str(a),'B':str(b),'input_html_and_captions_byte_identical':True,
             'ssim':ssim,'ssim_min_frame':min(frame_ssim),'psnr_db':psnr,'frames_compared':len(frame_ssim),
             'note':'Minor capture/encoder quantization differences; no lower quality setting. Metrics complement timing, safety, actual highlight checks and visual review.',
             'B_common_audit':str(delivery/'verification.json'),'B_layout_audit':str(delivery/'layout-audit.json'),
             'B_sha256':hashlib.sha256(b.read_bytes()).hexdigest()}
    (out/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
