from pathlib import Path
import json
p=Path('/tmp/jianci-production')
for ep in (17,18):
 e=p/f'edit/ep{ep}';e.mkdir(parents=True,exist_ok=True);cfg=json.loads((p/f'code/episode{ep}.json').read_text());l={x['id']:x['lines'] for x in cfg['clips']};segs=[]
 def add(cid,st,d,lines=[],repair=False,**kw):segs.append(dict(video=str(p/f'raw/ep{ep}{"-repair" if repair else ""}/{cid}-raw.mp4'),vstart=st,duration=d,lines=[l[cid][i]+[a,b] for i,a,b in lines],**kw))
 if ep==17:
  add('01',0,7.15,[(0,0,2.26),(1,2.84,6.88)],True,prefilter='delogo=x=545:y=255:w=130:h=75',label='次日 · 工作安排与情况说明')
  add('02',0,7.35,[(0,.02,7.06)],True,prefilter='delogo=x=545:y=255:w=130:h=75')
  add('03',0,5.68,[],telephone=True,label='9月3日 · 急救通话节选',label_duration=5.68)
  segs[-1]['lines']=[['caller','她说话含含糊糊的，站不稳。','Her speech is slurred. She is unsteady.',.18,2.78],['caller','对，还站着……','Yes, she is still standing...',3.74,5.68]]
  add('03',8.2,1.4,[],telephone=True,label='同一通话 · 随后',label_duration=1.4)
  segs[-1]['lines']=[['caller','她倒了！','She has fallen!',.14,1.16]]
  add('04',0,9.0,[(0,.02,5.5),(1,6.6,8.72)],crop='854:380:0:0',label='通话、现场影像与证人信息核对')
  add('05',0,11.1,[(0,.02,5.82),(1,7.18,10.8)],label='结合住院检查与原始病理复核')
  add('06',0,12.55,[(0,.11,8.79),(1,10.01,12.25)],True,label='补充调查及综合复核后',label_duration=3.2)
  add('07',0,8.4,[(0,0,3.68),(1,4.5,8.08)],crop='600:360:0:0',label='接待室 · 告知进展')
  add('08',0,3.15,[(0,0,2.78)],crop='854:380:0:0')
  overlays=[]
 else:
  add('01',0,9.7,[(0,0,2.66),(1,4.54,9.4)],True,label='此前 · 调查期间的谈话',label_duration=3.2)
  add('02',0,1.3,[(0,.08,1.02)])
  add('03',0,12.75,[(0,.08,4.8),(1,5.52,12.46)])
  add('04',0,9.4,[(0,0,1.28),(1,2.16,9.1)],crop='854:380:0:0')
  add('05',0,5.15,[(0,.05,4.83)],True,prefilter='delogo=x=545:y=255:w=130:h=75')
  add('06',0,11.3,[(0,.08,6.3),(1,7.3,11)],crop='590:380:0:0')
  start=sum(x['duration'] for x in segs)
  segs.append(dict(video=str(p/'raw/ep17/08-raw.mp4'),vstart=3.3,duration=4.6,mute=True,lines=[],label='数月后 · 审理结果',label_duration=4.6))
  overlays=[dict(start=start,end=start+4.6,text='经审理，陆承安因对知微实施暴力\\N并造成死亡，被判有罪。',tags=r'\an5\pos(640,690)\fs34\bord3\shad1'),dict(start=start,end=start+4.6,text="Following trial, Lu Cheng'an was convicted\\Nfor the violence that caused Zhiwei's death.",tags=r'\an2\pos(640,936)\fs25')]
  add('08',0,8.8,[(0,.18,4.86)],True,label='母亲家中 · 夜',label_duration=2)
 (e/'edit.json').write_text(json.dumps(dict(segments=segs,overlays=overlays),ensure_ascii=False,indent=2))
# Keep long bilingual captions inside the lower title-safe strip.
f=p/'code/render_episode.py';s=f.read_text();s=s.replace("add(aa,bb,name+'：'+cn,r'\\an2\\pos(640,881)\\fs34')","add(aa,bb,name+'：'+cn,r'\\an2\\pos(640,876)\\fs'+str(34 if len(name+cn)<34 else 30 if len(name+cn)<40 else 26))");s=s.replace(r'\an2\pos(640,938)\fs25',r'\an2\pos(640,946)\fs24');f.write_text(s)
