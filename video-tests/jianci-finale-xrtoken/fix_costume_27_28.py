import base64,json,os,re,subprocess,time,urllib.request,urllib.parse
from pathlib import Path
OUT=Path('output/jianci-finale-costume-fix');OUT.mkdir(parents=True,exist_ok=True)
HOST='https://api.xrtoken.ai';MODEL='wan3.0-video'
KEY=os.environ['XRTOKEN'].strip();assert KEY

def api(path,body=None):
 data=None if body is None else json.dumps(body,ensure_ascii=False).encode();req=urllib.request.Request(HOST+path,data=data,headers={'Authorization':'Bearer '+KEY,'Content-Type':'application/json'});return json.load(urllib.request.urlopen(req,timeout=90))
def dl(url,p):
 with urllib.request.urlopen(url,timeout=180) as f:p.write_bytes(f.read())
def task(tid,p):
 q=api('/v1/videos/generations/'+urllib.parse.quote(tid,safe=''));assert q.get('status')=='succeeded';u=q.get('video_url') or (q.get('content') or {}).get('video_url');assert u;dl(u,p)
def frame(tid,name,sec,crop):
 mp4=OUT/f'{name}.mp4';task(tid,mp4);jpg=OUT/f'{name}.jpg';cmd=['ffmpeg','-v','error','-y','-ss',str(sec),'-i',str(mp4),'-frames:v','1','-vf','crop='+crop,str(jpg)];subprocess.run(cmd,check=True);data='data:image/jpeg;base64,'+base64.b64encode(jpg.read_bytes()).decode();mp4.unlink();jpg.unlink();return data
def submit(name,prompt,refs):
 content=[{'type':'text','text':prompt}]+[{'type':'image_url','image_url':{'url':x},'role':'reference_image'} for x in refs]
 r=api('/v1/videos/generations',{'model':MODEL,'content':content,'duration':12,'resolution':'480P','ratio':'16:9','generate_audio':True,'watermark':False,'prompt_extend':False,'seed':906181});tid=r.get('id') or (r.get('data') or {}).get('id');assert isinstance(tid,str)
 end=time.monotonic()+2100
 while time.monotonic()<end:
  q=api('/v1/videos/generations/'+urllib.parse.quote(tid,safe=''));st=q.get('status')
  if st=='succeeded':
   u=q.get('video_url') or (q.get('content') or {}).get('video_url');p=OUT/f'{name}.mp4';dl(u,p);return {'id':name,'task_id':tid,'file':p.name}
  if st in ('failed','cancelled','expired'):raise RuntimeError(f'{name} {st}: {q.get("error","")}')
  time.sleep(12)
 raise TimeoutError(name)
def main():
 assert os.environ.get('GITHUB_RUN_ATTEMPT','1')=='1'
 # Use a verified present-day Jian frame from EP28 clip04: black turtleneck + dark gray jacket.
 jian=frame('8f2219f6-a0f0-4778-ad2a-d8311aae4582','jian-correct',2,'360:320:450:0')
 lin=frame('1af84fc1-63a2-4afc-bb82-6e79a07dcd4e','lin',1,'280:300:300:80')
 xu=frame('a8f8000e-6ef7-4714-aa1f-fb1a51f6c90c','xu',1,'360:300:250:0')
 p27='''12 seconds. Cinematic detailed hand-drawn 2D ANIME, cool blue-gray archive room, tense restrained forensic horror, realistic proportions. NO live action, NO 3D, NO gore, NO readable text, NO subtitles, NO music. Reference images are identity AND present-day clothing anchors. Jian MUST wear BLACK TURTLENECK and DARK GRAY CASUAL JACKET for the ENTIRE clip, absolutely NO white coat, NO lab coat, NO medical coat. Lin wears navy police uniform. Jian stands RIGHT, Lin LEFT, both positions stable. No flashback is shown; Jian only recounts a fragment of memory in the present, avoiding any unverified visual claim. At 0.45s Jian ON CAMERA says exactly in Mandarin: “我想起来一点。她把我推进储物间。”. At 5.65s Lin ON CAMERA says exactly: “看见第三个人了吗？”. At 8.35s Jian ON CAMERA says exactly: “没有。到这里就停。”. Only speaking person's mouth moves. No extra dialogue, no duplicate person, no outfit change, no teleport.'''
 p28='''12 seconds. Cinematic detailed hand-drawn 2D ANIME, cool blue-gray forensic lab, tense restrained atmosphere, realistic proportions. NO live action, NO 3D, NO gore, NO readable text, NO subtitles, NO music. Reference images are identity AND present-day clothing anchors. Jian MUST wear BLACK TURTLENECK and DARK GRAY CASUAL JACKET for the ENTIRE clip, absolutely NO white coat, NO lab coat, NO medical coat. Xu wears white forensic coat over muted green shirt and brown ponytail. Xu LEFT holds a sealed tiny historical hair evidence packet inside a transparent secondary container. Jian RIGHT stays behind the marked boundary, hands empty, never touches evidence. At 0.45s Xu ON CAMERA says exactly in Mandarin: “旧物里还有一小束头发，封存记录完整。”. At 7.40s Jian ON CAMERA says exactly: “这个可以不是记忆。”. Only speaking person's mouth moves. End on the sealed hair packet, no readable label. No extra dialogue, no outfit change, no duplicate person.'''
 rows=[];rows.append(submit('ep27-clip04-costume-fix',p27,[jian,lin]));rows.append(submit('ep28-clip05-costume-fix',p28,[xu,jian]));(OUT/'report.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print('COSTUME FIX READY')
if __name__=='__main__':main()
