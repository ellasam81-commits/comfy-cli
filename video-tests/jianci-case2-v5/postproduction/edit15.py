from pathlib import Path
import json
p=Path('/tmp/jianci-production');e=p/'edit/ep15';e.mkdir(parents=True,exist_ok=True);c=json.loads((p/'code/episode15.json').read_text());l={x['id']:x['lines'] for x in c['clips']};segs=[]
def add(cid,st,d,lines=[],repair=False,**kw):segs.append(dict(video=str(p/f'raw/ep15{"-repair" if repair else ""}/{cid}-raw.mp4'),vstart=st,duration=d,lines=[l[cid][i]+[a,b] for i,a,b in lines],**kw))
add('01',0,8.95,[(0,0,2.6),(1,3.84,8.66)],True,crop='854:380:0:0',label='接待室 · 补充询问')
add('02',0,8.2,[(0,0,1.96),(1,3.9,7.94)],True,crop='854:380:0:0')
add('03',0,4.98,[(0,.18,2.66),(1,3.56,4.74)],label='修复店 · 核实行踪')
add('04',0,3.15,[(0,.02,2.82)])
add('05',0,2.55,[(0,0,2)],True,label='邻近摄像头 · 核实拍摄范围')
add('05',3.05,3.2,[(1,.15,2.89)],True,crop='350:198:0:35')
add('06',0,10.7,[(0,.02,6.22),(1,7,10.42)],label='法医复核 · 仍需现场与生前记录')
add('07',0,6.55,[(0,.08,5.14),(1,5.14,6.3)],label='接待室 · 稍后')
segs.append(dict(video=str(p/'old/e13/08-raw.mp4'),vstart=8,duration=1.6,mute=True,crop='854:328:0:74',lines=[]))
add('08',0,4.4,[(0,1.3,3.16)],crop='854:380:0:0')
add('08',8.9,1.05,[],mute=True,crop='410:230:390:250')
add('09',0,3.35,[(0,.32,3.04)],label='原录像核查')
st=[];t=0
for x in segs:st.append(t);t+=x['duration']
(e/'edit.json').write_text(json.dumps(dict(segments=segs,sounds=[dict(type='heartbeat',time=st[9]+.25),dict(type='heartbeat',time=st[9]+1.15)]),ensure_ascii=False,indent=2))
segs[4]['lines']=[['zhou','这个镜头能拍到入口。','That camera covers the entrance.',0,2]]
segs[5]['lines']=[['zhou','先看原机。','Check the original recorder first.',.15,1.09],l['05'][1]+[1.51,2.89]]
(e/'edit.json').write_text(json.dumps(dict(segments=segs,sounds=[dict(type='heartbeat',time=st[9]+.25),dict(type='heartbeat',time=st[9]+1.15)]),ensure_ascii=False,indent=2))
