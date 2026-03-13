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
from typing import List, Dict, Optional, Generator, Tuple
from pathlib import Path
from datetime import datetime
import base64

# OpenAI SDK 用于调用 Kimi API (Moonshot 提供 OpenAI 兼容接口)
from openai import OpenAI, APIError, APITimeoutError
from config import LLM_CONFIG

class VideoUtils:
    """视频工具类 - 基于 ffmpeg/ffprobe（优雅重构版）"""
    
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
    Kimi-K2.5 API 服务
    
    用于 DAPR (雨中人绘画测试) 的心理分析，包括：
    - 绘画作品分析（图像 + 视频）
    - 生成图像编辑指令
    - 生成后续问题
    - 生成最终心理分析报告
    
    Note: 图像生成使用本地 ComfyUI，不在此类中
    """
    
    def __init__(self):
        self.api_key = LLM_CONFIG.get("api_key", "")
        self.base_url = LLM_CONFIG.get("base_url", "https://api.moonshot.cn/v1")
        self.model = LLM_CONFIG.get("model", "kimi-k2.5")
        self.max_tokens = LLM_CONFIG.get("max_tokens", 4096)
        self.temperature = LLM_CONFIG.get("temperature", 0.7)
        
        # 验证 API Key
        if not self.api_key:
            print("[LLM] 警告: MOONSHOT_API_KEY 未设置，请在环境变量中配置")
        
        # 初始化对话管理器
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

对受试者的提问应简洁明了"""
        
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
        
        # 解析完整结果
        print(f"[LLM Stream] 分析完成，解析结果...")
        result = self._parse_json_response(full_response)
        standardized = self._standardize_analysis_result(result)
        
        # 返回最终结果
        yield ("", standardized)
    
    
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
        # 构建分析摘要
        analysis_summary = ""
        if drawing_analysis:
            analysis_summary = f"""
绘画分析摘要：
- 人物大小：{drawing_analysis.get('drawing_features', {}).get('figure_size', '未知')}
- 人物位置：{drawing_analysis.get('drawing_features', {}).get('figure_position', '未知')}
- 雨的强度：{drawing_analysis.get('drawing_features', {}).get('rain_intensity', '未知')}
- 遮蔽物：{drawing_analysis.get('drawing_features', {}).get('shelter', '未知')}
- 整体氛围：{drawing_analysis.get('drawing_features', {}).get('mood', '未知')}
- 整体情绪：{drawing_analysis.get('expression_analysis', {}).get('overall_emotion', '未知')}
- 情绪轨迹：{drawing_analysis.get('process_expression_correlation', {}).get('emotion_trajectory', '未知')}
"""

        prompt = f"""【任务】基于DAPR心理干预理论，生成3个图像编辑变体

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
[
  {{"name": "中文名称（体现干预方向）", "description": "中文描述（心理意义说明）", "edit_prompt": "英文图像编辑指令（详细描述修改内容）", "color_prompt": "英文色彩描述（主色调+氛围）"}},
  {{"name": "...", "description": "...", "edit_prompt": "...", "color_prompt": "..."}},
  {{"name": "...", "description": "...", "edit_prompt": "...", "color_prompt": "..."}}
]

【严格要求】
1. 必须按照【输出格式】生成恰好3个变体，每个变体必须包含全部4个字段
2. edit_prompt和color_prompt使用英文，简洁明了
3. name和description使用中文，体现心理学专业术语

"""
        
        response = self.generate(prompt=prompt, images=[drawing_path])
        
        print(f"[LLM] 编辑指令原始响应 ({len(response)} 字符):")
        print("=" * 80)
        print(response)
        print("=" * 80)
        
        return self._parse_edit_instructions(response)
    
    def _parse_edit_instructions(self, response: str) -> List[Dict]:
        """解析编辑指令"""
        # 预处理
        cleaned = response
        cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'```(?:json)?\s*([\s\S]*?)```', r'\1', cleaned)
        cleaned = cleaned.strip()
        
        variations = []
        
        # 方法1: 直接解析
        try:
            data = json.loads(cleaned)
            if isinstance(data, list) and len(data) > 0:
                variations = data
            elif isinstance(data, dict):
                for key in ['variations', 'edits', 'variants', 'results', 'data']:
                    if key in data and isinstance(data[key], list):
                        variations = data[key]
                        break
            
            if variations:
                validated = self._validate_variations(variations)
                if validated:
                    print(f"[LLM] 解析成功: {len(validated)} 个变体")
                    return validated
        except Exception as e:
            print(f"[LLM] 方法1失败: {e}")
        
        # 方法2: 查找方括号
        try:
            start = cleaned.find('[')
            end = cleaned.rfind(']')
            if start != -1 and end != -1 and end > start:
                variations = json.loads(cleaned[start:end+1])
                if isinstance(variations, list):
                    validated = self._validate_variations(variations)
                    if validated:
                        return validated
        except Exception as e:
            print(f"[LLM] 方法2失败: {e}")
        
        # 所有方法失败，返回默认值
        print(f"[LLM] 警告: 解析失败，使用默认值")
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
                "edit_prompt": "Add warm lighting and cozy atmosphere",
                "color_prompt": "warm golden tones, soft oranges, gentle yellows"
            },
            {
                "name": "雨中希望",
                "description": "在雨景中增添希望和明亮元素",
                "edit_prompt": "Add hopeful elements like rainbow or sunlight breaking through clouds",
                "color_prompt": "bright blues, fresh greens, rainbow accents"
            },
            {
                "name": "宁静平衡",
                "description": "创造平静和谐的中性氛围",
                "edit_prompt": "Create a peaceful and balanced composition with harmonious colors",
                "color_prompt": "soft grays, gentle blues, balanced neutral tones"
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
        
        result = self._parse_json_response(response)
        if "raw_response" in result:
            # 解析失败，尝试从原始响应中提取关键信息
            print(f"[LLM] JSON解析失败，尝试从原始文本提取信息...")
            
            # 尝试提取关键字段
            raw_text = result.get("raw_response", "")
            
            # 简单提取压力水平
            stress_level = "中等"  # 默认值
            if any(word in raw_text.lower() for word in ["高压", "严重", "危机", "high stress", "crisis"]):
                stress_level = "高"
            elif any(word in raw_text.lower() for word in ["低压", "轻微", "low stress"]):
                stress_level = "低"
            
            # 简单提取情绪状态
            emotional_state = "情绪状态基于绘画分析：整体氛围反映当前心理状态"
            
            # 简单提取应对方式
            coping_style = "应对方式分析：基于绘画中的防护装备和人物姿态，显示出特定的应对模式"
            
            return {
                "summary": "基于您的DAPR绘画测试和图像选择，我们进行了综合分析。",
                "key_findings": [
                    "绘画特征反映了特定的压力感知模式",
                    "应对资源使用情况已初步评估",
                    "图像选择揭示了内在心理需求和倾向",
                    "整体分析提示建议进行更深入的专业评估"
                ],
                "psychological_profile": {
                    "stress_level": f"{stress_level}（建议专业评估以确认）",
                    "coping_style": coping_style,
                    "emotional_state": emotional_state,
                    "self_concept": "自我概念评估：基于人物表征分析，反映对自我的基本认知",
                    "support_resources": "支持资源评估：基于防护装备和积极元素的初步分析"
                },
                "risk_assessment": {
                    "level": "需进一步评估",
                    "indicators": ["建议专业评估以识别具体风险指标"],
                    "recommendations": "建议寻求持证心理咨询师或精神科医生进行全面评估"
                },
                "recommendations": [
                    "保持对自身心理状态的觉察",
                    "学习并实践积极的应对技能",
                    "建立或维护良好的社会支持网络",
                    "如有持续困扰，及时寻求专业心理服务"
                ],
                "intervention_priorities": [
                    "压力管理技能培养",
                    "应对资源增强和优化"
                ],
                "conclusion": "本分析基于DAPR投射测验的AI辅助解读，提供了心理状态的初步画像。每个人都有成长和改善的潜能，建议在专业指导下进行深入探索。",
                "disclaimer": "本分析仅供参考，不构成临床诊断。如需专业评估，请咨询持证心理咨询师或精神科医生。",
                "raw_analysis": raw_text[:1000] if len(raw_text) > 1000 else raw_text
            }
        return result
    
    def clear_conversation(self):
        """清空对话历史"""
        self.conversation.clear()
        print("[LLM] 对话历史已清空")


# 单例模式
_llm_service = None

def get_llm_service() -> KimiService:
    """获取 LLM 服务实例"""
    global _llm_service
    if _llm_service is None:
        _llm_service = KimiService()
    return _llm_service
