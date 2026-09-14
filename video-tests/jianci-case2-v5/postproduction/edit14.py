from pathlib import Path
import json
p=Path('/tmp/jianci-production');e=p/'edit/ep14';e.mkdir(parents=True,exist_ok=True)
c=json.loads((p/'code/episode14.json').read_text());l={x['id']:x['lines'] for x in c['clips']};segs=[]
def add(cid,st,d,lines=[],repair=False,**kw):
 segs.append(dict(video=str(p/f'raw/ep14{"-repair" if repair else ""}/{cid}-raw.mp4'),vstart=st,duration=d,lines=[l[cid][i]+[a,b] for i,a,b in lines],**kw))
add('01',0,8.3,[(0,.4,4.14),(1,5.22,8)],True,label='接待室 · 接续第13集')
add('02',.6,7.45,[(0,.28,3.92),(1,4.5,7.14)],True)
add('03',0,7.45,[(0,.11,4.67),(1,5.17,6.57)])
add('03',8.15,1.8)
add('04',0,5.35,[(0,.18,4.98)],True,label='稍后 · 法医资料复核')
add('05',6.2,3.45,[(0,.11,2.79)],audio=str(p/'raw/ep14/05-raw.mp4'),astart=0,label='现存检材 · 当前复核')
add('06',0,5.55,[(0,0,5.3)],True,label='首次尸检 · 回溯',label_duration=5.55)
add('07',0,9.8,[(0,.08,4.94),(1,4.94,9.42)],label='原始会话核实后')
add('08',0,3.3,[(0,.34,1.8)],crop='854:328:0:74')
add('04',8.1,.8,[],True,mute=True)
add('08',3.3,6.7,[(0,.32,1.86),(1,3.95,6.37)],crop='854:328:0:74')
# Split the sentence around a deliberate silent listening beat, with no repeated frames.
segs[-3]['lines'][0][1]='颈痛有很多原因。';segs[-3]['lines'][0][2]='Neck pain has many causes.'
segs[-1]['lines'][0][1]='先别把它当成那处伤。';segs[-1]['lines'][0][2]='We cannot equate it with that injury yet.'
starts=[];t=0
for x in segs:starts.append(t);t+=x['duration']
overlays=[dict(start=starts[7]+.1,end=starts[7]+2.4,text='9月2日 19:42 · 生前消息'),dict(start=starts[7]+2.5,end=starts[7]+4.85,text='9月3日下午 · 跌倒送医')]
(e/'edit.json').write_text(json.dumps(dict(segments=segs,overlays=overlays,sounds=[dict(type='knock',time=starts[8]+2.85),dict(type='knock',time=starts[8]+3.04)]),ensure_ascii=False,indent=2))
# Remove the unmotivated radio gesture; carry Lin's line over her open case notes.
x=segs.pop();a=dict(x);a['duration']=3.6;a['lines']=[x['lines'][0]];segs.append(a)
b=dict(x);b['vstart']=6.9;b['duration']=3.1;b['crop']='410:230:0:100';b['lines']=[x['lines'][1][:3]+[.35,2.77]];segs.append(b)
(e/'edit.json').write_text(json.dumps(dict(segments=segs,overlays=overlays,sounds=[dict(type='knock',time=starts[8]+2.85),dict(type='knock',time=starts[8]+3.04)]),ensure_ascii=False,indent=2))
