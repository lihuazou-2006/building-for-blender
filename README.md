# Blender Scene Builder

一个面向 Codex / Agent Skills 的 Blender 场景技能：整理已有模型和贴图，优先从共享库复用资产，规划缺失资产的离线申请，并通过 Blender 搭建可编辑场景。

当前版本 **v0.8.1**。文件扫描、资产索引、严格检索、离线申请和散布源码编译可本地运行；内容语义识别需要 Agent 查看预览/模型。实际生图与 Blender 执行需要相应工具。

## 安装

需要 Python 3.10+。将本仓库克隆为项目的技能文件夹：

```bash
git clone https://github.com/lihuazou-2006/building-for-blender.git .agents/skills/blender-scene-builder
cd .agents/skills/blender-scene-builder
python -m pip install -r requirements.txt
```

Pillow 用于图片检查和联系表。构建三维场景另需 Blender；让 Agent 操作 Blender 时需连接 Blender MCP。整理本地素材不需要 Tripo 账号。

## 收集已有素材文件夹

可以直接对 Agent 说：

> 用这个 Skill，把 `D:\我的素材` 扫描、识别分类并批量入库，告诉我哪些还需要检查。

也可在 Skill 根目录执行本地初分和入库：

```powershell
python scripts/folder_ingest.py import-folder --source "D:\我的素材" --report "work/asset-scan.json" --previews
```

源文件保留，库中保存完整相对目录快照以保留配套资源。扫描读取 GLB/glTF/OBJ 的结构名称和图片信息，按内容哈希去重。Agent 通过图片联系表/模型预览补充语义分类；未知内容保留待检查状态。

支持收集 GLB、glTF、FBX、OBJ、BLEND、STL、PLY 和常见图片。非自包含 GLB 模型先归档，需要在 Blender 检查、导出 GLB 后才能进入现有自动复用链。HDR/EXR 取决于本机解码器。完整流程与分类报告格式见 [文件夹入库说明](references/FOLDER_INGEST.md)。

## 素材库存放位置

默认：`<用户主目录>/Documents/Codex/SharedAssetLibrary`，首次初始化或入库创建。所有库命令支持 `--library`；其次读取环境变量 `BLENDER_ASSET_LIBRARY`。

```powershell
python scripts/asset_library.py init --library "D:\三维素材库"
python scripts/folder_ingest.py import-folder --source "D:\我的素材" --library "D:\三维素材库" --report "work/asset-scan.json" --previews
```

后续检索、审核和复用使用同一个库路径。该参数选择库位置，不迁移旧库。源文件夹、库目录和扫描报告不能互相混用。

## 从参考图搭建场景

对 Agent 提供图片、用途和预期气氛。Agent 分析元素、推荐风格，用户选择后检索共享库，补充缺失资产，再执行 Blender 组装和视觉检查。草地/森林使用少量基础模型实例化；薄层苔藓优先贴图或 Shader。

默认只准备 **离线 Mock Tripo 申请**，不提交付费任务。实际图像生成、正式 3D 生成和模型质量审核是后续步骤。内置海湾构建器属于固定示例，散布器属于小规模 linked Mesh 实例化；不承诺任意照片自动重建或生产级 Geometry Nodes。

操作规范见 [SKILL.md](SKILL.md)，场景数据与命令见 [场景工作流](references/SCENE_WORKFLOW.md)，共享库质量规则见 [素材库成长](references/LIBRARY_GROWTH.md)，散布限制见 [Blender 散布](references/BLENDER_SCATTER.md)。

## 测试

```bash
python -m unittest discover -s tests -v
```

41 项离线测试覆盖项目初始化、风格门禁、模型/贴图登记、审核与复用、批量扫描、结构名识别、依赖保留、重复导入、哈希变化、分类报告和 Mock 申请。测试图片由代码临时生成，不附带照片或第三方素材库。真实 Blender、Tripo 服务、第三方插件和部分图片解码器需自行实机验证。

## 许可证

源码、技能说明和本仓库自带示例采用 [MIT License](LICENSE)。用户导入的模型、贴图及外部插件遵循各自原有许可证，不因入库而改变授权。
