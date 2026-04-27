import base64
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import emoji
import requests
from astrbot.api.message_components import *
from bs4 import BeautifulSoup


# 请求openai访问的chat接口
def normalize_openai_base_url(base_url):
    if base_url.endswith('/v1') or base_url.endswith('/v1/'):
        base_url = base_url.replace('/v1/', '')
        base_url = base_url.replace('/v1', '')
    return base_url


def openai_query(base_url, api_key, model, query):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    data = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": query
            }
        ],
        "stream": False
    }

    base_url = normalize_openai_base_url(base_url)

    url = f'{base_url}/v1/chat/completions'
    print(url)
    
    response = requests.post(url, json=data, headers=headers)

    ret_result = ""
    if response.status_code == 200:
        result = response.json()
        ret_result = result['choices'][0]['message']['content']
    else:
        ret_result = f'Error: {response.status_code}, Message: {response.text}'
    return ret_result

# 请求openai访问的图片生成接口
def openai_image_query(base_url, api_key, model, query, n=1, response_format="b64_json"):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    data = {
        "model": model,
        "prompt": query,
        "n": n,
        "response_format": response_format
    }

    base_url = normalize_openai_base_url(base_url)
    url = f'{base_url}/v1/images/generations'
    print(url)

    response = requests.post(url, json=data, headers=headers)

    if response.status_code != 200:
        return f'Error: {response.status_code}, Message: {response.text}'

    result = response.json()
    return result


# 请求openai访问的图像/文档解析接口
def openai_analyse(base_url, api_key, model, url, query):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    data = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file_url": {
                            "url": url
                        } 
                    },
                    {
                        "type": "text",
                        "text": query
                    }
                ]
            }
        ]
    }

    url = f'{base_url}/chat/completions'
    # print(url)
    response = requests.post(url, json=data, headers=headers)

    ret_result = ""
    if response.status_code == 200:
        result = response.json()
        ret_result = result['choices'][0]['message']['content']
    else:
        ret_result = f'Error: {response.status_code}, Message: {response.text}'
    return ret_result
    
# 请求dify的api接口    
def dify_query(base_url, api_key, model, query):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    data = {
        "inputs": {},
        "query": query,
        "response_mode": "blocking",
        "user": "topwin",
        "conversation_id": "",
        "files": []
    }

    url = f'{base_url}/chat-messages'
    # print(url)
    response = requests.post(url, json=data, headers=headers)

    ret_result = ""
    if response.status_code == 200:
        result = response.json()
        ret_result = result['answer']
    else:
        ret_result = f'Error: {response.status_code}, Message: {response.text}'
    return ret_result

# 调用接口返回图像
def common_image(cfg, name, prompt, is_dify):
    chain = []
    
    if not prompt:
        chain.append(Plain("请提供提示词！使用用法 /命令 <提示词>"))
        return chain
        
    base_url = cfg.get("base_url", "")
    api_key = cfg.get("api_key", "")
    model = cfg.get("model", "")
    api_type = cfg.get("api_type", "chat")
    image_count = int(cfg.get("n", 1) or 1)
    response_format = cfg.get("response_format", "b64_json")
    
    if len(api_key) == 0:
        chain.append(Plain(f"未设置{name}的api_key，请设置后重试!"))
        return chain
    
    print("参数:", base_url, api_key, model, api_type)
    
    if is_dify:
        result = dify_query(base_url, api_key, model, prompt)
        return decode_image_result(result)

    if api_type == "image":
        result = openai_image_query(base_url, api_key, model, prompt, image_count, response_format)
        return decode_generation_result(result)

    result = openai_query(base_url, api_key, model, prompt)
    return decode_image_result(result)


def save_base64_image(image_data, prefix="openai_image"):
    image_dir = Path("data/temp")
    image_dir.mkdir(parents=True, exist_ok=True)
    image_path = image_dir / f"{prefix}_{int(time.time() * 1000)}_{random.randint(1000, 9999)}.png"
    image_path.write_bytes(base64.b64decode(image_data))
    return image_path


# 解析 /v1/images/generations 返回结果
def decode_generation_result(result):
    if isinstance(result, str):
        return [Plain(result)]

    data_list = result.get('data', [])
    if len(data_list) == 0:
        return [Plain("没有内容生成!")]

    chain = []

    for item in data_list:
        image_url = item.get('url')
        b64_json = item.get('b64_json')

        if image_url:
            chain.append(Image.fromURL(image_url))
            continue

        if b64_json:
            image_path = save_base64_image(b64_json)
            chain.append(Image.fromFileSystem(str(image_path)))

    if len(chain) == 0:
        chain.append(Plain("没有内容生成!"))

    return chain


