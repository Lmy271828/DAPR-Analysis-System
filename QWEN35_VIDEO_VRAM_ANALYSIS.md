# Qwen3.5 原生视频预处理机制与 7GB 显存限制方案

## 一、原生视频预处理机制深度解析

### 1.1 核心组件

Qwen3.5 的视频处理由 `transformers.models.qwen3_vl` 模块实现，包含三个关键类：

| 组件 | 文件 | 职责 |
|------|------|------|
| `Qwen3VLVideoProcessor` | `video_processing_qwen3_vl.py` | 视频帧采样、resize、patch 化 |
| `Qwen3VLProcessor` | `processing_qwen3_vl.py` | 多模态对齐（text/image/video token 拼接） |
| `Qwen3VLVisionModel` | `modeling_qwen3_vl.py` | Vision Encoder 前向传播 |

### 1.2 视频预处理流水线

```
原始视频 → [帧采样] → [smart_resize] → [归一化] → [时序补齐] → [Patch 展平] → pixel_values_videos
                ↓              ↓                              ↓
           VideoMetadata   grid_h/grid_w                   video_grid_thw
```

#### Step 1: 帧采样 (`sample_frames`)
- **默认 fps**: `2`（每秒抽 2 帧）
- **默认帧数范围**: `min_frames=4`, `max_frames=768`
- 采样逻辑：均匀分布 `np.linspace(0, total_num_frames - 1, num_frames)`
- 如传入 `VideoMetadata` 且指定 `fps`，则按 `num_frames = int(total_num_frames / metadata.fps * fps)` 计算

#### Step 2: 智能尺寸调整 (`smart_resize`)
这是控制显存的核心函数：

```python
def smart_resize(
    num_frames: int,
    height: int,
    width: int,
    temporal_factor: int = 2,      # temporal_patch_size
    factor: int = 32,               # patch_size * merge_size = 16 * 2
    min_pixels: int = 128 * 128,    # 16,384
    max_pixels: int = 16 * 16 * 2 * 2 * 2 * 6144,  # 6,291,456
):
    h_bar = round(height / factor) * factor   # 对齐到 32 倍数
    w_bar = round(width / factor) * factor
    t_bar = math.ceil(num_frames / temporal_factor) * temporal_factor  # 对齐到 2 倍数

    if t_bar * h_bar * w_bar > max_pixels:
        beta = math.sqrt((num_frames * height * width) / max_pixels)
        h_bar = max(factor, math.floor(height / beta / factor) * factor)
        w_bar = max(factor, math.floor(width / beta / factor) * factor)
    elif t_bar * h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (num_frames * height * width))
        h_bar = math.ceil(height * beta / factor) * factor
        w_bar = math.ceil(width * beta / factor) * factor

    return h_bar, w_bar
```

**关键洞察**：`max_pixels=6,291,456` 是**视频总像素预算**（帧数 × 高 × 宽），不是单帧预算。这意味着：
- 10 帧视频每帧可分配约 63 万像素 ≈ 800×800
- 5 帧视频每帧可分配约 126 万像素 ≈ 1120×1120
- **这是默认导致视频推理 OOM 的根本原因**

#### Step 3: 归一化与补齐
- 均值/方差：`[0.5, 0.5, 0.5]` / `[0.5, 0.5, 0.5]`（本项目 `preprocessor_config.json` 配置）
- 时序补齐：帧数不是 2 的倍数时，重复最后一帧补齐

#### Step 4: Patch 展平
```python
# 输入: (batch, T, C, H, W)
patches = stacked_videos.view(
    batch_size,
    grid_t,                    # T // 2 (temporal groups)
    temporal_patch_size,       # 2
    channel,
    grid_h // merge_size,      # H/16/2
    merge_size,                # 2
    patch_size,                # 16
    grid_w // merge_size,      # W/16/2
    merge_size,                # 2
    patch_size,                # 16
)
patches = patches.permute(0, 1, 4, 7, 5, 8, 3, 2, 6, 9)
flatten_patches = patches.reshape(
    batch_size,
    grid_t * grid_h * grid_w,   # 总 patch 数（未 merge）
    channel * temporal_patch_size * patch_size * patch_size  # 3*2*16*16=1536
)
```

