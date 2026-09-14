from pathlib import Path
import json,shutil,zipfile,hashlib
p=Path('/tmp/jianci-production');out=Path('/workspace/scratch/6651942d1ae0/剑刺_14-18_成片');out.mkdir(exist_ok=True)
rows=[]
for ep in range(14,19):
 f=next((p/'final').glob(f'剑刺_第{ep}集_*.mp4'));shutil.copy2(f,out/f.name)
 s=(p/f'edit/ep{ep}/subtitles.srt').read_text()
 if ep==18:
  blocks=s.strip().split('\n\n');blocks.append('0\n00:00:49,650 --> 00:00:54,250\n数月后，经审理，陆承安因对知微实施暴力并造成死亡，被判有罪。\nMonths later, Lu was convicted for the violence that caused Zhiwei’s death.')
  blocks.sort(key=lambda x:x.splitlines()[1]);s='\n\n'.join(str(i+1)+'\n'+'\n'.join(b.splitlines()[1:]) for i,b in enumerate(blocks))+'\n'
 (out/f'剑刺_第{ep}集_中英字幕.srt').write_text(s)
 q=json.loads((p/f'final-qa/ep{ep}/checks.json').read_text());rows.append(f'| {ep} | {q["duration"]:.2f} 秒 | 全帧解码正常；对白区间未检出静音 |')
report='''# 剑刺《她回来以后》第14—18集：成片与检查记录

作者：林爱丽。制作日期：2026-09-14。依据第二案 v5 剧本剪辑。本案为现代虚构故事，灵感来自1897年格林布赖尔幽灵案；案情、人物、法医细节与吸血鬼情节不应视为原型案件事实。

## 交付

五集独立 MP4，均有中文对白、中英硬字幕和悬疑 BGM；附可编辑 SRT。配乐为本次制作的低音持续音与稀疏琴音，接近第12集的克制悬疑风格，并非提取第12集原音轨。对白时配乐自动压低。

原生生成素材为480P。成片1280×960、24fps，上下区域用于片名和字幕；放大排版不等于新增高清细节。

| 集数 | 时长 | 技术检查 |
|---|---|---|
'''+ '\n'.join(rows)+'''

## 已修正的问题

- 第14集：替换错误人物及尸检镜头；删除异常叠化和多余声音；用现存检材复核衔接首次尸检回溯。结尾不必要的对讲机动作改用案卷特写承接声音。
- 第15集：重做母亲询问镜头，保持坐姿、低发髻、衣着；移除面对面谈话中的对讲机；保留同一张知微照片，照片特写缩到1.6秒；删除重复对白、乱码字幕和无关长停顿。核准周峤与林浅两句对白的字幕归属和时间。
- 第16集：补做店内开场，明确标注事件回溯，避免把变化机位当作未经剪辑的固定监控；保留陆承安和知微的左右关系及知微离场动作。裁去错误配角；删除许未后段变脸。红眼、两颗上犬齿、周峤和许未的反应以及林浅在场均有画面，剑刺退出时动作连续。露牙段视频和声音一起以0.9倍速处理，维持相对同步。
- 第17集：重做韩彻谈话，移除多余对讲机及变化的制服编号；许未独立复核，删除停工后的剑刺错误入镜。急救通话删去生成的无关杂话，按原先后顺序标为“节选”和“随后”。
- 第18集：重做剑刺独白及母亲家中结尾，清除错误配角和地点。庭外镜头两次生成失败，改用第17集未使用的归档素材配“数月后·审理结果”文字，交代判决；该段无旁白。不同集使用的是互不重叠的素材区间。

## 逻辑与连续性

1. 首次尸检已经发现血管损伤、血栓和脑梗死，并保留相关检材；现在复核的是病因及事件关系，不是埋葬后才第一次检查遗体。尸检画面全段标注回溯。
2. 9月2日店内暴力及当晚消息、9月3日跌倒前异常、住院记录与既有病理共同建立证据关系。颈痛本身不能证明谁施暴，也不能单独确定伤因或时间。
3. 法医结论依赖调查资料与复核结果；母亲叙述、剑刺感应和吸血鬼能力均未替代取证。
4. 第16集多人目击后剑刺停工；第17集安排评估与独立复核。第18集个人故事标注“此前”，随后才进入数月后的司法结果。
5. 剑刺讲述阿宁是个人陈述，韩彻要求核实；解释过往不代表立刻恢复工作。
6. 固定主角发型、眼镜、衣服、母亲坐姿和发髻、照片、手套等视觉锚点；重点检查人物出入、镜头左右位置及同场人员。

## 检查范围与局限

对源片进行每秒两帧的密集抽帧检查，检查最终各剪辑段的开头、中间、结尾；结合对白识别、词级时间、字幕及无BGM对白轨音量复核。五集最终文件逐帧解码正常，均含视频和音频流，音视频流时长差小于0.04秒，所有计划对白区间均有音频信号。

这不是连续人工视听播放验收，也不等于逐音素口型认证。自动语音识别会漏掉或误认汉字，特别是电话音效段，因此同时对照源片词级记录。生成动画仍可能存在细微口型、笔触或背景道具变形；本轮已处理检查中发现的明显错误。

## 生成费用记录

本轮各批次报告的标价估算合计 US$18.1104（约$18.11），包含失败请求的估算，不是已核实实际扣款。失败任务是否收费或退款、账户余额均未核实。第16集开场的前两次请求因参考图高度不足240像素而失败，修正尺寸后才成功。后期剪辑、字幕和配乐调整没有再调用付费视频生成。
'''
(out/'剑刺_14-18_检查与修改记录.md').write_text(report)
manifest=[dict(file=f.name,bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in sorted(out.glob('*.mp4'))]
(p/'delivery-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
z=out/'剑刺_第14-18集_全部视频与字幕.zip'
with zipfile.ZipFile(z,'w',zipfile.ZIP_STORED) as a:
 for f in sorted(out.iterdir()):
  if f!=z and f.is_file():a.write(f,f.name)
files=sorted(out.glob('*.mp4'))+sorted(out.glob('*.srt'))+[out/'剑刺_14-18_检查与修改记录.md',z]
(p/'upload-request.json').write_text(json.dumps({'uploads':[{'local_path':str(f),'purpose':'create_library_file'} for f in files]},ensure_ascii=False))
print('Packaged',len(files),'files',sum(f.stat().st_size for f in files))
