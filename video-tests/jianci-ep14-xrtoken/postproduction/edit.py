import json,subprocess,wave,shutil
from pathlib import Path
import numpy as np
from PIL import Image
P=Path('/tmp/ep14-work');R=P/'raw';R.mkdir(exist_ok=True)
cfg=json.loads((P/'episode.json').read_text())
OUT=Path('/workspace/scratch/6651942d1ae0/剑刺_第14集_她说脖子疼_中英字幕_BGM.mp4')
def run(a):subprocess.run(a,check=True)
def stamp(t):return f'{int(t//3600)}:{int(t%3600//60):02}:{t%60:05.2f}'
shutil.copy('/tmp/ep13-work/NotoSansCJKsc-Regular.otf',P/'NotoSansCJKsc-Regular.otf')
sr=24000;t=np.arange(sr*60)/sr;s=np.zeros_like(t)
for hz,amp,phase in [(43.654,.018,.8),(73.416,.032,0),(110,.019,1.1),(146.832,.013,2),(174.614,.009,.4),(220,.010,1.5)]:
 s+=amp*(.7+.3*np.sin(2*np.pi*.045*t+phase)**2)*np.sin(2*np.pi*hz*t+.045*np.sin(2*np.pi*.14*t+phase))
for start,hz in [(0,293.665),(9,220),(20,261.626),(30,220),(40,174.614),(50,293.665),(54,311.127)]:
 u=np.maximum(t-start,0);a=(t>=start)*(1-np.exp(-u*14))
 s+=.027*a*(np.exp(-u/2.8)*np.sin(2*np.pi*hz*u)+.16*np.exp(-u/.8)*np.sin(2*np.pi*2*hz*u))
s*=10**(-25.5/20)/np.sqrt(np.mean(s*s))
s*=np.minimum(t/1.2,1)*np.clip((60-t)/1.2,0,1)
with wave.open(str(P/'score.wav'),'wb') as w:
 w.setnchannels(2);w.setsampwidth(2);w.setframerate(sr);w.writeframes((np.clip(np.column_stack([s,s*.97]),-1,1)*32767).astype('<i2').tobytes())
header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans CJK SC,28,&H00FFFFFF,&H00FFFFFF,&H00151515,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,25,25,20,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
ev=[]
def event(a,b,txt,tag):ev.append(f'Dialogue: 0,{stamp(a)},{stamp(b)},Default,,0,0,0,,{{{tag}}}'+txt.replace('’',"'"))
event(0,60,'剑刺',r'\an7\pos(40,18)\fs40')
event(0,60,'她回来以后 · 第14集：她说脖子疼',r'\an7\pos(145,27)\fs28')
event(0,60,'作者：林爱丽',r'\an9\pos(1240,27)\fs24')
event(0,60,'真实案件灵感：1897年格林布赖尔幽灵案',r'\an7\pos(40,65)\fs20')
event(0,60,'Greenbrier, 1897 · 母亲见鬼为其说法；现代人物与情节虚构',r'\an7\pos(40,92)\fs17')
over=json.loads((P/'timings.json').read_text()) if (P/'timings.json').exists() else {}
srt=[]
for i,c in enumerate(cfg['clips']):
 for j,d in enumerate(c['dialogue']):
  a,b=over.get(c['id']+'-'+str(j),([.3,4.8] if j==0 else [5.1,9.6]));a+=i*10;b+=i*10
  event(a,b,d['speaker']+'：'+d['zh'],r'\an2\pos(640,661)\fs34')
  event(a,b,d['en'],r'\an2\pos(640,699)\fs25')
  def st(x):return f'{int(x//3600):02}:{int(x%3600//60):02}:{int(x%60):02},{round((x%1)*1000):03}'
  srt.append(f"{len(srt)+1}\n{st(a)} --> {st(b)}\n{d['speaker']}：{d['zh']}\n{d['en']}\n")
for a,b,txt in [(20,22.8,'次日 · 初检记录复核'),(30,32.8,'赵医生 · 初次接诊者'),(50,52.8,'接待室 · 补充询问')]:event(a,b,txt,r'\an7\pos(45,138)\fs23\bord2')
(P/'captions.ass').write_text(header+'\n'.join(ev)+'\n')
(P/'captions.srt').write_text('\n'.join(srt))
if not all((R/(i+'-raw.mp4')).exists() for i in ['01','03','04','05','06']):
 print('Prepared captions and score; waiting for six clips');raise SystemExit()
ns=[]
for c in cfg['clips']:
 if c['id']=='02': continue
 f=P/'edited'/(c['id']+'-raw.mp4')
 if not f.exists():f=R/(c['id']+'-raw.mp4')
 dest=P/(c['id']+'-normalized.mp4');frame=P/(c['id']+'-frame.jpg')
 if not dest.exists() or dest.stat().st_mtime<f.stat().st_mtime:
  run(['ffmpeg','-v','error','-y','-ss','2','-i',str(f),'-frames:v','1',str(frame)])
  im=np.asarray(Image.open(frame).convert('RGB'));h,w=im.shape[:2];ys=np.where((im.max(axis=2)>22).mean(axis=1)>.25)[0]
  top=int(ys[0])//2*2 if len(ys) else 0;bottom=(int(ys[-1])+1)//2*2 if len(ys) else h
  if top>h*.25 or bottom<h*.75 or bottom-top<h*.5:top,bottom=0,h
  top,bottom=48,376
  vf=f'crop={w}:{bottom-top}:0:{top},scale=1280:490:force_original_aspect_ratio=decrease,pad=1280:490:(ow-iw)/2:(oh-ih)/2:black,pad=1280:720:0:120:black,setsar=1,fps=30'
  run(['ffmpeg','-v','error','-y','-i',str(f),'-t','10','-vf',vf,'-af','aresample=48000,apad','-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-ar','48000','-ac','2',str(dest)])
 ns.append(dest)
(P/'concat.txt').write_text(''.join("file '"+str(f)+"'\n" for f in ns))
run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(P/'concat.txt'),'-c','copy',str(P/'assembled.mp4')])
print('Normalized five available clips; final edit pending')
