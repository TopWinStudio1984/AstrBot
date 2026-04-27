import base64
from io import BytesIO
from .util import write_log
import requests
import os
import time
import uuid
from astrbot.api.message_components import *

def generate_image(base_url, api_key, prompt, proxy_url):
    url = f"{base_url}/v1beta/models/gemini-2.0-flash-exp-image-generation:generateContent"
    headers = {
        "Content-Type": "application/json",
    }
    
    params = {
        "key": api_key
    }

    # 先考虑无会话历史
    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generation_config": {
            "response_modalities": ["Text", "Image"]
        }
    }

    # 创建代理配置
    proxies = None
    if proxy_url and len(proxy_url) > 0:
        proxies = {
            "http": proxy_url,
            "https": proxy_url
        }
    
    try:
        # 发送请求
        write_log(f"开始调用Gemini API生成图片")
        response = requests.post(
            url, 
            headers=headers, 
            params=params, 
            json=data,
            proxies=proxies,
            timeout=120  # 增加超时时间到120秒，解决多图文任务超时问题
        )
        
        write_log(f"Gemini API响应状态码: {response.status_code}")
        
        # 处理文本和图片响应，以列表形式返回所有部分
        image_datas = []
        text_responses = []
                
        if response.status_code == 200:
            result = response.json()
            
            # 记录完整响应内容，方便调试
            # write_log(f"Gemini API响应内容: {result}")
            
            # 提取响应
            candidates = result.get("candidates", [])
            if candidates and len(candidates) > 0:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                                
                for part in parts:
                    # 处理文本部分
                    if "text" in part and part["text"]:
                        text_responses.append(part["text"])
                        image_datas.append(None)  # 对应位置添加None表示没有图片
                    
                    # 处理图片部分
                    elif "inlineData" in part:
                        inline_data = part.get("inlineData", {})
                        if inline_data and "data" in inline_data:
                            # Base64解码图片数据
                            img_data = base64.b64decode(inline_data["data"])
                            image_datas.append(img_data)
                            text_responses.append(None)  # 对应位置添加None表示没有文本
                
                if not image_datas or all(img is None for img in image_datas):
                    write_log(f"API响应中没有找到图片数据: {result}")
                    # 检查是否有文本响应，仅返回文本数据
                    if text_responses and any(text is not None for text in text_responses):
                        # 仅返回文本响应，不修改e_context
                        return [], text_responses  # 返回空图片列表和文本
                    return [], []
                
                # return image_datas, text_responses
            
            # write_log(f"未找到生成的图片数据: {result}")
            # return [], []
        else:
            write_log(f"Gemini API调用失败 (状态码: {response.status_code}): {response.text}")
            return [], []
    except Exception as e:
        write_log(f"API调用异常: {str(e)}")
        return [], []
    
    # 保存图片到本地
    return save_image(image_datas)

    # 返回保存的图像地址
    # return image_paths, text_responses

def edit_image(base_url, api_key, image_url, prompt, proxy_url):
    url = f"{base_url}/v1beta/models/gemini-2.0-flash-exp-image-generation:generateContent"
    headers = {
        "Content-Type": "application/json",
    }
    
    params = {
        "key": api_key
    }

    # 读取图片文件并转换为base64字节
    image_datas = []
    try:
        with open(image_url, 'rb') as f:
            image_data = f.read()
            image_datas.append(image_data)
    except Exception as e:
        write_log(f"读取图片文件失败: {str(e)}")
        return [], []

    # 验证图片数据
    if not image_datas or len(image_datas) == 0:
        write_log("没有提供图片数据")
        return [], []
    
    # 将图片数据转换为Base64编码
    image_base64 = base64.b64encode(image_datas[0]).decode("utf-8")  # 使用第一张图片
    # print(image_base64)

    # 暂时处理无会话历史,直接显示提示和图片
    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    },
                    {
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": image_base64
                        }
                    }
                ]
            }
        ],
        "generation_config": {
            "response_modalities": ["Text", "Image"]
        }
    }

    # 创建代理配置
    proxies = None
    if proxy_url and len(proxy_url) > 0:
        proxies = {
            "http": proxy_url,
            "https": proxy_url
        }
    
    try:
        # 发送请求
        write_log(f"开始调用Gemini API编辑图片")
        response = requests.post(
            url, 
            headers=headers, 
            params=params, 
            json=data,
            proxies=proxies,
            timeout=120  # 增加超时时间到120秒，解决多图文任务超时问题
        )
        
        write_log(f"Gemini API响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            # 记录完整响应内容，方便调试
            # write_log(f"Gemini API响应内容: {result}")
            
            # 检查是否有内容安全问题
            candidates = result.get("candidates", [])
            if candidates and len(candidates) > 0:
                finish_reason = candidates[0].get("finishReason", "")
                if finish_reason == "IMAGE_SAFETY":
                    write_log("Gemini API返回IMAGE_SAFETY，图片内容可能违反安全政策")
                    return [], [json.dumps(result)]  # 返回整个响应作为错误信息
                
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                
                # 处理文本和图片响应，以列表形式返回所有部分
                text_responses = []
                image_datas = []
                
                for part in parts:
                    # 处理文本部分
                    if "text" in part and part["text"]:
                        text_responses.append(part["text"])
                        image_datas.append(None)  # 对应位置添加None表示没有图片
                    
                    # 处理图片部分
                    elif "inlineData" in part:
                        inline_data = part.get("inlineData", {})
                        if inline_data and "data" in inline_data:
                            # Base64解码图片数据
                            img_data = base64.b64decode(inline_data["data"])
                            image_datas.append(img_data)
                            text_responses.append(None)  # 对应位置添加None表示没有文本
                
                if not image_datas or all(img is None for img in image_datas):
                    write_log(f"API响应中没有找到图片数据: {result}")
                    
                    # 检查是否有文本响应，仅返回文本数据
                    if text_responses and any(text is not None for text in text_responses):
                        # 仅返回文本响应，不修改e_context
                        return [], text_responses  # 返回空图片列表和文本
                    return [], []
                
                # return image_datas, text_responses
            
            # write_log(f"未找到编辑后的图片数据: {result}")
            # return [], []
        else:
            write_log(f"Gemini API调用失败 (状态码: {response.status_code}): {response.text}")
            return [], []
    except Exception as e:
        write_log(f"API调用异常: {str(e)}")
        return [], []
    
    return save_image(image_datas)

def save_image(image_datas, save_dir = None):
    if not save_dir:
        save_dir = "/opt/App/filebrowser/filebrowser/files/图像编辑"

    # 保存图片到本地
    image_paths = []
    for i, image_data in enumerate(image_datas):
        if image_data is not None:  # 确保图片数据不为None
            # 确保有足够的clean_text
            # clean_text = clean_texts[i] if i < len(clean_texts) else f"image_{i}"
            # image_path = os.path.join(save_dir, f"gemini_{int(time.time())}_{uuid.uuid4().hex[:8]}_{clean_text}.png")
            image_path = os.path.join(save_dir, f"gemini_{int(time.time())}_{uuid.uuid4().hex[:8]}.png")
            with open(image_path, "wb") as f:
                f.write(image_data)
            image_paths.append(image_path)

    # print(image_paths)
    images = []
    for url in image_paths:
        images.append(url)
    
    chain = []
    # if len(text_responses) > 0:
    #     content = '\n'.join(text_responses)
    #     chain.append(Plain(content))

    for url in images:
        # chain.append(Image.fromURL(url))
        chain.append(Image.fromFileSystem(url))
        
    if len(chain) == 0:
        chain.append(Plain("没有内容生成!"))
        
    return chain, image_paths