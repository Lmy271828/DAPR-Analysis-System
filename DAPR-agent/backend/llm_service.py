"""
LLM 服务 - 使用 Kimi-K2.5 API (OpenAI兼容格式)
支持多模态输入：图像 + 视频(通过ffmpeg提取关键帧)

说明：
- Moonshot Kimi-K2.5 API 进行 DAPR 分析
- ComfyUI 图像生成工作流仍在本地运行
"""
import json
import os
import re
import subprocess
import tempfile
from typing import List, Dict, Optional, Generator, Tuple, Any
from pathlib import Path
from datetime import datetime
import base64

# OpenAI SDK 用于调用 Kimi API (Moonshot 提供 OpenAI 兼容接口)
from openai import OpenAI, APIError, APITimeoutError
from config import LLM_CONFIG

class VideoUtils:
    """视频工具类 - 基于 ffmpeg/ffprobe"""
    
    @staticmethod
    def get_video_info(video_path: str) -> Dict:
        """
        获取视频信息（时长、帧率、帧数等）
        使用多种方法尝试获取准确信息
        返回: {"duration": float, "fps": float, "total_frames": int, "width": int, "height": int}
        """
        if not os.path.exists(video_path):
            print(f"[VideoUtils] 文件不存在: {video_path}")
            return {"duration": 0, "fps": 0, "total_frames": 0, "width": 0, "height": 0}
        
        file_size = os.path.getsize(video_path)
        print(f"[VideoUtils] 视频文件: {video_path} ({file_size / 1024 / 1024:.2f} MB)")
        
        # 方法1: 使用 ffprobe 获取完整信息
        info = VideoUtils._probe_full_info(video_path)
        if info.get('duration', 0) > 0:
            return info
        
        # 方法2: 尝试从 format 层面获取时长
        duration = VideoUtils._probe_duration_only(video_path)
        if duration > 0:
            print(f"[VideoUtils] 从format获取时长: {duration:.1f}s")
            return {
                "duration": duration,
                "fps": 25.0,
                "total_frames": int(duration * 25),
                "width": 640,
                "height": 480
            }
        
        # 方法3: 使用 ffmpeg 计数实际帧数（最准确但较慢）
        frame_count = VideoUtils._count_frames(video_path)
        if frame_count > 0:
            # 假设默认fps=25，反推时长
            estimated_duration = frame_count / 25.0
            print(f"[VideoUtils] 通过帧数计算时长: {frame_count}帧 / 25fps = {estimated_duration:.1f}s")
            return {
                "duration": estimated_duration,
                "fps": 25.0,
                "total_frames": frame_count,
                "width": 640,
                "height": 480
            }
        
        # 方法4: 基于文件大小估算（最后降级方案）
        estimated_duration = (file_size * 8) / (2 * 1024 * 1024)  # 假设2Mbps码率
        print(f"[VideoUtils] 基于文件大小估算时长: {estimated_duration:.1f}s")
        return {
            "duration": max(estimated_duration, 10.0),  # 至少10秒
            "fps": 25.0,
            "total_frames": int(estimated_duration * 25),
            "width": 640,
            "height": 480
        }
    
    @staticmethod
    def _probe_full_info(video_path: str) -> Dict:
        """使用 ffprobe 获取完整视频信息"""
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=duration,r_frame_rate,nb_frames,width,height',
                '-of', 'json', video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                return {}
            
            data = json.loads(result.stdout)
            stream = data.get('streams', [{}])[0]
            
            if not stream:
                return {}
            
            # 解析帧率
            fps_str = stream.get('r_frame_rate', '0/1')
            if '/' in fps_str:
                num, den = fps_str.split('/')
                fps = float(num) / float(den) if float(den) != 0 else 0
            else:
                fps = float(fps_str)
            
            duration = float(stream.get('duration', 0))
            total_frames = int(stream.get('nb_frames', 0))
            width = int(stream.get('width', 0))
            height = int(stream.get('height', 0))
            
            if total_frames <= 0 and duration > 0 and fps > 0:
                total_frames = int(duration * fps)
            
            if duration > 0:
                print(f"[VideoUtils] 完整信息: 时长={duration:.1f}s, fps={fps:.1f}, 帧数={total_frames}, 分辨率={width}x{height}")
                
            return {
                "duration": duration,
                "fps": fps if fps > 0 else 25.0,
                "total_frames": total_frames,
                "width": width if width > 0 else 640,
                "height": height if height > 0 else 480
            }
        except Exception as e:
            print(f"[VideoUtils] _probe_full_info 失败: {e}")
            return {}
    
    @staticmethod
    def _probe_duration_only(video_path: str) -> float:
        """仅获取视频时长"""
        try:
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
                   '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout.strip():
                duration_str = result.stdout.strip()
                # 处理 'N/A' 或其他非数字字符串
                if duration_str.upper() == 'N/A' or not duration_str.replace('.', '').replace('-', '').isdigit():
                    return 0
                duration = float(duration_str)
                return duration if duration > 0 else 0
        except (ValueError, TypeError) as e:
            print(f"[VideoUtils] _probe_duration_only 转换失败: {e}")
        except Exception as e:
            print(f"[VideoUtils] _probe_duration_only 失败: {e}")
        return 0
    
    @staticmethod
    def _count_frames(video_path: str) -> int:
        """计数视频实际帧数（较慢但准确）"""
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-count_frames',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=nb_read_frames',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and result.stdout.strip():
                frame_count = int(result.stdout.strip())
                if frame_count > 0:
                    print(f"[VideoUtils] 实际帧数: {frame_count}")
                    return frame_count
        except Exception as e:
            print(f"[VideoUtils] _count_frames 失败: {e}")
        return 0
    
    
    @staticmethod
    def _format_video_info(info: Dict, video_name: str) -> str:
        """格式化视频信息为可读文本"""
        duration = info.get('duration', 0)
        fps = info.get('fps', 0)
        total_frames = info.get('total_frames', 0)
        width = info.get('width', 0)
        height = info.get('height', 0)
        
        parts = [f"- {video_name}"]
        if duration > 0:
            parts.append(f"时长{duration:.1f}s")
        if fps > 0:
            parts.append(f"原始fps={fps:.1f}")
        if total_frames > 0:
            parts.append(f"总帧数={total_frames}")
        if width > 0 and height > 0:
            parts.append(f"分辨率={width}x{height}")
        
        return ", ".join(parts) if len(parts) > 1 else f"- {video_name}: 信息不可用"
    
    @staticmethod
    def extract_key_frames(
        video_path: str, 
        output_dir: str,
        target_fps: float = 0.5,
        max_frames: int = 30
    ) -> List[str]:
        """
       
        不依赖视频时长信息，直接使用 ffmpeg 的 fps 过滤器按指定帧率提取
        
        Args:
            video_path: 视频文件路径
            output_dir: 输出目录
            target_fps: 目标帧率（每秒提取多少帧，默认0.5即每2秒一帧）
            max_frames: 最大提取帧数
            
        Returns:
            提取的帧文件路径列表
        """
        print(f"[VideoUtils] 提取关键帧: {video_path}")
        print(f"[VideoUtils] 参数: fps={target_fps}, max_frames={max_frames}")
        
        if not os.path.exists(video_path):
            print(f"[VideoUtils] 视频文件不存在: {video_path}")
            return []
        
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # 方法1: 使用 fps 过滤器（最优雅的方式）
            output_pattern = os.path.join(output_dir, "frame_%03d.jpg")
            
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-vf', f'fps={target_fps},scale=640:-1',  # fps过滤器+缩放
                '-frames:v', str(max_frames),  # 限制最大帧数
                '-q:v', '2',  # 高质量
                output_pattern
            ]
            
            print(f"[VideoUtils] 执行命令: ffmpeg -i {os.path.basename(video_path)} -vf fps={target_fps},scale=640:-1 -frames:v {max_frames}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            # 收集生成的帧
            frame_paths = []
            for i in range(1, max_frames + 1):
                frame_path = os.path.join(output_dir, f"frame_{i:03d}.jpg")
                if os.path.exists(frame_path):
                    file_size = os.path.getsize(frame_path)
                    if file_size > 0:
                        frame_paths.append(frame_path)
                    else:
                        print(f"[VideoUtils] 帧 {i} 大小为0，跳过")
                else:
                    break  # 没有更多帧了
            
            if frame_paths:
                print(f"[VideoUtils] 成功提取 {len(frame_paths)} 帧")
                if len(frame_paths) >= 2:
                    print(f"[VideoUtils] 首帧: {os.path.basename(frame_paths[0])}, 大小={os.path.getsize(frame_paths[0])} bytes")
                    print(f"[VideoUtils] 末帧: {os.path.basename(frame_paths[-1])}, 大小={os.path.getsize(frame_paths[-1])} bytes")
                return frame_paths
            else:
                print(f"[VideoUtils] 方法1失败，stderr: {result.stderr[:200] if result.stderr else 'N/A'}")
                # 尝试备用方法
                return VideoUtils._extract_frames_fallback(video_path, output_dir, target_fps, max_frames)
                
        except subprocess.TimeoutExpired:
            print(f"[VideoUtils] 提取超时（60s），尝试备用方法")
            return VideoUtils._extract_frames_fallback(video_path, output_dir, target_fps, max_frames)
        except Exception as e:
            print(f"[VideoUtils] 提取异常: {e}")
            import traceback
            traceback.print_exc()
            return VideoUtils._extract_frames_fallback(video_path, output_dir, target_fps, max_frames)
    
    @staticmethod
    def _extract_frames_fallback(video_path: str, output_dir: str, target_fps: float = 0.5, max_frames: int = 30) -> List[str]:
        """
        备用帧提取方法：使用 select 过滤器
        当 fps 过滤器失败时使用
        """
        print(f"[VideoUtils] 使用备用方法（select过滤器）")
        frame_paths = []
        
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # 计算采样间隔（假设原视频25fps）
            # 如果 target_fps=0.5，则每2秒一帧 = 每50帧取一帧（25fps * 2s）
            frame_interval = max(1, int(25 / target_fps)) if target_fps > 0 else 50
            
            output_pattern = os.path.join(output_dir, "frame_bak_%03d.jpg")
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-vf', f'select=not(mod(n\\,{frame_interval})),scale=640:-1',
                '-vsync', 'vfr',
                '-frames:v', str(max_frames),
                '-q:v', '2',
                output_pattern
            ]
            
            print(f"[VideoUtils] 备用命令: select每{frame_interval}帧取一帧")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            # 收集生成的帧
            for i in range(1, max_frames + 1):
                frame_path = os.path.join(output_dir, f"frame_bak_{i:03d}.jpg")
                if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
                    frame_paths.append(frame_path)
                else:
                    break
            
            if frame_paths:
                print(f"[VideoUtils] 备用方法成功提取 {len(frame_paths)} 帧")
            else:
                print(f"[VideoUtils] 备用方法也失败，stderr: {result.stderr[:200] if result.stderr else 'N/A'}")
                
        except Exception as e:
            print(f"[VideoUtils] 备用方法异常: {e}")
        
        return frame_paths


