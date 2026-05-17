"""
视频工具类 - 基于 ffmpeg/ffprobe
"""
import json
import os

import subprocess


from typing import Dict, List


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

    @staticmethod
    def compute_sampling_meta(
        duration: float,
        num_frames: int = 10,
        original_fps: float = 30.0,
        skip_head_tail: bool = True,
    ) -> dict:
        """
        计算均匀抽帧的时间戳和原视频帧索引。

        Returns:
            {
                "timestamps": List[float],   # 每帧在原视频中的时间戳（秒）
                "frame_indices": List[int],  # 每帧在原视频中的帧索引
                "start_time": float,
                "end_time": float,
            }
        """
        if skip_head_tail:
            margin = max(duration * 0.05, 0.3)
            start_time = margin
            end_time = duration - margin
            if end_time <= start_time:
                start_time = 0.0
                end_time = duration
        else:
            start_time = 0.0
            end_time = duration

        effective_duration = end_time - start_time
        step = effective_duration / num_frames
        timestamps = [start_time + (i + 0.5) * step for i in range(num_frames)]

        # 计算帧索引（确保不越界）
        max_idx = max(0, int(duration * original_fps) - 1)
        frame_indices = [min(int(ts * original_fps), max_idx) for ts in timestamps]

        return {
            "timestamps": timestamps,
            "frame_indices": frame_indices,
            "start_time": start_time,
            "end_time": end_time,
        }

    @staticmethod
    def extract_uniform_frames(
        video_path: str,
        output_dir: str,
        num_frames: int = 10,
        skip_head_tail: bool = True,
        crop_mode: str = "center",  # "center" | "canvas_ratio"
        max_size: int = 448,
    ) -> List[str]:
        """
        均匀时间步长提取视频帧，支持去头去尾和差异化裁剪策略。

        Args:
            video_path: 视频文件路径
            output_dir: 输出目录
            num_frames: 提取帧数（默认10）
            skip_head_tail: 是否去掉第一帧和最后一帧的时间区域（默认True）
            crop_mode: "center"=中心裁剪为正方形（摄像头）,
                      "canvas_ratio"=按画布比例850:1100裁剪（画布录像）
            max_size: 缩放后最长边像素

        Returns:
            提取的帧文件路径列表（按时间顺序）
        """
        print(f"[VideoUtils] 均匀提取帧: {video_path}")
        print(f"[VideoUtils] 参数: num_frames={num_frames}, skip_head_tail={skip_head_tail}, crop_mode={crop_mode}, max_size={max_size}")

        if not os.path.exists(video_path):
            print(f"[VideoUtils] 视频文件不存在: {video_path}")
            return []

        os.makedirs(output_dir, exist_ok=True)

        # 获取视频信息
        info = VideoUtils.get_video_info(video_path)
        duration = info.get("duration", 0)
        width = info.get("width", 640)
        height = info.get("height", 480)

        if duration <= 0:
            print(f"[VideoUtils] 无法获取视频时长，降级到旧版提取")
            return VideoUtils.extract_key_frames(video_path, output_dir, target_fps=0.5, max_frames=num_frames)

        # 计算有效时间范围（去掉首尾）
        if skip_head_tail:
            margin = max(duration * 0.05, 0.3)  # 至少去掉前后5%或0.3秒
            start_time = margin
            end_time = duration - margin
            if end_time <= start_time:
                # 视频太短，不去头尾
                start_time = 0.0
                end_time = duration
        else:
            start_time = 0.0
            end_time = duration

        effective_duration = end_time - start_time
        if effective_duration <= 0:
            print(f"[VideoUtils] 有效时长异常，使用全段")
            start_time = 0.0
            end_time = duration
            effective_duration = duration

        # 均匀取 num_frames 个时间点（取每个子区间中点，避免边缘）
        step = effective_duration / num_frames
        timestamps = [start_time + (i + 0.5) * step for i in range(num_frames)]
        print(f"[VideoUtils] 时间范围: {start_time:.2f}s ~ {end_time:.2f}s, step={step:.2f}s")
        print(f"[VideoUtils] 采样时间点: {[f'{t:.2f}' for t in timestamps]}")

        # 构建 ffmpeg 裁剪/缩放过滤器
        if crop_mode == "canvas_ratio":
            # 画布原始比例 850:1100，最长边限制为 max_size
            canvas_w, canvas_h = 850, 1100
            target_ratio = canvas_w / canvas_h  # ≈ 0.7727
            video_ratio = width / height if height > 0 else 1.0

            if video_ratio > target_ratio:
                # 视频更宽，裁左右
                new_h = height
                new_w = int(height * target_ratio)
                new_w = new_w // 2 * 2  # ffmpeg 要求偶数
                crop_x = (width - new_w) // 2
                crop_y = 0
            else:
                # 视频更高（或比例接近），裁上下
                new_w = width
                new_h = int(width / target_ratio)
                new_h = new_h // 2 * 2
                crop_x = 0
                crop_y = (height - new_h) // 2

            scale_w = int(max_size * canvas_w / canvas_h)
            scale_h = max_size
            scale_w = scale_w // 2 * 2

            vf_filter = f"crop={new_w}:{new_h}:{crop_x}:{crop_y},scale={scale_w}:{scale_h}"
            print(f"[VideoUtils] 画布裁剪: {width}x{height} -> crop={new_w}:{new_h}:{crop_x}:{crop_y} -> scale={scale_w}:{scale_h}")
        else:
            # center: 中心裁剪为正方形，再缩放
            crop_size = min(width, height)
            crop_x = (width - crop_size) // 2
            crop_y = (height - crop_size) // 2
            vf_filter = f"crop={crop_size}:{crop_size}:{crop_x}:{crop_y},scale={max_size}:{max_size}"
            print(f"[VideoUtils] 中心裁剪: {width}x{height} -> crop={crop_size}:{crop_size}:{crop_x}:{crop_y} -> scale={max_size}:{max_size}")

        # 逐时间点提取帧
        frame_paths = []
        for i, ts in enumerate(timestamps):
            output_path = os.path.join(output_dir, f"frame_{i:03d}.jpg")
            cmd = [
                'ffmpeg', '-y',
                '-ss', str(ts),
                '-i', video_path,
                '-vf', vf_filter,
                '-frames:v', '1',
                '-q:v', '2',
                output_path
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    frame_paths.append(output_path)
                else:
                    print(f"[VideoUtils] 时间点 {ts:.2f}s 提取失败")
            except Exception as e:
                print(f"[VideoUtils] 时间点 {ts:.2f}s 提取异常: {e}")

        if len(frame_paths) < num_frames:
            print(f"[VideoUtils] 警告: 只成功提取 {len(frame_paths)}/{num_frames} 帧")
        else:
            print(f"[VideoUtils] 成功提取 {len(frame_paths)} 帧")

        # 兜底：如果一帧都没提取到，回退到旧方法
        if not frame_paths:
            print(f"[VideoUtils] 均匀提取完全失败，回退到旧版 key_frames 提取")
            return VideoUtils.extract_key_frames(video_path, output_dir, target_fps=0.5, max_frames=num_frames)

        return frame_paths
