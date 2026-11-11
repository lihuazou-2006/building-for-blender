---
name: blender-scene-builder
description: 使用 Agent 和 Blender MCP 从照片或文字规划、搭建可编辑场景，优先复用共享模型和贴图库；支持扫描用户指定素材文件夹，提取内容信息、查看预览分类并批量入库。缺失资产默认只准备离线 Mock Tripo 申请。适用于参考图场景搭建、本地素材库整理和基础资产程序化复用。
---

# Blender Scene Builder

将参考图或文字转成元素清单、风格方案、资产计划和可编辑 Blender 场景；或单独收集用户已有素材。脚本生成成功不等于 Blender 已执行，图片任务不等于实际图片，离线申请不等于已提交的 3D 生成任务。

## 按用户任务读取

- **已有素材文件夹：** 读取 [FOLDER_INGEST.md](references/FOLDER_INGEST.md)，扫描 → Agent 查看预览/模型并补充分类 → 去重批量入库 → 汇报。不需要创建场景或选择场景风格。
- **参考图/文字搭场景：** 读取 [SCENE_WORKFLOW.md](references/SCENE_WORKFLOW.md)，先分析并推荐风格，用户选择后规划和执行。
- **共享库检索、冷启动、质量审核：** 读取 [LIBRARY_GROWTH.md](references/LIBRARY_GROWTH.md)。先查库，缺少什么补什么。
- **在地形上散布植被或岩石：** 读取 [BLENDER_SCATTER.md](references/BLENDER_SCATTER.md)。当前脚本是小规模 linked Mesh 实例化，不能声称已实现生产级 Geometry Nodes 散布。

## 素材库位置与状态

所有库命令采用相同优先级：`--library` 指定路径 → `BLENDER_ASSET_LIBRARY` 环境变量 → `<用户主目录>/Documents/Codex/SharedAssetLibrary`。首次初始化或导入创建。库独立于项目，后续检索、审核和复用须使用同一路径；指定新位置不会自动迁移旧库。

共享库的 `catalog.json`、`models/`、`textures/` 保存跨项目素材；项目内 `asset_library/` 保存参考图裁切、补全图、审核元数据与申请材料，二者不能混为一谈。

新素材默认 `registered_unverified`。只有经过真实检查、确认允许复用，并匹配 `asset_key + category + style_id + required_capabilities` 的模型才能被自动采用。文件名或类别相同不足以证明合适。`apply-reuse` 仅复制素材到项目，不代表已导入 Blender。

## 场景资产路由

| 内容 | 路线 |
|---|---|
| 建筑、船、树、草丛、岩石等独立模型 | 先查共享库；缺少则准备单体补全图与离线 Tripo 申请 |
| 草地、树林、乱石等重复分布 | 少量基础变体 + 实例化；不为每株草/每棵树单独生成模型 |
| 地形、海面、道路等连续环境 | Blender Mesh / Curve / Geometry Nodes / Shader |
| 苔藓、湿沙等表面覆盖 | 先查颜色贴图；缺少则规划纹理/Shader，近景立体团块可单独建模 |

一个 `asset_id` 只对应一个基础资产申请；需要多个变体时建立不同 ID。现有 CLI 不会自动把数量字段展开成多笔任务。

## 执行与交付

- 新场景应根据参考图、用途和气氛推荐 3–5 种不同风格。明确选择前仅做观察、风格候选和粗略清单；不正式批量生图、付费提交或大改场景。示例风格仅用于离线演示。
- `scene_elements.json` 中区分 `observed` 与 `inferred`。已有素材保持实际风格，不按当前场景强行改标签；无法识别时标记待检查。
- 默认 `execution_mode=mock_tripo`，只生成申请包。正式付费工作须先明确预算、数量及重试策略；遗留 live CLI 未经真实服务联调，不默认启用，不因网络异常自动重提。
- 在 Blender 真正导入并检查几何、比例、原点、法线、UV、材质与依赖后，才进行质量审核。碰撞、风摆、骨骼等能力必须实际核验。
- 场景按灰模确认、局部完善、视觉检查推进。保留现有工程副本，不静默覆盖资产或用户场景；连接超时时先核对 Blender 真实状态。
- 输出可编辑 `.blend` 与截图前，必须实际运行并检查。只完成计划、图片、素材复制或源码编译时，报告相应状态和剩余工作。

交付以实际产生的清单、风格文件、增长计划、素材 manifest、导入报告、离线申请队列和 Blender 文件为准。API Key 从环境变量读取，不写入配置或日志。只收集用户指定目录；不执行素材目录附带的脚本，不自动安装第三方插件。
