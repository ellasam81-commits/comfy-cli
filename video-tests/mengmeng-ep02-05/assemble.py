from pathlib import Path
import argparse,json,re,subprocess
ROOT=Path('/workspace/scratch/b4c0488cda29');SOURCE=ROOT/'ep02-05-source';RAW=ROOT/'output/mengmeng-ep02-05'
def run(args):
 r=subprocess.run(args,capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stderr[-2000:])
def stamp(t):
 n=round(t*100);return f'{n//360000}:{n//6000%60:02}:{n//100%60:02}.{n%100:02}'
ap=argparse.ArgumentParser();ap.add_argument('--episode',type=int);ap.add_argument('--prepare',action='store_true');args=ap.parse_args()
cfg=json.loads((SOURCE/'episodes.json').read_text());qa=json.loads((RAW/'transcripts.json').read_text())
overrides=json.loads((SOURCE/'edit_overrides.json').read_text()) if (SOURCE/'edit_overrides.json').exists() else {}
style='''[Script Info]
ScriptType: v4.00+
PlayResX: 854
PlayResY: 480
WrapStyle: 0
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Header,Noto Sans CJK SC,36,&H00F1F5FA,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,8,20,20,6,1
Style: Sub,Noto Sans CJK SC,34,&H00FFFFFF,&H00FFFFFF,&H0017100A,&H0017100A,0,0,0,0,100,100,0,0,1,2,0.4,2,28,28,15,1
Style: Note,Noto Sans CJK SC,27,&H009EEBFF,&H00FFFFFF,&H0017100A,&H0017100A,-1,0,0,0,100,100,0,0,1,2,0,7,28,28,84,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
names={2:'第二集',3:'第三集',4:'第四集',5:'第五集'}
for ep in cfg['episodes']:
 n=ep['episode']
 if args.episode and n!=args.episode:continue
 if not args.prepare and any(not (RAW/(c['id']+'-raw.mp4')).exists() or c['id'] not in qa for c in ep['clips']):print('Not ready',n);continue
 work=RAW/f'ep{n:02}-edit';work.mkdir(exist_ok=True)
 total=sum(overrides.get(c['id'],{}).get('duration',5) for c in ep['clips'])
 offset=0
 ass=style+f"Dialogue: 2,0:00:00.00,{stamp(total)},Header,,0,0,0,,萌萌谈与全城精灵\\N{{\\fs25\\b0}}{names[n]} · {ep['title']}  |  制作：林爱丽\n"
 if n==2:ass+='Dialogue: 1,0:00:00.04,0:00:01.80,Note,,0,0,0,,次日早晨\n'
 if n==4:
  cue=sum(overrides.get(c['id'],{}).get('duration',5) for c in ep['clips'][:10])
  ass+=f'Dialogue: 1,{stamp(cue+.02)},{stamp(cue+1.8)},Note,,0,0,0,,五分钟后\n'
 labels={2:(10.1,13.6,'团团 · 没事兽'),3:(5.1,8.6,'嘴嘴 · 嘴硬鸭'),4:(5.1,8.6,'灰五 · 拖延鸽'),5:(5.1,8.6,'逃逃 · 社恐兔')}
 st,ed,label=labels[n];ass+=f'Dialogue: 1,{stamp(st)},{stamp(ed)},Note,,0,0,0,,本集精灵：{label}\n'
 outputs=[]
 for c in ep['clips']:
  i=c['id'];out=work/(i+'.mp4');patch=overrides.get(i,{})
  if not (RAW/(i+'-raw.mp4')).exists():continue
  duration=patch.get('duration',5);inpoint=patch.get('inpoint',0)
  vf=patch.get('vf','scale=854:480,fps=24,setsar=1');af=patch.get('af','anull')
  valid=out.exists() and subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(out)],capture_output=True).returncode==0
  if not valid or patch.get('rerender'):
   staged=out.with_suffix('.building.mp4')
   run(['ffmpeg','-y','-v','error','-xerror','-ss',str(inpoint),'-i',str(RAW/(i+'-raw.mp4')),'-t',str(duration),'-vf',vf,'-af',af+f',afade=t=in:d=0.01,afade=t=out:st={duration-.02}:d=0.02,apad','-c:v','libx264','-threads','2','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2','-b:a','160k',str(staged)])
   staged.replace(out)
  outputs.append(out)
  if args.prepare:continue
  segs=qa[i];start=max(.03,min((x['start'] for x in segs),default=.1)-inpoint);end=min(duration-.06,max((x['end'] for x in segs),default=4.5)-inpoint+.15)
  start,end=patch.get('sub_start',start),patch.get('sub_end',end)
  zh=patch.get('zh',c['zh']);en=patch.get('en',c['en'])
  ass+=f'Dialogue: 1,{stamp(offset+start)},{stamp(offset+end)},Sub,,0,0,0,,{zh}\\N{{\\fs22}}{en}\n'
  offset+=duration
 if args.prepare:
  print('Prepared',n,len(outputs),'shots',flush=True);continue
 (work/'subs.ass').write_text(ass)
 (work/'concat.txt').write_text(''.join(f"file '{p}'\n" for p in outputs))
 run(['ffmpeg','-y','-v','error','-xerror','-f','concat','-safe','0','-i',str(work/'concat.txt'),'-c:v','copy','-af','aresample=async=1:first_pts=0','-c:a','aac','-b:a','192k',str(work/'joined.building.mp4')])
 (work/'joined.building.mp4').replace(work/'joined.mp4')
 title=re.sub('[“”"?？!！]','',ep['title']);final=RAW/f'萌萌谈_EP{n:02}_{title}.mp4'
 run(['ffmpeg','-y','-v','error','-xerror','-i',str(work/'joined.mp4'),'-t',str(total),'-vf',f'scale=736:414,pad=854:480:59:66:color=0x101824,ass={work / "subs.ass"}:fontsdir={ROOT / "names-source/fonts"}','-af','alimiter=limit=0.95:level=false','-c:v','libx264','-threads','2','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(final.with_suffix('.building.mp4'))])
 final.with_suffix('.building.mp4').replace(final)
 print('FINAL',n,str(final),final.stat().st_size,flush=True)