class ConversationManager:
    """对话历史管理器 - 支持长上下文"""
    
    def __init__(self, max_context_length: int = 32000, max_keep_turns: int = 20):
        self.max_context_length = max_context_length
        self.max_keep_turns = max_keep_turns
        self.messages = []
        self.summary = ""
    
    def add_message(self, role: str, content: str):
        """添加消息到历史"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        if len(self.messages) > self.max_keep_turns:
            self._compress_history()
    
    def _compress_history(self):
        """压缩历史对话"""
        recent_messages = self.messages[-10:]
        older_messages = self.messages[:-10]
        if older_messages:
            key_points = []
            for msg in older_messages:
                if msg["role"] == "user":
                    key_points.append(f"用户提到: {msg['content'][:50]}...")
                elif msg["role"] == "assistant":
                    key_points.append(f"AI回应: {msg['content'][:50]}...")
            self.summary = "\n".join(key_points[-5:])
        
        self.messages = recent_messages
    
    def get_messages(self, include_summary: bool = True) -> List[Dict]:
        """获取格式化的消息列表"""
        result = []
        if include_summary and self.summary:
            result.append({
                "role": "system",
                "content": f"【对话历史摘要】\n{self.summary}"
            })
        
        for msg in self.messages:
            result.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        return result
    
    def clear(self):
        """清空对话历史"""
        self.messages = []
        self.summary = ""


class KimiService:
    """
    Kimi-K2.5 API 服务 —— 每会话独立实例
    
    每个会话拥有独立的 KimiService 实例，确保对话历史、
    上下文记忆在不同用户之间完全隔离，避免会话污染。
    
    职责：
    - 绘画作品观察描述（图像 + 视频）
    - 生成图像编辑指令
    - 生成后续问题
    - 生成艺术创作反馈报告
    
    Note: 图像生成使用本地 ComfyUI，不在此类中
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
    
    def _encode_image(self, image_path: str) -> str:
        """将图像编码为 base64"""
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    
    def _build_multimodal_content(
        self, 
        text: str, 
        images: List[str] = None,
        video_frames: List[List[str]] = None  # 每个视频提取的帧列表
    ) -> List[Dict]:
        """
        构建多模态内容
        
        Args:
            text: 文本内容
            images: 图像路径列表
            video_frames: 视频帧路径列表的列表，每个子列表代表一个视频
        """
        content = []
        
        # 添加图像
        if images:
            for img_path in images:
                if os.path.exists(img_path):
                    ext = Path(img_path).suffix.lower()
                    if ext in ['.jpg', '.jpeg']:
                        mime_type = "image/jpeg"
                    elif ext == '.png':
                        mime_type = "image/png"
                    else:
                        mime_type = "image/jpeg"
                    
                    base64_data = self._encode_image(img_path)
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_data}"
                        }
                    })
        
        # 添加视频帧（作为连续图像）
        if video_frames:
            for video_idx, frames in enumerate(video_frames):
                if frames:
                    content.append({
                        "type": "text",
                        "text": f"\n【视频{video_idx + 1}关键帧序列（按时间顺序）】"
                    })
                    for frame_path in frames[:20]:  # 最多20帧避免超出token限制
                        if os.path.exists(frame_path):
                            base64_data = self._encode_image(frame_path)
                            content.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_data}"
                                }
                            })
        
        # 添加文本
        content.append({"type": "text", "text": text})
        
        return content
    
    def generate(
        self,
        prompt: str,
        images: List[str] = None,
        videos: List[str] = None,
        system_prompt: str = "",
        video_fps: float = 0.5,
        video_max_frames: int = 200
    ) -> str:
        """
        生成回复（支持图像和视频）
        
        Args:
            prompt: 提示词
            images: 图像路径列表
            videos: 视频路径列表
            system_prompt: 系统提示词
            video_fps: 视频采样帧率
            video_max_frames: 每个视频最大提取帧数
        """
        images = images or []
        videos = videos or []
        
        # 提取视频关键帧
        video_frames = []
        video_info_text = []
        
        for video_path in videos:
            if video_path and os.path.exists(video_path):
                # 获取视频信息
                info = VideoUtils.get_video_info(video_path)
                video_info_text.append(
                    f"- 视频: 时长{info.get('duration', 0):.1f}s, "
                    f"原始fps={info.get('fps', 0):.1f}, "
                    f"总帧数={info.get('total_frames', 0)}"
                )
                
                # 提取关键帧到临时目录
                temp_dir = tempfile.mkdtemp()
                frames = VideoUtils.extract_key_frames(
                    video_path, 
                    temp_dir,
                    target_fps=video_fps,
                    max_frames=video_max_frames
                )
                video_frames.append(frames)
        
        # 构建完整提示词（包含视频信息）
        full_prompt = prompt
        if video_info_text:
            full_prompt = f"{prompt}\n\n【视频信息】\n" + "\n".join(video_info_text) + "\n"
        
        # 构建消息
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # 构建多模态内容
        content = self._build_multimodal_content(full_prompt, images, video_frames)
        messages.append({"role": "user", "content": content})
        
        print(f"[LLM] 发送请求: {len(images)} 图像 + {len(videos)} 视频 -> {self.model}")
        
        # 调用 Kimi API
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            output_text = response.choices[0].message.content
            print(f"[LLM] 生成完成，输出长度: {len(output_text)}")
        except APIError as e:
            print(f"[LLM] API 错误: {e}")
            raise
        except APITimeoutError as e:
            print(f"[LLM] 请求超时: {e}")
            raise
        except Exception as e:
            print(f"[LLM] 请求失败: {e}")
            raise
        
        # 保存到对话历史（不包含图像，只保存文本）
        if system_prompt and not videos:
            self.conversation.add_message("user", prompt)
            self.conversation.add_message("assistant", output_text)
        
        return output_text
    
    def generate_stream(
        self,
        prompt: str,
        images: List[str] = None,
        videos: List[str] = None,
        system_prompt: str = "",
        video_fps: float = 0.2,
        video_max_frames: int = 200
    ) -> Generator[str, None, None]:
        """流式生成回复"""
        images = images or []
        videos = videos or []
        
        # 提取视频关键帧
        video_frames = []
        video_info_text = []
        
        for video_path in videos:
            if video_path and os.path.exists(video_path):
                info = VideoUtils.get_video_info(video_path)
                video_info_text.append(
                    f"- 视频: 时长{info.get('duration', 0):.1f}s"
                )
                
                temp_dir = tempfile.mkdtemp()
                frames = VideoUtils.extract_key_frames(
                    video_path, 
                    temp_dir,
                    target_fps=video_fps,
                    max_frames=video_max_frames
                )
                video_frames.append(frames)
        
        # 构建完整提示词
        full_prompt = prompt
        if video_info_text:
            full_prompt = f"{prompt}\n\n【视频信息】\n" + "\n".join(video_info_text) + "\n"
        
        # 构建消息
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        content = self._build_multimodal_content(full_prompt, images, video_frames)
        messages.append({"role": "user", "content": content})
        
        print(f"[LLM Stream] 开始流式生成: {len(images)} 图像 + {len(videos)} 视频")
        
        # 流式调用 Kimi API
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=True
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
        if system_prompt and not videos:
            self.conversation.add_message("user", prompt[:500])
            self.conversation.add_message("assistant", generated_text[:1000])
    
    def analyze_drawing_stream(
        self,
        drawing_path: str,
        webcam_video: str = None,
        screen_video: str = None
    ) -> Generator[Tuple[str, Optional[Dict]], None, None]:
        """
        流式分析 DAPR 绘画（雨中人测试）
        
        Args:
            drawing_path: 绘画图像路径
            webcam_video: 摄像头视频路径（面部表情）
            screen_video: 屏幕录制视频路径（绘画过程）
            
        Yields:
            Tuple[str, Optional[Dict]]: (文本块, 解析结果或None)
            - 生成过程中: (text_chunk, None)
            - 生成完成后: ("", parsed_result_dict)
        """
        import os
        
        # 读取系统提示词
        system_prompt = ""
        system_prompt_file = Path(__file__).parent / "prompts" / "DAPR_ANALYSIS_PROMPT.txt"
        if system_prompt_file.exists():
            with open(system_prompt_file, 'r', encoding='utf-8') as f:
                system_prompt = f.read()
        
        # 构建提示词
        has_webcam = webcam_video and os.path.exists(webcam_video)
        has_screen = screen_video and os.path.exists(screen_video)
        
        # 获取视频信息
        video_info_text = []
        
        if has_webcam:
            info = VideoUtils.get_video_info(webcam_video)
            video_info_text.append(
                VideoUtils._format_video_info(info, "第一个视频（面部表情）")
            )
        
        if has_screen:
            info = VideoUtils.get_video_info(screen_video)
            video_info_text.append(
                VideoUtils._format_video_info(info, "第二个视频（绘画过程）")
            )
        
        video_info_section = "\n\n【视频信息】\n" + "\n".join(video_info_text) if video_info_text else ""
        
        prompt = f"""请分析提供的素材（视频帧按时序排列）
1. 第一张图像：绘画成品
{"2. 第一个视频：绘画时的面部表情变化" if has_webcam else ""}
{("3. 第二个视频：绘画过程" if has_webcam else "2. 第一个视频：绘画过程") if has_screen else ""}
{video_info_section}


JSON结构必须包含以下字段：
{{
  "analysis": {{...详细分析...}},
  "questions_for_user": ["问题1", "问题2", "问题3"],
  "psychological_guesstimates": ["猜想1", "猜想2", "猜想3"]
}}

对受试者的提问应简洁明了

【严格输出契约（必须遵守）】
仅返回 JSON，不要 markdown，不要解释文字，不要多余前后缀。
输出必须为以下顶层结构之一：
1) 成功：
{{
  "status": "ok",
  "data": {{
    "analysis": {{...}},
    "questions_for_user": ["..."],
    "psychological_guesstimates": ["..."]
  }}
}}
2) 无法确定/失败：
{{
  "status": "unknown",
  "error": {{
    "code": "INSUFFICIENT_INFO",
    "message": "原因"
  }}
}}
禁止输出任何其他顶层字段。"""
        
        # 准备视频输入
        videos = []
        if has_webcam:
            videos.append(webcam_video)
        if has_screen:
            videos.append(screen_video)
        
        # 流式生成
        full_response = ""
        for chunk in self.generate_stream(
            prompt=prompt,
            images=[drawing_path],
            videos=videos,
            system_prompt=system_prompt,
            video_fps=0.5,
            video_max_frames=150
        ):
            full_response += chunk
            yield (chunk, None)  # 返回文本块，尚未完成
        
        # 解析完整结果（严格校验 + 有界修复）
        print(f"[LLM Stream] 分析完成，解析结果...")
        result = self._parse_analysis_response_with_contract(full_response)
        standardized = self._standardize_analysis_result(result)
        
        # 返回最终结果
        yield ("", standardized)
    
    def _clean_json_text(self, response: str) -> str:
        """清理模型响应中的包裹内容，尽量保留JSON主体"""
        cleaned = response or ""
        cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'```(?:json)?\s*([\s\S]*?)```', r'\1', cleaned)
        cleaned = cleaned.strip()
        # 截取首个 { 到最后一个 }，避免前后解释文本干扰
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start:end + 1]
        return cleaned.strip()

    def _validate_analysis_contract(self, payload: Dict[str, Any]) -> Tuple[bool, str]:
        """校验分析输出契约"""
        if not isinstance(payload, dict):
            return False, "payload不是对象"

        # 兼容旧格式（无status包装），交由后续转换
        if "status" not in payload:
            if (
                isinstance(payload.get("analysis"), dict)
                and isinstance(payload.get("questions_for_user", payload.get("questions", [])), list)
                and isinstance(payload.get("psychological_guesstimates", payload.get("hypotheses", [])), list)
            ):
                return True, ""
            return False, "缺少status且不符合旧格式"

        allowed_top_keys = {"status", "data", "error"}
        extra_keys = set(payload.keys()) - allowed_top_keys
        if extra_keys:
            return False, f"存在额外顶层字段: {sorted(extra_keys)}"

        status = payload.get("status")
        if status not in {"ok", "unknown", "error"}:
            return False, "status必须是ok/unknown/error"

        if status == "ok":
            data = payload.get("data")
            if not isinstance(data, dict):
                return False, "status=ok时data必须是对象"

            required_data_keys = {"analysis", "questions_for_user", "psychological_guesstimates"}
            missing_data_keys = required_data_keys - set(data.keys())
            if missing_data_keys:
                return False, f"data缺少字段: {sorted(missing_data_keys)}"

            if not isinstance(data.get("analysis"), dict):
                return False, "data.analysis必须是对象"
            if not isinstance(data.get("questions_for_user"), list):
                return False, "data.questions_for_user必须是数组"
            if not isinstance(data.get("psychological_guesstimates"), list):
                return False, "data.psychological_guesstimates必须是数组"
            if not all(isinstance(x, str) for x in data.get("questions_for_user", [])):
                return False, "data.questions_for_user必须是字符串数组"
            if not all(isinstance(x, str) or isinstance(x, dict) for x in data.get("psychological_guesstimates", [])):
                return False, "data.psychological_guesstimates元素类型不合法"
            return True, ""

        # unknown/error
        err = payload.get("error")
        if not isinstance(err, dict):
            return False, "status=unknown/error时error必须是对象"
        if not isinstance(err.get("code"), str) or not isinstance(err.get("message"), str):
            return False, "error必须包含字符串code和message"
        return True, ""

    def _normalize_analysis_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """将契约/旧格式统一转换为内部兼容格式"""
        if not isinstance(payload, dict):
            return {"raw_response": str(payload)}

        status = payload.get("status")
        if status == "ok" and isinstance(payload.get("data"), dict):
            data = payload["data"]
            return {
                "analysis": data.get("analysis", {}),
                "questions_for_user": data.get("questions_for_user", []),
                "psychological_guesstimates": data.get("psychological_guesstimates", [])
            }

        if status in {"unknown", "error"}:
            err = payload.get("error", {}) if isinstance(payload.get("error"), dict) else {}
            msg = err.get("message", "模型未返回可解析结构化结果")
            return {
                "analysis": {},
                "questions_for_user": [
                    "你最想让画里的哪个部分发生变化？为什么？",
                    "在这个场景里，你最在意的感受是什么？"
                ],
                "psychological_guesstimates": [
                    f"模型返回未知状态：{msg}"
                ]
            }

        # 旧格式兼容
        return payload

    def _request_json_repair(self, raw_response: str, error_message: str) -> str:
        """让模型仅做JSON修复，不做重分析"""
        repair_prompt = f"""你是JSON修复器。请根据错误信息修复下方文本为合法JSON。

要求（严格）：
1. 仅返回JSON，不要任何解释。
2. 顶层只允许 status/data/error。
3. 若信息不足，返回：
{{
  "status":"unknown",
  "error":{{"code":"REPAIR_FAILED","message":"原因"}}
}}
4. 若可修复，返回：
{{
  "status":"ok",
  "data":{{
    "analysis":{{}},
    "questions_for_user":[],
    "psychological_guesstimates":[]
  }}
}}

错误信息：
{error_message}

待修复文本：
{raw_response}
"""
        try:
            fixed = self.generate(prompt=repair_prompt, system_prompt="")
            return fixed
        except Exception as e:
            print(f"[LLM] JSON修复请求失败: {e}")
            return ""

    def _parse_analysis_response_with_contract(self, response: str, max_retries: int = 2) -> Dict[str, Any]:
        """解析分析响应：严格契约校验 + 有界修复重试"""
        current_text = response or ""
        last_error = "unknown"

        for attempt in range(max_retries + 1):
            cleaned = self._clean_json_text(current_text)
            print(f"[LLM] 清理后响应 ({len(cleaned)} 字符):")
            print(cleaned[:300])

            try:
                parsed = json.loads(cleaned)
                valid, err = self._validate_analysis_contract(parsed)
                if valid:
                    print(f"[LLM] 分析JSON契约校验通过 (attempt={attempt})")
                    return self._normalize_analysis_payload(parsed)
                last_error = f"契约校验失败: {err}"
                print(f"[LLM] {last_error}")
            except json.JSONDecodeError as e:
                last_error = f"JSON解析失败: {e}"
                print(f"[LLM] {last_error}")
            except Exception as e:
                last_error = f"解析异常: {e}"
                print(f"[LLM] {last_error}")

            # 旧逻辑兜底尝试
            try:
                json_match = re.search(r'\{[\s\S]*\}', current_text or "")
                if json_match:
                    parsed = json.loads(json_match.group())
                    valid, err = self._validate_analysis_contract(parsed)
                    if valid:
                        print(f"[LLM] 备用解析成功")
                        return self._normalize_analysis_payload(parsed)
                    last_error = f"备用契约校验失败: {err}"
                    print(f"[LLM] {last_error}")
            except Exception as e2:
                print(f"[LLM] 备用解析也失败: {e2}")

            if attempt < max_retries:
                repaired = self._request_json_repair(current_text, last_error)
                if repaired:
                    current_text = repaired
                    continue
                break

        print(f"[LLM] 分析结果最终解析失败，返回unknown兜底: {last_error}")
        return self._normalize_analysis_payload({
            "status": "unknown",
            "error": {
                "code": "ANALYSIS_PARSE_FAILED",
                "message": last_error
            }
        })

    def _validate_final_report_contract(self, payload: Dict[str, Any]) -> Tuple[bool, str]:
        """校验最终报告输出契约（兼容旧格式）"""
        if not isinstance(payload, dict):
            return False, "payload不是对象"

        # 兼容旧格式：无 status 包装，直接是报告对象
        if "status" not in payload:
            if isinstance(payload.get("summary"), str) and (
                isinstance(payload.get("psychological_profile"), dict)
                or isinstance(payload.get("stress_level"), str)
            ):
                return True, ""
            return False, "缺少status且不符合报告对象格式"

        allowed_top_keys = {"status", "data", "error"}
        extra = set(payload.keys()) - allowed_top_keys
        if extra:
            return False, f"存在额外顶层字段: {sorted(extra)}"

        status = payload.get("status")
        if status not in {"ok", "unknown", "error"}:
            return False, "status必须是ok/unknown/error"

        if status == "ok":
            data = payload.get("data")
            if not isinstance(data, dict):
                return False, "status=ok时data必须是对象"
            if not isinstance(data.get("summary"), str):
                return False, "data.summary必须是字符串"
            return True, ""

        err = payload.get("error")
        if not isinstance(err, dict):
            return False, "status=unknown/error时error必须是对象"
        if not isinstance(err.get("code"), str) or not isinstance(err.get("message"), str):
            return False, "error必须包含字符串code和message"
        return True, ""

    def _normalize_final_report_result(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        统一最终报告结构，并对齐前端展示字段：
        - 顶层 stress_level / coping_style / emotional_state / self_concept
        - key_insights / recommendations / follow_up
        """
        # 1) 解包 status/data 契约
        if isinstance(payload, dict) and payload.get("status") == "ok" and isinstance(payload.get("data"), dict):
            report = dict(payload["data"])
        elif isinstance(payload, dict) and payload.get("status") in {"unknown", "error"}:
            err = payload.get("error", {}) if isinstance(payload.get("error"), dict) else {}
            msg = err.get("message", "最终报告生成失败")
            report = {
                "summary": "本次最终报告生成未完全成功，以下为保守兜底结果。",
                "key_findings": [msg],
                "psychological_profile": {
                    "stress_level": "未评估",
                    "coping_style": "未评估",
                    "emotional_state": "未评估",
                    "self_concept": "未评估"
                },
                "recommendations": ["建议稍后重试，或在咨询师端查看原始日志进行补充判断。"],
                "intervention_priorities": []
            }
        else:
            report = dict(payload) if isinstance(payload, dict) else {}

        profile = report.get("psychological_profile", {})
        if not isinstance(profile, dict):
            profile = {}

        # 2) 关键字段扁平化（前端直接读取顶层）
        report["stress_level"] = report.get("stress_level") or profile.get("stress_level") or "未评估"
        report["coping_style"] = report.get("coping_style") or profile.get("coping_style") or "未评估"
        report["emotional_state"] = report.get("emotional_state") or profile.get("emotional_state") or "未评估"
        report["self_concept"] = report.get("self_concept") or profile.get("self_concept") or "未评估"

        # 3) 别名映射，兼容前端字段
        if not isinstance(report.get("key_insights"), list):
            key_findings = report.get("key_findings")
            report["key_insights"] = key_findings if isinstance(key_findings, list) else []

        if not isinstance(report.get("follow_up"), list):
            priorities = report.get("intervention_priorities")
            report["follow_up"] = priorities if isinstance(priorities, list) else []

        # 4) 兜底 summary/recommendations
        if not isinstance(report.get("summary"), str) or not report.get("summary").strip():
            report["summary"] = "综合分析已完成，但部分结构化字段缺失。"
        if not isinstance(report.get("recommendations"), list):
            report["recommendations"] = []

        # 5) 生成 deep_analysis（前端可展示）
        deep_analysis = report.get("deep_analysis", {})
        if not isinstance(deep_analysis, dict):
            deep_analysis = {}
        deep_analysis.setdefault("self_concept", report.get("self_concept", ""))
        report["deep_analysis"] = deep_analysis

        return report

    def _request_final_report_repair(self, raw_response: str, error_message: str) -> str:
        """请求模型修复最终报告JSON，仅做结构修复"""
        repair_prompt = f"""你是JSON修复器。请仅修复下方内容为合法JSON。

严格要求：
1) 仅返回JSON，不要解释。
2) 顶层结构必须是以下两种之一：
   a) {{"status":"ok","data":{{...报告对象...}}}}
   b) {{"status":"unknown","error":{{"code":"REPAIR_FAILED","message":"..."}}}}
