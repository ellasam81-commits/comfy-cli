from pathlib import Path
import subprocess,json
P=Path(__file__).resolve().parent
SRC=P.parent/'ending-fix/source/萌萌谈_EP04_拖延鸽把咖啡推迟了五分钟.mp4'
N=P/'new'; F=P/'fonts';W=P/'edit';W.mkdir(exist_ok=True)
def run(a):subprocess.run(['ffmpeg','-y','-v','error','-xerror',*map(str,a)],check=True)
def enc():return ['-c:v','libx264','-threads','2','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2','-b:a','192k']
style='''[Script Info]
ScriptType: v4.00+
PlayResX: 854
PlayResY: 480
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Header,Noto Sans CJK SC,36,&H00F1F5FA,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,8,20,20,6,1
Style: Sub,Noto Sans CJK SC,34,&H00FFFFFF,&H00FFFFFF,&H0017100A,&H0017100A,0,0,0,0,100,100,0,0,1,2,0.4,2,28,28,15,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 2,0:00:00.00,0:00:05.00,Header,,0,0,0,,萌萌谈与全城精灵\\N{\\fs25\\b0}第四集 · 拖延鸽把咖啡推迟了五分钟  |  制作：林爱丽
'''
(W/'09.ass').write_text(style+'Dialogue: 1,0:00:00.10,0:00:03.20,Sub,,0,0,0,,萌萌谈：文件我来压。灰五，你去睡。\\N{\\fs22}I will hold the papers. Huiwu, go get some sleep.\n')
(W/'12.ass').write_text(style+'Dialogue: 1,0:00:00.10,0:00:02.15,Sub,,0,0,0,,煤球：萌萌谈，咖啡好了！\\N{\\fs22}Mengmeng Tan, your coffee is ready!\nDialogue: 1,0:00:02.45,0:00:04.98,Sub,,0,0,0,,煤球：咖啡上班了，人下班了。\\N{\\fs22}Coffee is on duty. He has clocked out.\n')
for name,start,duration in [('a',0,38),('b',43,10)]:
 run(['-ss',start,'-i',SRC,'-t',duration,'-vf','fps=24,setsar=1','-af','aresample=async=1:first_pts=0',*enc(),W/(name+'.mp4')])
# Cat visibly speaks first. Cut to the sleeping recipient for the punchline.
run(['-i',N/'04_12-raw.mp4','-ss',55.3,'-i',SRC,'-filter_complex','[0:v]trim=duration=2.3,setpts=PTS-STARTPTS,scale=854:480,fps=24,setsar=1[c];[1:v]trim=duration=2.7,setpts=PTS-STARTPTS,crop=448:252:320:140,scale=854:480,fps=24,setsar=1[r];[c][r]concat=n=2:v=1:a=0[v]','-map','[v]','-map','0:a','-t',5,*enc(),W/'12-clean.mp4'])
for name,source in [('09',N/'04_09-raw.mp4'),('12',W/'12-clean.mp4')]:
 run(['-i',source,'-t',5,'-vf',f'scale=736:414,pad=854:480:59:66:color=0x101824,fps=24,setsar=1,ass={W/name}.ass:fontsdir={F}','-af','aresample=async=1:first_pts=0,afade=t=in:d=0.01,afade=t=out:st=4.98:d=0.02,alimiter=limit=0.95:level=false',*enc(),W/(name+'.mp4')])
(W/'concat.txt').write_text(''.join(f"file '{W/n}.mp4'\n" for n in ['a','09','b','12']))
OUT=P/'萌萌谈_EP04_拖延鸽把咖啡推迟了五分钟.mp4'
run(['-f','concat','-safe',0,'-i',W/'concat.txt','-t',58,'-c:v','copy','-af','aresample=async=1:first_pts=0','-c:a','aac','-b:a','192k','-movflags','+faststart',OUT])
run(['-i',OUT,'-f','null','-']);print(OUT,flush=True)
