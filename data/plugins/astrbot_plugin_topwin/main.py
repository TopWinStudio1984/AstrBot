from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from astrbot.api.provider import ProviderRequest, LLMResponse, Provider
import requests, re, html
from astrbot.api.message_components import *
from astrbot.api.all import *

from .lib import MySQL, Tools, OneNav, Stock
from .lib.object import Record as DbRecord
from .lib.util import current_time, common_image, openai_query, dify_query, format_formula, decode_image_result, move_image, remove_think
from .lib.gemini import generate_image, edit_image

import aiohttp
import asyncio
import time
from typing import Any, Dict, Optional, Union, cast
import json

# 用于跟踪每个用户的状态，防止超时或重复请求
USER_STATES: Dict[str, Optional[float]] = {}
USER_PROMPTS: Dict[str, Optional[str]] = {}
USER_IMAGES: Dict[str, Optional[str]] = {}
USER_IMAGE_FILES: Dict[str, Optional[str]] = {}
USER_IMAGE_INFOS: Dict[str, Optional[str]] = {}
USER_LAST_IMAGES: Dict[str, Optional[str]] = {}  # 保存最后编辑的图片的路径

@register("topwin_tools", "P.Dragon", "P.Dragon个人的自定义工具插件", "0.1")
class TopwinToolsPlugin(Star):
    def __init__(self, context: Context, config: dict[str, Any]):
        super().__init__(context)
        self.context: Context = context
        
        self.config = config
        self.glm_cfg: dict[str, Any] = config.get("glm_config") or {}
        self.mmapi_cfg: dict[str, Any] = config.get("mmapi_config") or {}
        self.analyse_cfg: dict[str, Any] = config.get("analyse_config") or {}
        self.share_cfg: dict[str, Any] = config.get("share_config") or {}
        self.editimage_dir = "/opt/App/filebrowser/filebrowser/files/图像编辑"

        # Mysql的相关操作
        self.mysql_handler = MySQL(self.mmapi_cfg)
        self.lastRecord = None
        
        # Stock的相关操作
        self.stock_handler = Stock(self.mmapi_cfg)

        # Tools的相关操作
        self.tools_handler = Tools(self.mmapi_cfg)
        
        print("topwin_tools初始化")


# ***************************************************************************************************
# 框架生命周期部分的处理
# ***************************************************************************************************   
            # @event_message_type(EventMessageType.ALL) # 注册一个过滤器，参见下文。
    # @filter.event_message_type(filter.EventMessageType.ALL)
    # async def on_message(self, event: AstrMessageEvent):
    #     print(event.message_obj.raw_message) # 平台下发的原始消息在这里
    #     print(event.message_obj.message) # AstrBot 解析出来的消息链内容
    
    # 收到LLM请求时
    @filter.on_llm_request()
    async def my_custom_hook_1(self, event: AstrMessageEvent, req: ProviderRequest): # 请注意有三个参数
        print("收到LLM请求时", req.system_prompt) # 打印请求的文本
        pass
        # req.system_prompt += "自定义 system_prompt"
    
    # 发送消息给消息平台适配器前
    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        print("发送消息给消息平台适配器前") # 打印消息链   , event.get_result()
        pass 
    
    # 发送消息给消息平台适配器后
    @filter.after_message_sent()
    async def after_message_sent(self, event: AstrMessageEvent):
        print("发送消息给消息平台适配器后") 
        pass

    # LLM请求完成时
    @filter.on_llm_response()
    async def on_llm_resp(self, event: AstrMessageEvent, resp: LLMResponse): # 请注意有三个参数
        # resp.completion_text += " end "
        
        # 对公式进行格式化
        resp.completion_text = format_formula(resp.completion_text)
        
        model = "dify"
        prompt = event.message_str
        if resp.raw_completion:
            model = resp.raw_completion.model
        content = resp.completion_text
        
        id = await self.save_record(event, model, prompt, content)
        if isinstance(id, int):
            resp.completion_text += f"[ {id} ] 链接地址:[ http://s.net11.cn/tmp/{id} ]"
        
        print("LLM请求完成")
    
    
    async def save_record(self, event, model, prompt, content):
        username = event.get_sender_id()
        nickname = event.get_sender_name()
        update_time = current_time()
       
        
        record = DbRecord(0, "astrbot", model, "", username, nickname, update_time, prompt, content)
        id = self.mysql_handler.saveRecordTmp(record)
        if isinstance(id, int):
            # 记录最后一次id，方便使用命令保存
            record.id = id
            self.lastRecord = record
        return id
    