3) 报告对象至少包含：
   - summary (string)
   - psychological_profile (object，含stress_level/coping_style/emotional_state/self_concept)
4) 不要输出 markdown 代码块。

错误信息：
{error_message}

待修复文本：
{raw_response}
"""
        try:
            return self.generate(prompt=repair_prompt, system_prompt="")
        except Exception as e:
            print(f"[LLM] Final Report 修复请求失败: {e}")
            return ""

    def _parse_final_report_with_contract(self, response: str, max_retries: int = 2) -> Dict[str, Any]:
        """解析最终报告：严格校验 + 有界修复重试 + 前端字段归一化"""
        current_text = response or ""
        last_error = "unknown"

        for attempt in range(max_retries + 1):
            cleaned = self._clean_json_text(current_text)
            print(f"[LLM] 清理后响应 ({len(cleaned)} 字符):")
            print(cleaned[:300])

            try:
                parsed = json.loads(cleaned)
                valid, err = self._validate_final_report_contract(parsed)
                if valid:
                    print(f"[LLM] Final Report 契约校验通过 (attempt={attempt})")
                    return self._normalize_final_report_result(parsed)
                last_error = f"Final Report 契约校验失败: {err}"
                print(f"[LLM] {last_error}")
            except json.JSONDecodeError as e:
                last_error = f"JSON解析失败: {e}"
                print(f"[LLM] {last_error}")
            except Exception as e:
                last_error = f"解析异常: {e}"
                print(f"[LLM] {last_error}")

            # 备用提取
            try:
                json_match = re.search(r'\{[\s\S]*\}', current_text or "")
                if json_match:
                    parsed = json.loads(json_match.group())
                    valid, err = self._validate_final_report_contract(parsed)
                    if valid:
                        print(f"[LLM] 备用解析成功")
                        return self._normalize_final_report_result(parsed)
                    last_error = f"备用契约校验失败: {err}"
                    print(f"[LLM] {last_error}")
            except Exception as e2:
                print(f"[LLM] 备用解析也失败: {e2}")

            if attempt < max_retries:
                repaired = self._request_final_report_repair(current_text, last_error)
                if repaired:
                    current_text = repaired
                    continue
                break

        print(f"[LLM] Final Report 最终解析失败，返回兜底: {last_error}")
        return self._normalize_final_report_result({
            "status": "unknown",
            "error": {
                "code": "FINAL_REPORT_PARSE_FAILED",
                "message": last_error
            }
        })

    
    def _standardize_analysis_result(self, result: Dict) -> Dict:
        """标准化分析结果字段，确保与 main.py 兼容"""
        standardized = {
            "analysis": result.get("analysis", {}),
            "questions": [],  # main.py 期望的字段名
            "hypotheses": [],  # main.py 期望的字段名
            "raw_response": result.get("raw_response", "")
        }
        
        # 处理 questions 字段（支持多种可能的字段名）
        questions = result.get("questions_for_user", result.get("questions", []))
        if isinstance(questions, list):
            standardized["questions"] = questions
        
        # 处理 hypotheses 字段（支持多种可能的字段名）
        hypotheses = result.get("psychological_guesstimates", result.get("hypotheses", []))
        if isinstance(hypotheses, list):
            # 将字符串列表转换为对象列表
            standardized["hypotheses"] = [
                {"description": h, "confidence": "medium"} if isinstance(h, str) else h
                for h in hypotheses
            ]
        
        # 提取分析摘要（用于对话历史）
        analysis = result.get("analysis", {})
        drawing_features = analysis.get("drawing_features", {})
        summary_parts = []
        for key, value in drawing_features.items():
            if value:
                summary_parts.append(f"{key}: {value}...")
        standardized["analysis_summary"] = " | ".join(summary_parts) if summary_parts else "分析完成"
        
        return standardized
    
    def _parse_json_response(self, response: str) -> Dict:
        """解析JSON响应"""
        # 多步清理
        cleaned = response
        # 1. 移除 <think>...</think>
        cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL)
        # 2. 移除markdown代码块
        cleaned = re.sub(r'```(?:json)?\s*([\s\S]*?)```', r'\1', cleaned)
        # 3. 移除开头非JSON内容
        cleaned = re.sub(r'^[\s\S]*?(?=\{)', '', cleaned)
        # 4. 移除结尾额外内容
        end_brace = cleaned.rfind('}')
        if end_brace != -1:
            cleaned = cleaned[:end_brace+1]
        cleaned = cleaned.strip()
        
        print(f"[LLM] 清理后响应 ({len(cleaned)} 字符):")
        print(cleaned[:300])
        
        # 解析JSON
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                print(f"[LLM] JSON解析成功")
                return data
        except json.JSONDecodeError as e:
            print(f"[LLM] JSON解析失败: {e}")
        
        # 备用解析
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                if isinstance(data, dict):
                    print(f"[LLM] 备用解析成功")
                    return data
        except Exception as e2:
            print(f"[LLM] 备用解析也失败: {e2}")
        
        return {"raw_response": response}
    
    def generate_edit_instructions(
        self,
        hypotheses: List[Dict],
        drawing_path: str,
        drawing_analysis: Dict = None
    ) -> List[Dict]:
        """生成自适应编辑指令"""
        # 构建分析摘要（兼容多种结构，避免会话摘要注入失败）
        analysis = drawing_analysis if isinstance(drawing_analysis, dict) else {}
        if isinstance(analysis.get("analysis"), dict):
            analysis = analysis.get("analysis", {})

        drawing_features = analysis.get("drawing_features", {}) if isinstance(analysis.get("drawing_features"), dict) else {}
        expression_analysis = analysis.get("expression_analysis", {}) if isinstance(analysis.get("expression_analysis"), dict) else {}
        process_corr = analysis.get("process_expression_correlation", {}) if isinstance(analysis.get("process_expression_correlation"), dict) else {}
        analysis_summary = f"""
