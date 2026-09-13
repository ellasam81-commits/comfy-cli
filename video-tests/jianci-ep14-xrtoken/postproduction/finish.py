import json,subprocess,shutil
from pathlib import Path
P=Path('/tmp/ep14-work');ROOT=Path('/workspace/scratch/6651942d1ae0')
cfg=json.loads((P/'episode.json').read_text());over=json.loads((P/'timings.json').read_text())
# Remove the failed conversational digression and its unanswered setup question.
# No substitute repeated reaction, no new paid submissions.
cuts=json.loads((P/'cuts.json').read_text())
T=sum(b-a for _,a,b in cuts)
out=ROOT/'剑刺_第14集_她说脖子疼_中英字幕_BGM.mp4'
inputs=[];filters=[];labels=[];cursor=0;mapping=[]
for n,(cid,a,b) in enumerate(cuts):
 inputs+=['-i',str(P/(cid+'-normalized.mp4'))]
 filters += [f'[{n}:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{n}]',f'[{n}:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.012,afade=t=out:st={b-a-.012}:d=0.012[a{n}]']
 labels.append(f'[v{n}][a{n}]');mapping.append((cid,a,b,cursor));cursor+=b-a
filters.append(''.join(labels)+f'concat=n={len(cuts)}:v=1:a=1[v][a]')
subprocess.run(['ffmpeg','-v','error','-y']+inputs+['-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-b:a','192k',str(P/'cut.mp4')],check=True)
header=(P/'captions.ass').read_text().split('Dialogue:')[0];events=[];srt=[]
def stamp(t):return f'{int(t//3600)}:{int(t%3600//60):02}:{t%60:05.2f}'
def event(a,b,txt,tag):events.append(f'Dialogue: 0,{stamp(a)},{stamp(b)},Default,,0,0,0,,{{{tag}}}'+txt.replace('’',"'"))
event(0,T,'剑刺',r'\an7\pos(40,18)\fs40')
event(0,T,'她回来以后 · 第14集：她说脖子疼',r'\an7\pos(145,27)\fs28')
event(0,T,'作者：林爱丽',r'\an9\pos(1240,27)\fs24')
event(0,T,'真实案件灵感：1897年格林布赖尔幽灵案',r'\an7\pos(40,65)\fs20')
event(0,T,'Greenbrier, 1897 · 母亲见鬼为其说法；现代人物与情节虚构',r'\an7\pos(40,92)\fs17')
for cid,a,b,start in mapping:
 c=next(c for c in cfg['clips'] if c['id']==cid)
 for j,d in enumerate(c['dialogue']):
  aa,bb=over[cid+'-'+str(j)];aa=max(aa,a);bb=min(bb,b)
  if bb<=aa:continue
  aa=aa-a+start;bb=bb-a+start
  event(aa,bb,d['speaker']+'：'+d['zh'],r'\an2\pos(640,661)\fs34')
  event(aa,bb,d['en'],r'\an2\pos(640,699)\fs25')
  def st(x):return f'{int(x//3600):02}:{int(x%3600//60):02}:{int(x%60):02},{round((x%1)*1000):03}'
  srt.append(f"{len(srt)+1}\n{st(aa)} --> {st(bb)}\n{d['speaker']}：{d['zh']}\n{d['en']}\n")
 label={'03':'次日 · 初检记录复核','04':'赵医生 · 初次接诊者','06':'接待室 · 补充询问'}.get(cid)
 if label:event(start,min(start+2.5,T),label,r'\an7\pos(45,138)\fs23\bord2')
(P/'final.ass').write_text(header+'\n'.join(events)+'\n');(ROOT/'剑刺_第14集_中英字幕.srt').write_text('\n'.join(srt))
f=f"[1:a]atrim=duration={T},afade=t=out:st={T-1}:d=1[score];[0:a]asplit[voice][sc];[score][sc]sidechaincompress=threshold=0.05:ratio=3:attack=25:release=500[bg];[voice][bg]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=0[a];[0:v]ass={P/'final.ass'}:fontsdir={P}[v]"
subprocess.run(['ffmpeg','-v','error','-y','-i',str(P/'cut.mp4'),'-i',str(P/'score.wav'),'-filter_complex',f,'-map','[v]','-map','[a]','-t',str(T),'-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(out)],check=True)
(P/'final_mapping.json').write_text(json.dumps({'duration':T,'cuts':mapping},indent=2))
print(out,T)
