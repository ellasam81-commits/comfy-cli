# 《吸血法医·剑刺》双场景 / 三模型试片

制作：林爱丽。当前版本为每集60秒、12个分镜的新版，建议两季各54集；不是仓库内旧版《尸体锁门》的续拍。

本次仅测试第二集镜头08—09：5秒现代检刺翻案卷，动作与纸声接到5秒古代赫连昭野翻验尸簿。两种造型是同一个人的漫长人生，古代只是记忆片段。参考脸采用用户最新“七八分像、更多原创化”的二维动画设计。

- 三个指定模型各请求一次10秒，不生成整集，不自动重试。
- Seedance Mini 480p约US$0.352；Wan 3.0 480p约US$0.50；H3参考图768P约US$1.125；总估算US$1.977。
- 价格是2026-09-05官网公开估算，不含税、汇率、重做与后期，不是实扣价。
- 原生音轨保留。无声或接近静音会使工作流报错；字幕、配音准确性、脸部和转场仍需人工观看。
- 原始视频和统一854×480预览一同保存，避免把H3较高分辨率直接当作人物稳定性的优势。
- 参考视频只提供视觉设计方向；本测试不复制该视频的声音。

## 文件
- `test.json`：两场景提示词与三款模型的固定参数。
- `modern.png` / `ancient.png`：最新版参考帧，每款收到完全相同的两张图。
- `run_test.py`：只读鉴权检查、三次异步提交、轮询、下载、音轨检查和预览转换。
- `test_jianci_transition.py`：离线验证费用设置、音频、图片、输出URL选择和防重复提交。
- 独立的 GitHub Actions 验证与生成工作流。

## 在手机上运行
工作流出现在默认分支后，可打开 Actions，选 **Jian Ci - Three models - Two scenes - 10 seconds each**，点击 **Run workflow**。每次新运行都可能产生上述费用，使用仓库已有 `SEGMIND_API_KEY` Secret。不要将密钥写进代码或聊天。当前试片分支也支持通过专用 `run.request.json` 的一次修改触发；只有这条路径会触发付费生成，编辑其他参考图或代码不会自动生成视频。

本地只检查、不调用任何API：
```sh
python -m unittest discover -s video-tests/jianci-transition -p test_jianci_transition.py
python video-tests/jianci-transition/run_test.py
```

工作流按仓库AGENTS.md进行全仓库lint、format、pytest检查；在这些检查通过前不打开PR。新工作流直接在仓库调用Segmind API，沿用既有Segmind工作流路径；没有安装本地GPU，也没有把指定模型改成Comfy平台上的另一款模型。

## 评片
先确认两句中文完整、男声连续，再检查5秒附近的手、书页方向、脸型、镜头位置和年代切换。保留全部原始结果，不先换脸、补配音或修掉坏帧来掩盖问题。单次试片只用于决定下一步制作，不是全季稳定性的统计结论。

官方依据：[Mini规格](https://www.segmind.com/models/seedance-2.0-mini/api)、[Mini价格](https://www.segmind.com/models/seedance-2.0-mini/pricing)、[Wan规格](https://www.segmind.com/models/wan3.0-video/api)、[Wan价格](https://www.segmind.com/models/wan3.0-video/pricing)、[H3规格](https://www.segmind.com/models/minimax-h3-reference-to-video/api)、[H3价格](https://www.segmind.com/models/minimax-h3-reference-to-video/pricing)、[H3新增768p说明](https://docs.segmind.com/docs/platform/release-notes/2026-08-09-weekly)。

法医表达“水中发现不直接等于溺水”的依据：[皇家病理学院专业教学材料](https://www.rcpath.org/asset/79EA19E1-E7D8-465E-900746D3DC346108/)。