#### Step 5: 时间戳注入
在 `Qwen3VLProcessor.__call__` 中，每帧视频 patch 前会插入时间戳 token：
```
<1.0 seconds><|vision_start|>[frame_0_patches]<|vision_end|>
<1.5 seconds><|vision_start|>[frame_1_patches]<|vision_end|>
```
这使得视频 token 在 LLM 中带有明确时序信息。

### 1.3 Vision Encoder 内部机制

```python
class Qwen3VLVisionModel:
    patch_embed: Conv3d(3, 1024, kernel=[2,16,16], stride=[2,16,16])
    blocks: 24 × Qwen3VLVisionBlock
    merger: PatchMerger (1024*4 → 2048)
```

- **输入**: `flatten_patches` 先通过 `Conv3d` 嵌入到 1024 维
- **Attention**: 使用 `cu_seqlens` 做变长序列 attention，支持 Flash Attention
- **Spatial Merge**: 每 2×2 空间 patch 合并为 1 个 token，最终输出到 LLM 的维度为 2048

---

## 二、显存占用模型与瓶颈分析

### 2.1 显存构成

| 组件 | 估算公式 | 典型值 (5帧 448×448 + 1图 448×448) |
|------|---------|-----------------------------------|
| **模型权重** | 固定 | ~2.3 GB (AWQ INT4 展开后) |
| **Vision 激活** | `patches × hidden × layers × dtype` | ~0.3-0.8 GB |
| **Text KV Cache** | `2 × seq_len × layers × kv_heads × head_dim × dtype` | ~0.05-0.2 GB |
| **Text 激活** | `batch × seq_len × hidden × 系数` | ~0.2-0.5 GB |
| **系统/缓存** | PyTorch CUDA cache | ~0.3-0.5 GB |
| **总计** | | **~3.5-5.0 GB** |

### 2.2 视频参数 → Token 数量换算

```python
def calc_video_tokens(num_frames, height, width, 
                      patch_size=16, temporal_patch_size=2, merge_size=2):
    grid_t = math.ceil(num_frames / temporal_patch_size)
    grid_h = height // patch_size
    grid_w = width // patch_size
    total_patches = grid_t * grid_h * grid_w
    tokens_after_merge = total_patches // (merge_size ** 2)
    return grid_t, grid_h, grid_w, total_patches, tokens_after_merge

# 示例计算:
# 5帧 448×448  → grid_t=3, grid_h=28, grid_w=28, patches=2352, tokens=588
# 10帧 800×800 → grid_t=5, grid_h=50, grid_w=50, patches=12500, tokens=3125
# 5帧 1920×1080(默认resize) → 可能产生 ~8000+ tokens
```

**显存瓶颈规律**：
- Vision Encoder 的 Attention 显存与 `patches²` 成正比（当不使用 Flash Attention 时）
- 3125 tokens 的 QK^T 矩阵：`3125² × 16 heads × 4B ≈ 625MB`（单头），实际在 eager/sdpa 模式下会分配大临时张量
- 使用 Flash Attention 后，Attention 显存降为线性 `O(patches)`

---

## 三、7GB 显存限制方案

### 3.1 核心策略：三层防御体系

```
┌─────────────────────────────────────────────┐
│  第一层：输入节流（最关键，决定峰值上限）      │
│  - 限制 max_pixels                            │
│  - 限制 video_max_frames                      │
│  - 限制 image_max_size                        │
├─────────────────────────────────────────────┤
│  第二层：计算优化（降低推理过程显存）          │
│  - Flash Attention 2                          │
│  - KV Cache 量化                              │
│  - gradient_checkpointing (vision)            │
├─────────────────────────────────────────────┤
│  第三层：显存回收（防止碎片累积）              │
│  - torch.cuda.empty_cache()                   │
│  - 及时卸载模型                               │
└─────────────────────────────────────────────┘
```

### 3.2 推荐配置参数

