# v0.8 Blender 程序化散布入口

`scatter_library.py` 将项目已复用的 GLB 和用户指定的 XY 矩形区域编译为 Blender Python 执行代码。

- **小规模测试技术：** 共享 Mesh 数据的 Blender `Object.copy()` linked clones（每项最多 300，总计最多 800），不是大规模 Geometry Nodes。
- **必要输入：** GLB 已经从共享库通过 `apply-reuse` 放入当前项目；Blender 中已经存在可射线检测的地面 Mesh（例如海湾 Demo 的 `SB_terrain`）；`bounds_xy` 是真实有地面的范围。
- **行为：** 导入一次基础 GLB → 将网格当实例源 → 使用稳定 `seed` 随机采样 → 向指定地形射线贴地 → 复制共享网格数据的对象 → 生成执行报告 → 保存为新文件 `results/scatter_scene.blend`。
- **保护：** 不允许覆盖之前输出的散布 `.blend`；发现同 ID 的已生成散布物体时停止，不无脑重建；在外部项目文件里运行则拒绝执行。
- **限制：** 复杂 GLB 父子层级、动画/骨骼、材质变化、碰撞剔除与坡度权重需要更多实机测试；大规模草地必须接入 Geometry Nodes 并增加区块和可见性优化。

按 `examples/library_scatter_plan.sample.json` 填写真实 `asset_id`、`count`、`surface_object`、`bounds_xy` 后：

```
python scripts/scatter_library.py compile-scatter --project demo/coastal_mock --plan /path/to/your_scatter_plan.json
```

将 `generated/mcp_scatter.py` 的**完整源码**交给已连接 Blender 的 Codex/MCP 执行（工具名称、参数以现场声明为准）。该命令只编译代码，不能证明 Blender 已运行成功。
