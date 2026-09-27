from pathlib import Path
import subprocess,json
from PIL import Image,ImageDraw
P=Path(__file__).resolve().parent;cfg=json.load(open(P/'episodes.json'));out=[]
sheet=Image.new('RGB',(960,5*210),'#15202b');dr=ImageDraw.Draw(sheet)
for row,e in enumerate(cfg['episodes']):
 n=e['episode'];f=P/'final'/f'萌萌谈_EP{n:02}_{e["title"]}.mp4';assert f.is_file(),f
 info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(f)]));d=float(info['format']['duration'])
 assert abs(d-60)<.1,(f,d)
 assert any(s['codec_type']=='audio' for s in info['streams'])
 dr.text((8,row*210+3),f'EP{n:02}: 3s / 30s / 57s',fill='white')
 for col,at in enumerate([3,30,57]):
  p=P/'review'/f'final{n:02}-{at}.jpg';subprocess.run(['ffmpeg','-y','-v','error','-ss',str(at),'-i',str(f),'-frames:v','1',str(p)],check=True)
  sheet.paste(Image.open(p).resize((320,180)),(col*320,row*210+23))
 out.append({'episode':n,'title':e['title'],'local_path':str(f),'duration':d,'bytes':f.stat().st_size,'has_audio':True})
(P/'work/final-verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));sheet.save(P/'review/final-contact.jpg');print(json.dumps(out,ensure_ascii=False,indent=2))
