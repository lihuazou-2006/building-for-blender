# 文件夹批量收集与内容分类（v0.8.1）

用户说“把这个素材文件夹收进库”“扫描已有素材”“批量整理模型/贴图”时使用本流程。只需要用户给出源文件夹；不是创建场景，不需要先选择场景风格。不要为整理本地素材调用 Tripo。

## 素材库位置

所有 `asset_library.py` 和 `folder_ingest.py` 命令统一使用以下优先级：

1. 命令行 `--library <绝对路径>`。
2. 环境变量 `BLENDER_ASSET_LIBRARY`。
3. 默认 `<用户主目录>/Documents/Codex/SharedAssetLibrary`。

Windows 默认示例：`C:\Users\<用户名>\Documents\Codex\SharedAssetLibrary`。库独立于技能和单个场景项目；首次初始化或入库时创建。旧示例显式传入 `--library SharedAssetLibrary` 时仍是当前工作目录下的测试库，不会自动迁移旧库。选择了另一个库时，后续规划、审核、复用继续使用同一个路径。

## Agent 的完整工作流

1. 将用户给出的源文件夹作为 `--source`，报告写入当前任务的 `work/`，不要写回源文件夹。扫描会递归枚举全部普通文件，计算哈希，跳过符号链接、junction 和目标库目录；不解压压缩包，不执行目录中的脚本。
2. 执行扫描并生成图片联系表（Pillow 可用时）：

   ```powershell
   python scripts/folder_ingest.py scan-folder --source "D:\我的素材" --report "<当前任务绝对路径>\work\asset-scan.json" --previews
   ```

3. 阅读扫描报告。模型会尝试读取 GLB/glTF 的节点、网格、材质名，以及 OBJ 的对象/组/材质名；图片读取真实格式、尺寸，并校验可解码性。文件路径和这些结构名只提供初步分类线索，不等于视觉识别。
4. **完成内容识别：** 查看 `previews` 所列图片联系表，必要时打开原图。对模型优先使用随附预览图；名称不明确、预览不足或需要判断风格时，通过可用的 Blender MCP/Blender 工具检查模型。不能运行陌生 `.blend` 中的脚本。把实际看见的类别、名称、风格、材质用途等写到下面的 `analysis.json`。不凭用户选定的场景风格，强行给所有已有素材贴同一种风格。没有视觉能力或 Blender 时继续收集，保留 `unknown` / `semantic_review=needed`，在结果中列出待识别项，不能声称全部识别完成。
5. 批量导入，允许报告里部分文件检查失败；成功条目入库，失败条目进入导入报告，原始文件仍随源快照保存：

   ```powershell
   python scripts/folder_ingest.py import-folder --source "D:\我的素材" --report "<当前任务绝对路径>\work\asset-scan.json" --analysis "<当前任务绝对路径>\work\analysis.json"
   ```

   如果用户明确说有权跨项目复用，可附 `--allow-reuse --license-note "用户确认允许在自己的项目中复用"`。否则照常入库，授权保持未确认，不阻塞收集。
6. 汇报实际库路径、扫描文件数、新增资产数、重复数、识别失败/待识别数。入库默认 `registered_unverified`，语义分类审核和模型质量审核是两回事。继续沿用 `approve-model` / `approve-texture` 的真实检查报告门禁。

已知内容的快速一键入库也可直接调用 `import-folder --source ... --report ... --previews`；报告不存在时自动扫描，已有报告时验证源文件未变化。**这条独立命令只做本地初分，完整视觉识别由上述 Agent 流程完成。** 如果源发生变化，重新执行 `scan-folder` 再导入；不拿旧分类报告匹配新文件。

## 内容分类报告

`analysis.json` 的每项必须绑定扫描报告里的相对路径和 SHA-256，并写明实际检查证据。可只包含需要修正/补充的条目：

```json
{
  "entries": [
    {
      "relative_path": "植被/001.glb",
      "source_sha256": "从扫描报告复制该文件的sha256",
      "name": "海岸草丛",
      "category": "vegetation",
      "asset_key": "coastal_grass_clump",
      "style_id": "japanese_cel",
      "tags": ["grass", "coastal"],
      "evidence": "实际模型预览中可见扁平草叶和赛璐璐配色；记录所查看预览的路径"
    },
    {
      "relative_path": "材质/岩石颜色.png",
      "source_sha256": "从扫描报告复制该文件的sha256",
      "asset_type": "texture",
      "texture_role": "albedo",
      "category": "rock",
      "asset_key": "shore_rock_surface",
      "style_id": "realistic",
      "evidence": "实际打开原图确认是岩石颜色纹理"
    }
  ]
}
```

`category` 沿用原库类别：`building / vegetation / boat / vehicle / prop / rock / furniture / structure / creature / other`。`asset_key`、`style_id` 使用字母、数字、下划线或连字符。同一资产家族应与项目清单采用相同 key；CLI 不进行语义相似度匹配。不能确定时使用 `unknown`。

图片角色：`albedo / normal / roughness / metallic / ao / height / opacity / unknown`。未识别用途的图片先归为 `reference_image`，避免把参考照片直接当贴图。法线、粗糙度等可以收集，但不会被现有单张颜色贴图复用逻辑误用。整套 PBR 自动连线尚未实现。

## 存储结构与格式边界

```text
SharedAssetLibrary/
  catalog.json                        # 全部资产索引、来源、语义与质量状态
  models/<category>/<id>/original.glb  # 自包含 GLB
  textures/<category>/<id>/original.* # 已识别用途的图片
  images/<category>/<id>/original.*   # 参考图或用途待确认图片
  sources/<folder-digest>/...         # 原文件夹完整相对路径快照
  imports/<folder-digest>.json         # 扫描、内容分类和实际入库结果
```

- 支持收集 GLB、glTF、FBX、OBJ、BLEND、STL、PLY，以及 PNG/JPG/WebP/TIFF/BMP/HDR/EXR 等图片。图片可否检查取决于本机解码器；不能解码则记录失败，不伪造成功。其余扩展名仍被扫描并随源快照保留为配套文件，不单独冒充资产。
- GLB/glTF/OBJ 有结构读取；FBX/BLEND/STL/PLY 先作为 `source_model` 归档，语义识别依赖 Agent 实际预览。**自动格式转换与渲染没有在此脚本内实现。**
- 除自包含 GLB 外，模型保留在源快照中，保留同目录 MTL/BIN/贴图等相对依赖；含外部依赖的 GLB 也作为 `source_model`，不能直接进入单文件复用。glTF 越界、远程或缺失依赖会明确报错。外部绝对路径、文件夹之外的 FBX/BLEND/OBJ 依赖仍须在 Blender 检查和打包。
- `source_model` 后续在 Blender 检查/打包、导出自包含 GLB，再以新 ID 登记并审核。现有项目复用仍只处理已批准的 GLB 和兼容颜色贴图；WebP/EXR 等入库不代表现有 PNG/JPG 复用链已支持，应先转换并登记。
- 按内容哈希去重；图片还区分用途，非自包含模型将完整源文件夹摘要纳入身份，避免同一 glTF 的 BIN/贴图变了还被跳过。同一次扫描重复入库不新增资产。重复条目不会覆盖既有分类或审核结果；应在首次导入前完成 Agent 分类。
- 源文件夹只读、保留原文件。为保留依赖，库会保存完整快照，GLB/图片另存分类副本，会额外占用磁盘；源文件夹请选实际素材根目录，而非整个磁盘。
- 本流程没有全盘搜集、后台监控、云上传或付费生成。后续新增素材时再次扫描指定文件夹即可。
