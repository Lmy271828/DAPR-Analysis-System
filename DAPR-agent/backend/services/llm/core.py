"""
LLM 服务 — 双模型架构

- KimiService（云端）: 纯文字问答，处理访谈对话、问题生成、最终报告
- LocalVLMService（本地 Qwen3.5）: 多模态分析，处理绘画/视频敏感数据

安全隔离：原始图像/视频仅由本地 VLM 处理，云端 Kimi 只接收文字结果。
"""
import json
import os
import re
import tempfile
import threading
from typing import List, Dict, Optional, Generator, Tuple
from pathlib import Path

# OpenAI SDK 用于调用 Kimi API (Moonshot 提供 OpenAI 兼容接口)
from openai import OpenAI, APIError, APITimeoutError
from config import LLM_CONFIG, LOCAL_VLM_CONFIG

from services.video import VideoUtils
from services.conversation import ConversationManager
from services.llm import prompts
from services.llm import parsers

# 结构化生成约束（可选依赖）
try:
    from lmformatenforcer import JsonSchemaParser
    from lmformatenforcer.integrations.transformers import (
        build_transformers_prefix_allowed_tokens_fn
    )
    _LM_FORMAT_ENFORCER_AVAILABLE = True
except ImportError:
    _LM_FORMAT_ENFORCER_AVAILABLE = False

# 本地 VLM (Qwen3.5 AWQ INT4)
try:
    import torch
    from PIL import Image
    from transformers import Qwen3_5ForConditionalGeneration, AutoProcessor, TextIteratorStreamer
    from transformers.video_utils import VideoMetadata
    _LOCAL_VLM_AVAILABLE = True
except ImportError as _e:
    _LOCAL_VLM_AVAILABLE = False
    print(f"[LocalVLM] 依赖缺失，无法加载本地模型: {_e}")


