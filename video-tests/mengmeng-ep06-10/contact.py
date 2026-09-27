from pathlib import Path
from PIL import Image,ImageDraw
import subprocess,json,sys
P=Path(__file__).resolve().parent;R=P/'raw';D=P/'review';D.mkdir(exist_ok=True)
for n in range(6,11):
 for group in range(3):
  im=Image.new('RGB',(1020,4*217),'#14202c');dr=ImageDraw.Draw(im)
  for row,shot in enumerate(range(group*4+1,group*4+5)):
   cid=f'{n:02}_{shot:02}';dr.text((8,row*217+4),f'{cid}   0.7s                            2.5s                         end',fill='white')
   for col,label in enumerate(['a','b','end']):
    f=R/(cid+'-'+label+'.jpg')
    if f.exists():im.paste(Image.open(f).resize((340,191)),(col*340,row*217+24))
  im.save(D/f'ep{n:02}-{group+1}.jpg')
print(D)