绘画分析摘要：
- 人物大小：{drawing_features.get('figure_size', '未知')}
- 人物位置：{drawing_features.get('figure_position', '未知')}
- 雨的强度：{drawing_features.get('rain_intensity', '未知')}
- 遮蔽物：{drawing_features.get('shelter', '未知')}
- 整体氛围：{drawing_features.get('mood', '未知')}
- 整体情绪：{expression_analysis.get('overall_emotion', '未知')}
- 情绪轨迹：{process_corr.get('emotion_trajectory', '未知')}
""".strip()

        prompt = f"""【任务】基于DAPR心理干预理论，生成3个图像编辑变体（保持与原图高度一致）

【心理分析基础】
DAPR（雨中人绘画测试）通过分析压力感知与应对资源的关系评估心理状态。
- 雨象征外部压力源
- 防护装备象征应对资源和防御机制
- 人物表征反映自我概念

【当前心理状态分析】
{analysis_summary}

【待验证的心理猜想】
{json.dumps(hypotheses, ensure_ascii=False, indent=2)}

【心理干预理论】
三个变体应分别代表不同的心理干预方向，干预方向应参考【当前心理状态分析】和【待验证的心理猜想】

【输出格式】
{{
  "status": "ok",
  "data": [
    {{"name": "中文名称（体现干预方向）", "description": "中文描述（心理意义说明）", "edit_prompt": "英文图像编辑指令（轻量、保结构）", "color_prompt": "英文色彩描述（轻量色调调整）"}},
    {{"name": "...", "description": "...", "edit_prompt": "...", "color_prompt": "..."}},
    {{"name": "...", "description": "...", "edit_prompt": "...", "color_prompt": "..."}}
  ]
}}