class KimiService:
    """
    Kimi-K2.5 API 服务 —— 云端纯文字 LLM

    每个会话拥有独立的 KimiService 实例，确保对话历史、
    上下文记忆在不同用户之间完全隔离，避免会话污染。

    职责（纯文字）：
    - 访谈对话评估与问题生成
    - 艺术创作反馈报告生成

    Note: 图像/视频分析由 LocalVLMService 处理，
    原始敏感数据不上云端。
    """

    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.api_key = LLM_CONFIG.get("api_key", "")
        self.base_url = LLM_CONFIG.get("base_url", "https://api.moonshot.cn/v1")
        self.model = LLM_CONFIG.get("model", "kimi-k2.5")
        self.max_tokens = LLM_CONFIG.get("max_tokens", 4096)
        self.temperature = LLM_CONFIG.get("temperature", 0.7)

        # 验证 API Key
        if not self.api_key:
            print("[LLM] 警告: MOONSHOT_API_KEY 未设置，请在环境变量中配置")

        # 初始化对话管理器（每实例独立，避免会话间污染）
        self.conversation = ConversationManager(
            max_context_length=self.max_tokens * 8,
            max_keep_turns=20
        )

        # 初始化 OpenAI 客户端
        try:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            print(f"[LLM] Kimi 服务已初始化")
            print(f"[LLM] 模型: {self.model}")
            print(f"[LLM] Base URL: {self.base_url}")
        except Exception as e:
            print(f"[LLM] 初始化失败: {e}")
            raise

    def _build_response_format(self, force_json: bool, json_schema: dict = None):
        """构建 Moonshot 兼容的 response_format 参数。

        Moonshot 要求 json_schema 必须包含 name 字段。
        如果传入的 schema 没有 name，自动填充默认值。
        """
        if json_schema:
            schema_name = json_schema.get("name", "structured_output")
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": json_schema,
                }
            }
        if force_json:
            return {"type": "json_object"}
        return None

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        force_json: bool = False,
        json_schema: dict = None,
    ) -> str:
        """纯文字生成回复（云端 Kimi 不接触图像/视频）

        Args:
            json_schema: 传入则启用 Moonshot JSON Schema 严格模式。
                         若 API 不支持，自动降级为 json_object 并重试一次。
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        print(f"[LLM] 发送文字请求 -> {self.model} (schema={json_schema is not None})")

        response_format = self._build_response_format(force_json, json_schema)
        used_schema = json_schema is not None

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                **({"response_format": response_format} if response_format else {})
            )
            output_text = response.choices[0].message.content
            print(f"[LLM] 生成完成，输出长度: {len(output_text)}")
        except APITimeoutError as e:
            print(f"[LLM] 请求超时: {e}")
            raise
        except APIError as e:
            # Moonshot 旧版/部分模型不支持 json_schema，自动降级为 json_object
            status_code = getattr(e, "status_code", None) or getattr(e, "http_status", None)
            if used_schema and status_code in (400, 422):
                print(f"[LLM] JSON Schema 模式不受支持 (status={status_code})，降级为 json_object 模式")
                response_format = self._build_response_format(force_json=True, json_schema=None)
                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        max_tokens=self.max_tokens,
                        temperature=self.temperature,
                        **({"response_format": response_format} if response_format else {})
                    )
                    output_text = response.choices[0].message.content
                    print(f"[LLM] 降级后生成完成，输出长度: {len(output_text)}")
                except Exception as e2:
                    print(f"[LLM] 降级后请求失败: {e2}")
                    raise
            else:
                print(f"[LLM] API 错误: {e}")
                raise
        except Exception as e:
            print(f"[LLM] 请求失败: {e}")
            raise

        # 保存到对话历史
        if system_prompt:
            self.conversation.add_message("user", prompt)
            self.conversation.add_message("assistant", output_text)

        return output_text

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        force_json: bool = False,
        json_schema: dict = None,
    ) -> Generator[str, None, None]:
        """纯文字流式生成回复（云端 Kimi 不接触图像/视频）"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        print(f"[LLM Stream] 开始流式文字请求")

        response_format = self._build_response_format(force_json, json_schema)

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=True,
                **({"response_format": response_format} if response_format else {})
            )
        except Exception as e:
            print(f"[LLM Stream] 启动流式请求失败: {e}")
            raise

        generated_text = ""
        for chunk in stream:
            if chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                generated_text += text
                yield text

        print(f"[LLM Stream] 流式生成完成: {len(generated_text)} 字符")

        # 保存到对话历史
        if system_prompt:
            self.conversation.add_message("user", prompt[:500])

        generated_text = ""
        for chunk in stream:
            if chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                generated_text += text
                yield text

        print(f"[LLM Stream] 流式生成完成: {len(generated_text)} 字符")

        # 保存到对话历史
        if system_prompt:
            self.conversation.add_message("user", prompt[:500])
            self.conversation.add_message("assistant", generated_text[:1000])

    # --- 绘画分析已迁移到 LocalVLMService，KimiService 只处理纯文字 ---

    def generate_follow_up_questions(
        self,
        selected_image: Dict,
        hypotheses: List[Dict],
        conversation_history: List[Dict] = None,
        selection_behavior: Dict = None
    ) -> List[str]:
        """基于图像选择、选择行为数据和访谈对话历史生成深入问题（DAPR深度访谈阶段）"""

        # 格式化访谈对话历史
        if conversation_history:
            conversation_text = "\n".join([
                f"{'AI' if msg.get('role') == 'agent' else '用户'}: {msg.get('content', '')}"
                for msg in conversation_history
            ])
        else:
            conversation_text = "（无访谈对话记录）"

        # 格式化选择行为数据
        selection_text = ""
        if selection_behavior:
            sel = selection_behavior
            view_order = sel.get('viewOrder', [])
            final = sel.get('finalSelection', {})
            hesitations = sel.get('hesitationIndicators', [])
            durations = sel.get('viewDurations', {})
            
            selection_text = f"""【实际选择行为数据】
- 图像查看顺序: {view_order}
- 最终选择是第 {final.get('viewOrder', 'N/A')} 个查看的图像（共查看 {final.get('totalViews', 'N/A')} 张）
- 各图像停留时长(ms): {durations}
- 犹豫指标 ({len(hesitations)} 个):
"""
            for h in hesitations:
                selection_text += f"  • [{h.get('type', '')}] {h.get('description', '')}\n"
        else:
            selection_text = "（无选择行为数据）"

        prompt = prompts.build_follow_up_questions_prompt(
            selected_image, conversation_text, hypotheses, selection_text
        )

        response = self.generate(prompt=prompt, force_json=True)

        try:
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        return ["您为什么选择这张图片？这与您最初的画作有什么不同？", "如果画中的人物是您自己，这个场景代表您内心有什么样的渴望或需要？"]

    def generate_final_report(
        self,
        selected_image: Dict,
        previous_hypotheses: List[Dict],
        conversation_history: List[Dict],
        final_answers: List[str],
        drawing_analysis: Dict = None,
        selection_behavior: Dict = None,
        user_info: Dict = None
    ) -> Dict:
        """生成最终艺术创作反馈报告（非诊断）"""

        conversation_text = ""
        if conversation_history:
            conversation_lines = []
            for msg in conversation_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    conversation_lines.append(f"用户: {content[:100]}...")
                elif role == "assistant":
                    conversation_lines.append(f"AI: {content[:100]}...")
            conversation_text = "\n".join(conversation_lines)

        selection_text = ""
        if selection_behavior:
            sel = selection_behavior
            selection_text = f"""
【选择行为数据】
- 图像查看顺序: {sel.get('viewOrder', [])}
- 最终选择: 第{sel.get('finalSelection', {}).get('viewOrder', 'N/A')}个查看的图像
- 犹豫指标: {len(sel.get('hesitationIndicators', []))}个
"""

        user_info_text = ""
        if user_info:
            user_info_text = f"""
【受试者基本信息】
- 年龄段: {user_info.get('age_group', '未提供')}
- 性别: {user_info.get('gender', '未提供')}
- 特殊考虑: {user_info.get('special_considerations', '无')}
"""

        # 提取绘画分析中的评分数据
        scoring_data = ""
        if drawing_analysis:
            analysis = drawing_analysis.get("analysis", {})
            scoring = analysis.get("scoring", {})
            if scoring:
                stress = scoring.get("stress_indicators", {})
                coping = scoring.get("coping_resources", {})
                scoring_data = f"""
【DAPR综合评分数据】
压力总分: {stress.get('total_stress_score', 'N/A')}/18
应对资源总分: {coping.get('total_coping_score', 'N/A')}/10
综合评分: {scoring.get('composite_score', 'N/A')}
"""

        prompt = prompts.build_final_report_prompt(
            user_info_text=user_info_text,
            scoring_data=scoring_data,
            selected_image=selected_image,
            selection_text=selection_text,
            conversation_text=conversation_text,
            previous_hypotheses=previous_hypotheses,
            final_answers=final_answers,
        )

        response = self.generate(prompt=prompt, force_json=True)
        return parsers.parse_final_report_with_contract(response)

    def clear_conversation(self):
        """清空对话历史"""
        self.conversation.clear()
        print("[LLM] 对话历史已清空")