def openai_edit_image_query(base_url, api_key, model, image_path, prompt, size=None, response_format="b64_json"):
    base_url = normalize_openai_base_url(base_url)
    url = f'{base_url}/v1/images/edits'
    print(url)

    data = {
        "prompt": prompt,
        "response_format": response_format,
    }
    if model:
        data["model"] = model
    if size:
        data["size"] = size

    with Path(image_path).open("rb") as image_file:
        files = {
            "image": (Path(image_path).name, image_file, "application/octet-stream")
        }
        response = requests.post(
            url,
            data=data,
            files=files,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    if response.status_code != 200:
        return f'Error: {response.status_code}, Message: {response.text}'

    return response.json()


def edit_image_with_openai(cfg, image_path, prompt):
    if not prompt:
        return [Plain("请提供图像编辑提示词!")], []

    base_url = cfg.get("base_url", "")
    api_key = cfg.get("api_key", "")
    model = cfg.get("model", "")
    size = cfg.get("size", "")
    response_format = cfg.get("response_format", "b64_json")

    if len(api_key) == 0:
        return [Plain("未设置图生图的api_key，请设置后重试!")], []

    result = openai_edit_image_query(
        base_url=base_url,
        api_key=api_key,
        model=model,
        image_path=image_path,
        prompt=prompt,
        size=size,
        response_format=response_format,
    )

    if isinstance(result, str):
        return [Plain(result)], []

    data_list = result.get("data", [])
    if len(data_list) == 0:
        return [Plain("没有内容生成!")], []

    chain = []
    image_paths = []
    for item in data_list:
        image_url = item.get("url")
        b64_json = item.get("b64_json")

        if image_url:
            chain.append(Image.fromURL(image_url))
            continue

        if b64_json:
            saved_path = save_base64_image(b64_json, prefix="openai_edit")
            image_paths.append(str(saved_path))
            chain.append(Image.fromFileSystem(str(saved_path)))

    if len(chain) == 0:
        chain.append(Plain("没有内容生成!"))

    return chain, image_paths


# 去除思考过程
def remove_think(content):
    match = re.search(r'<think>(.*?)</think>', content, re.DOTALL)
    if match:
        content = match.group(1).strip()
    return content
        
# 解析图像返回结果    
def decode_image_result(result):
    result = remove_think(result)
    
    arr = result.split('\n')
    arr = [item for item in arr if item != ""]
    
    chain = []
    contents = []
    images = []
    for line in arr:
        if '![图像' in line or '![生成的图像' in line  or '![image' in line:
            pattern = r'(https?://[^\s<>"]+|www\.[^\s<>"]+)[)]+'
            urls = re.findall(pattern, line)
            if len(urls) > 0:
                url = urls[0]
                images.append(url)
        else:
            contents.append(line)
    
    if len(contents) > 0:
        content = '\n'.join(contents)
        chain.append(Plain(content))
    for url in images:
        chain.append(Image.fromURL(url))
        
    if len(chain) == 0:
        chain.append(Plain("没有内容生成!"))
        
    return chain


mobile_header = {'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}

def get_json(url):
    headers = mobile_header
    resp = requests.get(url, headers=headers)
    return resp.json()

def get_soup(url):
    headers = mobile_header
    resp = requests.get(url, headers=headers)
    soup = BeautifulSoup(resp.text, 'html.parser')
    return soup

# 将gpts的名字列表按4列布局排版处理
def format_gpts_key(gpts_key, num_columns = 2, has_index = True):
    string_list = []

    index = 1
    for k, v in gpts_key.items():
        if has_index:
            string_list.append(f"[{index}] {k} {v}")
        else:
            string_list.append(f"[{k}] {v}")
        index += 1

    max_length = max(len(s) for s in string_list)
    # num_columns = 2
    column_width = max_length + 10  # Add extra space for padding

    formatted_strings = []

    for i in range(0, len(string_list), num_columns):
        row_strings = string_list[i:i+num_columns]
        formatted_row = ''

        for s in row_strings:
            padding = ' ' * (column_width - len(s))
            formatted_row += s + padding

        formatted_strings.append(formatted_row)

    return '\n'.join(formatted_strings)

# 需要通过其它进程来启用当前进程
def restart_program():
    # current_pid = os.getpid()
    # print("Restarting the program...", current_pid)
    # # subprocess.Popen(["python", "restart.py"], stdin=f'{current_pid}')
    # subprocess.Popen(f"python restart.py {current_pid}", shell=True)
    # subprocess.Popen(["python", "restart.py"])
    # 杀死当前进程
    # os._exit(0)

    python = sys.executable
    os.execl(python, python, *sys.argv)
    #  获取当前 Python 解释器的路径
    
    # python = sys.executable
    
    # # 获取当前脚本的路径及参数
    # script = os.path.abspath(sys.argv[0])
    # args = sys.argv[1:]
    
    # # 替换当前进程
    # os.execv(python, [python, script] + args)


# 判断一个字符串是否和数组中的字符串前面部分匹配,并返回匹配的前缀
def is_prefix_match(prefix, string_array):
    for item in string_array:
        if item.startswith(prefix):
            return item
    return ""

# 使用正则表达式提取前缀
def extract_prefix(text):
    text = text.strip()
    pattern = r'^(\S+)'
    match = re.match(pattern, text)
    if match:
        return match.group(1)
    else:
        return ""
    
# 使用正则表达式提取前缀和后缀
def extract_prefix_and_suffix( text):
    # 使用正则表达式来匹配第一个以一个或多个空格隔开的前缀和后面的部分
    match = re.match(r'^\s*(\S+)\s+(.*)$', text)
    if match:
        prefix = match.group(1)  # 匹配到的前缀
        suffix = match.group(2)  # 匹配到的后缀
        return prefix, suffix
    else:
        return None, None  # 如果没有匹配到，返回None
  
# 生成6位随机码  
def generate_random_code():
    """生成 6 位包含数字和大小写字母的随机码."""
    # 定义包含数字和大小写字母的字符串
    pwd = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

    # 生成随机数
    random_number = random.randint(0, 36**6 - 1)

    # 将随机数转换为 36 进制
    random_code = ""
    while random_number > 0:
        random_code += pwd[random_number % 36]
        random_number //= 36

    # 返回随机码
    return random_code

# 获取当前时间
def current_time(format=""):
    updateTime = datetime.now()
    if(len(format) == 0):
        update_time = datetime.strftime(updateTime,'%Y-%m-%d %H:%M:%S')
    else:
        update_time = datetime.strftime(updateTime, format)
    return update_time

# 时间戳转换正常时间
def timestamp_to_time(timestamp, format = ""):
    dt_object = datetime.fromtimestamp(timestamp)
    if(len(format) == 0):
        formatted_date_time = dt_object.strftime('%Y-%m-%d %H:%M:%S')
    else:
        formatted_date_time = dt_object.strftime(format)
    
    return formatted_date_time

def replace_with_link(match):
    url, text = match.groups()
    url = url.strip()
    text = text.replace('\n','')

    if len(url) > 0:
        return f'{text} [ {url} ]'
    else:
        return f'{text}'

def replace_span_with_text(match):
    span_content = match.group(1)
    return span_content

# 将信息进行分批发送 
def batch_send(content, username):
    batch_size = 6000  # 每批打印的字数
    # 计算需要分成多少批次
    num_batches = (len(content) + batch_size - 1) // batch_size
    print("批次数量", num_batches)

    # 分批打印
    for i in range(num_batches):
        start = i * batch_size
        end = (i + 1) * batch_size
        print(content[start:end] + "\n\n")
        # itchat.send(content[start:end], toUserName=username)
        time.sleep(1)

def convert_to_divs(text):
    # 将输入的字符串按换行符分割成列表
    lines = text.split('\n')
    
    # 使用列表推导式创建一个包含div标签的列表
    # 每个div标签内包含原始字符串的一行
    wrapped_lines = ['<div>{}</div>'.format(line) for line in lines]
    
    # 使用join方法将列表中的所有div标签字符串连接成一个完整的字符串
    html_string = '\n'.join(wrapped_lines)
    
    return html_string

# 去除emoji字符
def remove_emoji(text):
  """从字符串中删除 emoji。

  Args:
    text: 要处理的字符串。

  Returns:
    已删除 emoji 的字符串。
  """
  return (emoji.replace_emoji(text, ''))

# 删除字符串中的空字符行
def remove_empty_lines(text):
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if line.strip():
            cleaned_lines.append(line)
    cleaned_text = '\n'.join(cleaned_lines)
    return cleaned_text

# 删除字符串中连续相同的文字保留一个
def remove_duplicate_lines(text):
    lines = text.split('\n')
    cleaned_lines = []
    prev_line = None
    for line in lines:
        if line != prev_line:
            cleaned_lines.append(line)
            prev_line = line
    cleaned_text = '\n'.join(cleaned_lines)
    return cleaned_text

# 根据定义的头和尾对多行字符串进行截取
def cut_head_tail(text, head_str, tail_str):
    lines = text.split('\n')
    cleaned_lines = []
    start = False
    for line in lines:
        if head_str in line:
            start = True
            continue
        if tail_str in line:
            break

        if start:
            cleaned_lines.append(line)

    cleaned_text = '\n'.join(cleaned_lines)
    return cleaned_text

# 自定义解析rss
def parse_rss(url):
    items = []
    try:
        response = requests.get(url, timeout=5)
        soup = BeautifulSoup(response.content, 'xml') # 注意这里使用'xml'解析器
        items = []
        
        for item in soup.find_all('item'):
            print(item)
            title = item.find('title').text
            link = item.find('link').text
            description = item.find('description').text
            published = item.find('pubDate').text

            entry = {
                'title': title,
                'link': link,
                'description': description,
                'published': published
            }

            items.append(entry)
        # 处理响应
    except requests.Timeout:
        # print("请求超时，请稍后重试。")
        return None
    except requests.RequestException as e:
        # 处理其他请求异常
        # print("请求发生异常:", e)
        return None
    
    return items

def write_log(msg):
    print(f"[ {current_time()} ] {msg}")
    

def remove_xf_search_source(text):
    # 定义要匹配的模式，包括```searchSource和```及其之间的内容
    pattern = r'```searchSource.*?```'
    
    # 使用re.sub函数替换匹配的内容为空字符串
    cleaned_text = re.sub(pattern, '', text, flags=re.DOTALL)
    
    return cleaned_text
    
def is_url(s):
    # 正则表达式模式，匹配一般的URL
    url_pattern = re.compile(
        r'^(?:http|ftp)s?://' # http:// 或 https:// 或 ftp://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' # 域名
        r'localhost|' # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|' # IPv4
        r'\[?[A-F0-9]*:[A-F0-9:]+\]?)' # IPv6
        r'(?::\d+)?' # 端口号
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return re.match(url_pattern, s) is not None


def format_formula(input_string):
    # 定义正则表达式，匹配 \[ 和 \] 之间的内容，包括换行符
    pattern = r'\\[.*?\\]'
    
    # 使用正则表达式替换
    def replace_match(match):
        # 获取匹配到的字符串
        matched_text = match.group(0)
        # 替换 \n 为空字符串
        replaced_text = matched_text.replace('\n', '')
        # 替换 \[ 和 \] 为 $$
        replaced_text = replaced_text.replace('\\[', '$$').replace('\\]', '$$')
        return replaced_text
    
    # 替换所有匹配的内容
    result = re.sub(pattern, replace_match, input_string, flags=re.DOTALL)
    return result

def format_formula1(input_string):
    result = input_string.replace("\\[", "$$")
    result = result.replace("\\]", "$$")
    
    parts= result.split('$$')
    # 对每个进行处理，如果是奇数索引的块（即$$之间的内容），则替换换行符
    for i in range(1, len(parts), 2):
        parts[i] = parts[i].replace('\n', ' ')
    # 重新组合文本
    return '$$'.join(parts)

# 将原目录的文件复制到新目录，并返回新路径,主要配合FileBrowser
def move_image(image_src, target_dir):
    target_path = Path(target_dir)
    target_path.mkdir(parents=True, exist_ok=True)

    image_src = str(image_src).strip()
    if not image_src:
        return ""

    def save_binary_image(image_bytes, suffix=".png"):
        image_path = target_path / f"image_{int(time.time() * 1000)}_{random.randint(1000, 9999)}{suffix}"
        image_path.write_bytes(image_bytes)
        return str(image_path)

    if image_src.startswith("data:"):
        try:
            header, encoded = image_src.split(",", 1)
            match = re.search(r"image/([a-zA-Z0-9]+)", header)
            suffix = f".{match.group(1)}" if match else ".png"
            return save_binary_image(base64.b64decode(encoded), suffix)
        except Exception:
            return image_src

    if image_src.startswith("base64://"):
        try:
            encoded = image_src[len("base64://") :]
            return save_binary_image(base64.b64decode(encoded), ".png")
        except Exception:
            return image_src

    try:
        return save_binary_image(base64.b64decode(image_src, validate=True))
    except Exception:
        pass

    if is_url(image_src):
        try:
            response = requests.get(image_src, timeout=10)
            response.raise_for_status()
            suffix = Path(image_src.split("?", 1)[0]).suffix or ".png"
            return save_binary_image(response.content, suffix)
        except Exception:
            return image_src

    src_path = Path(image_src)
    if not src_path.exists() or not src_path.is_file():
        return image_src

    destination = target_path / src_path.name

    try:
        shutil.move(str(src_path), str(destination))
    except Exception:
        return str(src_path)

    return str(destination)