# ***************************************************************************************************
# 即梦视频生成
# ***************************************************************************************************
    @filter.command("tt")
    async def test(self, event: AstrMessageEvent):
        from astrbot.api.message_components import Video
        # fromFileSystem 需要用户的协议端和机器人端处于一个系统中。
        music = Video.fromFileSystem(
            path="data/test.mp4"
        )
        # 更通用
        # music = Video.fromURL(
        #     url="https://example.com/video.mp4"
        # )
        yield event.chain_result(cast(list[BaseMessageComponent], [music]))
        
    @filter.command("v")
    async def jimeng_generator_video(self, event: AstrMessageEvent, prompt: str = ""):
        '''即梦视频生成 命令格式: /v 内容'''

        url = "http://read.tdkc.com.cn:8101/jimeng/generate_video/"

        payload = json.dumps({
        "prompt": "小马过河",
        "aspect_ratio": "16:9",
        "duration_ms": 5000,
        "fps": 24
        })

        # fromFileSystem 需要用户的协议端和机器人端处于一个系统中。
        music = Video.fromFileSystem(
            path="test.mp4"
        )

        headers = {
            'Authorization': 'Bearer Qweasd@12345',
            'Content-Type': 'application/json'
        }
    
        response = requests.request("POST", url, headers=headers, data=payload)
        result = response.json()

        if result['code'] == 200:
            # video = Video.fromFileSystem(result['file_path'])
            video = Video.fromURL(result['video_url'])
            yield event.chain_result(cast(list[BaseMessageComponent], [video]))   
        else:
            yield event.plain_result(f"生成视频失败!{result['message']}")



# ***************************************************************************************************
# 画图的处理部分
# ***************************************************************************************************
    @filter.command("img1")
    async def glm_image(self, event: AstrMessageEvent, prompt: str = ""):
        glm_cfg = dict(self.glm_cfg)
        api_type = str(glm_cfg.get("api_type", "image")).strip().lower() or "image"
        if api_type not in {"chat", "image"}:
            yield event.plain_result("glm_config.api_type 配置错误，请填写 chat 或 image")
            return

        glm_cfg["api_type"] = api_type
        chain = cast(list[BaseMessageComponent], common_image(glm_cfg, "GLM画图", prompt, False))
        yield event.chain_result(chain)