【严格要求】
1. 必须按照【输出格式】生成恰好3个变体，每个变体必须包含全部4个字段
2. edit_prompt和color_prompt使用英文，简洁明了，每条不超过30个单词
3. name和description使用中文，体现心理学专业术语
4. 只输出JSON，不要markdown代码块，不要解释文字，不要多余字段

"""
        
        response = self.generate(prompt=prompt, images=[drawing_path])
        
        print(f"[LLM] 编辑指令原始响应 ({len(response)} 字符):")
        print("=" * 80)
        print(response)
        print("=" * 80)
        
        return self._parse_edit_instructions(response)
    
    def _parse_edit_instructions(self, response: str) -> List[Dict]:
        """解析编辑指令（严格契约 + 旧格式兼容 + 有界修复）"""
        current_text = response or ""
        last_error = "unknown"

        for attempt in range(3):
            cleaned = self._clean_json_text(current_text)
            variations: List[Dict] = []
            try:
                data = json.loads(cleaned)
                # 新契约: {"status":"ok","data":[...]}
                if isinstance(data, dict) and data.get("status") == "ok" and isinstance(data.get("data"), list):
                    variations = data.get("data", [])
                # 旧格式兼容
                elif isinstance(data, list):
                    variations = data
                elif isinstance(data, dict):
                    for key in ["variations", "edits", "variants", "results", "data"]:
                        if isinstance(data.get(key), list):
                            variations = data.get(key, [])
                            break

                if variations:
                    validated = self._validate_variations(variations)
                    if validated:
                        print(f"[LLM] 编辑指令解析成功: {len(validated)} 个变体 (attempt={attempt})")
                        return validated
                last_error = "未找到有效变体数组"
            except Exception as e:
                last_error = str(e)
                print(f"[LLM] 编辑指令解析失败 (attempt={attempt}): {e}")

            # 最后一次不再修复
            if attempt >= 2:
                break

            repair_prompt = f"""你是JSON修复器。请把下列文本修复为合法JSON。
