# Qwen3.5 2B VLM 显存优化指南

## 硬件约束

- GPU: RTX 5060 Laptop 8GB
- 模型: Qwen3.5 2B AWQ INT4 (~2.3 GB 权重)
- 可用余量: ~5.7 GB（权重加载后）
- 单图推理峰值: ~4.2 GB ✅ 安全
- **视频推理风险**: 多帧大图可能触发 OOM

## 视频推理的显存瓶颈分析

Qwen3.5 的 vision encoder 使用 `patch_size=16`，图像会被切分为 patch tokens：

| 图像尺寸 | Patch Tokens | 显存影响 |
|---------|-------------|---------|
| 336×336 | 441 | 基准 |
| 448×448 | 784 | +78% |
| 591×406 (test.jpeg) | ~945 | +114% |
| 1920×1080 | ~8,100 | **+1700%** |

**关键问题**: processor 的 `longest_edge=16777216` 几乎不限制输入尺寸，大图像直接送入会产生数万 tokens，撑爆显存。

视频帧叠加效应（假设每帧 1920×1080）：
- 5 帧 → ~40,500 image tokens → **极易 OOM**
- 5 帧 resize 到 336×336 → ~2,200 image tokens → 安全

## 优化策略（按优先级）

### 1. 图像/视频帧 Resize（最关键）

在送入 processor 前，强制限制图像最长边为 448 或 336：

```python
from PIL import Image

def resize_for_vlm(img: Image.Image, max_size: int = 448) -> Image.Image:
    if max(img.size) > max_size:
        ratio = max_size / max(img.size)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
    return img
```

**效果**: 将 1920×1080 的帧从 ~8,100 tokens 降到 ~784 tokens，**显存节省约 90%**。

### 2. 减少视频帧数

| 帧数 | 估算 Image Tokens (448×448) | 风险 |
|------|---------------------------|------|
| 10 | ~7,840 | 高（接近 OOM） |
| 6 | ~4,704 | 中 |
| **5** | **~3,920** | **推荐** |
| 3 | ~2,352 | 低 |

### 3. 限制输出长度

```python
max_new_tokens = 512  # 分析/问答通常不需要 2048
```

### 4. 每次推理后清理 GPU Cache

```python
import torch

def generate(...):
    with torch.inference_mode():
        output = model.generate(...)
    # 立即释放中间激活值
    torch.cuda.empty_cache()
    return output
```

### 5. 启用 KV Cache 量化（需要安装后端）

```bash
pip install hqq  # 或 optimum-quanto
```

```python
from transformers.cache_utils import QuantizedCache

cache = QuantizedCache(
    backend="hqq",           # 或 "quanto"
    config=model.config,
    nbits=8,                 # INT8，从 bf16 的 2 byte 降到 1 byte
    q_group_size=64,
    residual_length=128,
)
output = model.generate(..., past_key_values=cache)
```

**预期效果**: KV cache 减半（~50-100 MB 节省，对长序列效果显著）。

### 6. 对话历史截断

`InterviewAgent` 已限制 `MAX_TURNS=8`，对话历史不会无限增长。如需更激进：

```python
# 只保留最近 4 轮用于上下文
conversation_history = conversation_history[-4:]
```

### 7. 视频帧分批处理（终极方案）

如果必须处理大量帧，不要一次性送入：

```python
# 先处理绘画图像
response1 = model.generate(images=[drawing], prompt=..., max_new_tokens=256)

# 再分批处理视频帧（每批 2-3 帧）
for batch in chunked(video_frames, 2):
    response = model.generate(images=batch, prompt="Continue analysis...", max_new_tokens=128)
```

### 8. vLLM（长期方案）

vLLM 的 PagedAttention 可以大幅节省 KV cache 内存，支持更高的并发。但需要：
- 将 AWQ 模型转换为 vLLM 支持的格式
- 重写推理代码以使用 vLLM 的异步 API

## 当前已启用优化

✅ `flash-linear-attention` + `causal-conv1d` — fast path 已解锁（+10% 速度）
✅ `video_max_frames=10` — 可进一步降到 5-6
❌ 图像 resize — **未启用，最关键**
❌ KV cache 量化 — `hqq`/`optimum-quanto` 未安装
❌ `torch.cuda.empty_cache()` — 未在每次推理后调用

## 推荐配置

```python
LOCAL_VLM_CONFIG = {
    "model_path": "...",
    "max_new_tokens": 512,      # 从 2048 降到 512（分析/问答足够）
    "video_max_frames": 5,       # 从 10 降到 5
    "video_fps": 0.5,
    "image_max_size": 448,       # 限制图像最长边
    "use_local_vlm": True,
}
```

## 显存预算估算

采用推荐配置后：
- 模型权重: 2.3 GB
- 5 帧 448×448: ~3,920 image tokens → ~0.8 GB 激活值
- 生成长度 512: ~0.3 GB KV cache + 激活值
- **预估峰值: ~3.4 GB** ✅ 远低于 8GB 上限