# ***************************************************************************************************
# 临时模型切换
# ***************************************************************************************************
    @filter.command("m")
    async def model_ls(self, event: AstrMessageEvent, idx_or_name: Optional[Union[int, str]] = None, prompt: str = ""):
        '''临时切换模型 命令格式: /m 模型编号 内容'''
        provider = self.context.get_using_provider(event.unified_msg_origin)
        if not provider or not isinstance(provider, Provider):
            yield event.plain_result("未找到任何 LLM 提供商。请先配置。")
            return
        
        models = []
        try:
            models = await provider.get_models()
        except BaseException as e:
            yield event.plain_result("获取模型列表失败: " + str(e)).use_t2i(False)
            return
        i = 1
        cmd_msg = "下面列出了此服务提供商可用模型:"
        for model in models:
            cmd_msg += f"\n{i}. {model}"
            i += 1
            
        cmd_msg += f"\n\n 当前模型：[ {provider.get_model()} ]"
        cmd_msg += "\nTips: 使用临时切换模型命令 /tmp 模型编号 问题，即可临时更换模型。"
        
        if idx_or_name is None or  (not isinstance(idx_or_name, int)):
            yield event.plain_result(cmd_msg)
            return
        else:
            if idx_or_name > len(models) or idx_or_name < 1:
                yield event.plain_result("模型序号错误。")
            else:
                try:
                    new_model = models[idx_or_name-1]
                except BaseException as e:
                    yield event.plain_result("切换模型未知错误: "+str(e))
                    return
                
                # 采用provider的信息和选择的模型进行调用
                cfg  = provider.provider_config or {}
                base_url = cfg.get("api_base", None)
                key_config = cfg.get("key") or []
                api_key = key_config[0] if isinstance(key_config, list) and len(key_config) > 0 else ""

                if not api_key:
                    yield event.plain_result("当前 provider 未配置 API Key。")
                    return
                
                # 问小白单独处理,不经过oneapi的处理
                # if new_model == "wenxiaobai":
                #     base_url = "http://bjnas.top:8004/v1"
                #     api_key = "keep_secret"
                #     print("问小白")

                # 2025.04.13 问小白的内容中处理
                if new_model == "wenxiaobai" and (prompt.startswith("画") or prompt.startswith("帮我画") or prompt.startswith("请帮我画")):
                    new_model = "wenxiaobai-image"
                    
                content = event.message_str
                index = content.find(" ", 3)
                prompt = content[index+1:]

                print(base_url, api_key, new_model, prompt)
        
                result = openai_query(base_url, api_key, new_model, prompt)
                result = remove_think(result)
                result = format_formula(result)

                if new_model == "wenxiaobai-image":
                    chain = decode_image_result(result)
                    yield event.chain_result(chain)
                    return
                
                id = await self.save_record(event, model, prompt, result)
                if isinstance(id, int):
                    result += f"[ {id} ] 链接地址:[ http://s.net11.cn/tmp/{id} ]"
                
                yield event.plain_result(f"{result}")
                

# ***************************************************************************************************
# 分享链接的处理部分
# ***************************************************************************************************
# 处理所有消息类型的事件
    @event_message_type(EventMessageType.ALL)
    async def handle_share_article(self, event: AstrMessageEvent):
        return
        raw_message = event.message_obj.raw_message
        xml_content = raw_message['Content']['string']
        pattern = re.compile(r'<url>(.*?)</url>', re.DOTALL)
        match = pattern.search(xml_content)
        if match:
            url = html.unescape(html.unescape(match.group(1)))
            print(f"handle_share_article: [ {url} ]")

            base_url = self.share_cfg.get("base_url", "")
            api_key = self.share_cfg.get("api_key", "")
            model = self.share_cfg.get("model", "")
            prompt = self.share_cfg.get("prompt", "")
             
            if not api_key or len(api_key) == 0:
                yield event.plain_result("文章分享的解析的api_key未设置。")
                return

            if not prompt or len(prompt) == 0:
                prompt = f"帮我总结一下这个链接: {url}"
            else:
                prompt = prompt.replace("{url}", url)
            
            print(f"提示词: {prompt}")
            result = openai_query(base_url, api_key, model, prompt)
            result = format_formula(result)
            
            # id = await self.save_record(event, model, prompt, result)
            # if isinstance(id, int):
            #     result += f"[ {id} ] 链接地址:[ http://s.net11.cn/tmp/{id} ]"
            
            yield event.plain_result(f"{result}")