```python
LOCAL_VLM_CONFIG = {
    "model_path": "./model",
    "torch_dtype": "bfloat16",
    "device_map": "cuda",
    
    # === 第一层：输入节流 ===
    "max_new_tokens": 512,           # 限制生成长度
    "video_max_frames": 5,           # 最多 5 帧（本项目已配置）
    "video_fps": 0.5,                # 每 2 秒 1 帧（本项目已配置）
    "image_max_size": 448,           # 图像最长边 448（本项目已配置）
    
    # === 新增关键参数 ===
    "video_max_pixels": 2_000_000,   # 视频总像素预算（默认 6.3M → 2M）
    "image_max_pixels": 1_000_000,   # 图像总像素预算
}
```

**`video_max_pixels=2_000_000` 的效果**：
- 5 帧视频 → 每帧约 40 万像素 ≈ 640×640 上限
- 实际 `smart_resize` 后约 448×448 或 384×384
- video tokens 控制在 **400-600** 以内
- 峰值显存可控制在 **4.5GB 以下**

### 3.3 代码实现（核心修改）

#### 修改 1：传入 `max_pixels` 给 Processor（最关键）

```python
# DAPR-agent/backend/services/llm/core.py
# 在 _prepare_inputs 方法中修改 processor 调用

def _prepare_inputs(self, ...):
    # ... 前面的帧提取代码不变 ...
    
    # 关键：限制视频和图像的像素预算
    video_max_pixels = LOCAL_VLM_CONFIG.get("video_max_pixels", 2_000_000)
    image_max_pixels = LOCAL_VLM_CONFIG.get("image_max_pixels", 1_000_000)
    
    inputs = self._processor(
        text=[text],
        images=all_images if all_images else None,
        videos=[all_videos] if all_videos else None,
        video_metadata=[video_metadata_list] if video_metadata_list else None,
        return_tensors="pt",
        padding=True,
        # 传入像素限制参数
        images_kwargs={"max_pixels": image_max_pixels} if all_images else {},
        videos_kwargs={"max_pixels": video_max_pixels} if all_videos else {},
    ).to(self._model.device)
    
    return inputs
```

#### 修改 2：启用 Flash Attention 2

```python
# DAPR-agent/backend/services/llm/core.py
# 在 _ensure_model_loaded 中

cls._model = Qwen3_5ForConditionalGeneration.from_pretrained(
    model_path,
    torch_dtype=torch.bfloat16,
    device_map="cuda",
    trust_remote_code=True,
    attn_implementation="flash_attention_2",  # 新增
)
```

> **注意**：需先安装 `pip install flash-attn --no-build-isolation`，若安装失败可回退到 `"sdpa"`

#### 修改 3：KV Cache 量化（进阶）

```python
# 在 generate() 中使用量化 KV cache
from transformers import QuantizedCache, QuantizedCacheConfig

cache_config = QuantizedCacheConfig(
    backend="quanto",      # 或 "HQQ"
    nbits=8,
    q_group_size=64,
    residual_length=128,
)
past_key_values = QuantizedCache(cache_config)

output_ids = self._model.generate(
    **inputs,
    max_new_tokens=LOCAL_VLM_CONFIG.get("max_new_tokens", 512),
    do_sample=False,
    past_key_values=past_key_values,  # 传入量化 cache
)
```

#### 修改 4：显存清理

```python
# 在每次推理后清理
def generate(self, ...):
    with self._model_lock:
        inputs = self._prepare_inputs(...)
        with torch.inference_mode():
            output_ids = self._model.generate(**inputs, ...)
        
        # 立即释放中间激活
        del inputs
        torch.cuda.empty_cache()
        
        generated_ids = output_ids[0][...]
        response = self._processor.decode(...)
        
        del output_ids
        torch.cuda.empty_cache()
    
    return response
```

### 3.4 配置参数对照表

| 参数 | 当前值 | 推荐值 | 预期显存影响 |
|------|--------|--------|-------------|
| `video_max_pixels` | 未设置（默认 6.3M） | **2,000,000** | ↓ 1.5-2.5 GB |
| `image_max_pixels` | 未设置（默认 6.3M） | **1,000,000** | ↓ 0.3-0.5 GB |
| `video_max_frames` | 5 | 5（保持） | 基准 |
| `video_fps` | 0.5 | 0.5（保持） | 基准 |
| `image_max_size` | 448 | 448（保持） | 基准 |
| `max_new_tokens` | 512 | 512（保持） | 基准 |
| `attn_implementation` | 默认 (eager/sdpa) | **flash_attention_2** | ↓ 0.5-1.0 GB |
| KV Cache 量化 | 无 | **quanto 8-bit** | ↓ 0.1-0.2 GB |
| `empty_cache()` | 无 | **每次推理后** | 防止碎片 |

