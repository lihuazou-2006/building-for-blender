# v0.8 素材库成长与复用规则

v0.8.1 已增加用户素材文件夹的递归扫描、内容元数据提取、Agent 预览分类和去重批量入库，见 [FOLDER_INGEST.md](FOLDER_INGEST.md)。默认库是 `<用户主目录>/Documents/Codex/SharedAssetLibrary`；显式 `--library` 与环境变量 `BLENDER_ASSET_LIBRARY` 可更改。原有审核/复用门禁继续有效。

## 双层素材库

**项目资产库：** `project/asset_library/` 保存参考照片裁切、真实生成的单体图、图像审核与 Tripo 请求。它可以只包含图片，不意味着已有 3D 模型。

**共享库：** `SharedAssetLibrary/catalog.json` 和 `models/`、`textures/` 保存已拥有的 GLB 模型与 PNG/JPG 纹理，跨项目复用。不要把用户无权再分发的商业资产公开上传。

## 为什么需要 `asset_key`

场景里的 `rock_near_water` 是一个对象/类别的 ID，而共享库里的 `rock_source_A` 是一个实际资产版本。二者通过语义家族 `asset_key=shore_rock` 连接。只按 `category=rock` 匹配会错误替代某种特殊岩石，因此必须同时检查 `asset_key`、`category`、`style_id`、能力和许可证，最后确认文件真实存在、hash 未变化。

如果风格变化、资产损坏、模型未审核、许可证不允许或缺少风摆/碰撞/内部结构能力，路线必须回退到新的图片任务或 Blender 精修，而不是强行复用。

## 植被、岩石、苔藓建议

- **岩石：** 模型库提供 3–6 种岩石 GLB，区域散布器负责坡度、间距、旋转、比例和聚类。当前 v0.8 CLI 一个 ID 对应一项申请，不会自动生成 6 种；需要建立 6 个变体资产 ID。
- **草：** 库里可以保存少量草丛 GLB；程序化散布数量可以是成千上万，但大规模应使用 Geometry Nodes。单株纤细草叶往往也可以直接用节点生成，不值得每片都用 Tripo。
- **灌木/树木：** 可由 Tripo 建立少量风格一致的基础模型。要做树叶风摆，需检查拓扑和可拆分枝叶；普通 Tripo 网格不保证具备该结构。
- **苔藓：** 石头或地表覆盖优先纹理/材质、顶点权重和 Decal；如是可看到体积的苔藓垫、团块，则可以做 GLB 资产并实例化。

## 模型状态

`registered_unverified → validated → library_reused_pending_blender_import → imported_pending_visual_review`。

第一个 `validated` 是用户提供 Blender 审核报告并确认后才成立；`apply-reuse` 将已验证 GLB 复制到项目，但还不代表项目已成功导入或放置。对贴图同理，`material_reused_pending_setup` 表示贴图文件已准备好，而不是材质节点已经连好。

## Growth Plan 的典型输出

```json
{
  "summary": {
    "reuse": 1,
    "generate_request": 2,
    "procedural": 3,
    "material_reuse": 1
  },
  "entries": [
    {"asset_id": "shore_rock", "route": "library_reuse"},
    {"asset_id": "coastal_grass_clump", "route": "mock_tripo_request"},
    {"asset_id": "moss_surface", "route": "material_library_reuse"},
    {"asset_id": "ocean", "route": "procedural_environment"}
  ],
  "real_tripo_calls": 0
}
```

这只是展示字段意义的片段，不是 `plan-growth` 的固定结果。

## v0.8 已实现与未实现

**已实现代码：** 共享库索引创建、GLB 注册、纹理注册、用户审核报告门禁、哈希完整性检查、严格路由、素材复用到项目、缺失模型生成离线 Tripo 申请、针对库中已复用 GLB 编译 Blender linked instances 脚本。

**尚待实机联调：** Blender GLB 精修、实际实例散布效果、Geometry Nodes 生产级散布、遮挡补全图自动生图、自动提取 GLB 材质贴图、Tripo 提交后的自动入库、跨风格材质转换和基于图像的语义相似度搜索。这些不能当作已经完成的功能。