# ***************************************************************************************************
# 文档和图像识别的处理部分
# ***************************************************************************************************
    @command("解析")
    async def analyse_image(self, event: AstrMessageEvent, prompt : str = ""):
        '''这是一个图片和文件解析的工具,命令格式: /解析 要描述的内容'''
        user_id = event.get_sender_id()  # 获取用户ID
        
        USER_STATES[user_id] = time.time()  # 记录用户请求的时间
        USER_PROMPTS[user_id] = prompt
        yield event.plain_result("开始等待解析图片和文件,请在30秒内发送你要解析的图片/文件或者url地址")  # 提示用户发送图片
        await asyncio.sleep(30)  # 等待30秒
        # 如果超时，删除用户状态并通知用户
        if user_id in USER_STATES:
            del USER_STATES[user_id]
            del USER_PROMPTS[user_id]
            yield event.plain_result("识图等待超时,请重新执行命令. /识图 内容")
    
    
    # 处理所有消息类型的事件
    @event_message_type(EventMessageType.ALL)
    async def handle_image_file(self, event: AstrMessageEvent):
        print("handle_image_file")
        # return
        user_id = event.get_sender_id()  # 获取发送者的ID
        
        # if user_id not in USER_STATES:  # 如果用户没有发起请求，跳过
        #     return
        
        print(self.glm_cfg)
        
        # 检查消息中是否包含地址
        image_url = ""
        image_file = ""
        prompt = ""
        for c in event.message_obj.message:
            if isinstance(c, Image):
                image_url = c.url
                image_file = c.file
                break
            if isinstance(c, Plain):
                prompt = c.text
                break
        
        base_url = self.analyse_cfg.get("base_url", "")
        api_key = self.analyse_cfg.get("api_key", "")
        model = self.analyse_cfg.get("model", "")

        print(base_url, api_key, model)

        if len(image_url) == 0:
            if user_id not in USER_STATES:
                print(f"提示词超时: {prompt}")
                return
            else:
                image_url = USER_IMAGES[user_id]
        else:
            # 如果上传了图片,等待10秒用户输入问题,如果没有输入,则用默认问题
            USER_STATES[user_id] = time.time()  # 记录用户请求的时间
            USER_IMAGES[user_id] = image_url    # 记录用户请求的额图片
            image_file = move_image(image_file, self.editimage_dir)
            print(image_file)
            USER_IMAGE_FILES[user_id] = image_file  # 记录用户请求的本地文件路径
            USER_LAST_IMAGES[user_id] = image_file

            # 2025.04.13 增加问小白的图片解析功能
            if 'wenxiaobai' in model:
                print("图片上传问小白服务器")
                url = "http://bjnas.top:8101/wenxb/upload_image"
                params = {
                    "token": "Qweasd@12345"
                }

                with open(image_file, 'rb') as f:
                    # 创建文件对象
                    files = {'file': (image_file.split('/')[-1], f, 'application/octet-stream')}
                    
                    # 发送POST请求
                    response = requests.post(url,params=params, files=files)
                    result = response.json()
                    print("上传问小白图片成功",result)
                    USER_IMAGE_INFOS[user_id] = result['data']

            tmp_prompt = self.analyse_cfg.get("prompt", "")
            yield event.plain_result(f"您上传了一张图片，触发了大模型的图像解析和编辑操作,会话时间10分钟,命令格式如下：\n格式: 1 [提示词]  -> 采用提示词进行文字解析，默认提示词为:[ {tmp_prompt} ]\n格式: 2 图像处理内容 -> 对图像进行编辑操作\n格式: 3 -> 结束图像解析/编辑工作")
            await asyncio.sleep(600) 

            if user_id in USER_STATES:
                del USER_STATES[user_id]
            if user_id in USER_IMAGES:
                del USER_IMAGES[user_id]
            if user_id in USER_IMAGE_FILES:
                del USER_IMAGE_FILES[user_id]
            if user_id in USER_LAST_IMAGES:
                del USER_LAST_IMAGES[user_id]
            if user_id in USER_IMAGE_INFOS:
                del USER_IMAGE_INFOS[user_id]
            # yield event.plain_result(f"本轮图像解析/编辑时间到,请重新开启新一轮处理")
            print(f"本轮图像解析/编辑时间到,请重新开启新一轮处理")
            return
        
        # # 删除用户状态，表示用户已提交图片
        # if user_id in USER_STATES:
        #     del USER_STATES[user_id]
        #     del USER_IMAGES[user_id]
        #     del USER_IMAGE_FILES[user_id]
        # else:
        #     print(f"已采用自定义提示词")
        #     return
        image_info = {}
        if user_id in USER_IMAGE_INFOS:
            image_info = USER_IMAGE_INFOS[user_id]

        if prompt.strip() == "3":
            yield event.plain_result("本轮图像解析/图像编辑工作结束")

            if user_id in USER_STATES:
                del USER_STATES[user_id]
            if user_id in USER_IMAGES:
                del USER_IMAGES[user_id]
            if user_id in USER_IMAGE_FILES:
                del USER_IMAGE_FILES[user_id]
            if user_id in USER_LAST_IMAGES:
                del USER_LAST_IMAGES[user_id]
            if user_id in USER_IMAGE_INFOS:
                del USER_IMAGE_INFOS[user_id]
            return
        
        if user_id not in USER_STATES:
            return
        
         # 拦截图像编辑
        if prompt.startswith("2 "):
            prompt = prompt[2:].strip()  # 获取实际内容
            
            # 获取本地图片文件路径
            image_file = USER_LAST_IMAGES[user_id]
            if not image_file or len(image_file) == 0:
                yield event.plain_result("未找到需要处理的图片文件")
                return
            
            base_url = self.glm_cfg.get("base_url", "")
            api_key = self.glm_cfg.get("api_key", "")
            proxy_url = self.glm_cfg.get("proxy_url", "")
            print(image_file)
            chain, image_paths = edit_image(base_url, api_key, image_file, prompt, proxy_url)
            if len(image_paths) > 0:
                USER_LAST_IMAGES[user_id] = image_paths[0]
            
            if len(chain) == 0:
                yield event.plain_result("编辑图像失败,请重新输入提示词")
                return

            yield event.chain_result(chain)
            return
            
        if not prompt or len(prompt) == 0 or prompt.strip() == "1":
            prompt = self.analyse_cfg.get("prompt", "")

        if prompt.startswith("1 "):
            prompt = prompt[2:].strip()  # 获取实际内容
  
        # yield event.plain_result(f"正在解析图片内容请稍后,提示词为: [ {prompt} ]")
                            
        # 如果未配置API Key，提醒用户
        if not api_key:
            yield event.plain_result("请先配置识图/文档解析API Key")
            return

        # data/temp/1739346982_a0959f73.jpg
        # image_name = image_url.split("/")[-1]
        print(image_url)
        print(base_url, api_key, model)
        # image_url = "http://wefile.net11.cn/1739316882_71799dea.jpg"
        try:
            # 使用aiohttp进行异步请求
            async with aiohttp.ClientSession() as session:
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
                                        "url": image_url
                                    } 
                                },
                                {
                                    "type": "text",
                                    "text": prompt
                                }
                            ]
                        }
                    ]
                }

                if image_info:
                    data = {
                        "model": model,
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "image_info": image_info
                    }
                print(data)

                # 调用SauceNAO API进行图片搜索
                url = f'{base_url}/chat/completions'
                # print(url)
                # print(data)
                # print(headers)
                async with session.post(url, json=data, headers=headers) as resp:
                    data = await resp.json()  # 解析返回的JSON数据
                print(data)
                ret_result = data['choices'][0]['message']['content']
                yield event.plain_result(ret_result)
                
        except Exception as e:  # 捕获异常并返回错误信息
            print(f"识图/解析文档失败: {str(e)}")
            yield event.plain_result(f"识图/解析文档失败: {str(e)}")
            
            
                    
