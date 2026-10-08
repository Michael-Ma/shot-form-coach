# 库里投篮教学与技术路线研究

核查日期：2026-10-07。这里区分官方教学内容、实验研究、工具能力与本项目的设计判断。没有观看或下载付费完整课程，没有取得可直接复用的库里逐帧运动标注。

## 库里教学可以转化成什么

| 资料中的重点 | 可采用的产品设计 | 不能直接推导的结论 |
| --- | --- | --- |
| 站姿、身体协调和从下肢开始的动作配合 | 将下沉、起身、举球与离手的关系作为观察对象 | 单一站姿角度适用于所有人，或视频能测出用了多少腿部力量 |
| 自然、适合身体的站姿 | 比较平衡与重复性，允许个人差异 | 与库里脚尖朝向不同就判错 |
| 出手时手臂伸展和完成动作 | 检查出手附近的轨迹与随挥保持 | 出手后较早收手一定导致未进 |
| 手部位置与指腹持球的教学 | 在手部足够清晰的素材中单独复核持球与离手 | 用身体骨架直接测出指压、辅助手推力或球旋转 |
| 从近距离开始的 form shooting 与录像复盘 | 为一项训练目标选择近距离练法，并保存重拍前后证据 | 一次训练或几次命中就证明长期改善 |
| 观察自己的失误模式 | 将动作观察和落点/命中信息分开记录，再检验关系 | 未进方向可以唯一反推出某个技术错误 |

主要依据为 MasterClass 发布的 Curry 课程页和三篇公开教学文章：

- [Shooting: Stance, Alignment, and Mechanics](https://www.masterclass.com/classes/stephen-curry-teaches-shooting-ball-handling-and-scoring/chapters/shooting-stance-alignment-and-mechanics)
- [Stance, alignment and mechanics](https://www.masterclass.com/articles/how-to-shoot-a-basketball-with-steph-curry)
- [Form shooting](https://www.masterclass.com/articles/steph-currys-tips-for-form-shooting-in-basketball)
- [Practice routine](https://www.masterclass.com/articles/stephen-currys-practice-tips)

课程公开预览与文章中的部分措辞属于教学口令，不能未经检验就转成跨体型、跨视角的硬阈值。项目应保存原始出处，并把可复用原则与个体动作习惯分开。

## 运动科学证据的含义

[Slegers、Lee 与 Wong 2021](https://www.jssm.org/volume20/iss3/cap/jssm-20-508.pdf)
研究了 12 名男性熟练球员的罚球和三分球。该实验将同一个体的出手参数变化与表现关联，说明评估重复性有价值；它没有给出适用于所有人的单一姿势，也不是改变某个关节就提高命中率的干预证据。

该研究使用约 60 FPS、较快快门、固定侧面拍摄、标定物和人工球轨迹。当前广角斜侧面素材约 30 FPS，拍摄条件与标定条件不同，不能直接套用论文中的精确球速或角度估计精度。首版使用投影指标与时间区间，并单独评估误差。

其他关于投篮距离、个体差异和跳投运动学的论文已找到，但部分全文读取遇到访问验证；设计中的具体数值不依赖未完整读取的论文或搜索摘要。

## 现成工具如何分工

| 工具 | 官方资料支持的能力 | 本项目使用方式 |
| --- | --- | --- |
| MediaPipe Pose Landmarker | 视频模式、33 个身体关键点、图像与模型 world 坐标、可见性 | 首个本地姿态基线；验证投篮遮挡、出手附近抖动及投篮侧混淆 |
| MMPose / RTMPose | 身体与 whole-body 模型；可用部署路径 | 对困难片段做第二条基线；关键点更多不等于手部动作一定可测 |
| OpenCap | 多机位流程及单目 beta；多机位文档说明标定和可见性条件 | 后续独立验证三维路径，首版不依赖其未经投篮场景验证的动力学输出 |
| 现有 Gemini adapter | 本项目已有视频事件观察与调用记录 | 提议阶段、解释结构化证据和生成训练语言；不承担未经约束的数值测量 |
| FFmpeg / PyAV | 现有工程已验证的源时间、帧索引与裁片流程 | 导入、扩大上下文、源帧截图、对比视频与时间追溯 |

官方技术来源：

- [MediaPipe Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python)
- [MMPose inference](https://github.com/open-mmlab/mmpose/blob/main/docs/en/user_guides/inference.md)
- [RTMPose whole-body model metadata](https://github.com/open-mmlab/mmpose/blob/main/configs/wholebody_2d_keypoint/rtmpose/coco-wholebody/rtmpose_coco-wholebody.yml)
- [OpenCap current capture options](https://www.opencap.ai/)
- [OpenCap multi-camera best practices](https://www.opencap.ai/best-practices)

## 参考视频素材的状态

[MasterClass 官方公开视频](https://www.youtube.com/watch?v=nievJITvq_o)可作为教学入口。
[NBA 的 Curry shooting-form 页面](https://www.nba.com/watch/video/artof3bblock)仍存在，但本次读取显示视频不可用，因此没有把它当作已观看的动作证据。

要做“本人和库里本人同阶段并排”的正式输出，还需要取得可用于该分析与展示的参考片段，并标注阶段、视角、投篮距离与类型。当前仓库仅保存来源链接和原创示意；分析可用性与对外分发权限应分开记录。


## 后续补充 2026 10 07

[MediaPipe、模型比较和投篮纠正研究补充](RESEARCH_COACHING_AND_MODELS.zh-CN.md)记录新增论文的证据范围、拟加入的功能和限制。[模型评测方案](MODEL_EVALUATION.zh-CN.md)记录候选与验证方法。用户已确认自动分析后可选修正关键阶段，见 [ADR 0002](ADR-0002-optional-phase-correction.md)。
