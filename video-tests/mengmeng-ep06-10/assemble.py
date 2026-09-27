from pathlib import Path
import json,subprocess,math,wave,sys,os
import numpy as np
P=Path(__file__).resolve().parent; RAW=P/'raw';W=P/'edit';W.mkdir(exist_ok=True);OUT=P/'final';OUT.mkdir(exist_ok=True)
F=P.parent/'two-fix/fonts';cfg=json.load(open(P/'episodes.json'));trans=json.load(open(RAW/'transcripts.json')) if (RAW/'transcripts.json').exists() else {}
STYLE='''[Script Info]
ScriptType: v4.00+
PlayResX: 854
PlayResY: 480
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Header,Noto Sans CJK SC,27,&H00F4F6FA,&H00FFFFFF,&H00101824,&H00101824,-1,0,0,0,100,100,0,0,1,0,0,8,15,15,4,1
Style: Sub,Noto Sans CJK SC,27,&H00FFFFFF,&H00FFFFFF,&H00101824,&H00101824,0,0,0,0,100,100,0,0,1,2,0.5,2,17,17,14,1
Style: Time,Noto Sans CJK SC,34,&H00FFFFFF,&H00FFFFFF,&H00101824,&H00101824,-1,0,0,0,100,100,0,0,1,2,0,5,10,10,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def run(a):subprocess.run(['ffmpeg','-y','-v','error',*map(str,a)],check=True)
def enc():return ['-c:v','libx264','-threads','2','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2','-b:a','160k']
def clock(t):return f'{int(t)//3600}:{int(t)//60%60:02}:{t%60:05.2f}'
def music(n):
 sr=24000;x=np.zeros(sr*60,dtype=np.float32);rng=np.random.default_rng(900+n)
 # Original very quiet plucked pentatonic cue, gaps leave room for dialogue.
 notes=[60,64,67,69,67,64,62,67,71,69,67,64]
 for i,beat in enumerate(np.arange(1,59,1.25)):
  if n in [9,10] and 11<beat<43:continue
  if i%4==3:continue
  midi=notes[(i+n)%len(notes)];f=440*2**((midi-69)/12);dur=.55;t=np.arange(int(sr*dur))/sr
  tone=(np.sin(2*np.pi*f*t)+.28*np.sin(2*np.pi*f*2*t)+.12*np.sin(2*np.pi*f*3*t))*np.exp(-7*t)*np.minimum(1,t/.009)*.019
  a=int(beat*sr);x[a:a+len(tone)]+=tone
 x*=np.minimum(1,np.arange(len(x))/sr/1.5)*np.minimum(1,(len(x)-np.arange(len(x)))/sr/1.5)
 p=W/f'music{n:02}.wav'
 with wave.open(str(p),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr);w.writeframes((x*32767).astype('<i2').tobytes())
 return p
for e in cfg['episodes']:
 n=e['episode']
 if len(sys.argv)>1 and n!=int(sys.argv[1]):continue
 paths=[]
 for c in e['clips']:
  cid=c['id'];src=RAW/(cid+'-raw.mp4');replacement=P/'corrected'/(cid+'-raw.mp4');src=replacement if replacement.exists() else src;assert src.is_file(),src
  c=dict(c)
  if cid=='07_01':c.update(zh='等一下，我能救……我能救。',en='Wait. I can save this... I can save this.')
  txt=STYLE+f'Dialogue: 2,0:00:00.00,0:00:05.00,Header,,0,0,0,,萌萌谈与全城精灵\\N{{\\fs19\\b0}}第{n}集 · {e["title"]}  |  制作：林爱丽\n'
  if c['zh']:
   segs=trans.get(cid,{}).get('segments',[]);start=max(.05,min(4.0,segs[0]['start']-.07 if segs else .25));end=min(4.95,max(3.7,segs[-1]['end']+.15 if segs else 4.75))
   start=max(start,{'08_01':3.05,'09_01':2.92,'10_01':2.56}.get(cid,0))
   txt+=f'Dialogue: 1,{clock(start)},{clock(end)},Sub,,0,0,0,,{c["speaker"]}：{c["zh"]}\\N{{\\fs17}}{c["en"]}\n'
  labels={'07_02':'回回能力：倒退8秒','07_05':'再次倒退8秒','08_02':'随便标签：帽子','08_05':'随便标签：优惠券','08_11':'这次自己选：家'}
  if cid in labels:txt+=f'Dialogue: 3,0:00:01.30,0:00:04.50,Time,,0,0,0,,{{\\an7\\pos(77,86)\\fs21}}{labels[cid]}\n'
  if cid=='09_07':txt+='Dialogue: 3,0:00:00.30,0:00:03.50,Time,,0,0,0,,3分钟后\\N{\\fs21}Three minutes later\n'
  if cid=='10_02':txt+='Dialogue: 1,0:00:00.40,0:00:02.20,Time,,0,0,0,,{\\an7\\pos(78,88)\\fs21}便签：记得找自己\n'
  ass=W/(cid+'.ass');ass.write_text(txt);dst=W/(cid+'.mp4')
  vf=f'crop=iw:ih-28:0:0,scale=736:390,pad=854:480:59:66:color=0x101824,fps=24,setsar=1,ass={ass}:fontsdir={F}'
  run(['-i',src,'-t',5,'-vf',vf,'-af','aresample=async=1:first_pts=0,apad,atrim=duration=5,afade=t=in:d=0.012,afade=t=out:st=4.98:d=0.02',*enc(),dst]);paths.append(dst)
 cat=W/f'concat{n:02}.txt';cat.write_text(''.join(f"file '{p}'\n" for p in paths))
 clean=W/f'joined{n:02}.mp4';run(['-f','concat','-safe',0,'-i',cat,'-t',60,'-c','copy',clean])
 dest=OUT/f'萌萌谈_EP{n:02}_{e["title"]}.mp4'
 run(['-i',clean,'-i',music(n),'-filter_complex','[0:a]loudnorm=I=-18:TP=-1.5:LRA=8[d];[d][1:a]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=false[a]','-map','0:v','-map','[a]','-t',60,'-c:v','copy','-c:a','aac','-b:a','192k','-movflags','+faststart',dest])
 run(['-xerror','-i',dest,'-f','null','-']);atomic=dest.with_suffix('.ready.mp4');atomic.write_bytes(dest.read_bytes());os.replace(atomic,dest);print(dest,flush=True)