要求：
1. 只输出JSON，不要解释。
2. 顶层结构必须为：
{{"status":"ok","data":[{{"name":"","description":"","edit_prompt":"","color_prompt":""}},{{...}},{{...}}]}}
3. data 必须恰好3项，每项包含 name/description/edit_prompt/color_prompt 四个字段。

错误信息：{last_error}
原文本：
{current_text}
"""
            repaired = self.generate(prompt=repair_prompt, system_prompt="")
            if repaired:
                current_text = repaired

        print(f"[LLM] 警告: 编辑指令解析失败，使用默认值")
        return self._get_default_variations()
    
    def _validate_variations(self, variations: List[Dict]) -> List[Dict]:
        """验证并修复变体数据"""
        validated = []
        defaults = self._get_default_variations()
        
        for i, var in enumerate(variations[:3]):
            if not isinstance(var, dict):
                validated.append(defaults[i])
                continue
            
            name = var.get("name") if var.get("name") and var.get("name") != "string" else defaults[i]["name"]
            description = var.get("description") if var.get("description") and var.get("description") != "string" else defaults[i]["description"]
            edit_prompt = var.get("edit_prompt") if var.get("edit_prompt") and var.get("edit_prompt") != "string" else defaults[i]["edit_prompt"]
            color_prompt = var.get("color_prompt") if var.get("color_prompt") and var.get("color_prompt") != "string" else defaults[i]["color_prompt"]
            
            validated.append({
                "name": name,
                "description": description,
                "edit_prompt": edit_prompt,
                "color_prompt": color_prompt
            })
        
        # 补充默认值
        while len(validated) < 3:
            validated.append(defaults[len(validated)])
        
        return validated[:3]
    
    def _get_default_variations(self) -> List[Dict]:
        """获取默认变体"""
        return [
            {
                "name": "温暖庇护",
                "description": "用温暖的色调和安全感增强画面",
                "edit_prompt": "Preserve original composition and character scale unchanged, minimal edits only. Add a small transparent umbrella and slightly soften rain stroke contrast around the head and shoulders. Keep all original linework and object layout.",
                "color_prompt": "Keep original palette, add subtle warm highlights (soft amber) only in local areas"
            },
            {
                "name": "雨中希望",
                "description": "在雨景中增添希望和明亮元素",
                "edit_prompt": "Preserve original composition, character position and scale unchanged, minimal edits only. Keep rain and cloud structure, add a gentle light break near cloud edge and a small reflective highlight on ground. Do not redraw scene.",
                "color_prompt": "Slightly increase brightness in cool blues with tiny fresh green accents, no dramatic color shift"
            },
            {
                "name": "宁静平衡",
                "description": "创造平静和谐的中性氛围",
                "edit_prompt": "Preserve original composition and all main contours unchanged, minimal edits only. Slightly regularize rain spacing and add a small practical raincoat detail while keeping the character pose intact. Maintain original scene geometry.",
                "color_prompt": "Neutral soft grays and gentle blue tint, very low saturation change"
            }
        ]
    
    def generate_follow_up_questions(
        self,
        selected_image: Dict,
        hypotheses: List[Dict],
        user_answers: List[str] = None
    ) -> List[str]:
        """基于图像选择生成深入问题（DAPR深度访谈阶段）"""
        prompt = f"""【DAPR深度访谈 - 图像选择探索】

