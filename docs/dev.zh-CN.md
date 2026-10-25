# novel2img 开发文档

[English](dev.md) | 简体中文

安装、使用、配置、HTTP API 和开发说明。项目概览请看 [README](../README.zh-CN.md)。

## 流水线细节

1. 按章节标题把文本切成若干章（纯正则匹配，不用 LLM）。
2. 通过 [Ollama](https://ollama.com) 运行的 LLM 读取一章，以 JSON 返回最多 `MAX_SCENES` 个场景：
   一句与原文同语言的场景概括，以及一条约 30–45 个 tag 的英文 Danbooru tag prompt，重要的排在前面。
3. 如果填写了风格描述，LLM 会把它合并进每条 prompt（每个场景一次调用，并行执行），插在对应的 tag 旁边，
   而不是简单追加到末尾。
4. 卸载 LLM 释放内存，然后用 [🤗 diffusers](https://github.com/huggingface/diffusers) 加载模型逐个出图，
   每张图一完成就推送到浏览器。

内置 prompt 针对能理解 Danbooru tag 的二次元 SDXL 模型（Illustrious、NoobAI 及其大量衍生模型）编写。
如果使用其他类型的模型，请按需修改 [prompt 模板](#自定义-prompt)。

## 环境要求

- Python 3.9 或更高版本
- [Ollama](https://ollama.com) 和一个对话模型
- 一个单文件 `.safetensors` 格式的 Stable Diffusion 模型。最推荐能理解 Danbooru tag 的二次元 SDXL 模型，
  例如 WAI-Illustrious-SDXL 或其他 Illustrious-XL 衍生模型。
- 运行 SDXL 大约需要 8 GB 显存；Apple Silicon 需要 16 GB 统一内存（出图前会先卸载 LLM，两者才放得下）。

## 安装

1. 安装并启动 Ollama，然后拉取模型：

   ```bash
   ollama pull BlackHillsInfoSec/llama-3.1-8b-abliterated
   ```

2. 克隆本仓库，把模型文件放进 `models/`：

   ```bash
   git clone https://github.com/RalfZhang/novel2img.git
   cd novel2img
   cp ~/Downloads/waiIllustriousSDXL_v170.safetensors models/
   ```

   文件名不同也没关系，在 `.env` 里把 `SD_MODEL_PATH` 指向它即可。

3. 启动（macOS / Linux）：

   ```bash
   ./run.sh
   ```

   首次运行会在 `.venv` 创建虚拟环境、安装依赖（包括 PyTorch，需要一些时间），并把 `.env.example`
   复制为 `.env`。

4. 打开 <http://127.0.0.1:8000>。

第一次生成时还会加载模型（约 30–60 秒），并从 Hugging Face 下载几个很小的配置文件（不是模型权重）。
**中国大陆用户**如果无法访问 huggingface.co，请在 `.env` 中加入镜像地址：`HF_ENDPOINT=https://hf-mirror.com`。

<details>
<summary>Windows，或手动安装</summary>

```shell
python -m venv .venv
.venv\Scripts\activate          # macOS / Linux：source .venv/bin/activate
pip install -e .
copy .env.example .env          # macOS / Linux：cp .env.example .env
novel2img                       # 或：python -m novel2img
```

在 Windows 上，`pip install torch` 默认安装的是仅支持 CPU 的版本。如果使用 NVIDIA 显卡，请先按
<https://pytorch.org/get-started/locally/> 上的说明安装 CUDA 版 PyTorch，再执行 `pip install -e .`。

运行 `novel2img --host 0.0.0.0 --port 8000` 可以让局域网内的其他设备访问界面。
</details>

## 使用网页界面

1. 把一章或整本小说粘贴到大文本框里。章节会在输入时自动识别，从下拉列表中选择要生成的一章。
2. 可选：描述想要的风格或修改，例如：
   - `水彩画风，柔和光线`
   - `把主角改成穿轻甲的银发少女`
   - `ink wash painting, cold colors`（中英文均可）
3. 点击 **生成本章**。先出现各场景的卡片，图片生成一张显示一张。点击图片可查看原图；
   **展开 prompt** 可查看实际发送给模型的完整 prompt。
4. 点击 **下一章 →** 继续生成下一章。

**种子**留空则每张图随机。填写种子后，第 *i* 个场景使用「种子 + *i*」，可以完全复现同一章的结果。
图片保存在 `outputs/` 目录。界面右上角可以切换中英文。

## 示例

`examples/novels/` 里有两篇原创短篇，可以直接拿来试：

| 文件 | 内容 |
| --- | --- |
| [`lantern-keeper.en.txt`](../examples/novels/lantern-keeper.en.txt) | 英文，3 章：灯塔守护人、海难与一盏奇异的提灯 |
| [`snow-night.zh.txt`](../examples/novels/snow-night.zh.txt) | 中文武侠，3 章：剑客雪夜归山门 |

另外还有两个脚本。请在仓库根目录、激活虚拟环境（`source .venv/bin/activate`）后运行。

**只切分场景、不出图**：只需要 Ollama，不需要显卡，适合检查章节识别和调试 prompt：

```bash
python examples/plan_scenes.py examples/novels/snow-night.zh.txt --chapter 2
python examples/plan_scenes.py examples/novels/lantern-keeper.en.txt --style "水彩画风；把主角改成女性"
```

**通过 HTTP API 生成一章**并保存图片（需要先启动服务）：

```bash
python examples/api_client.py examples/novels/snow-night.zh.txt --chapter 3 --seed 42 --out storyboard/
```

也可以直接用 `curl`：

```bash
curl -N http://127.0.0.1:8000/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"text": "第一章 风雪夜归\n雪下了整整一夜。", "max_scenes": 2}'
```

## 配置

配置项从 `.env` 读取（`run.sh` 会用 [`.env.example`](../.env.example) 生成它），同名环境变量优先于文件。
相对路径以启动 novel2img 时所在的目录为基准。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama 服务地址 |
| `OLLAMA_MODEL` | `BlackHillsInfoSec/llama-3.1-8b-abliterated` | 负责切分场景和写 prompt 的对话模型 |
| `OLLAMA_NUM_CTX` | `8192` | LLM 上下文长度（token），章节特别长时调大 |
| `OLLAMA_UNLOAD` | `true` | 出图前卸载 LLM，把内存让给图像模型 |
| `SD_MODEL_PATH` | `models/waiIllustriousSDXL_v170.safetensors` | 模型文件 |
| `SD_IS_SDXL` | `true` | SDXL 系模型（Illustrious、NoobAI、Pony 等）填 `true`，SD 1.5 填 `false` |
| `SD_DEVICE` | `auto` | `auto`、`cuda`、`mps` 或 `cpu` |
| `SD_DTYPE` | `float16` | `float16`、`bfloat16` 或 `float32`（CPU 始终使用 `float32`） |
| `LORA_DIR` | `models/lora` | LoRA 文件所在目录 |
| `LORA_SPEC` | *（空）* | 要加载的 LoRA，格式 `文件.safetensors:权重,…`；权重默认 1.0，slider 类 LoRA 可用负权重 |
| `IMG_WIDTH`、`IMG_HEIGHT` | `832`、`1216` | 图片尺寸；SDXL 在约 100 万像素时效果最好 |
| `IMG_STEPS` | `24` | 采样步数 |
| `IMG_CFG` | `5.5` | 引导系数（CFG） |
| `MAX_SCENES` | `8` | 每章默认最多场景数，可在界面中修改 |
| `QUALITY_TAGS` | `masterpiece, best quality, …` | 自动加在每条 prompt 最前面的质量 tag |
| `NEGATIVE_PROMPT` | `bad quality, worst quality, …` | 负面 prompt |
| `OUTPUT_DIR` | `outputs` | 图片保存目录 |
| `PROMPTS_DIR` | *（空）* | 自定义 prompt 模板所在目录，见下文 |
| `LOG_LEVEL` | `INFO` | 服务端日志级别 |

**选哪个 LLM？** 默认的 abliterated 版 Llama 3.1 8B 不会拒绝小说里常见的黑暗或暴力情节。任何 Ollama
对话模型都能用，能稳定按要求输出 JSON 的模型效果最好。处理中文小说时，Qwen 系列（例如 `qwen2.5:7b`）
对原文的理解更好。

## 自定义 prompt

发送给 LLM 的指令是 [`novel2img/prompts/`](../novel2img/prompts/) 下的 Markdown 模板：

| 模板 | 用途 | 占位符 |
| --- | --- | --- |
| `scene_system.md` | 挑选场景、编写 tag 的规则和示例 | `$max_scenes` |
| `scene_user.md` | 包装章节内容 | `$title`、`$body`、`$max_scenes` |
| `adjust_system.md` | 把风格描述合并进 prompt 的规则 | 无 |
| `adjust_user.md` | 包装单条 prompt 和风格描述 | `$input`（包含两者的 JSON）、`$prompt`、`$adjustment` |

如果不想改动包内文件，可以把要修改的模板复制到自己的目录中编辑，并把 `PROMPTS_DIR` 设为该目录；
目录里没有的模板会自动使用内置版本。每次请求都会重新读取模板，配合 `examples/plan_scenes.py`
可以反复调试，无需重启。常见用途：换成更适合你所用模型或题材的示例，或固定场景概括的语言。

## HTTP API

| 接口 | 说明 |
| --- | --- |
| `GET /api/config` | 模型名称和默认参数（供界面使用） |
| `POST /api/split` | `{"text"}` → `{"chapters": [{"index", "title", "length"}]}` |
| `POST /api/generate` | 生成一章，以 Server-Sent Events 流式返回进度 |

`/api/generate` 接收 `{"text", "chapter_index": 0, "style": "", "max_scenes": null, "seed": null}`。
`text` 可以是整本小说，由 `chapter_index` 指定生成哪一章。返回的事件如下：

| 事件 | 数据 |
| --- | --- |
| `chapter` | `index`、`title`、`total`、`has_next` |
| `status` | `stage`（`planning`、`adjusting`、`unloading_llm`、`loading_model`、`rendering`）和 `message`；出图阶段还有 `scene_index`、`total` |
| `scenes` | `count` 和 `scenes`：`[{summary, prompt, original_prompt?}]` |
| `image` | `scene_index`、`summary`、`prompt`、`full_prompt`、`seed`、`filename`、`url` |
| `error` | `message`。带 `scene_index` 表示只有这张图失败，其余场景继续；不带则表示本次生成已中止 |
| `done` | `chapter_index` |

FastAPI 自带的交互式接口文档位于 <http://127.0.0.1:8000/docs>。

## 项目结构

```text
novel2img/
├── chapters.py     章节切分
├── llm.py          Ollama 客户端，宽松的 JSON 解析
├── scenes.py       挑选场景、合并风格描述（LLM）
├── tags.py         清洗 Danbooru tag prompt
├── image_gen.py    diffusers：模型加载、LoRA、按 CLIP 长度截断 prompt
├── pipeline.py     章节 → 场景 → 图片，以事件流输出进度
├── server.py       FastAPI 应用：HTTP API 与网页界面
├── config.py       从 .env 和环境变量读取配置
├── cli.py          novel2img 命令
├── prompts/        LLM prompt 模板
└── static/         网页界面（纯 HTML、CSS、JavaScript，无需构建）
examples/           示例小说和示例脚本
tests/              测试（不需要显卡、Ollama 或模型）
```

## 开发

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

测试用假的 Ollama 和图像模型替代真实组件，在任何机器上大约一秒即可跑完。`novel2img --reload`
会在代码修改后自动重启服务。

## 常见问题

- **「Cannot reach Ollama」**：启动 Ollama（打开应用或运行 `ollama serve`），并检查 `OLLAMA_URL`。
- **「model … not found」**：先拉取模型：`ollama pull <OLLAMA_MODEL>`。
- **「Image model not found」**：把模型文件放到 `SD_MODEL_PATH` 指向的位置。
- **第一张图特别慢**：加载模型需要 30–60 秒，每次启动服务只加载一次。
- **16 GB 内存的机器上内存不足或特别慢**：保持 `OLLAMA_UNLOAD=true`，关闭其他大型应用，或调小
  `IMG_WIDTH` / `IMG_HEIGHT`。在 16 GB 的 Apple Silicon Mac 上，24 步每张图大约需要 30–60 秒。
- **无法访问 huggingface.co**：首次加载模型时需要从 Hugging Face 下载几个小配置文件。在 `.env` 中设置镜像，
  例如 `HF_ENDPOINT=https://hf-mirror.com`；文件缓存到本地后，设置 `HF_HUB_OFFLINE=1` 即可完全离线。
- **prompt 像句子，或者 tag 太少**：小模型的表现差异很大。换一个 `OLLAMA_MODEL` 试试，或调整
  [prompt 模板](#自定义-prompt)。
- **识别不出章节**：章节标题必须单独占一行，例如 `第一章 标题`、`第12回`、`楔子`、`Chapter 3: Title`、
  `CHAPTER IV`、`Prologue`。第一个标题之前的内容（书名、作者等）会被跳过；完全没有标题时，整段文本视为一章。

## 合理使用

novel2img 不会过滤文本或图片，生成的内容取决于你的文本、模型和设置。请遵守所用模型的许可协议以及
当地法律。不要在未经本人同意的情况下描绘真实人物，也不要生成任何涉及未成年人的色情内容。
