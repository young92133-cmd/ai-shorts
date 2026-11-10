"""Verify actual comparison MP4s and make decoded-frame contact sheets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "output/hyperframes-comparison-20261109"
FONT = ROOT / "renderers/hyperframes/poc/assets/fonts/NotoSansKR-VF.ttf"


def pcm(path: Path) -> np.ndarray:
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "8000",
                                   "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1"])
    return np.frombuffer(raw, dtype="<f4")


def audio_alignment(reference: np.ndarray, actual: np.ndarray) -> dict:
    n = 1 << (len(reference) + len(actual) - 1).bit_length()
    cross = np.fft.irfft(np.fft.rfft(actual, n) * np.conj(np.fft.rfft(reference, n)), n)
    limit = 800
    values = np.concatenate([cross[-limit:], cross[:limit+1]])
    lag = int(np.argmax(values)) - limit
    a = actual[max(lag,0):]; b = reference[max(-lag,0):]
    length = min(len(a),len(b)); a,b = a[:length],b[:length]
    correlation = float(np.dot(a.astype(np.float64),b) / np.sqrt(np.dot(a,a)*np.dot(b,b)))
    return {"lag_samples_at_8khz":lag,"offset_milliseconds":lag/8,"correlation":correlation}


def main() -> None:
    records = {name:json.loads((REPORT/f"{name}-result.json").read_text(encoding="utf-8")) for name in ("ffmpeg","hyperframes")}
    videos = {name:Path(data["metrics"]["video"]) for name,data in records.items()}
    source = json.loads((REPORT/"source-protection.json").read_text(encoding="utf-8"))
    source_dir,job = Path(source["source"]),Path(source["clone"])
    tl = json.loads((job/"timeline.json").read_text(encoding="utf-8"))
    original_words = [w for line in tl["subtitles"]["lines"] for w in line.get("words",[])]
    total = sum(s["duration"] for s in tl["scenes"])
    for rel,checksum in source["sha256"].items():
        assert hashlib.sha256((source_dir/rel).read_bytes()).hexdigest()==checksum, f"Source changed: {rel}"
    assert (source_dir/"timeline.json").read_bytes()==(job/"timeline.json").read_bytes()
    for p in [source_dir/"narration.mp3",*[x for x in (source_dir/"audio").glob('*') if x.is_file()]]:
        assert p.read_bytes()==(job/p.relative_to(source_dir)).read_bytes(), "TTS material changed"
    old_state=json.loads((source_dir/"project_state.json").read_text(encoding="utf-8"))
    new_state=json.loads((job/"project_state.json").read_text(encoding="utf-8"))
    assert old_state.get("ai_calls")==new_state.get("ai_calls"), "Unexpected new AI call record"

    probe = {}
    for name,path in videos.items():
        result=json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-show_streams","-show_format","-of","json",str(path)]))
        (REPORT/f"{name}-ffprobe.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        video=next(x for x in result['streams'] if x['codec_type']=='video')
        audio=next(x for x in result['streams'] if x['codec_type']=='audio')
        assert (video['width'],video['height'],video['r_frame_rate'],video['codec_name'])==(1080,1920,'30/1','h264')
        assert audio['codec_name']=='aac'
        duration=float(result['format']['duration'])
        assert abs(duration-total)<.12
        probe[name]={"duration":duration,"video_frames":int(video['nb_read_frames']),"resolution":"1080x1920","fps":"30/1",
                     "video_codec":video['codec_name'],"audio_codec":audio['codec_name'],"sample_rate":audio['sample_rate'],
                     "bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
    assert probe['ffmpeg']['sha256']==source['sha256']['final.mp4'], "FFmpeg result differs from the original delivery"

    projects = [p.parent for p in (job/'renders').glob('*/hyperframes/index.html')]
    assert len(projects)==1, "Select the intended successful generated project explicitly"
    generated=projects[0]
    pages=json.loads((generated/'caption-map.json').read_text(encoding='utf-8'))
    mapped=[w for page in pages for row in page['rows'] for w in row]
    assert mapped==original_words, "Word text/timing changed"
    assert all(len(p['rows'])<=2 for p in pages)
    manifest=json.loads((generated/'asset-manifest.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256(Path(x['original']).read_bytes()).hexdigest()==x['sha256'] for x in manifest)

    times=[1,4,9,16,22,28]
    frames=REPORT/'frames';frames.mkdir(exist_ok=True)
    saved={}
    for name,path in videos.items():
        for t in times:
            target=frames/f'{name}-{t:02d}s.png'
            if not target.exists():
                subprocess.run(['ffmpeg','-v','error','-ss',str(t),'-i',str(path),'-frames:v','1',str(target)],check=True)
            saved[name,t]=Image.open(target).convert('RGB')

    # Inspect every encoded HyperFrames frame, not just the generated HTML.
    decoder=subprocess.Popen(['ffmpeg','-v','error','-i',str(videos['hyperframes']),'-an','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE)
    unsafe=[];highlighted=0;expected_highlight=0;misses=[];i=0
    color=tl['subtitles']['style']['highlight'].lstrip('#');rgb_color=np.array([int(color[n:n+2],16) for n in (0,2,4)],dtype=np.int16)
    while True:
        data=decoder.stdout.read(1080*1920*3)
        if not data:break
        assert len(data)==1080*1920*3
        rgb=np.frombuffer(data,dtype=np.uint8).reshape(1920,1080,3)
        ground=rgb[10,10].astype(np.int16)
        bad=sum(int(np.count_nonzero(np.max(np.abs(z.astype(np.int16)-ground),axis=2)>40)) for z in [rgb[:250],rgb[1520:],rgb[250:1520,930:]])
        if bad:unsafe.append({'frame':i,'pixels':bad})
        crop=rgb[1320:1470,72:900].astype(np.int16)
        count=int(np.count_nonzero(np.max(np.abs(crop-rgb_color),axis=2)<40))
        moment=i/30
        # Avoid one-frame edge ambiguities; compare well inside each saved word.
        expected=any(w['start']+.035<=moment<=w['end']-.035 for w in original_words)
        if expected:
            expected_highlight+=1
            if count>=15:highlighted+=1
            else:misses.append(i)
        i+=1
    assert decoder.wait()==0 and i==probe['hyperframes']['video_frames']
    assert not unsafe, f"HyperFrames safe-zone intrusion: {unsafe[:4]}"
    assert expected_highlight and highlighted/expected_highlight>.98, f"Highlight misses {misses[:12]}"
    reference=pcm(source_dir/'narration.mp3')
    alignment={name:audio_alignment(reference,pcm(path)) for name,path in videos.items()}
    assert all(v['correlation']>.98 and abs(v['offset_milliseconds'])<=1000/30 for v in alignment.values()),alignment

    font=ImageFont.truetype(str(FONT),28)
    sheet=Image.new('RGB',(1128,1400),'#f4f2e9');draw=ImageDraw.Draw(sheet)
    guide=sheet.copy();gd=ImageDraw.Draw(guide)
    for row,name in enumerate(['ffmpeg','hyperframes']):
        for col,t in enumerate([4,9,16]):
            x,y=8+376*col,48+700*row
            label=f'{"A. FFmpeg" if row==0 else "B. HyperFrames"} · {t}초'
            draw.text((x,y-40),label,font=font,fill='#101e25')
            image=saved[name,t].resize((360,640),Image.Resampling.LANCZOS)
            sheet.paste(image,(x,y))
            gd.text((x,y-40),label,font=font,fill='#101e25');guide.paste(image,(x,y))
            gd.rectangle((x,y+250/3,x+930/3,y+1520/3),outline='#f47d37',width=2)
    sheet.save(REPORT/'comparison-4s-9s-16s.png');guide.save(REPORT/'comparison-safe-guides.png')
    summary={'ok':True,'probe':probe,'ffmpeg_byte_identical_to_original':True,'input_timeline_unchanged':True,
             'source_files_preserved':len(source['sha256']),'original_tts_preserved':True,'new_ai_calls':0,
             'word_timing_entries_reused':len(mapped),'caption_pages':len(pages),'max_caption_rows':max(len(p['rows']) for p in pages),
             'hyperframes_safety':{'frames_checked':i,'unsafe_frames':unsafe,'safe_box':[0,250,930,1520],
                                  'note':'Foreground-pixel check with RGB tolerance 40; original FFmpeg is byte-preserved, not restyled.'},
             'word_highlight':{'expected_interior_frames':expected_highlight,'matching_frames':highlighted,'missed_frames':misses},
             'audio_alignment':alignment,'generated_project':str(generated),'frames_seconds':times,
             'metrics':{name:r['metrics'] for name,r in records.items()}}
    (REPORT/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