# ***************************************************************************************************
# Stock的处理部分
# ***************************************************************************************************
    @command_group("st")
    def stock(self):
        '''
        这是一个 Stock 指令组，取缩写st
        [查看新闻] /st news 内容
        [查找信息] /st search 名称/代码
        [统计信息] /st stat [1-9]
        [推荐信息] /st t [1-9]
                   '最新投资评级', '上调评级股票', '下调评级股票', '股票综合评级', '首次评级股票', '目标涨幅排名', '机构关注度', '行业关注度', '投资评级选股'
        [筹码分布] /st cm 名称/代码
        '''
        pass

    @stock.command("news")
    async def st_news(self, event: AstrMessageEvent, prompt : str = ""):
        result = self.stock_handler.dispatch("news", prompt)
        yield event.plain_result(f"{result}")

    @stock.command("search")
    async def st_search(self, event: AstrMessageEvent, prompt : str = ""):
        result = self.stock_handler.dispatch("search", prompt)
        yield event.plain_result(f"{result}")

    @stock.command("stat")
    async def st_stat(self, event: AstrMessageEvent, prompt : str = ""):
        result = self.stock_handler.dispatch("stat", prompt)
        yield event.plain_result(f"{result}")

    @stock.command("t")
    async def st_recommended(self, event: AstrMessageEvent, prompt : str = ""):
        result = self.stock_handler.dispatch("t", prompt)
        yield event.plain_result(f"{result}")

    @stock.command("cm")
    async def st_cm(self, event: AstrMessageEvent, prompt : str = ""):
        result = self.stock_handler.dispatch("cm", prompt)
        if isinstance(result, list):
            yield event.chain_result(result)
        else:
            yield event.plain_result(f"{result}")
        
        
        
