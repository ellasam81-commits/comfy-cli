import base64,json,os,re,subprocess,urllib.request,urllib.parse
from pathlib import Path
ROOT=Path(__file__).parent
CFG=json.loads((ROOT/'episodes.json').read_text(encoding='utf-8'))
EPDATA=CFG['episodes']['27']; TITLE=CFG['titles']['27']
OUT=Path('output/jianci-finale-repair-v2/ep27'); OUT.mkdir(parents=True,exist_ok=True)
HOST='https://api.xrtoken.ai'
EXISTING={'01':'0a263141-c341-4e43-bcfa-5868c72aa4fc','02':'bf406aae-fcd3-45da-85af-6e5b221d655a','03':'9414afdd-7550-44b5-b34e-154142b25f8e','04':'877c8d27-8bcf-43e7-b5ce-e789205a88e0'}
VOICE_HAN1='https://storage.googleapis.com/adm--audio-playback--7d--public/mcp-preview/fbfb57d9-e26e-45f4-b6b3-209fa61196cc.mp3'
VOICE_JIAN='https://storage.googleapis.com/adm--audio-playback--7d--public/mcp-preview/beda3784-fda3-467e-826e-cfcbc3f210ae.mp3'
VOICE_HAN2='https://storage.googleapis.com/adm--audio-playback--7d--public/mcp-preview/ec0e86e8-b2b4-4509-aeef-81d34909c037.mp3'
def run(c):subprocess.run(c,check=True)
def probe(p):return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,width,height','-of','json',str(p)]))
def api(path):
 k=os.environ['XRTOKEN'].strip();req=urllib.request.Request(HOST+path,headers={'Authorization':'Bearer '+k,'Content-Type':'application/json'});return json.load(urllib.request.urlopen(req,timeout=90))
def dl(url,p):
 with urllib.request.urlopen(url,timeout=180) as f:p.write_bytes(f.read())
def task_video(tid,p):
 q=api('/v1/videos/generations/'+urllib.parse.quote(tid,safe=''));assert q.get('status')=='succeeded';url=q.get('video_url') or (q.get('content') or {}).get('video_url');assert url;dl(url,p)
def ref_jpg(name):
 r=CFG['known_refs'][name];tmp=OUT/f'ref-{name}.mp4';task_video(r['task_id'],tmp);jpg=OUT/f'{name}.jpg';cmd=['ffmpeg','-v','error','-y','-ss',str(r['seconds']),'-i',str(tmp),'-frames:v','1'];
 if r.get('crop'):cmd+=['-vf','crop='+r['crop']]
 run(cmd+[str(jpg)]);tmp.unlink(missing_ok=True);return jpg
def still_vid(jpg,dur,out,zoom):
 vf=f"scale=900:600:force_original_aspect_ratio=increase,crop=832:480,zoompan=z='min(zoom+{zoom},1.08)':d={int(dur*25)}:s=832x480:fps=25"
 run(['ffmpeg','-v','error','-y','-loop','1','-i',str(jpg),'-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-vf',vf,'-t',str(dur),'-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(out)])
def make_local05(han,jian):
 v1=OUT/'han1-vis.mp4';v2=OUT/'jian-vis.mp4';v3=OUT/'han2-vis.mp4';still_vid(han,6.3,v1,'0.0012');still_vid(jian,2.1,v2,'0.0010');still_vid(han,3.6,v3,'0.0008')
 lst=OUT/'local-list.txt';lst.write_text(f"file '{v1.resolve().as_posix()}'\nfile '{v2.resolve().as_posix()}'\nfile '{v3.resolve().as_posix()}'\n")
 vis=OUT/'05-vis.mp4';run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(lst),'-c:v','libx264','-c:a','aac',str(vis)])
 a1=OUT/'han1.mp3';a2=OUT/'jian.mp3';a3=OUT/'han2.mp3';dl(VOICE_HAN1,a1);dl(VOICE_JIAN,a2);dl(VOICE_HAN2,a3)
 out=OUT/'05-raw.mp4';fc='[1:a]adelay=450|450[h1];[2:a]adelay=6700|6700[j];[3:a]adelay=8550|8550[h2];[0:a][h1][j][h2]amix=inputs=4:duration=first:normalize=0[a]'
 run(['ffmpeg','-v','error','-y','-i',str(vis),'-i',str(a1),'-i',str(a2),'-i',str(a3),'-filter_complex',fc,'-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','160k','-t','12',str(out)]);return out