用户选择了图像变体：{selected_image.get('name', '未知')}
变体描述：{selected_image.get('description', '无描述')}

【选择行为分析】
用户选择该变体可能反映以下心理动态：
- 对该变体所代表的心理状态的认同或向往
- 对当前自我状态的隐性表达
- 对理想自我的投射

【用户已提供的选择理由】
{chr(10).join([f"- {ans}" for ans in (user_answers or [])]) if user_answers else "（用户尚未提供详细理由）"}

【待验证的心理猜想】
{json.dumps(hypotheses, ensure_ascii=False, indent=2)}

【DAPR深度询问原则】
1. **投射认同探索**：用户选择的图像往往代表其认同或渴望的心理状态
2. **对比分析**：对比原始绘画与选择变体的差异，揭示心理需求
3. **自我概念验证**：通过选择行为验证对自我概念的假设
4. **干预敏感性评估**：评估用户对积极改变的接受程度

【问题生成要求】
生成1-2个开放式深入问题，要求：
1. 基于DAPR投射理论，探索选择背后的心理动机
2. 关联原始绘画分析中发现的压力感知和应对资源，但不能在问题中直接提及具体的投射关系
3. 温和、非评判，鼓励自我探索
4. 有助于验证或修正之前的心理假设

【示例问题类型】
- "这张图片中的[元素]与您最初的画作有什么不同？这种变化对您意味着什么？"
- "如果画中的人物是您自己，选择这个版本代表您内心有什么样的渴望？"
- "在这个场景中，您感受到的安全感/希望感来自哪里？"