### 3.5 显存预算预估（采用全部优化后）

| 场景 | 估算峰值显存 | 安全余量 |
|------|-------------|---------|
| 单图 448×448 + 文字 | ~3.0 GB | ✅ 安全 |
| 1图 + 1视频(5帧 448×448) + 文字 | ~3.8 GB | ✅ 安全 |
| 1图 + 2视频(各5帧) + 文字 | ~4.5 GB | ✅ 安全 |
| 1图 + 2视频(各5帧) + 长生成(1024 tokens) | ~5.2 GB | ✅ 安全 |
| **最坏情况**（默认 6.3M pixels，10帧） | ~7-9 GB | ❌ OOM 风险 |

---

## 四、项目文件修改清单

| 文件 | 修改内容 | 优先级 |
|------|---------|--------|
| `DAPR-agent/backend/config.py` | 增加 `video_max_pixels`、`image_max_pixels` | 🔴 高 |
| `DAPR-agent/backend/services/llm/core.py` | `_prepare_inputs()` 传入 pixel 限制参数 | 🔴 高 |
| `DAPR-agent/backend/services/llm/core.py` | `_ensure_model_loaded()` 启用 `attn_implementation` | 🟡 中 |
| `DAPR-agent/backend/services/llm/core.py` | `generate()` 增加 `empty_cache()` | 🟡 中 |
| `DAPR-agent/docs/VLM_VRAM_OPTIMIZATION.md` | 更新文档 | 🟢 低 |

---

## 五、验证方法

运行以下测试脚本监控显存：

```python
import torch
from transformers import Qwen3_5ForConditionalGeneration, AutoProcessor

model = Qwen3_5ForConditionalGeneration.from_pretrained(
    "./model", torch_dtype=torch.bfloat16, device_map="cuda",
    trust_remote_code=True, attn_implementation="flash_attention_2"
)
processor = AutoProcessor.from_pretrained("./model", trust_remote_code=True)

# 构造一个 5 帧视频的测试输入
messages = [{
    "role": "user",
    "content": [
        {"type": "video", "video": [frame1, frame2, frame3, frame4, frame5]},
        {"type": "text", "text": "描述这个视频"}
    ]
}]

text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = processor(text=[text], videos=[[frame1,...,frame5]], return_tensors="pt",
                   videos_kwargs={"max_pixels": 2_000_000}).to("cuda")

print(f"输入序列长度: {inputs.input_ids.shape[1]}")
print(f"推理前显存: {torch.cuda.memory_allocated()/1024**3:.2f} GB")

with torch.inference_mode():
    output = model.generate(**inputs, max_new_tokens=256)

print(f"推理后显存: {torch.cuda.memory_allocated()/1024**3:.2f} GB")
print(f"峰值显存: {torch.cuda.max_memory_allocated()/1024**3:.2f} GB")
```

---

## 六、总结

Qwen3.5 的原生视频预处理采用 **"时空 Patch + 3D Conv 嵌入"** 的架构：
1. `temporal_patch_size=2` 将视频按每 2 帧分组
2. `Conv3d` 同时提取时空特征
3. `smart_resize` 根据总像素预算动态调整尺寸
4. 每帧视频在 prompt 中注入时间戳，保持时序感知

**将峰值显存限制在 7GB 以下的核心策略**：
1. **限制 `max_pixels`**（最关键）：将视频总像素预算从默认 6.3M 降到 2M，直接削减 60%+ 的 vision tokens
2. **启用 Flash Attention 2**：避免 `O(patches²)` 的 attention 显存爆炸
3. **保持现有帧数/尺寸限制**：`video_max_frames=5`、`image_max_size=448`
4. **显存回收**：每次推理后 `torch.cuda.empty_cache()`

按此方案实施后，**1图 + 2视频的复杂场景峰值显存可控制在 5GB 以内**，为 8GB 显卡（如 RTX 5060 Laptop）留出充足余量。