def st(x):
 ms=int(round(x*1000));h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000);return f'{h:02}:{m:02}:{s:02},{ms:03}'
def make_srt():
 names={'jian':'剑刺','lin':'林浅','zhou':'周峤','xu':'许未','han':'韩彻'};cues=[(0.05,1.85,'《吸血法医·剑刺》第27集《阿宁》\nJian Ci · Episode 27 — A-Ning')]
 for i,c in enumerate(EPDATA):
  times=[float(x) for x in re.findall(r'At ([0-9.]+)s',c['prompt'])]
  if c['id']=='05':times=[0.45,6.70,8.55]
  assert len(times)==len(c['lines'])
  for j,(ln,t0) in enumerate(zip(c['lines'],times)):
   sp,zh,en=ln;t1=(times[j+1]-0.18 if j+1<len(times) else min(11.3,t0+max(1.5,min(4.5,len(zh)/4+.6))));cues.append((i*12+t0,i*12+t1,f'{names[sp]}：{zh}\n{en}'))
 p=OUT/'EP27_bilingual.srt'
 with p.open('w',encoding='utf-8') as f:
  for n,(a,b,t) in enumerate(cues,1):f.write(f'{n}\n{st(a)} --> {st(b)}\n{t}\n\n')
 return p
def finish(raws):
 lst=OUT/'concat.txt';lst.write_text(''.join(f"file '{p.resolve().as_posix()}'\n" for p in raws));joined=OUT/'EP27_joined.mp4';run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(lst),'-c:v','libx264','-preset','veryfast','-crf','20','-c:a','aac','-b:a','160k',str(joined)])
 srt=make_srt();esc=str(srt.resolve()).replace(':','\\:').replace("'","\\'");out=OUT/'剑刺_第27集_阿宁_中英字幕_BGM.mp4';dur=float(probe(joined)['format']['duration']);fc=f"[0:v]subtitles='{esc}':force_style='FontName=Noto Sans CJK SC,FontSize=18,Outline=2,MarginV=26'[v];[0:a]volume=1[a0];[1:a]volume=.010,lowpass=f=95[a1];[2:a]volume=.004,lowpass=f=650[a2];[a0][a1][a2]amix=inputs=3:duration=first:normalize=0[a]"
 run(['ffmpeg','-v','error','-y','-i',str(joined),'-f','lavfi','-t',str(dur),'-i','sine=frequency=49:sample_rate=48000','-f','lavfi','-t',str(dur),'-i','anoisesrc=color=brown:amplitude=.02:sample_rate=48000','-filter_complex',fc,'-map','[v]','-map','[a]','-c:v','libx264','-c:a','aac','-b:a','160k','-t','60',str(out)])
 m=probe(out);types=[s.get('codec_type') for s in m['streams']];assert 'video' in types and 'audio' in types
 for i,t in enumerate([2,14,26,38,50],1):run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(out),'-frames:v','1',str(OUT/f'proof-{i:02d}.jpg')])
 (OUT/'report.json').write_text(json.dumps({'episode':27,'mode':'local-final-clip-no-third-paid-retry','final':out.name,'reused':['01','02','03','04'],'local':['05'],'technical_qc':{'has_video':True,'has_audio':True,'proof_frames':5}},ensure_ascii=False,indent=2))
def main():
 assert os.environ.get('JIANCI_EXECUTE')=='1';assert os.environ.get('GITHUB_RUN_ATTEMPT','1')=='1';han=ref_jpg('han');jian=ref_jpg('jian');raws=[]
 for cid in ['01','02','03','04']:
  p=OUT/f'{cid}-raw.mp4';task_video(EXISTING[cid],p);raws.append(p)
 raws.append(make_local05(han,jian));finish(raws);print('EP27 V2 READY')
if __name__=='__main__':main()