# ***************************************************************************************************
# MySQL操作部分的处理部分
# ***************************************************************************************************
    @command_group("my")
    def mysql(self):
        '''
        这是一个 MySQL 指令组，取缩写my
        [查看帮助] /my help
        [查找内容] /my search [内容]
        [查看详情] /my detail id
        [收藏记录] /my save [临时id]
        [删除记录] /my delete [收藏id]
        [token记录] /my token [内容]
        [token添加] /my tadd 标题,基地址,api_key
        '''
        pass
    
    @mysql.command("help")
    async def mysql_help(self, event: AstrMessageEvent):
        result = self.mysql_handler.dispatch("help", "")
        yield event.plain_result(f"{result}")
        
    @mysql.command("search")
    async def mysql_search(self, event: AstrMessageEvent, prompt : str = ""):
        result = self.mysql_handler.dispatch("search", prompt)
        yield event.plain_result(f"{result}")
        
    @mysql.command("detail")
    async def mysql_detail(self, event: AstrMessageEvent, prompt : str = ""):
        username = event.get_sender_id()
        result = self.mysql_handler.dispatch("detail", prompt)
        yield event.plain_result(f"{result}")
        
    @mysql.command("save")
    async def mysql_save(self, event: AstrMessageEvent, prompt : str = ""):
        result = self.mysql_handler.dispatch("save", prompt, self.lastRecord)
        yield event.plain_result(f"{result}")
        
    @mysql.command("delete")
    async def mysql_delete(self, event: AstrMessageEvent, prompt : str = ""):
        result = self.mysql_handler.dispatch("delete", prompt)
        yield event.plain_result(f"{result}")
        
    @mysql.command("token")
    async def mysql_token(self, event: AstrMessageEvent, prompt : str = ""):
        result = self.mysql_handler.dispatch("token", prompt)
        yield event.plain_result(f"{result}")
        
    @mysql.command("tadd")
    async def mysql_tadd(self, event: AstrMessageEvent, prompt : str = ""):
        result = self.mysql_handler.dispatch("tadd", prompt)
        yield event.plain_result(f"{result}")
        
    @mysql.command("sa")
    async def mysql_sa(self, event: AstrMessageEvent, prompt : str = ""):
        result = self.mysql_handler.dispatch("sa", prompt)
        yield event.plain_result(f"{result}")
        
 
