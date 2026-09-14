import base64, json, os, re, subprocess, time, urllib.request, urllib.parse
from pathlib import Path

ROOT=Path(__file__).parent
CFG=json.loads((ROOT/'episodes.json').read_text(encoding='utf-8'))
EP=28; EPDATA=CFG['episodes']['28']; TITLE=CFG['titles']['28']
OUT=Path('output/jianci-finale-repair-v2/ep28'); OUT.mkdir(parents=True,exist_ok=True)
HOST='https://api.xrtoken.ai'; MODEL=CFG['model']; RES=CFG['resolution']; RATIO=CFG['ratio']; SEED=CFG['seed']
EXISTING={'01':'2f7cc6d9-8dc4-4032-8afd-ace8ec00ca12'}
VOICE_LIN='https://storage.googleapis.com/adm--audio-playback--7d--public/mcp-preview/298b9d78-bd21-41ef-bc3c-b7122f18450e.mp3'
VOICE_HAN='https://storage.googleapis.com/adm--audio-playback--7d--public/mcp-preview/eb840242-8066-491c-bf18-5c7c31225e5a.mp3'
SAFE={
'03':"12 seconds. Cinematic detailed hand-drawn 2D anime, cold blue-gray archive consultation room, restrained mystery, realistic adult proportions. ABSOLUTELY NO corpse, NO morgue, NO cremation or burial imagery, NO body drawer, NO blood, NO injury, NO ghost, NO readable generated text, NO subtitles, NO music. Only Xu and Han visible. Xu stands LEFT holding a plain closed archive folder with no visible writing. Han stands RIGHT, hands empty. Camera stays on their faces and the closed folder. At 0.45s Xu ON CAMERA says exactly: “之后没有火化记录，也没有埋葬编号。” At 6.20s Han ON CAMERA says exactly: “只剩一句：转移前，遗体不在原位。” Hold quiet reaction. No extra dialogue or people.",
'04':"12 seconds. Cinematic detailed hand-drawn 2D anime, cool blue-gray records corridor, restrained psychological suspense, realistic adult proportions. NO corpse, NO morgue, NO body drawer, NO flashback, NO ghost, NO blood, NO injury, NO supernatural effect, NO text, NO music. Only Lin LEFT and Jian RIGHT, several steps apart. Jian wears black turtleneck and dark gray jacket. At 0.45s Lin ON CAMERA says exactly: “尸体不见了？” At 2.15s Jian ON CAMERA says exactly: “可能不是尸体。” At 4.35s Lin ON CAMERA says exactly: “这是记忆，还是推断？” At 7.20s Jian ON CAMERA says exactly: “现在只是推断。” Jian is calm and explicitly uncertain. Only speaker mouth moves; no extra people.",
'05':"12 seconds. Cinematic detailed hand-drawn 2D anime, clean forensic evidence room, cold blue-gray light, restrained suspense, realistic adult proportions. NO body, NO injury, NO blood, NO scalp imagery, NO gore, NO readable generated text, NO music. Xu stands LEFT holding a tiny sealed transparent secondary container with a few loose dark hair strands only. Jian stands RIGHT behind a floor boundary, hands empty, never touches it. At 0.45s Xu ON CAMERA says exactly: “旧物里还有一小束头发，封存记录完整。” At 7.40s Jian ON CAMERA says exactly: “这个可以不是记忆。” End close on the sealed evidence container. No extra dialogue or people."
}
def run(c): subprocess.run(c,check=True)
def probe(p): return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,width,height','-of','json',str(p)]))
def api(path,body=None):
 k=os.environ['XRTOKEN'].strip(); data=None if body is None else json.dumps(body,ensure_ascii=False).encode(); req=urllib.request.Request(HOST+path,data=data,headers={'Authorization':'Bearer '+k,'Content-Type':'application/json'}); return json.load(urllib.request.urlopen(req,timeout=90))
def dl(url,p):
 with urllib.request.urlopen(url,timeout=180) as f:p.write_bytes(f.read())
