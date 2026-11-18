"""Verify saved A/B and new C, without generating content or touching inputs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from verify_renderer_comparison import ROOT, FONT, pcm, audio_alignment


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',default='output/hyperframes-stage3-accepted-20261110')
    args=parser.parse_args();report=ROOT/args.report
    previous=ROOT/'output/hyperframes-comparison-20261109'
    records={'A':load(previous/'ffmpeg-result.json'),'B':load(previous/'hyperframes-result.json'),
             'C':load(report/'hyperframes-result.json')}
    videos={name:Path(r['metrics']['video']) for name,r in records.items()}
    source=load(previous/'source-protection.json');job=Path(source['clone']);original=Path(source['source'])
    for rel,digest in source['sha256'].items():
        assert hashlib.sha256((original/rel).read_bytes()).hexdigest()==digest,rel
    assert (original/'timeline.json').read_bytes()==(job/'timeline.json').read_bytes()
    for p in [original/'narration.mp3',*(original/'audio').glob('*')]:
        if p.is_file():assert p.read_bytes()==(job/p.relative_to(original)).read_bytes()
    assert load(original/'project_state.json')['ai_calls']==load(job/'project_state.json')['ai_calls']
    tl=load(job/'timeline.json');total=sum(s['duration'] for s in tl['scenes'])
    words=[w for line in tl['subtitles']['lines'] for w in line['words']]
    sidecar=load(videos['C'].with_suffix('.render.json'))
    generated=next(p.parent/'hyperframes' for p in (job/'renders').glob('*/render-result.json')
                   if load(p).get('output')==str(videos['C']) and load(p).get('status')=='complete')
    layout=load(generated/'layout-map.json');safe=layout['safe_area']
    pages=load(generated/'caption-map.json')
    assert [w for page in pages for row in page['rows'] for w in row]==words
    assert all(len(page['rows'])<=2 for page in pages)
    for asset in load(generated/'asset-manifest.json'):
        assert hashlib.sha256(Path(asset['original']).read_bytes()).hexdigest()==asset['sha256']
    probes={}
    for name,path in videos.items():
        raw=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)]))
        (report/f'{name}-ffprobe.json').write_text(json.dumps(raw,indent=2),encoding='utf-8')
        v=next(s for s in raw['streams'] if s['codec_type']=='video');a=next(s for s in raw['streams'] if s['codec_type']=='audio')
        assert (v['width'],v['height'],v['r_frame_rate'],v['codec_name'],a['codec_name'])==(1080,1920,'30/1','h264','aac')
        assert abs(float(raw['format']['duration'])-total)<.12
        probes[name]={'duration':float(raw['format']['duration']),'frames':int(v['nb_read_frames']),
                      'resolution':[1080,1920],'fps':30,'codecs':['h264','aac'],'bytes':path.stat().st_size,
                      'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    old=load(previous/'verification.json')['probe']
    assert probes['A']['sha256']==old['ffmpeg']['sha256']==source['sha256']['final.mp4']
    assert probes['B']['sha256']==old['hyperframes']['sha256']
    alignment={name:audio_alignment(pcm(original/'narration.mp3'),pcm(path)) for name,path in videos.items()}
    assert all(abs(v['offset_milliseconds'])<=1000/30 and v['correlation']>.98 for v in alignment.values()),alignment
    frames=report/'frames';frames.mkdir(exist_ok=True)
    saved={};times=[1,4,9,16,22,28]
    for name,video in videos.items():
        for t in times:
            target=frames/f'{name}-{t:02}s.png'
            if not target.exists():subprocess.run(['ffmpeg','-v','error','-ss',str(t),'-i',str(video),'-frames:v','1',str(target)],check=True)
            saved[name,t]=Image.open(target).convert('RGB')
    font=ImageFont.truetype(str(FONT),25)
    for selected in ([4,9,22],[1,16,28]):
        sheet=Image.new('RGB',(1128,2100),'#f4f2e9');draw=ImageDraw.Draw(sheet)
        guided=sheet.copy();gd=ImageDraw.Draw(guided)
        for row,(name,label) in enumerate([('A','FFmpeg'),('B','HyperFrames 2'),('C','HyperFrames 3')]):
            for col,t in enumerate(selected):
                x,y=8+376*col,48+700*row
                for canvas,pen in [(sheet,draw),(guided,gd)]:
                    pen.text((x,y-38),f'{name} · {label} · {t}초',font=font,fill='#101e25')
                    canvas.paste(saved[name,t].resize((360,640),Image.Resampling.LANCZOS),(x,y))
                gd.rectangle((x+safe['left']/3,y+safe['top']/3,x+(1080-safe['right'])/3,y+(1920-safe['bottom'])/3),outline='#fb913a',width=2)
        stem='comparison-'+ '-'.join(str(t)+'s' for t in selected)
        sheet.save(report/(stem+'.png'));guided.save(report/(stem+'-safe.png'))
    # Decode all output frames, checking actual highlight pixels well inside
    # original word windows. Full-frame backgrounds may legally cross guides.
    decoder=subprocess.Popen(['ffmpeg','-v','error','-i',str(videos['C']),'-an','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE)
    color=tl['subtitles']['style']['highlight'].lstrip('#');color=np.array([int(color[n:n+2],16) for n in (0,2,4)],dtype=np.int16)
    count=expected=matching=0;misses=[]
    while True:
        raw=decoder.stdout.read(1080*1920*3)
        if not raw:break
        assert len(raw)==1080*1920*3
        rgb=np.frombuffer(raw,dtype=np.uint8).reshape(1920,1080,3)
        moment=count/30
        if any(w['start']+.035<=moment<=w['end']-.035 for w in words):
            expected+=1
            crop=rgb[1920-safe['bottom']-178:1920-safe['bottom'],safe['left']:1080-safe['right']].astype(np.int16)
            colored=int(np.count_nonzero(np.max(np.abs(crop-color),axis=2)<40))
            if colored>=15:matching+=1
            else:misses.append(count)
        count+=1
    assert decoder.wait()==0 and count==probes['C']['frames']
    assert matching/expected>.98,(matching,expected,misses[:20])
    def sample(t):
        raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(t),'-i',str(videos['C']),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
        return np.frombuffer(raw,dtype=np.uint8).reshape(1920,1080,3)
    # Separate native-title appearance and explicit three-step growth from
    # the unchanged voice/subtitle pixels.
    title_counts=[]
    for t in [.033,.4]:
        crop=sample(t)[550:820,72:930]
        title_counts.append(int(np.count_nonzero(np.min(crop,axis=2)>180)))
    step_counts=[]
    for t in [8.45,8.78,9.3]:
        crop=sample(t)[830:1070,72:930].astype(np.int16)
        step_counts.append(int(np.count_nonzero((crop[:,:,1]>crop[:,:,0]+35)&(crop[:,:,1]>90)&(crop[:,:,2]>70))))
    assert title_counts[1]>title_counts[0]*1.5+100,title_counts
    assert step_counts[0]<step_counts[1]<step_counts[2],step_counts
    strict_files=list((generated/'.hyperframes/artifacts/checks').glob('*.json'))
    strict=load(max(strict_files,key=lambda p:p.stat().st_mtime))
    assert strict['ok']
    categories={k:{n:v.get(n) for n in ('ok','errorCount','warningCount')} for k,v in strict.items() if isinstance(v,dict) and 'errorCount' in v}
    (report/'hyperframes-strict-check.json').write_text(json.dumps(strict,ensure_ascii=False,indent=2),encoding='utf-8')
    verification={'ok':True,'probe':probes,'generated_project':str(generated),'source_files_preserved':len(source['sha256']),
                  'A_B_byte_preserved':True,'timeline_unchanged':True,'tts_bytes_preserved':True,'new_ai_calls':0,
                  'word_entries_reused':len(words),'caption_pages':len(pages),'max_caption_rows':max(len(x['rows']) for x in pages),
                  'actual_mp4_highlight':{'frames':count,'expected_interior_frames':expected,'matching_frames':matching,'misses':misses},
                  'audio_alignment':alignment,'native_title_bright_pixels':title_counts,'step_growth_pixels':step_counts,
                  'strict_checks':categories,'layout':layout,'media_preparation':load(generated/'media-preparation.json'),
                  'metrics':{k:v['metrics'] for k,v in records.items()},'render_record':sidecar,
                  'safety_note':'Full backgrounds may cross safe guides. Separate per-frame DOM text-range audit + actual decoded frames verify important text; inherited text inside the original low-resolution source image is not independently relocated.'}
    (report/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:verification[k] for k in ['ok','generated_project','actual_mp4_highlight','audio_alignment','native_title_bright_pixels','step_growth_pixels','strict_checks']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
