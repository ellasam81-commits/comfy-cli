import json, subprocess, wave
from pathlib import Path
import numpy as np
from PIL import Image
P=Path('/tmp/ep13-work')
R=P/'raw'
OUT=Path('/workspace/scratch/6651942d1ae0/剑刺_第13集_你看见了_中英字幕_BGM.mp4')
cfg=json.loads((P/'episode.json').read_text())

def run(args):
 subprocess.run(args,check=True)

def stamp(t):
 h=int(t//3600);m=int(t%3600//60);s=t%60
 return f'{h}:{m:02}:{s:05.2f}'

def esc(t):
 return t.replace('’', chr(39)).replace('\\','').replace('{','').replace('}','')

# Synthesized original suspense score: low drones and sparse decaying tones.
sr=24000;t=np.arange(sr*90,dtype=np.float64)/sr
score=np.zeros_like(t)
for f,amp,phase in [(55,.021,.1),(82.41,.010,1.2),(110,.006,2.3),(116.54,.004,.8)]:
 score+=amp*np.sin(2*np.pi*f*t+0.12*np.sin(2*np.pi*.11*t+phase))*(.75+.25*np.sin(2*np.pi*.06*t+phase))
for start,f in [(0,220),(20,164.81),(29,196),(39,146.83),(49,164.81),(61,220),(70,207.65),(78,146.83),(85,110)]:
 u=np.maximum(t-start,0);env=(t>=start)*(1-np.exp(-u*9))*np.exp(-u/2.5)
 score+=.013*env*(np.sin(2*np.pi*f*u)+.24*np.sin(2*np.pi*f*2.006*u))
score*=np.minimum(t/1.8,1)*np.minimum((90-t)/1.5,1)
# Keep Lin's nod nearly silent and pause score at the case change.
score[(t>=15)&(t<20)]*=.1
score[(t>=59.5)&(t<60.5)]*=0
with wave.open(str(P/'score.wav'),'wb') as w:
 w.setnchannels(2);w.setsampwidth(2);w.setframerate(sr)
 stereo=np.column_stack([score,score*.94])
 w.writeframes((np.clip(stereo,-1,1)*32767).astype('<i2').tobytes())

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
events=[]
def event(start,end,text,tag='',layer=0):
 events.append(f'Dialogue: {layer},{stamp(start)},{stamp(end)},Default,,0,0,0,,{{{tag}}}{esc(text)}')
for start,end,case,source,en in [(0,60,'屋里还有一个人','真实案件灵感：1922年德国欣特凯费克农场案','Hinterkaifeck, 1922 · 现代人物、情节与吸血鬼设定为虚构'),(60,90,'她回来以后','真实案件灵感：1897年格林布赖尔幽灵案','Greenbrier, 1897 · 母亲见鬼为其说法；现代人物与情节虚构')]:
 event(start,end,'剑刺',r'\an7\pos(40,18)\fs40')
 event(start,end,case+' · 第13集：你看见了',r'\an7\pos(145,27)\fs28')
 event(start,end,'作者：林爱丽',r'\an9\pos(1240,27)\fs24')
 event(start,end,source,r'\an7\pos(40,65)\fs20')
 event(start,end,en,r'\an7\pos(40,92)\fs17')
# Optional reviewed timing overrides keyed by clip and slot.
overrides=json.loads((P/'timings.json').read_text()) if (P/'timings.json').exists() else {}
for idx,c in enumerate(cfg['clips']):
 for j,slot in enumerate(c['subtitle_slots']):
  zh=slot['zh'];en=slot['en']
  if '无对白' in zh: continue
  zh=zh.replace('（画外）','').replace('（画外音）','')
  a,b=overrides.get(f'{idx+1:02d}-{j}',[slot['start']+.25,slot['end']-.15])
  event(idx*10+a,idx*10+b,zh,r'\an2\pos(640,661)\fs34')
  event(idx*10+a,idx*10+b,en,r'\an2\pos(640,699)\fs26')
event(20,24.8,'三天后 · 案情复核',r'\an7\pos(45,138)\fs23\bord2')
event(20.6,24.7,'尸检：颈部受压致死',r'\an7\pos(45,179)\fs21\bord2')
event(45.3,47.5,'梁川持卡影像',r'\an7\pos(45,138)\fs23\bord2')
event(47.5,49.7,'罗茵设备／威胁账号',r'\an7\pos(45,138)\fs23\bord2')
(P/'captions.ass').write_text(header+'\n'.join(events)+'\n')
if not (R/'01-raw.mp4').exists():
 print('Prepared score and captions; waiting for raw video')
 raise SystemExit()
normalized=[]
for c in cfg['clips']:
 f=(P/'edited'/(c['id']+'-raw.mp4')) if (P/'edited'/(c['id']+'-raw.mp4')).exists() else R/(c['id']+'-raw.mp4');dest=P/(c['id']+'-normalized.mp4');frame=P/(c['id']+'-cropcheck.png')
 if not f.exists(): continue
 if dest.exists() and dest.stat().st_mtime >= f.stat().st_mtime:
  normalized.append(dest)
  continue
 run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss','2','-i',str(f),'-frames:v','1',str(frame)])
 im=np.asarray(Image.open(frame).convert('RGB'));h,w=im.shape[:2]
 rows=(im.max(axis=2)>22).mean(axis=1);ys=np.where(rows>.25)[0]
 top=int(ys[0])//2*2 if len(ys) else 0;bottom=(int(ys[-1])+1)//2*2 if len(ys) else h
 # Only remove contiguous letterbox margins, not arbitrary dark scene content.
 if top>h*.25 or bottom<h*.75 or bottom-top<h*.5: top,bottom=0,h
 vf=f'crop={w}:{bottom-top}:0:{top},scale=1280:490:force_original_aspect_ratio=decrease,pad=1280:490:(ow-iw)/2:(oh-ih)/2:black,pad=1280:720:0:120:black,setsar=1,fps=30'
 run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(f),'-t','10','-vf',vf,'-af','aresample=48000,apad','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2',str(dest)])
 normalized.append(dest)
if len(normalized)!=9:
 print('Normalized',len(normalized),'clips; waiting for missing outputs')
 raise SystemExit()
(P/'concat.txt').write_text(''.join("file '"+str(f)+"'\n" for f in normalized))
run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(P/'concat.txt'),'-c','copy',str(P/'assembled.mp4')])
flt=f"[0:a]asplit=2[voice][sc];[1:a][sc]sidechaincompress=threshold=0.015:ratio=8:attack=15:release=350[bg];[voice][bg]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a];[0:v]ass={P/'captions.ass'}:fontsdir={P}[v]"
run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(P/'assembled.mp4'),'-i',str(P/'score.wav'),'-filter_complex',flt,'-map','[v]','-map','[a]','-t','90','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(OUT)])
print(OUT)
