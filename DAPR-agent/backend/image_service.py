"""
图像生成服务 - 集成 ComfyUI API
使用 API 格式工作流 (color_the_dapr_doodle_api.json)

核心优化：
1. FP4 Text Encoder（降低显存占用，模型可常驻）
2. 异步 aiohttp（替代阻塞 urllib）
3. 批量提交（3个任务一次性入队）
4. 并行轮询（谁先完成先返回）
5. 模型预热（首次调用时预加载权重到显存）
"""
import json
import os
import time
import uuid
import random
import asyncio
import aiohttp
from typing import List, Dict, Optional, Any
from pathlib import Path

from config import COMFYUI_CONFIG, OUTPUTS_DIR


class ComfyUIService:
    """ComfyUI API 异步服务"""
    
    # 类级别：标记是否已完成模型预热
    _models_warmed_up = False
    
    def __init__(self):
        self.server_address = COMFYUI_CONFIG["server_address"]
        self.workflow_path = COMFYUI_CONFIG["workflow_path"]
        self.timeout = COMFYUI_CONFIG["timeout"]
        self.session: Optional[aiohttp.ClientSession] = None
        
        # 加载 API 格式的工作流模板
        with open(self.workflow_path, 'r', encoding='utf-8') as f:
            self.workflow_template = json.load(f)
        
        print(f"[ImageGen] 工作流加载完成: {len(self.workflow_template)} 个节点")
        print(f"[ImageGen] Text Encoder: qwen_3_4b_fp4_flux2.safetensors (FP4)")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self.session
    
    async def close(self):
        """关闭连接池"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    # ─────────────────────────────────────────────
    # 底层 HTTP API
    # ─────────────────────────────────────────────
    
    async def upload_image_async(
        self,
        image_path: str,
        name: Optional[str] = None
    ) -> Dict:
        """异步上传图像到 ComfyUI"""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图像不存在: {image_path}")
        
        if name is None:
            name = os.path.basename(image_path)
        
        session = await self._get_session()
        
        with open(image_path, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('image', f, filename=name)
            
            async with session.post(
                f"http://{self.server_address}/upload/image",
                data=data
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                # 图像可能已存在
                return {"name": name, "exists": True}
    
    async def queue_prompt_async(
        self,
        prompt: Dict,
        client_id: str = None
    ) -> Dict:
        """异步提交工作流到 ComfyUI 队列"""
        if client_id is None:
            client_id = str(uuid.uuid4())
        
        session = await self._get_session()
        payload = {"prompt": prompt, "client_id": client_id}
        
        async with session.post(
            f"http://{self.server_address}/prompt",
            json=payload
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
    
    async def get_history_async(self, prompt_id: str) -> Dict:
        """异步获取任务执行历史"""
        session = await self._get_session()
        async with session.get(
            f"http://{self.server_address}/history/{prompt_id}"
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
    
    async def get_image_async(
        self,
        filename: str,
        subfolder: str = "",
        folder_type: str = "output"
    ) -> bytes:
        """异步获取生成的图像数据"""
        session = await self._get_session()
        params = {"filename": filename}
        if subfolder:
            params["subfolder"] = subfolder
        if folder_type:
            params["type"] = folder_type
        
        async with session.get(
            f"http://{self.server_address}/view",
            params=params
        ) as resp:
            resp.raise_for_status()
            return await resp.read()
    
    # ─────────────────────────────────────────────
    # 工作流修改
    # ─────────────────────────────────────────────
    
    def modify_workflow(
        self,
        input_image: str,
        prompt: str,
        seed: Optional[int] = None,
        steps: int = 4,
        cfg: float = 1.0,
        filename_prefix: str = "DAPR-Flux2",
        clip_name: str = "qwen_3_4b_fp4_flux2.safetensors",
    ) -> Dict:
        """
        修改工作流参数
        
        Args:
            input_image: 输入图像文件名
            prompt: 编辑提示词
            seed: 随机种子
            steps: 采样步数
            cfg: CFG值
            filename_prefix: 输出文件名前缀
            clip_name: 文本编码器模型名（默认FP4版本）
        """
        wf = json.loads(json.dumps(self.workflow_template))  # 深拷贝
        
        # 修改输入图像 (节点 76 - LoadImage)
        if "76" in wf and "inputs" in wf["76"]:
            wf["76"]["inputs"]["image"] = input_image
        
        # 修改提示词 (节点 75:74 - CLIPTextEncode)
        if "75:74" in wf and "inputs" in wf["75:74"]:
            wf["75:74"]["inputs"]["text"] = prompt
            print(f"[ImageGen] 已更新提示词: {prompt[:50]}...")
        
        # 修改随机种子 (节点 75:73 - RandomNoise)
        if seed is None:
            seed = random.randint(0, 2**63 - 1)
        if "75:73" in wf and "inputs" in wf["75:73"]:
            wf["75:73"]["inputs"]["noise_seed"] = seed
        
        # 修改采样步数 (节点 75:62 - Flux2Scheduler)
        if steps is not None and "75:62" in wf and "inputs" in wf["75:62"]:
            wf["75:62"]["inputs"]["steps"] = steps
        
        # 修改 CFG (节点 75:63 - CFGGuider)
        if cfg is not None and "75:63" in wf and "inputs" in wf["75:63"]:
            wf["75:63"]["inputs"]["cfg"] = cfg
        
        # 修改输出文件名前缀 (节点 9 - SaveImage)
        if "9" in wf and "inputs" in wf["9"]:
            wf["9"]["inputs"]["filename_prefix"] = filename_prefix
        
        # 修改文本编码器（支持动态切换）
        if "75:71" in wf and "inputs" in wf["75:71"]:
            wf["75:71"]["inputs"]["clip_name"] = clip_name
        
        return wf
    
    # ─────────────────────────────────────────────
    # 批量提交与并行轮询
    # ─────────────────────────────────────────────
    
    async def submit_batch(
        self,
        input_name: str,
        variations: List[Dict],
    ) -> List[Dict]:
        """
        批量提交任务到 ComfyUI 队列
        
        一次性提交所有任务，ComfyUI 会复用已加载的模型依次执行。
        """
        submitted = []
        
        for i, variation in enumerate(variations[:3]):
            edit_prompt = variation.get('edit_prompt', '')
            color_prompt = variation.get('color_prompt', '')
            full_prompt = f"{edit_prompt}. {color_prompt}".strip()
            
            wf = self.modify_workflow(
                input_image=input_name,
                prompt=full_prompt,
                filename_prefix=f"DAPR-{variation.get('id', i)}",
                clip_name="qwen_3_4b_fp4_flux2.safetensors",
            )
            
            result = await self.queue_prompt_async(wf)
            prompt_id = result.get("prompt_id")
            
            submitted.append({
                "prompt_id": prompt_id,
                "variation": variation,
                "index": i,
                "prompt": full_prompt,
            })
            print(f"[ImageGen] 已提交任务 {i} (prompt_id={prompt_id[:8]}...)")
        
        return submitted
    
    async def _poll_single(
        self,
        prompt_id: str,
        poll_interval: float = 0.5
    ) -> Optional[Dict]:
        """
        轮询单个任务直到完成或超时。
        返回 history 数据，超时时返回 None。
        """
        start_time = time.time()
        
        while time.time() - start_time < self.timeout:
            history = await self.get_history_async(prompt_id)
            if prompt_id in history:
                print(f"[ImageGen] 任务完成 {prompt_id[:8]}...")
                return history[prompt_id]
            await asyncio.sleep(poll_interval)
        
        print(f"[ImageGen] 任务超时 {prompt_id[:8]}...")
        return None
    
    async def poll_batch(
        self,
        submitted: List[Dict],
        poll_interval: float = 0.5,
    ) -> tuple[List[Dict], List[Dict]]:
        """
        并行轮询批量任务，谁先完成先处理谁。
        
        使用 asyncio.as_completed 实现"流式"返回已完成任务。
        """
        # 包装轮询协程，使其返回 (item, history) 元组
        async def _poll_with_meta(item: Dict) -> tuple[Dict, Optional[Dict]]:
            history = await self._poll_single(item["prompt_id"], poll_interval)
            return item, history
        
        # 为每个任务创建独立协程
        tasks = [asyncio.create_task(_poll_with_meta(item)) for item in submitted]
        
        completed = []
        failed = []
        
        for coro in asyncio.as_completed(tasks):
            try:
                item, history = await coro
                if history is None:
                    failed.append(item)
                    continue
                
                outputs = history.get("outputs", {})
                if "9" in outputs:
                    images = outputs["9"].get("images", [])
                    for img_info in images:
                        completed.append({
                            "item": item,
                            "image_info": img_info,
                            "history": history,
                        })
                else:
                    failed.append(item)
                    
            except Exception as e:
                print(f"[ImageGen] 任务轮询异常: {e}")
                # 尝试从异常中恢复 item 信息
                failed.append({"index": -1, "prompt_id": "unknown"})
        
        return completed, failed
    
    async def download_results(
        self,
        completed: List[Dict],
        output_dir: str,
    ) -> List[Dict]:
        """异步下载已完成任务的图像"""
        results = []
        
        async def _download_one(entry: Dict) -> Optional[Dict]:
            item = entry["item"]
            img_info = entry["image_info"]
            filename = img_info["filename"]
            subfolder = img_info.get("subfolder", "")
            
            try:
                image_data = await self.get_image_async(filename, subfolder)
                output_path = os.path.join(output_dir, filename)
                
                with open(output_path, 'wb') as f:
                    f.write(image_data)
                
                return {
                    "id": item["variation"].get('id', item["index"]),
                    "name": item["variation"].get('name', f'变体{item["index"]}'),
                    "description": item["variation"].get('description', ''),
                    "filepath": output_path,
                    "filename": filename,
                    "prompt": item["prompt"],
                    "hypothesis_id": item["variation"].get('hypothesis_id'),
                    "index": item["index"],
                }
            except Exception as e:
                print(f"[ImageGen] 下载图像失败 {filename}: {e}")
                return None
        
        # 并行下载所有图像
        download_tasks = [_download_one(entry) for entry in completed]
        downloaded = await asyncio.gather(*download_tasks)
        
        for result in downloaded:
            if result is not None:
                results.append(result)
        
        # 按原始顺序排序
        results.sort(key=lambda x: x["index"])
        return results
    
    # ─────────────────────────────────────────────
    # 模型预热（预加载权重到显存）
    # ─────────────────────────────────────────────
    
    async def warmup(self, force: bool = False) -> bool:
        """
        发送一个 dummy prompt 让 ComfyUI 加载所有模型到显存。
        
        预热后，后续批量任务的模型加载时间为 0。
        使用 1 step 最小化开销。
        """
        if ComfyUIService._models_warmed_up and not force:
            print("[ImageGen] 模型已预热，跳过")
            return True
        
        print("[ImageGen] 正在预热模型（预加载到显存）...")
        
        try:
            # 构建最小化工作流用于预热
            wf = json.loads(json.dumps(self.workflow_template))
            
            # 最小化设置：1 step，空提示词
            if "75:62" in wf and "inputs" in wf["75:62"]:
                wf["75:62"]["inputs"]["steps"] = 1
            
            if "75:74" in wf and "inputs" in wf["75:74"]:
                wf["75:74"]["inputs"]["text"] = "warmup"
            
            # 使用 FP4 encoder
            if "75:71" in wf and "inputs" in wf["75:71"]:
                wf["75:71"]["inputs"]["clip_name"] = "qwen_3_4b_fp4_flux2.safetensors"
            
            if "9" in wf and "inputs" in wf["9"]:
                wf["9"]["inputs"]["filename_prefix"] = "DAPR-warmup"
            
            result = await self.queue_prompt_async(wf)
            prompt_id = result.get("prompt_id")
            
            # 等待预热完成
            history = await self._poll_single(prompt_id, poll_interval=0.3)
            
            if history:
                ComfyUIService._models_warmed_up = True
                print("[ImageGen] 模型预热完成，权重已驻留显存")
                return True
            else:
                print("[ImageGen] 模型预热超时")
                return False
                
        except Exception as e:
            print(f"[ImageGen] 模型预热失败: {e}")
            return False
    
    # ─────────────────────────────────────────────
    # 对外 API
    # ─────────────────────────────────────────────
    
    async def generate_variations_async(
        self,
        input_image_path: str,
        variations: List[Dict],
        output_dir: str = None,
        do_warmup: bool = True,
    ) -> List[Dict]:
        """
        异步生成多个图像变体（批量提交 + 并行轮询）
        
        Args:
            input_image_path: 原始绘画路径
            variations: 编辑指令列表
            output_dir: 输出目录
            do_warmup: 是否先预热模型
        
        Returns:
            生成的图像信息列表（按原始顺序排列）
        """
        if output_dir is None:
            output_dir = str(OUTPUTS_DIR)
        os.makedirs(output_dir, exist_ok=True)
        
        # 上传原始图像
        session_id = os.path.basename(os.path.dirname(input_image_path))
        original_name = os.path.basename(input_image_path)
        input_name = f"{session_id}_{original_name}"
        
        try:
            await self.upload_image_async(input_image_path, input_name)
            print(f"[ImageGen] 已上传图像: {input_name}")
        except Exception as e:
            print(f"[ImageGen] 上传图像警告: {e}")
        
        variations = variations[:3]
        print(f"[ImageGen] 将生成 {len(variations)} 个图像变体")
        
        # 可选：预热模型（首次调用时）
        if do_warmup:
            await self.warmup()
        
        # 1. 批量提交（一次性入队）
        t0 = time.time()
        submitted = await self.submit_batch(input_name, variations)
        print(f"[ImageGen] 批量提交耗时: {time.time()-t0:.2f}s")
        
        # 2. 并行轮询（谁先完成先处理）
        t1 = time.time()
        completed, failed = await self.poll_batch(submitted)
        print(f"[ImageGen] 并行轮询耗时: {time.time()-t1:.2f}s")
        
        if failed:
            print(f"[ImageGen] {len(failed)} 个任务失败")
        
        # 3. 并行下载
        t2 = time.time()
        results = await self.download_results(completed, output_dir)
        print(f"[ImageGen] 并行下载耗时: {time.time()-t2:.2f}s")
        
        total = time.time() - t0
        print(f"[ImageGen] 总耗时: {total:.2f}s | 成功: {len(results)}/{len(variations)}")
        
        return results
    
    # ─────────────────────────────────────────────
    # 向后兼容的同步 API
    # ─────────────────────────────────────────────
    
    def generate_variations(
        self,
        input_image_path: str,
        variations: List[Dict],
        output_dir: str = None
    ) -> List[Dict]:
        """
        同步封装（向后兼容）。
        内部使用 asyncio.run 调用异步实现。
        """
        try:
            loop = asyncio.get_running_loop()
            # 如果在已有事件循环中（如 FastAPI），在新线程中运行
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    self.generate_variations_async(input_image_path, variations, output_dir)
                )
                return future.result()
        except RuntimeError:
            # 没有运行中的事件循环
            return asyncio.run(
                self.generate_variations_async(input_image_path, variations, output_dir)
            )


# 单例模式（带生命周期管理）
_image_service: Optional[ComfyUIService] = None

def get_image_service() -> ComfyUIService:
    """获取图像服务实例"""
    global _image_service
    if _image_service is None:
        _image_service = ComfyUIService()
    return _image_service

async def close_image_service():
    """关闭图像服务（释放连接池）"""
    global _image_service
    if _image_service is not None:
        await _image_service.close()
        _image_service = None
