# 场景分析、离线申请与 Blender 执行

## 分析与风格

1. 确认参考图、项目和工具，观察主要独立实体、重复资产、连续环境及表面材质。
2. 推荐 3–5 种适合当前用途的不同风格，等待用户选择。用 `set-style-candidates` 提供动态候选，随后 `select-style` 写入 `style_choice.json`、`style_guide.json`。
3. Agent 编写 `scene_elements.json`。主要字段如下；样例 JSON 仅演示数据格式，不代表识别了用户的新照片。

```json
{
  "elements": [{
    "asset_id": "rock_near_water",
    "asset_key": "shore_rock",
    "name": "岸边岩石",
    "kind": "repeated_asset",
    "category": "rock",
    "observed": ["灰色岩石"],
    "inferred": ["底部被遮挡"],
    "tripo_candidate": true,
    "instances_estimated": 20,
    "views": ["main"]
  }]
}
```

`kind` 取 `independent_asset / repeated_asset / continuous_environment / supporting_structure`；类别见 [FOLDER_INGEST.md](FOLDER_INGEST.md)。`asset_id` 标识项目对象，`asset_key` 标识跨项目家族。需要碰撞/风摆等时使用布尔字典 `required_capabilities`。

可选 `bbox_norm=[x0,y0,x1,y1]`，坐标为从左上角开始的 0–1 归一化范围。`views` 可包含 `main/front/side/back/top`。表面材质使用 `material_key`。连续环境不能标为 Tripo 候选。

## 先查库，再补缺失资产

在 Skill 根目录运行；命令省略 `--library` 时使用默认共享库：

```powershell
python scripts/asset_library.py init
python scripts/scene_builder.py init --project work/coast --preset blank --reference "path/to/user_reference.png"
python scripts/mock_asset_pipeline.py import-analysis --project work/coast --file "path/to/scene_elements.json"
python scripts/mock_asset_pipeline.py set-style-candidates --project work/coast --file "path/to/style_candidates.json"
python scripts/scene_builder.py select-style --project work/coast --id USER_SELECTED_STYLE
python scripts/asset_library.py plan-growth --project work/coast
python scripts/asset_library.py apply-reuse --project work/coast
python scripts/mock_asset_pipeline.py prepare-mock --project work/coast
```

`plan-growth` 按匹配结果选择 `library_reuse / material_library_reuse / mock_tripo_request / procedural_material_needs_texture / procedural_environment`。已匹配资产须先 `apply-reuse`；不能重复为它建立生成申请。

缺少基础模型时，Agent 使用实际图像生成工具创建单体补全图，保留可见特征并明确推断部分。CLI 只生成裁切参考、图像任务和离线申请，不自带图像模型。工具不可用时保留 `awaiting_real_generated_images`，不能将裁切预览冒充生成图。

```powershell
python scripts/mock_asset_pipeline.py ingest-image --project work/coast --id ASSET_ID --view main --image "path/to/completed.png"
python scripts/mock_asset_pipeline.py approve-asset --project work/coast --id ASSET_ID
python scripts/mock_asset_pipeline.py queue-status --project work/coast
```

要求的 side/back 等视图必须齐全且内容一致，才可批准。队列保持 `mode=offline_mock`、`real_tripo_calls=0`、`is_submitted=false`；`approved_for_manual_or_future_submission` 只说明图片材料已审核。未来获得真实 GLB 后，按 [LIBRARY_GROWTH.md](LIBRARY_GROWTH.md) 登记、检查、审核。

## Blender 执行与验收

程序化场景以用户确认的布局为准，逐步确认地形、建筑、植被和水域。需要散布时读取 [BLENDER_SCATTER.md](BLENDER_SCATTER.md)。大面积苔藓优先纹理/Shader；水面仍需 Mesh 承载。

`scene_builder.py compile` / `run-blender` 提供固定海湾示例构建器，用于检查 Blender 连接、GLB 导入与报告链路；不是任意参考图自动重建器。编译后可把生成 Python 完整源码交给现场实际可用的 Blender MCP 执行工具；工具名以现场声明为准。

验收时检查实际 Mesh、轴向/比例/原点、材质贴图、几何/法线，以及主视角和辅助视角。精确门窗、室内、风摆、骨骼、LOD 与碰撞需针对真实资产修整；普通生成网格不保证具备这些能力。执行报告 `finished=true` 仍不能替代视觉检查。
