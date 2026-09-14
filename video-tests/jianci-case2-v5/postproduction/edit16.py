from pathlib import Path
import json
p=Path('/tmp/jianci-production');e=p/'edit/ep16';e.mkdir(parents=True,exist_ok=True);c=json.loads((p/'code/episode16.json').read_text());l={x['id']:x['lines'] for x in c['clips']};segs=[]
def add(cid,st,d,lines=[],**kw):segs.append(dict(video=str(p/f'raw/ep16/{cid}-raw.mp4'),vstart=st,duration=d,lines=[l[cid][i]+[a,b] for i,a,b in lines],**kw))
segs.append(dict(video=str(p/'raw/ep16-valid-reference/01-raw.mp4'),vstart=0,duration=10,lines=[l['01'][0]+[0,2.72]],label='9月2日 · 店内事件回溯',label_duration=10))
add('02',0,7.45,[(0,.02,3.58),(1,4.38,7.14)],crop='560:350:0:10',label='讯问室 · 核对录像所见')
add('03',0,11.2,[(0,.18,6.1),(1,7.48,10.92)],label='法医复核 · 结合个案资料')
add('04',0,10.2,[(0,0,6.64),(1,7.9,9.92)],label='调查组 · 核实先后顺序')
add('05',0,10/.9,[(0,1.36/.9,3.16/.9),(1,3.72/.9,6.06/.9)],rate=.9)
add('06',0,9.9,[(0,0,2.98),(1,2.98,9.58)],crop='500:400:340:0',label='隔壁休息室 · 片刻后')
add('07',0,3.1,[(0,.08,2.88)])
add('08',0,10.5,[(0,.02,8.48),(1,9.16,10.22)],crop='854:380:0:0')
add('09',0,4.3,[(0,0,3.24)],crop='854:380:0:0')
(e/'edit.json').write_text(json.dumps(dict(segments=segs,sounds=[dict(type='heartbeat',time=39.5),dict(type='heartbeat',time=40.6)]),ensure_ascii=False,indent=2))
