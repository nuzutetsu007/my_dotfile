---
name: 本地图片生成
description: |
  用本机已部署的 stable-diffusion.cpp（Vulkan 后端 + Iris-3B Q4_K GGUF）在本地 GPU 上生成图片，输出 PNG 文件。
  当用户说“生成图片”“画一张”“来张图”“文生图”“本地出图”“本地图片生成”“用 sd.cpp 出图”“帮我生成一张……的图”“给我出一张 1024 的……”等任何本地图像生成请求时，都使用本 Skill，
  即使用户没有提到 stable-diffusion.cpp、Iris、GGUF 或 sd.cpp 也要用。支持提示词、尺寸、步数、CFG、种子、负面提示词和批量出图；不调用云端 API，不启动 Web UI。
compatibility:
  tools: [read, write, edit, bash]
  dependencies: [stable-diffusion.cpp Linux Vulkan 预编译包, Iris-3B Q4_K GGUF, Qwen3-VL-4B-Instruct Q4_K_M GGUF]
---

# 本地图片生成

在本机用 stable-diffusion.cpp 做文生图。默认模型是 **Iris-3B（Q4_K 量化，像素空间生成）**，文本编码器是 **Qwen3-VL-4B-Instruct（Q4_K_M）**，走 **Vulkan/NVIDIA** 后端。

## 已部署环境

| 内容 | 路径 |
|---|---|
| 可执行文件和动态库 | `/home/hashira/create/hongguo/sd-cpp/`（`sd-cli`） |
| Iris-3B 扩散模型 | `/home/hashira/create/hongguo/models/diffusion_models/iris-3b-turbo-Q4_K.gguf` |
| Qwen3-VL-4B 文本编码器 | `/home/hashira/create/hongguo/models/text_encoders/Qwen3VL-4B-Instruct-Q4_K_M.gguf` |

这些路径可以用环境变量 `SD_CPP_DIR` 和 `SD_MODELS_DIR` 覆盖。

## 生成图片

**先把提示词转成英文**。Iris-3B 的这套 GGUF + sd.cpp 路径对中文提示词处理很差：汉字会被当作图像内容直接画进画面（出现大块乱码文字）。用户用中文描述需求时，先把它准确翻译成英文再传给脚本；中文原文只用于和用户沟通，不作为生成输入。翻译时保留风格、光线、构图、材质等细节。

然后用封装好的脚本，它会校验参数、设置库路径并使用正确的后端参数：

```bash
S=~/.agents/skills/本地图片生成/scripts/generate_image.py

python3 "$S" "a lovely cat, cinematic lighting"              # 默认 1024x1024，输出到 ./generated.png
python3 "$S" "cyberpunk city night, neon signs, rain reflections" -o /tmp/city.png -W 1024 -H 768
python3 "$S" "橘猫睡觉" -W 512 -H 512 -s 42 --steps 20 --cfg 3
python3 "$S" "极简产品海报，白底，咖啡杯" -n "文字, 水印" -b 2 -o /tmp/poster_%d.png
```

参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `prompt`（位置参数） | 必填 | 正向提示词；连同模板后缀上限约 300 token |
| `-o, --output` | `./generated.png` | 输出 PNG 路径；批量时路径里要含 `%d` |
| `-W, --width` / `-H, --height` | 1024 | 必须是 **16 的倍数** |
| `--steps` | 20 | 采样步数 |
| `--cfg` | 3.0 | Iris 官方示例用 3； turbo 变体可用 1 |
| `-s, --seed` | 随机 | 固定种子便于复现 |
| `-n, --negative` | 空 | 负面提示词 |
| `-b, --batch` | 1 | 批量张数 |
| `-v, --verbose` | 关 | 打印实际执行的命令 |

生成结束后脚本会打印输出文件绝对路径；确认文件存在再向用户报告，必要时把图片展示给用户。

## 关键约束（踩过的坑）

- **绝对不要传 `--offload-to-cpu`**：这个预编译 Vulkan 版本会因此进入单线程图切分，进程卡住数分钟不动（CPU 约 100%，无进展）。正确配置是权重直放 GPU：`--backend diffusion=vulkan0,te=vulkan0 --auto-fit off -t 16`。显存不够时降低分辨率，而不是加 offload。
- **不要传 `--vae`**：Iris 在像素空间直接生成图像，没有 VAE。
- 宽高必须是 16 的倍数；1024×1024 约需 5 GB 显存，512×512 约需 4.5 GB。
- 提示词含模板开销约 40 token，正文请控制在约 260 token 以内。**用英文写提示词**；中文提示词会产生汉字乱码贴图。
- Q4_K 量化图会有轻微噪点或文字状伪影，属正常现象。
- nvtop 对 Vulkan compute 的利用率显示可能偏低；用 `nvidia-smi` 看 `sd-cli` 的显存占用确认它在工作。

## 模型缺失时

先检查文件是否存在；缺失时不要擅自下载几 GB 的文件，先告知用户大小并征得同意。用户同意后用 curl 直连下载（比未登录的 `hf` xet 通道稳定）：

```bash
mkdir -p /home/hashira/create/hongguo/models/{diffusion_models,text_encoders}
curl -L -C - -o /home/hashira/create/hongguo/models/diffusion_models/iris-3b-turbo-Q4_K.gguf \
  https://huggingface.co/wbruna/Iris-3b-sdcpp-GGUF/resolve/main/iris-3b-turbo-Q4_K.gguf
curl -L -C - -o /home/hashira/create/hongguo/models/text_encoders/Qwen3VL-4B-Instruct-Q4_K_M.gguf \
  https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct-GGUF/resolve/main/Qwen3VL-4B-Instruct-Q4_K_M.gguf
```

如果用户要的是别的模型（SD1.5/SDXL/Z-Image 等），先确认本机是否已有对应权重；没有的话说明当前环境只部署了 Iris-3B。