def task_video(tid,p):
 q=api('/v1/videos/generations/'+urllib.parse.quote(tid,safe='')); assert q.get('status')=='succeeded'; url=q.get('video_url') or (q.get('content') or {}).get('video_url'); dl(url,p)
def ref_data(name):
 r=CFG['known_refs'][name]; tmp=OUT/f'ref-{name}.mp4'; task_video(r['task_id'],tmp); jpg=OUT/f'{name}.jpg'; cmd=['ffmpeg','-v','error','-y','-ss',str(r['seconds']),'-i',str(tmp),'-frames:v','1'];
 if r.get('crop'):cmd+=['-vf','crop='+r['crop']]
 run(cmd+[str(jpg)]); tmp.unlink(missing_ok=True); return 'data:image/jpeg;base64,'+base64.b64encode(jpg.read_bytes()).decode(),jpg
def submit(c,refs):
 content=[{'type':'text','text':SAFE[c['id']]}]
 for n in c['refs']:content.append({'type':'image_url','image_url':{'url':refs[n]},'role':'reference_image'})
 r=api('/v1/videos/generations',{'model':MODEL,'content':content,'duration':12,'resolution':RES,'ratio':RATIO,'generate_audio':True,'watermark':False,'prompt_extend':False,'seed':SEED}); tid=r.get('id') or (r.get('data') or {}).get('id'); assert tid
 end=time.monotonic()+2400
 while time.monotonic()<end:
  q=api('/v1/videos/generations/'+urllib.parse.quote(tid,safe='')); st=q.get('status')
  if st=='succeeded': return tid,q.get('video_url') or (q.get('content') or {}).get('video_url')
  if st in ('failed','cancelled','expired'): raise RuntimeError(f"{c['id']} {st}: {q.get('error','')}")
  time.sleep(12)
 raise TimeoutError(tid)
