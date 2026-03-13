"""
图像生成服务 - 集成 ComfyUI API
使用 API 格式工作流 (color_the_dapr_doodle_api.json)
"""
import json
import urllib.request
import urllib.parse
import urllib.error
import os
import time
import uuid
import random
from typing import List, Dict, Optional
from pathlib import Path

from config import COMFYUI_CONFIG, OUTPUTS_DIR


class ComfyUIService:
    """ComfyUI API 服务"""
    
    def __init__(self):
        self.server_address = COMFYUI_CONFIG["server_address"]
        self.workflow_path = COMFYUI_CONFIG["workflow_path"]
        self.timeout = COMFYUI_CONFIG["timeout"]
        
        # 加载 API 格式的工作流模板
        with open(self.workflow_path, 'r', encoding='utf-8') as f:
            self.workflow_template = json.load(f)
        
        print(f"[ImageGen] 工作流加载完成: {len(self.workflow_template)} 个节点")
    
    def upload_image(self, image_path: str, name: Optional[str] = None) -> Dict:
        """上传图像到 ComfyUI"""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图像不存在: {image_path}")
        
        if name is None:
            name = os.path.basename(image_path)
        
        with open(image_path, 'rb') as f:
            data = f.read()
        
        # 使用 multipart/form-data 上传
        import mimetypes
        boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
        
        body = []
        body.append(f'--{boundary}'.encode())
        body.append(f'Content-Disposition: form-data; name="image"; filename="{name}"'.encode())
        content_type = mimetypes.guess_type(image_path)[0] or 'application/octet-stream'
        body.append(f'Content-Type: {content_type}'.encode())
        body.append(b'')
        body.append(data)
        body.append(f'--{boundary}--'.encode())
        
        req = urllib.request.Request(
            f"http://{self.server_address}/upload/image",
            data=b'\r\n'.join(body),
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            # 图像可能已存在
            return {"name": name, "exists": True}
    
    def queue_prompt(self, prompt: Dict, client_id: str = None) -> Dict:
        """提交工作流"""
        if client_id is None:
            client_id = str(uuid.uuid4())
        
        payload = {
            "prompt": prompt,
            "client_id": client_id
        }
        data = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(
            f"http://{self.server_address}/prompt",
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read())
    
    def get_history(self, prompt_id: str) -> Dict:
        """获取任务执行历史"""
        with urllib.request.urlopen(
            f"http://{self.server_address}/history/{prompt_id}",
            timeout=30
        ) as response:
            return json.loads(response.read())
    
    def get_image(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        """获取生成的图像数据"""
        params = {"filename": filename}
        if subfolder:
            params["subfolder"] = subfolder
        if folder_type:
            params["type"] = folder_type
        
        query_string = urllib.parse.urlencode(params)
        url = f"http://{self.server_address}/view?{query_string}"
        
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read()
    
    def wait_for_prompt(self, prompt_id: str) -> Dict:
        """等待工作流执行完成"""
        start_time = time.time()
        
        while time.time() - start_time < self.timeout:
            history = self.get_history(prompt_id)
            if prompt_id in history:
                return history[prompt_id]
            time.sleep(0.5)
        
        raise TimeoutError(f"等待超时 ({self.timeout}s)")
    
    def modify_workflow(
        self,
        input_image: str,
        prompt: str,
        seed: Optional[int] = None,
        steps: int = 4,
        cfg: float = 1.0,
        filename_prefix: str = "DAPR-Flux2"
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
        
        return wf
    
    def generate_variations(
        self,
        input_image_path: str,
        variations: List[Dict],
        output_dir: str = None
    ) -> List[Dict]:
        """
        生成多个图像变体
        
        Args:
            input_image_path: 原始绘画路径
            variations: 编辑指令列表
            output_dir: 输出目录
        
        Returns:
            生成的图像信息列表
        """
        if output_dir is None:
            output_dir = OUTPUTS_DIR
        
        os.makedirs(output_dir, exist_ok=True)
        
        # 上传原始图像 - 使用唯一文件名避免会话间冲突
        session_id = os.path.basename(os.path.dirname(input_image_path))
        original_name = os.path.basename(input_image_path)
        input_name = f"{session_id}_{original_name}"
        try:
            self.upload_image(input_image_path, input_name)
            print(f"[ImageGen] 已上传图像: {input_name}")
        except Exception as e:
            print(f"上传图像警告: {e}")
        
        generated_images = []
        
        # 限制最多生成3个变体（避免时间过长）
        variations = variations[:3]
        print(f"[ImageGen] 将生成 {len(variations)} 个图像变体")
        
        for i, variation in enumerate(variations):
            try:
                # 构建提示词
                edit_prompt = variation.get('edit_prompt', '')
                color_prompt = variation.get('color_prompt', '')
                full_prompt = f"{edit_prompt}. {color_prompt}".strip()
                
                # 修改工作流
                wf = self.modify_workflow(
                    input_image=input_name,
                    prompt=full_prompt,
                    filename_prefix=f"DAPR-{variation.get('id', i)}"
                )
                
                # 提交任务
                result = self.queue_prompt(wf)
                prompt_id = result.get("prompt_id")
                
                # 等待完成
                history = self.wait_for_prompt(prompt_id)
                
                # 获取输出
                outputs = history.get("outputs", {})
                if "9" in outputs:
                    images = outputs["9"].get("images", [])
                    for img_info in images:
                        filename = img_info["filename"]
                        subfolder = img_info.get("subfolder", "")
                        
                        # 下载图像
                        image_data = self.get_image(filename, subfolder)
                        
                        # 保存到本地
                        output_path = os.path.join(output_dir, filename)
                        with open(output_path, 'wb') as f:
                            f.write(image_data)
                        
                        generated_images.append({
                            "id": variation.get('id', i),
                            "name": variation.get('name', f'变体{i}'),
                            "description": variation.get('description', ''),
                            "filepath": output_path,
                            "filename": filename,
                            "prompt": full_prompt,
                            "hypothesis_id": variation.get('hypothesis_id')
                        })
                        
            except Exception as e:
                print(f"生成变体 {i} 失败: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        return generated_images


# 单例模式
_image_service = None

def get_image_service() -> ComfyUIService:
    """获取图像服务实例"""
    global _image_service
    if _image_service is None:
        _image_service = ComfyUIService()
    return _image_service