def init_local_vlm(model_path: str = None):
    """预加载本地 VLM 模型（在应用启动时调用）"""
    if not _LOCAL_VLM_AVAILABLE:
        print("[LocalVLM] 依赖不可用，跳过预加载")
        return
    if LocalVLMService._model is not None:
        return
    if model_path:
        LOCAL_VLM_CONFIG["model_path"] = model_path
    LocalVLMService._ensure_model_loaded()


class LocalVLMService:
    """
    本地 Qwen3.5 AWQ INT4 VLM 服务

    全局单例模型，会话级对话历史隔离。
    使用线程锁确保 GPU 推理串行（8GB 显存限制）。

    职责（多模态）：
    - DAPR 绘画/视频分析（敏感数据不上云端）

    分析完成后应调用 unload() 释放显存，
    后续文字处理由 KimiService 接管。
    """

    _model = None
    _processor = None
    _init_lock = threading.Lock()
    _model_lock = threading.Lock()

    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self._ensure_model_loaded()
        self.conversation = ConversationManager(
            max_context_length=4096 * 4,
            max_keep_turns=20
        )

    @classmethod
    def _ensure_model_loaded(cls):
        if cls._model is not None:
            return
        with cls._init_lock:
            if cls._model is not None:
                return
            model_path = LOCAL_VLM_CONFIG["model_path"]
            print(f"[LocalVLM] Loading Qwen3.5 AWQ INT4 from {model_path}...")
            cls._processor = AutoProcessor.from_pretrained(
                model_path, trust_remote_code=True
            )
            # 尝试启用 Flash Attention 2 以降低 vision/text attention 峰值显存
            attn_impl = "flash_attention_2"
            try:
                import flash_attn  # noqa: F401
            except ImportError:
                attn_impl = "sdpa"
                print("[LocalVLM] flash-attn 未安装，回退到 SDPA")
            cls._model = Qwen3_5ForConditionalGeneration.from_pretrained(
                model_path,
                torch_dtype=torch.bfloat16,
                device_map="cuda",
                trust_remote_code=True,
                attn_implementation=attn_impl,
            )
            print(f"[LocalVLM] Model loaded on {cls._model.device}")
            print(f"[LocalVLM] VRAM: {torch.cuda.memory_allocated()/1024**3:.2f} GB")

    @staticmethod
    def _resize_for_vlm(img: Image.Image, max_size: int = 448) -> Image.Image:
        """限制图像尺寸，避免大图像产生过量 patch tokens"""
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        return img

    def _prepare_inputs(
        self,
        prompt: str,
        images: List[str],
        videos: List[str],
        system_prompt: str,
        video_max_frames: int = 10,
        video_types: List[str] = None,
    ):
        """
        构建模型输入。

        图像和视频分开传入 processor，视频以原生帧序列方式处理，
        利用 temporal_patch_size 进行时序合并，减少 token 消耗。
        """
        max_size = LOCAL_VLM_CONFIG.get("image_max_size", 448)
        all_images = []
        all_videos = []           # List[List[PIL.Image]]，每个内部列表是一个视频
        video_metadata_list = []  # List[VideoMetadata]

        for img_path in (images or []):
            if img_path and os.path.exists(img_path):
                img = Image.open(img_path).convert("RGB")
                img = self._resize_for_vlm(img, max_size)
                all_images.append(img)

        for idx, video_path in enumerate(videos or []):
            if video_path and os.path.exists(video_path):
                info = VideoUtils.get_video_info(video_path)
                temp_dir = tempfile.mkdtemp()
                # 根据视频类型选择裁剪策略
                video_type = (video_types or [])[idx] if video_types and idx < len(video_types) else "webcam"
                crop_mode = "canvas_ratio" if video_type == "canvas" else "center"
                frame_paths = VideoUtils.extract_uniform_frames(
                    video_path,
                    temp_dir,
                    num_frames=video_max_frames,
                    skip_head_tail=True,
                    crop_mode=crop_mode,
                    max_size=max_size,
                )
                frames = []
                for fp in frame_paths:
                    if os.path.exists(fp):
                        img = Image.open(fp).convert("RGB")
                        img = self._resize_for_vlm(img, max_size)
                        frames.append(img)
                if frames:
                    all_videos.append(frames)
                    # 使用原视频信息构造正确的 VideoMetadata，确保时戳计算准确
                    original_fps = info.get("fps", 30.0)
                    duration = info.get("duration", 0)
                    original_total_frames = info.get("total_frames", int(duration * original_fps) if duration > 0 else 0)

                    # 计算抽出的帧在原视频中的正确索引
                    sampling_meta = VideoUtils.compute_sampling_meta(
                        duration=duration,
                        num_frames=len(frames),
                        original_fps=original_fps,
                        skip_head_tail=True,
                    )
                    frame_indices = sampling_meta["frame_indices"]

                    video_metadata_list.append(
                        VideoMetadata(
                            total_num_frames=original_total_frames,
                            fps=original_fps,
                            width=frames[0].width,
                            height=frames[0].height,
                            duration=duration,
                            frames_indices=frame_indices,
                        )
                    )

        content = []
        for img in all_images:
            content.append({"type": "image", "image": img})
        for video_frames in all_videos:
            content.append({"type": "video", "video": video_frames})
        content.append({"type": "text", "text": prompt})

        messages = [{"role": "user", "content": content}]
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        text = self._processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
            enable_thinking=False
        )

        # 构建 processor kwargs，传入像素预算限制（显存优化的核心）
        processor_kwargs = {"return_tensors": "pt", "padding": True}
        if all_images:
            processor_kwargs["images"] = all_images
            processor_kwargs["images_kwargs"] = {
                "max_pixels": LOCAL_VLM_CONFIG.get("image_max_pixels", 1_000_000)
            }
        if all_videos:
            processor_kwargs["videos"] = [all_videos]
            processor_kwargs["videos_kwargs"] = {
                "max_pixels": LOCAL_VLM_CONFIG.get("video_max_pixels", 2_000_000)
            }
        if video_metadata_list:
            processor_kwargs["video_metadata"] = [video_metadata_list]

        inputs = self._processor(text=[text], **processor_kwargs).to(self._model.device)

        return inputs

    def generate(
        self,
        prompt: str,
        images: List[str] = None,
        videos: List[str] = None,
        system_prompt: str = "",
        video_max_frames: int = 10,
        force_json: bool = False,
        json_schema: dict = None,
        max_new_tokens: int = None,
    ) -> str:
        images = images or []
        videos = videos or []

        # force_json：追加格式提醒，强化 JSON 输出约束
        if force_json:
            prompt = prompt + "\n\n【重要】你必须只输出合法 JSON，不要 markdown 代码块，不要解释文字。"

        with self._model_lock:
            inputs = self._prepare_inputs(
                prompt, images, videos, system_prompt, video_max_frames
            )
            print(f"[LocalVLM] Generating: {len(images)} images + {len(videos)} videos, "
                  f"input_ids: {inputs.input_ids.shape}")

            # 构建 generation 参数
            generation_kwargs = dict(
                **inputs,
                max_new_tokens=max_new_tokens or LOCAL_VLM_CONFIG.get("max_new_tokens", 512),
                do_sample=LOCAL_VLM_CONFIG.get("do_sample", True),
                temperature=LOCAL_VLM_CONFIG.get("temperature", 0.1),
                top_p=LOCAL_VLM_CONFIG.get("top_p", 0.9),
                repetition_penalty=LOCAL_VLM_CONFIG.get("repetition_penalty", 1.05),
            )

            # ── 约束解码：lm-format-enforcer ──
            if force_json and json_schema and _LM_FORMAT_ENFORCER_AVAILABLE:
                parser = JsonSchemaParser(json_schema)
                prefix_fn = build_transformers_prefix_allowed_tokens_fn(
                    self._processor.tokenizer, parser
                )
                generation_kwargs["prefix_allowed_tokens_fn"] = prefix_fn
                print(f"[LocalVLM] 约束解码已启用: {json_schema.get('type', 'unknown')} schema")

            with torch.inference_mode():
                output_ids = self._model.generate(**generation_kwargs)
            generated_ids = output_ids[0][inputs.input_ids.shape[1]:]
            response = self._processor.decode(generated_ids, skip_special_tokens=True)
            # 清理残留的空 think 标签
            response = response.replace('<think>\n\n</think>\n\n', '').strip()

            # 显存回收：释放推理过程中的中间张量
            del inputs, output_ids, generated_ids
            torch.cuda.empty_cache()

        print(f"[LocalVLM] Generated {len(response)} chars")
        return response

    def generate_stream(
        self,
        prompt: str,
        images: List[str] = None,
        videos: List[str] = None,
        video_types: List[str] = None,
        system_prompt: str = "",
        video_max_frames: int = 10,
        force_json: bool = False,
        json_schema: dict = None,
        max_new_tokens: int = None,
    ) -> Generator[str, None, None]:
        images = images or []
        videos = videos or []

        # force_json：追加格式提醒，强化 JSON 输出约束
        if force_json:
            prompt = prompt + "\n\n【重要】你必须只输出合法 JSON，不要 markdown 代码块，不要解释文字。"

        inputs = self._prepare_inputs(
            prompt, images, videos, system_prompt, video_max_frames, video_types
        )
        streamer = TextIteratorStreamer(
            self._processor, skip_prompt=True, skip_special_tokens=True
        )
        generation_kwargs = dict(
            inputs,
            streamer=streamer,
            max_new_tokens=max_new_tokens or LOCAL_VLM_CONFIG.get("max_new_tokens", 2048),
            do_sample=LOCAL_VLM_CONFIG.get("do_sample", True),
            temperature=LOCAL_VLM_CONFIG.get("temperature", 0.1),
            top_p=LOCAL_VLM_CONFIG.get("top_p", 0.9),
            repetition_penalty=LOCAL_VLM_CONFIG.get("repetition_penalty", 1.05),
        )

        # ── 约束解码：lm-format-enforcer ──
        if force_json and json_schema and _LM_FORMAT_ENFORCER_AVAILABLE:
            parser = JsonSchemaParser(json_schema)
            prefix_fn = build_transformers_prefix_allowed_tokens_fn(
                self._processor.tokenizer, parser
            )
            generation_kwargs["prefix_allowed_tokens_fn"] = prefix_fn
            print(f"[LocalVLM Stream] 约束解码已启用: {json_schema.get('type', 'unknown')} schema")

        def _generate():
            with self._model_lock:
                self._model.generate(**generation_kwargs)

        thread = threading.Thread(target=_generate)
        thread.start()

        generated_text = ""
        for text in streamer:
            # 流式生成中逐步清理 think 标签残留
            if '<think>' in text:
                text = text.replace('<think>\n\n</think>\n\n', '')
            generated_text += text
            yield text

        thread.join()
        print(f"[LocalVLM Stream] Completed: {len(generated_text)} chars")

    def analyze_drawing_stream(
        self,
        drawing_path: str,
        webcam_video: str = None,
        canvas_video: str = None,
        user_profile: dict = None
    ) -> Generator[Tuple[str, Optional[Dict]], None, None]:
        """绘画分析流（方案 B：图像与视频解耦，分批推理）

        Batch A: 绘画成品 → drawing_features
        Batch B: webcam + canvas 视频 → expression_observation + process_observation
        """
        import os

        has_webcam = webcam_video and os.path.exists(webcam_video)
        has_screen = canvas_video and os.path.exists(canvas_video)

        video_info_text = []
        if has_webcam:
            info = VideoUtils.get_video_info(webcam_video)
            video_info_text.append(VideoUtils._format_video_info(info, "第一个视频（面部表情）"))
        if has_screen:
            info = VideoUtils.get_video_info(canvas_video)
            video_info_text.append(VideoUtils._format_video_info(info, "第二个视频（绘画过程）"))
        video_info_section = "\n\n【视频信息】\n" + "\n".join(video_info_text) if video_info_text else ""

        # ── Batch A: 图像分析（绘画成品）──
        yield ("【正在分析绘画成品】", None)
        image_prompt = prompts.build_image_analysis_prompt(user_profile)
        image_schema = None
        try:
            from services.llm.schemas import IMAGE_ANALYSIS_SCHEMA
            image_schema = IMAGE_ANALYSIS_SCHEMA
        except ImportError:
            pass

        image_response = ""
        for chunk in self.generate_stream(
            prompt=image_prompt,
            images=[drawing_path],
            force_json=True,
            json_schema=image_schema,
            max_new_tokens=4096,
        ):
            image_response += chunk
            yield (chunk, None)

        print(f"[LocalVLM Stream] Batch A 完成，解析图像分析结果...")
        image_result = parsers.parse_image_analysis_response(image_response)

        # ── Batch B: 视频分析（表情 + 绘画过程）──
        if has_webcam or has_screen:
            yield ("【正在分析视频】", None)
            video_prompt = prompts.build_video_analysis_prompt(
                has_webcam, has_screen, video_info_section, user_profile
            )
            videos = []
            video_types = []
            if has_webcam:
                videos.append(webcam_video)
                video_types.append("webcam")
            if has_screen:
                videos.append(canvas_video)
                video_types.append("canvas")

            video_schema = None
            try:
                from services.llm.schemas import VIDEO_ANALYSIS_SCHEMA
                video_schema = VIDEO_ANALYSIS_SCHEMA
            except ImportError:
                pass

            video_response = ""
            for chunk in self.generate_stream(
                prompt=video_prompt,
                videos=videos,
                video_types=video_types,
                video_max_frames=LOCAL_VLM_CONFIG.get("video_max_frames", 10),
                force_json=True,
                json_schema=video_schema,
                max_new_tokens=4096,
            ):
                video_response += chunk
                yield (chunk, None)

            print(f"[LocalVLM Stream] Batch B 完成，解析视频分析结果...")
            video_result = parsers.parse_video_analysis_response(video_response)
        else:
            video_result = {"analysis": {"expression_observation": [], "process_observation": []}}

        # ── 合并两批结果 ──
        merged_analysis = {
            "drawing_features": image_result.get("analysis", {}).get("drawing_features", []),
            "expression_observation": video_result.get("analysis", {}).get("expression_observation", []),
            "process_observation": video_result.get("analysis", {}).get("process_observation", []),
        }
        merged_result = {
            "analysis": merged_analysis,
            "questions_for_user": [],
            "psychological_guesstimates": [],
        }
        standardized = parsers.standardize_analysis_result(merged_result)
        yield ("", standardized)

    # --- 后续问题生成 / 最终报告 已迁移到 KimiService（云端纯文字处理） ---

    def clear_conversation(self):
        self.conversation.clear()
        print("[LocalVLM] 对话历史已清空")

    @classmethod
    def unload(cls):
        """释放本地 VLM 显存（用于分析完成后切换权重）"""
        if cls._model is not None:
            print("[LocalVLM] Unloading model from GPU...")
            import gc
            cls._model.cpu()
            del cls._model
            cls._model = None
            if cls._processor is not None:
                del cls._processor
                cls._processor = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                print(f"[LocalVLM] VRAM after unload: {torch.cuda.memory_allocated()/1024**3:.2f} GB")
        else:
            print("[LocalVLM] Model not loaded, nothing to unload")


def create_llm_service(session_id: str):
    """
    创建本地 VLM 服务（用于图像/视频分析阶段）

    始终优先使用 Qwen3.5 本地模型处理敏感的多模态数据，
    确保原始图像/视频不上云端。
    """
    if _LOCAL_VLM_AVAILABLE:
        print(f"[LLM] 为会话 {session_id[:8]}... 创建 LocalVLMService 实例")
        return LocalVLMService(session_id=session_id)
    print(f"[LLM] 本地 VLM 不可用，为会话 {session_id[:8]}... 回退到 KimiService")
    return KimiService(session_id=session_id)


def create_cloud_llm_service(session_id: str):
    """
    创建云端 LLM 服务（用于纯文字问答阶段）

    仅接收本地 VLM 处理后的文字结果，不接触原始图像/视频，
    实现敏感数据不上云端的安全隔离。
    """
    print(f"[LLM] 为会话 {session_id[:8]}... 创建 KimiService（云端）实例")
    return KimiService(session_id=session_id)