def local_clip02(lin_jpg,han_jpg):
 linv=OUT/'lin-vis.mp4'; hanv=OUT/'han-vis.mp4'
 vf1="scale=900:600:force_original_aspect_ratio=increase,crop=832:480,zoompan=z='min(zoom+0.0012,1.08)':d=155:s=832x480:fps=25"
 vf2="scale=900:600:force_original_aspect_ratio=increase,crop=832:480,zoompan=z='min(zoom+0.0010,1.07)':d=145:s=832x480:fps=25"
 run(['ffmpeg','-v','error','-y','-loop','1','-i',str(lin_jpg),'-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-vf',vf1,'-t','6.2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(linv)])
 run(['ffmpeg','-v','error','-y','-loop','1','-i',str(han_jpg),'-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-vf',vf2,'-t','5.8','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(hanv)])
 lst=OUT/'local-list.txt'; lst.write_text(f"file '{linv.resolve().as_posix()}'\nfile '{hanv.resolve().as_posix()}'\n")
 vis=OUT/'02-vis.mp4'; run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(lst),'-c:v','libx264','-c:a','aac',str(vis)])
 lmp=OUT/'lin.mp3'; hmp=OUT/'han.mp3'; dl(VOICE_LIN,lmp); dl(VOICE_HAN,hmp)
 out=OUT/'02-raw.mp4'; fc='[1:a]adelay=450|450,volume=1.0[l];[2:a]adelay=6200|6200,volume=1.0[h];[0:a][l][h]amix=inputs=3:duration=first:normalize=0[a]'
 run(['ffmpeg','-v','error','-y','-i',str(vis),'-i',str(lmp),'-i',str(hmp),'-filter_complex',fc,'-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','160k','-t','12',str(out)])
 return out
def srt_time(x):
 ms=int(round(x*1000)); h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); s,ms=divmod(ms,1000); return f'{h:02}:{m:02}:{s:02},{ms:03}'
def make_srt():
 names={'jian':'剑刺','lin':'林浅','zhou':'周峤','xu':'许未','han':'韩彻'}; cues=[(0.05,1.85,'《吸血法医·剑刺》第28集《这个人死过》\nJian Ci · Episode 28 — This Man Died Before')]
 for i,c in enumerate(EPDATA):
  p=SAFE.get(c['id'],c['prompt']); times=[float(x) for x in re.findall(r'At ([0-9.]+)s',p)]
  if c['id']=='02': times=[0.45,6.20]
  assert len(times)==len(c['lines'])
  for j,(ln,st) in enumerate(zip(c['lines'],times)):
   sp,zh,en=ln; end=(times[j+1]-0.18 if j+1<len(times) else min(11.3,st+max(1.5,min(4.5,len(zh)/4+0.6)))); cues.append((i*12+st,i*12+end,f'{names[sp]}：{zh}\n{en}'))
 p=OUT/'EP28_bilingual.srt'
 with p.open('w',encoding='utf-8') as f:
  for n,(a,b,t) in enumerate(cues,1):f.write(f'{n}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n\n')
 return p
def finish(raws,rep):
 lst=OUT/'concat.txt'; lst.write_text(''.join(f"file '{p.resolve().as_posix()}'\n" for p in raws)); joined=OUT/'EP28_joined.mp4'; run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(lst),'-c:v','libx264','-preset','veryfast','-crf','20','-c:a','aac','-b:a','160k',str(joined)])
 srt=make_srt(); esc=str(srt.resolve()).replace(':','\\:').replace("'","\\'"); out=OUT/'剑刺_第28集_这个人死过_中英字幕_BGM.mp4'; dur=float(probe(joined)['format']['duration']); fc=f"[0:v]subtitles='{esc}':force_style='FontName=Noto Sans CJK SC,FontSize=18,Outline=2,MarginV=26'[v];[0:a]volume=1[a0];[1:a]volume=.010,lowpass=f=95[a1];[2:a]volume=.004,lowpass=f=650[a2];[a0][a1][a2]amix=inputs=3:duration=first:normalize=0[a]"
 run(['ffmpeg','-v','error','-y','-i',str(joined),'-f','lavfi','-t',str(dur),'-i','sine=frequency=49:sample_rate=48000','-f','lavfi','-t',str(dur),'-i','anoisesrc=color=brown:amplitude=.02:sample_rate=48000','-filter_complex',fc,'-map','[v]','-map','[a]','-c:v','libx264','-c:a','aac','-b:a','160k','-t','60',str(out)])
 m=probe(out); assert 'video' in [s.get('codec_type') for s in m['streams']] and 'audio' in [s.get('codec_type') for s in m['streams']]
 for i,t in enumerate([2,14,26,38,50],1):run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(out),'-frames:v','1',str(OUT/f'proof-{i:02d}.jpg')])
 rep['final']=out.name; (OUT/'report.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2))
def main():
 assert os.environ.get('JIANCI_EXECUTE')=='1'; assert os.environ.get('GITHUB_RUN_ATTEMPT','1')=='1'
 refs={}; imgs={}
 for n in CFG['known_refs']:
  refs[n],imgs[n]=ref_data(n)
 rep={'episode':28,'mode':'targeted-v2-no-third-video-attempt-for-clip02','clips':[]}; raws=[]
 p=OUT/'01-raw.mp4'; task_video(EXISTING['01'],p); raws.append(p); rep['clips'].append({'id':'01','source':'reused-success'})
 p=local_clip02(imgs['lin'],imgs['han']); raws.append(p); rep['clips'].append({'id':'02','source':'local-fallback-existing-frames-plus-voice','paid_video_retry':False})
 for cid in ['03','04','05']:
  c=next(x for x in EPDATA if x['id']==cid); tid,url=submit(c,refs); p=OUT/f'{cid}-raw.mp4'; dl(url,p); raws.append(p); rep['clips'].append({'id':cid,'source':'first-paid-generation','task_id':tid}); (OUT/'progress.json').write_text(json.dumps(rep,ensure_ascii=False,indent=2))
 finish(raws,rep); print('EP28 V2 READY')
if __name__=='__main__':main()