# ***************************************************************************************************
# 工具的处理部分
# ***************************************************************************************************
    @command_group("t")
    def tools(self):
        '''
        这是一个 Tools工具箱 指令组，取缩写t
        [翻译] /t 翻译 内容
        [菜谱] /t 菜谱 内容
        [音乐] /t 音乐 内容
        [单词] /t 单词 内容
        [Linux] /t Linux 命令
        [科技] /t 科技
        [60s图] /t 60s [day/baidu/weibo]
        [新闻] /t news [数字]
        [老赖] /t laolai 姓名
        [天气] /t 天气 地区
        [词语字典] /t 词典 内容
        [古诗] /t 古诗 内容
        [高校] /t 高校 内容
        [RSS] /t rss 内容
        [计算缸径] /t 缸径 kN值,MPa值,立柱个数
        '''
        pass

    def r(self, tools_type, prompt, param=""):
        result = self.tools_handler.dispatch(tools_type, prompt, param)
        return result
        
    @tools.command("翻译")
    async def translate(self, event: AstrMessageEvent, prompt: str = ""):
        yield event.plain_result(f"{self.r('翻译', prompt)}")
        
    @tools.command("菜谱")
    async def cookbook(self, event: AstrMessageEvent, prompt: str = ""):
        yield event.plain_result(f"{self.r('菜谱', prompt)}")
        
    @tools.command("音乐")
    async def music(self, event: AstrMessageEvent, prompt: str = ""):
        yield event.plain_result(f"{self.r('音乐', prompt)}")
        
    @tools.command("单词")
    async def word(self, event: AstrMessageEvent, prompt: str = ""):
        yield event.plain_result(f"{self.r('单词', prompt)}")
        
    @tools.command("linux")
    async def linux(self, event: AstrMessageEvent, prompt: str = ""):
        yield event.plain_result(f"{self.r('linux', prompt)}")
    
    @tools.command("科技")
    async def science(self, event: AstrMessageEvent, prompt: str = ""):
        yield event.plain_result(f"{self.r('科技', prompt)}")    
        
    @tools.command("60s")
    async def SixtyS(self, event: AstrMessageEvent, prompt: str = ""):
        url = f"{self.r('60s', prompt)}"
        if url is not None and len(url) > 0 and 'http' in url:
            chain = cast(list[BaseMessageComponent], [Image.fromURL(url)])
            yield event.chain_result(chain) 
        else:
            yield event.plain_result("命令错误,格式为: /t 60s [day/baidu/weibo]")   
        
    @tools.command("news")
    async def news(self, event: AstrMessageEvent, prompt: str = ""):
        yield event.plain_result(f"{self.r('news', prompt)}")
        
    @tools.command("laolai")
    async def laolai(self, event: AstrMessageEvent, prompt: str = ""):
        yield event.plain_result(f"{self.r('laolai', prompt)}")
        
    @tools.command("天气")
    async def weather(self, event: AstrMessageEvent, prompt: str = ""):
        yield event.plain_result(f"{self.r('天气', prompt)}")
        
    @tools.command("词典")
    async def dictionary(self, event: AstrMessageEvent, prompt: str = ""):
        yield event.plain_result(f"{self.r('词典', prompt)}")
        
    @tools.command("古诗")
    async def poetry(self, event: AstrMessageEvent, prompt: str = ""):
        yield event.plain_result(f"{self.r('古诗', prompt)}")
        
    @tools.command("高校")
    async def school(self, event: AstrMessageEvent, prompt: str = ""):
        yield event.plain_result(f"{self.r('高校', prompt)}")
        
    @tools.command("rss")
    async def rss(self, event: AstrMessageEvent, prompt: str = "", param: str = ""):
        yield event.plain_result(f"{self.r('rss', prompt, param)}")
        
    @tools.command("缸径")
    async def calc_radius(self, event: AstrMessageEvent, prompt: str = ""):
        yield event.plain_result(f"{self.r('缸径', prompt)}")
        

# ***************************************************************************************************
# 测试的处理部分
# ***************************************************************************************************              
    # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    @filter.command("hello")
    async def say_hello(self, event: AstrMessageEvent):
        '''这是一个 hello world 指令'''
        user_name = event.get_sender_name()
        message_str = event.message_str # 用户发的纯文本消息字符串
        message_chain = event.get_messages() # 用户所发的消息的消息链 # from astrbot.api.message_components import *
        logger.info(message_chain)
        yield event.plain_result(f"Hello, {user_name}, 你发了 {message_str}!") # 发送一条纯文本消息
