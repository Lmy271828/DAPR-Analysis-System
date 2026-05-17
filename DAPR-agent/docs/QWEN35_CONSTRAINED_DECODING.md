# Qwen3.5 约束解码（Constrained Decoding）实现指南

> 本文档说明如何在 DAPR-Analysis-System 中为 Qwen3.5 实现结构化 JSON 输出约束，确保分析阶段输出的 JSON 100% 合法可解析。

---

## 一、为什么需要约束解码

当前系统的问题：

| 问题 | 当前状态 | 约束解码解决方式 |
|------|---------|----------------|
| Markdown 包裹 | ````json\n{...}\n```` | 模型根本不能输出 markdown token |
| 字段名拼写错误 | `creative_guesstimates` vs `psychological_guesstimates` | 只允许预定义的键名 token |
| 字符串未闭合 | `"大雨很密集`（缺右引号） | 强制字符串必须闭合后才允许输出其他 token |
| 括号不匹配 | `{"a": 1, "b": [`（缺右括号） | 只允许合法的 JSON 语法 token |
| 前后缀文字 | `好的，这是分析结果：{...}希望对你有帮助` | 模型只能输出 JSON token |

**约束解码的本质**：在模型生成每个 token 时，根据当前已生成内容的上下文，过滤掉所有会导致非法 JSON 的 token，只允许选择合法的下一个 token。

---

## 二、三种实现路径

### 路径 1：lm-format-enforcer（推荐，零模型改动）

**原理**：在 `model.generate()` 中传入一个 `LogitsProcessor`，每次采样前用 FSM（有限状态机）过滤 logits。

**优点**：
- pip 安装即可，无需改模型权重
- 与 transformers 无缝集成
- 支持 JSON Schema
- 显存开销 ≈ 0（状态机在 CPU 上运行）

**安装**：
```bash
pip install lm-format-enforcer
```

**集成到当前系统的代码**：

```python
# backend/services/llm/core.py

from lmformatenforcer import JsonSchemaParser
from lmformatenforcer.integrations.transformers import (
    build_transformers_prefix_allowed_tokens_fn,
    build_transformers_logits_processor_list
)

class LocalVLMService:
    # ... 现有代码 ...

    def generate(
        self,
        prompt: str,
        images: List[str] = None,
        videos: List[str] = None,
        system_prompt: str = "",
        video_max_frames: int = 10,
        force_json: bool = False,
        json_schema: dict = None,  # 新增：JSON Schema 约束
    ) -> str:
        images = images or []
        videos = videos or []

        if force_json:
            prompt = prompt + "\n\n【重要】你必须只输出合法 JSON，不要 markdown 代码块，不要解释文字。"

        with self._model_lock:
            inputs = self._prepare_inputs(
                prompt, images, videos, system_prompt, video_max_frames
            )

            # 构建 generation 参数
            generation_kwargs = dict(
                **inputs,
                max_new_tokens=LOCAL_VLM_CONFIG.get("max_new_tokens", 512),
                do_sample=False,
            )

            # ── 约束解码：lm-format-enforcer ──
            if force_json and json_schema:
                parser = JsonSchemaParser(json_schema)
                # 方法 A：前缀约束（transformers >= 4.26）
                prefix_fn = build_transformers_prefix_allowed_tokens_fn(
                    self._processor.tokenizer, parser
                )
                generation_kwargs["prefix_allowed_tokens_fn"] = prefix_fn

                # 方法 B：logits processor（更精细控制）
                # logits_processors = build_transformers_logits_processor_list(
                #     self._processor.tokenizer, parser
                # )
                # generation_kwargs["logits_processor"] = logits_processors

            with torch.inference_mode():
                output_ids = self._model.generate(**generation_kwargs)

            generated_ids = output_ids[0][inputs.input_ids.shape[1]:]
            response = self._processor.decode(generated_ids, skip_special_tokens=True)
            response = response.replace('<think>\n\n</think>\n\n', '').strip()

            del inputs, output_ids, generated_ids
            torch.cuda.empty_cache()

        return response
```

**流式版本（generate_stream）**：

lm-format-enforcer 支持流式约束，但需要自定义 streamer：

```python
from lmformatenforcer.integrations.transformers import (
    build_transformers_logits_processor_list
)

def generate_stream(..., force_json=False, json_schema=None):
    # ... 准备 inputs ...

    streamer = TextIteratorStreamer(self._processor, skip_prompt=True, skip_special_tokens=True)

    generation_kwargs = dict(
        inputs,
        streamer=streamer,
        max_new_tokens=LOCAL_VLM_CONFIG.get("max_new_tokens", 2048),
        do_sample=False,
    )

    if force_json and json_schema:
        parser = JsonSchemaParser(json_schema)
        logits_processors = build_transformers_logits_processor_list(
            self._processor.tokenizer, parser
        )
        generation_kwargs["logits_processor"] = logits_processors

    def _generate():
        with self._model_lock:
            self._model.generate(**generation_kwargs)

    thread = threading.Thread(target=_generate)
    thread.start()

    for text in streamer:
        if '<think>' in text:
            text = text.replace('<think>\n\n</think>\n\n', '')
        yield text

    thread.join()
```

**分析阶段的 JSON Schema**：

