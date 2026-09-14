import json,sys,subprocess,math,re
from pathlib import Path
import numpy as np,wave
P=Path('/tmp/jianci-production');C=P/'code';ep=int(sys.argv[1]);E=P/f'edit/ep{ep}';E.mkdir(parents=True,exist_ok=True)
cfg=json.loads((C/f'episode{ep}.json').read_text());plan=json.loads((E/'edit.json').read_text());names={'mother':'罗素琴','lin':'林浅','jian':'剑刺','xu':'许未','zhou':'周峤','han':'韩彻','lu':'陆承安','narrator':'旁白','caller':'报案路人'}
font=P/'old/ep14-full/NotoSansCJKsc-Regular.otf'
W,H=1280,960;events=[];srt=[];timeline=[];cursor=0
header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 960
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans CJK SC,34,&H00FFFFFF,&H00FFFFFF,&H00181818,&H90000000,0,0,0,0,100,100,0,0,1,1.5,0,2,40,40,20,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def stamp(t):return f'{int(t//3600)}:{int(t%3600//60):02}:{t%60:05.2f}'
def add(a,b,txt,tags,layer=0):
 if b>a:events.append(f'Dialogue: {layer},{stamp(a)},{stamp(b)},Default,,0,0,0,,{{{tags}}}'+txt)
def st(t):
 ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
for i,s in enumerate(plan['segments']):
 v=Path(s['video']);a=Path(s.get('audio',str(v)));vs=s.get('vstart',0);ast=s.get('astart',vs);d=s['duration'];dst=E/f'{i:02d}.mp4';crop=s.get('crop');rate=s.get('rate',1)
 vf=(s.get('prefilter','')+',' if s.get('prefilter') else '')+(f'crop={crop},' if crop else '')+f'setpts=(PTS-STARTPTS)/{rate},'+'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1,fps=24,pad=1280:960:0:110:black'
 af=f'atempo={rate},atrim=duration={d},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,afade=t=in:st=0:d=0.015,afade=t=out:st={d-.015}:d=0.015'
 if s.get('mute'):af+=',volume=0'
 if s.get('telephone'):af+=',highpass=f=350,lowpass=f=3200'
 subprocess.run(['ffmpeg','-v','error','-y','-ss',str(vs),'-i',str(v),'-ss',str(ast),'-i',str(a),'-t',str(d),'-filter_complex',f'[0:v]{vf}[v];[1:a]{af}[a]','-map','[v]','-map','[a]','-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-b:a','192k',str(dst)],check=True)
 for line in s.get('lines',[]):
  r,cn,en,ls,le=line;aa=cursor+ls;bb=cursor+min(le,d);name=names.get(r.split()[0],r)
  add(aa,bb,name+'：'+cn,r'\an2\pos(640,876)\fs'+str(34 if len(name+cn)<34 else 30 if len(name+cn)<40 else 26))
  # Wrap long English lines deliberately into two compact rows.
  if len(en)>110:
   words=en.split();half=len(en)//2;acc='';k=0
   while k<len(words) and len(acc)<half:acc+=(' ' if acc else '')+words[k];k+=1
   en=acc+r'\N'+' '.join(words[k:])
  add(aa,bb,en,r'\an2\pos(640,946)\fs24')
  srt.append(f'{len(srt)+1}\n{st(aa)} --> {st(bb)}\n{name}：{cn}\n{en.replace(chr(92)+"N",chr(10))}\n')
 if s.get('label'):add(cursor,cursor+min(d,s.get('label_duration',2.4)),s['label'],r'\an7\pos(35,135)\fs28\bord2',1)
 timeline.append(dict(index=i,start=cursor,end=cursor+d,source=str(v),source_start=vs));cursor+=d
T=cursor
add(0,T,'剑刺',r'\an7\pos(35,13)\fs39')
add(0,T,f"她回来以后 · 第{ep}集：{cfg['title']}",r'\an7\pos(143,23)\fs28')
add(0,T,'作者：林爱丽',r'\an9\pos(1245,24)\fs24')
add(0,T,'灵感：1897年格林布赖尔幽灵案 · 现代人物、案情及吸血鬼情节均为虚构',r'\an7\pos(35,73)\fs21')
for x in plan.get('overlays',[]):add(x['start'],x['end'],x['text'],x.get('tags',r'\an7\pos(35,135)\fs28\bord2'),2)
(E/'captions.ass').write_text(header+'\n'.join(events)+'\n');(E/'subtitles.srt').write_text('\n'.join(srt));(E/'timeline.json').write_text(json.dumps(timeline,ensure_ascii=False,indent=2))
(E/'concat.txt').write_text(''.join("file '"+str(E/f'{i:02d}.mp4')+"'\n" for i in range(len(plan['segments']))))
subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(E/'concat.txt'),'-c','copy',str(E/'cut.mp4')],check=True)
# Original restrained suspense bed, in the same low-drone and sparse-piano style.
sr=24000;t=np.arange(math.ceil(sr*T))/sr;music=np.zeros_like(t)
for hz,amp,phase in [(43.654,.018,.8),(73.416,.032,0),(110,.019,1.1),(146.832,.013,2),(174.614,.009,.4)]:music+=amp*(.7+.3*np.sin(2*np.pi*.045*t+phase)**2)*np.sin(2*np.pi*hz*t+.045*np.sin(2*np.pi*.14*t+phase))
for k,start in enumerate(np.arange(0,T,11)):
 hz=[293.665,220,261.626,174.614][(k+ep)%4];u=np.maximum(t-start,0);music+=.027*(t>=start)*(1-np.exp(-u*14))*(np.exp(-u/2.8)*np.sin(2*np.pi*hz*u)+.16*np.exp(-u/.8)*np.sin(4*np.pi*hz*u))
music*=10**(-29/20)/np.sqrt(np.mean(music*music));music*=np.minimum(t/1.2,1)*np.clip((T-t)/1.5,0,1)
for x in plan.get('sounds',[]):
 start=x['time'];u=t-start;sel=(u>=0)&(u<.16)
 if x['type']=='knock':music[sel]+=.07*np.exp(-u[sel]*40)*np.sin(2*np.pi*170*u[sel])
 if x['type']=='heartbeat':
  for delay in (0,.21):
   u=t-start-delay;sel=(u>=0)&(u<.18);music[sel]+=.065*np.exp(-u[sel]*27)*np.sin(2*np.pi*55*u[sel])
with wave.open(str(E/'score.wav'),'wb') as w:
 w.setnchannels(2);w.setsampwidth(2);w.setframerate(sr);w.writeframes((np.clip(np.column_stack((music,music*.97)),-1,1)*32767).astype('<i2').tobytes())
f=f'[1:a]atrim=duration={T}[score];[0:a]asplit[voice][sc];[score][sc]sidechaincompress=threshold=0.035:ratio=4:attack=20:release=400[bg];[voice][bg]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=0[a];[0:v]ass={E}/captions.ass:fontsdir={font.parent}[v]'
out=P/f'final/剑刺_第{ep}集_{cfg["title"]}_中英字幕_BGM.mp4';out.parent.mkdir(exist_ok=True)
subprocess.run(['ffmpeg','-v','error','-y','-i',str(E/'cut.mp4'),'-i',str(E/'score.wav'),'-filter_complex',f,'-map','[v]','-map','[a]','-t',str(T),'-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-b:a','192k','-pix_fmt','yuv420p','-movflags','+faststart',str(out)],check=True)
print('RENDERED',out,T,flush=True)