【输出格式】
只返回JSON数组格式的问题列表，不要任何解释：
["问题1...", "问题2..."]"""

        response = self.generate(prompt=prompt)
        
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
        """生成最终DAPR心理分析报告"""
        
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
风险等级: {scoring.get('risk_level', 'N/A')}
"""
        
        prompt = f"""【DAPR（雨中人绘画测试）最终分析报告】

你是一位资深临床心理专家，精通DAPR投射测验的分析与解读。请基于以下完整数据生成专业的心理分析报告。

## 一、测试理论基础
DAPR（Draw-A-Person-in-the-Rain）是基于精神分析投射理论的经典心理评估工具：
- **雨**象征外部压力源和生活挑战
- **人物**反映自我概念和自我力量
- **防护装备**象征应对资源和防御机制
- **环境元素**指示压力强度和威胁感知

## 二、受试者数据汇总

### 2.1 基本信息
{user_info_text if user_info_text else "（未提供）"}

### 2.2 绘画分析摘要
{scoring_data}

### 2.3 图像选择结果
【用户选择的变体】
- 名称: {selected_image.get('name', '未知名称')}
- 描述: {selected_image.get('description', '无描述')}
- 干预方向: {selected_image.get('name', '').replace('温暖庇护', '安全感增强').replace('雨中希望', '希望感引导').replace('宁静平衡', '自我力量强化') if '温暖庇护' in selected_image.get('name', '') or '雨中希望' in selected_image.get('name', '') or '宁静平衡' in selected_image.get('name', '') else '基于选择内容判断'}

{selection_text}

### 2.4 对话与回答摘要
【深度访谈回答】
{chr(10).join([f"Q{i+1}: {q}\nA: {a}" for i, (q, a) in enumerate(zip(previous_hypotheses, final_answers))]) if previous_hypotheses and final_answers else "（暂无详细回答）"}

【对话历史】
{conversation_text if conversation_text else "（暂无详细对话）"}

## 三、分析维度与要求

### 3.1 压力-资源动态分析
基于DAPR评分系统分析：
- **压力感知水平**：低/中/高/危机
- **应对资源充足度**：充足/有限/匮乏
- **压力-资源匹配度**：平衡/轻微失衡/严重失衡

### 3.2 自我概念评估
- 自我价值感水平
- 自我力量感
- 自我整合度

### 3.3 应对风格识别
| 应对类型 | 特征 | 适应性 |
|----------|------|--------|
| 积极应对 | 直面问题、寻求解决 | 高 |
| 回避应对 | 退缩、隔离 | 中-低 |
| 情绪聚焦 | 关注情绪调节 | 视情境 |
| 问题聚焦 | 直接解决问题 | 高 |

### 3.4 图像选择的投射意义
用户选择的变体反映了：
- 对某种心理状态的认同或渴望
- 内在心理需求的表达
- 对改变的准备度和方向

## 四、报告输出要求

请以JSON格式输出完整报告，包含以下字段：

```json
{{
  "summary": "整体印象总结（2-3句话概括核心发现）",
  "key_findings": [
    "发现1：基于绘画特征的观察...",
    "发现2：基于过程分析的推断...",
    "发现3：基于图像选择的投射意义...",
    "发现4：综合评估的主要结论..."
  ],
  "psychological_profile": {{
    "stress_level": "低/中/高/危机 - 基于DAPR综合评分",
    "coping_style": "应对风格详细描述（基于防护装备和人物姿态）",
    "emotional_state": "情绪状态描述（基于表情和氛围元素）",
    "self_concept": "自我概念评估（基于人物大小、位置、完整性）",
    "support_resources": "支持资源评估（基于防护装备和积极元素）",
    "resilience_indicators": "心理韧性指标（如有）"
  }},
  "risk_assessment": {{
    "level": "低/中/高/危机",
    "indicators": ["风险指标1", "风险指标2"],
    "recommendations": "针对风险的具体建议"
  }},
  "developmental_considerations": "发展性考虑（儿童/青少年/老年特殊说明，如适用）",
  "recommendations": [
    "建议1：基于评估的个性化建议",
    "建议2：应对技能提升方向",
    "建议3：支持资源利用建议",
    "建议4：后续关注要点"
  ],
  "intervention_priorities": [
    "优先干预方向1",
    "优先干预方向2"
  ],
  "conclusion": "总结性陈述（强调成长潜能和积极方向）",
  "disclaimer": "本分析基于DAPR投射测验的AI辅助解读，仅供参考，不构成临床诊断。如需专业评估，请咨询持证心理咨询师或精神科医生。"
}}
```

## 五、输出规范
1. 内容专业但易懂，避免过度病理化语言
2. 强调优势和成长潜能
3. 对于高风险指标，明确建议寻求专业帮助
4. 考虑发展性因素（如为儿童/青少年/老年人）
5. 确保JSON格式正确，可被直接解析

请只输出JSON格式的报告，不要任何其他内容："""

        response = self.generate(prompt=prompt)
        return self._parse_final_report_with_contract(response)
    
    def clear_conversation(self):
        """清空对话历史"""
        self.conversation.clear()
        print("[LLM] 对话历史已清空")


def create_llm_service(session_id: str) -> KimiService:
    """
    创建一个新的、会话隔离的 LLM 服务实例
    
    重要：每次处理新会话时必须调用此工厂函数创建新实例，
    禁止在不同会话之间复用同一个 KimiService 实例，
    否则会导致对话历史泄漏（会话污染）。
    
    Args:
        session_id: 会话唯一标识，用于日志追踪和隔离确认
        
    Returns:
        KimiService: 绑定到指定会话的独立服务实例
    """
    print(f"[LLM] 为会话 {session_id[:8]}... 创建独立的 KimiService 实例")
    return KimiService(session_id=session_id)