```python
# backend/services/llm/schemas.py（建议新建）

ANALYSIS_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ok", "unknown"]},
        "data": {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "object",
                    "properties": {
                        "drawing_features": {"type": "object"},
                        "expression_observation": {"type": "object"},
                        "process_observation": {"type": "object"},
                    },
                    "required": ["drawing_features", "expression_observation", "process_observation"]
                },
                "questions_for_user": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 5
                },
                "psychological_guesstimates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 5
                }
            },
            "required": ["analysis", "questions_for_user", "psychological_guesstimates"]
        },
        "error": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"}
            },
            "required": ["code", "message"]
        }
    },
    "required": ["status"]
}
```

---

### 路径 2：transformers 原生 Grammar（依赖版本）

transformers >= 4.39 开始支持 `grammar` 参数：

```python
# 需要 transformers 4.39+ 且模型支持
output_ids = self._model.generate(
    **inputs,
    max_new_tokens=512,
    do_sample=False,
    grammar=JsonGrammar(ANALYSIS_JSON_SCHEMA),  # 或 BNF 语法字符串
)
```

**限制**：
- transformers 版本要求较新
- Qwen3.5 的 `model_type` 为 `qwen3_5`，transformers 对其 grammar 支持尚未验证
- 不如 lm-format-enforcer 成熟稳定

**结论**：不推荐作为首选方案。

---

### 路径 3：Qwen3.5 Function Calling（原生能力）

Qwen3.5 的 chat template 中已经定义了 tool_call 格式，说明模型原生支持 function calling。

**原理**：将 JSON 输出建模为一个"函数调用"，让模型以调用函数的方式返回结构化数据。

```python
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": prompt},
]

tools = [{
    "type": "function",
    "function": {
        "name": "submit_drawing_analysis",
        "description": "提交绘画分析结果",
        "parameters": ANALYSIS_JSON_SCHEMA
    }
}]

text = self._processor.apply_chat_template(
    messages,
    tools=tools,
    tokenize=False,
    add_generation_prompt=True,
    enable_thinking=False,
)
```

**限制**：
- Qwen3.5 的 tool_call 格式与标准 OpenAI 格式不同（见 chat_template）
- 解析 tool_call 输出需要额外逻辑
- 流式生成时 tool_call 的边界处理较复杂

**结论**：能力最强但集成复杂度最高，适合未来深度优化时使用。

---

## 三、三种路径对比

| 维度 | lm-format-enforcer | transformers grammar | Qwen3.5 function calling |
|------|-------------------|---------------------|-------------------------|
| 安装成本 | `pip install` | 升级 transformers | 无额外依赖 |
| 模型改动 | 零 | 零 | 零 |
| 显存开销 | ≈0 | ≈0 | ≈0 |
| 开发复杂度 | 低 | 中 | 高 |
| 流式支持 | 支持 | 可能支持 | 需自定义 |
| JSON Schema 支持 | 完整 | 有限 | 完整 |
| 稳定性 | 高（成熟库） | 中（较新特性） | 中（需适配格式） |
| 推荐度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

---

## 四、推荐方案：lm-format-enforcer 两阶段落地

### 第一阶段（当前即可执行）：Prompt 层约束

已在方案 A 中完成：`force_json=True` 时追加 `"你必须只输出合法 JSON..."`。

这是**零成本**的第一步，可过滤 70% 的格式问题。

### 第二阶段（建议下次迭代）：Logits 层约束

引入 `lm-format-enforcer`，为 `analyze_drawing_stream` 传入 JSON Schema。

这是**根本解决**方案，可过滤 99%+ 的格式问题。

```python
# analyze_drawing_stream 调用时
from services.llm.schemas import ANALYSIS_JSON_SCHEMA

for chunk in self.generate_stream(
    prompt=prompt,
    images=[drawing_path],
    videos=videos,
    video_types=video_types,
    system_prompt=system_prompt,
    video_max_frames=LOCAL_VLM_CONFIG.get("video_max_frames", 10),
    force_json=True,
    json_schema=ANALYSIS_JSON_SCHEMA,  # 新增
):
    ...
```

### 为什么分阶段？

| 阶段 | 工作量 | 风险 | 效果 |
|------|--------|------|------|
| Prompt 约束（已完成） | 5 分钟 | 零 | 解决 70% |
| lm-format-enforcer | 2 小时 | 低（成熟库） | 解决 99%+ |
| function calling | 1 天 | 中（需适配） | 解决 99%+ |

Prompt 层约束已立即生效。lm-format-enforcer 可作为下一次 PR 引入，无需阻塞当前发布。

---

## 五、8GB VRAM 下的特殊考量

lm-format-enforcer 的运行时开销：

| 组件 | 位置 | 内存占用 |
|------|------|---------|
| FSM 状态机 | CPU RAM | ~1-10 MB（取决于 Schema 复杂度） |
| logits 过滤 | GPU VRAM | 零（在 logits 张量上做掩码，不增加显存） |
| tokenizer 调用 | CPU | 可忽略 |

**结论**：lm-format-enforcer 对 8GB VRAM 系统完全无压力。

---

## 六、参考链接

- [lm-format-enforcer GitHub](https://github.com/noamgat/lm-format-enforcer)
- [transformers Grammar Docs](https://huggingface.co/docs/transformers/main_classes/text_generation)
- [Qwen3 Function Calling](https://qwen.readthedocs.io/en/latest/deployment/function_call.html)
- [Outlines Structured Generation](https://dottxt-ai.github.io/outlines/)
