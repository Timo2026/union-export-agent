# 交付包 08 · UI 截图清单（SCREENSHOTS.md）

## 采集方式（两种，都实测过）

**方式 A（自动真后端截图，推荐）**：
```bash
python scripts/screenshot_ui_13tabs.py   # 自动起服务+headless Chromium 逐标签截图
```
已有 15 张在 `docs/screenshots/`（根架构页+13 标签+API 目录，全部真后端零 mockup）。

**方式 B（已补拍 09-27，公网真后端）**：/#/search 的 reid 尽调 + 知识库 3D 点云（hover 交互）——
```bash
python scripts/screenshot_search_8051.py --url http://<NODE-PUBLIC-IP>:8051 --out docs/screenshots
```
本机无 Chromium，复用系统 Edge（channel=msedge + SwiftShader WebGL）。hover 检测锚点必须是
`div.pointer-events-none.absolute`（tooltip 唯一类）；早先用文本「点击固定详情」会命中 canvas
下方静态图例行——假阳性坑，已在脚本注释锁定。

## 决赛截图清单（13+2 张）

| 文件 | 页面 | 演示要点 |
|---|---|---|
| 00_root_index.png | 根架构页 | 系统总览 |
| 01_workbench.png | 三栏协作台 | 邮件→报价工作流 |
| 02_models.png | 模型注册表 | 6 lane 全 Omni 拓扑（v2 决策可视化） |
| 03_demo.png | 黄金链场景 S1-S5 | PASS/HITL/BLOCKED 三路径 |
| 05_threeD.png | 3D STEP | OCP 真几何 |
| 08_skills.png | Skill 控制台 | 38 注册/79 运行时 |
| 09_mailbox.png | 邮件台 | 78+ 封真实邮件自动分类 |
| 10_v12.png | V12 内核仪表板 | 确定性引擎状态 |
| 11_rfq.png | RFQ 管线 | 全生命周期 |
| 12_flywheel.png | 客户飞轮 | 66 客户/3530 报价 |
| 13_ops.png | 运维诊断 | 全链路离线可观测 |
| 15_search_reid.png | /#/search 尽调 | reid 汇报（决策层 5 项 + Omni live 综合徽标 + 475 篇动态计数） |
| 16_search_pointcloud.png | /#/search 点云 | 3D 点云（PCA+kNN 边）+ hover 节点 tooltip（真实文档「横梁伸长杆盖-V1.0.PDF」· 761字） |

## 截图纪律（铁律①）
- 邮箱截图用演示账号（tester@qq.com），真实凭据不入图
- 状态页数字来自真实端点（/health contexts=4364+ 实测）
