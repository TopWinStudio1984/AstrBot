from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from astrbot.api.provider import ProviderRequest, LLMResponse, Provider
import requests, re, html
from astrbot.api.message_components import *
from astrbot.api.all import *

from .lib import MySQL, Tools, OneNav, Stock
from .lib.object import Record as DbRecord
from .lib.util import (
    current_time,
    common_image,
    openai_query,
    dify_query,
    format_formula,
    decode_image_result,
    move_image,
    remove_think,
    edit_image_with_openai,
)

import asyncio
from typing import Any, Dict, Optional, Union, cast
import json

# Used to track each user's image edit session.
USER_STATES: Dict[str, Optional[float]] = {}
USER_IMAGE_FILES: Dict[str, Optional[str]] = {}
USER_LAST_IMAGES: Dict[str, Optional[str]] = {}

@register("topwin_tools", "P.Dragon", "P.Dragon个人的自定义工具插件", "0.1")
class TopwinToolsPlugin(Star):
    def __init__(self, context: Context, config: dict[str, Any]):
        super().__init__(context)
        self.context: Context = context
        
        self.config = config
        self.image_cfg: dict[str, Any] = config.get("image_config") or {}
        self.mmapi_cfg: dict[str, Any] = config.get("mmapi_config") or {}
        self.share_cfg: dict[str, Any] = config.get("share_config") or {}
        # self.editimage_dir = "/opt/App/filebrowser/filebrowser/files/图像编辑"
        self.editimage_dir = r"D:\TDDownload\images"

        # Mysql的相关操作
        self.mysql_handler = MySQL(self.mmapi_cfg)
        self.lastRecord = None
        
        # Stock的相关操作
        self.stock_handler = Stock(self.mmapi_cfg)

        # Tools的相关操作
        self.tools_handler = Tools(self.mmapi_cfg)
        
        print("topwin_tools初始化")

    def get_image_command_prefixes(self) -> list[str]:
        prefixes = self.image_cfg.get("command_prefixes", ["img"])
        if not isinstance(prefixes, list):
            return ["img"]

        normalized_prefixes: list[str] = []
        for item in prefixes:
            prefix = str(item).strip()
            if prefix:
                normalized_prefixes.append(prefix)

        return normalized_prefixes or ["img"]

    def extract_image_prompt(self, message: str) -> tuple[Optional[str], Optional[str]]:
        content = message.strip()
        if not content:
            return None, None

        candidates = [content]
        if content.startswith("/"):
            candidates.append(content[1:].strip())

        for candidate in candidates:
            for prefix in self.get_image_command_prefixes():
                if candidate == prefix:
                    return "", prefix
                if candidate.startswith(f"{prefix} "):
                    return candidate[len(prefix):].strip(), prefix

        return None, None

    def get_edit_image_command_prefixes(self) -> list[str]:
        prefixes = self.image_cfg.get("edit_prefixes", ["图生图"])
        if not isinstance(prefixes, list):
            return ["图生图"]

        normalized_prefixes: list[str] = []
        for item in prefixes:
            prefix = str(item).strip()
            if prefix:
                normalized_prefixes.append(prefix)

        return normalized_prefixes or ["图生图"]

    def extract_edit_image_prompt(self, message: str) -> tuple[Optional[str], Optional[str]]:
        content = message.strip()
        if not content:
            return None, None

        candidates = [content]
        if content.startswith("/"):
            candidates.append(content[1:].strip())

        for candidate in candidates:
            for prefix in self.get_edit_image_command_prefixes():
                if candidate == prefix:
                    return "", prefix
                if candidate.startswith(f"{prefix} "):
                    return candidate[len(prefix):].strip(), prefix

        return None, None

    def clear_edit_image_state(self, user_id: str):
        USER_STATES.pop(user_id, None)
        USER_IMAGE_FILES.pop(user_id, None)
        USER_LAST_IMAGES.pop(user_id, None)

    async def expire_edit_image_state(self, event: AstrMessageEvent, user_id: str, timestamp: float):
        await asyncio.sleep(30)
        if USER_STATES.get(user_id) != timestamp:
            return

        self.clear_edit_image_state(user_id)
        await event.send(event.plain_result("图生图已取消，请重新上传图片后再试。"))

    async def render_common_image(self, event: AstrMessageEvent, prompt: str):
        image_cfg = dict(self.image_cfg)
        api_type = str(image_cfg.get("api_type", "image")).strip().lower() or "image"
        if api_type not in {"chat", "image"}:
            yield event.plain_result("image_config.api_type 配置错误，请填写 chat 或 image")
            return

        image_cfg["api_type"] = api_type
        chain = cast(list[BaseMessageComponent], common_image(image_cfg, "通用画图", prompt, False))
        yield event.chain_result(chain)


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
        # print("收到LLM请求时", req.system_prompt) # 打印请求的文本
        print("收到LLM请求时")
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
# 通用画图的处理部分
# ***************************************************************************************************
    @filter.command("img")
    async def common_image_command(self, event: AstrMessageEvent, prompt: str = ""):
        async for result in self.render_common_image(event, prompt):
            yield result

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_general_image_command(self, event: AstrMessageEvent):
        prompt, prefix = self.extract_image_prompt(event.message_str)
        if prefix is None:
            return

        if event.message_str.strip().startswith("/") and prefix == "img":
            return

        async for result in self.render_common_image(event, prompt or ""):
            yield result
        event.stop_event()


# ***************************************************************************************************
# 图生图的处理部分
# ***************************************************************************************************
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_image_edit_request(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()

        image_file = ""
        for component in event.message_obj.message:
            if isinstance(component, Image):
                image_file = component.file or ""
                break
        
        print("image_file1")
        if image_file:
            image_file = move_image(image_file, self.editimage_dir)
            print(image_file[:100])
            timestamp = asyncio.get_running_loop().time()
            USER_STATES[user_id] = timestamp
            USER_IMAGE_FILES[user_id] = image_file
            USER_LAST_IMAGES[user_id] = image_file

            prefixes_text = " / ".join(self.get_edit_image_command_prefixes())
            yield event.plain_result(
                f"已收到图片，请在30秒内发送“前缀 处理命令”进行图生图，例如：{prefixes_text} 把背景改成海边。"
            )
            asyncio.create_task(self.expire_edit_image_state(event, user_id, timestamp))
            return

        prompt, prefix = self.extract_edit_image_prompt(event.message_str)
        if prefix is None or user_id not in USER_STATES:
            return

        if not prompt:
            yield event.plain_result("请输入图像编辑指令，例如：图生图 把背景改成海边。")
            event.stop_event()
            return

        image_file = USER_LAST_IMAGES.get(user_id)
        if not image_file:
            self.clear_edit_image_state(user_id)
            yield event.plain_result("未找到待处理的图片，请重新上传图片后再试。")
            event.stop_event()
            return

        print("收到指令" + prompt)

        chain, image_paths = edit_image_with_openai(self.image_cfg, image_file, prompt)
        print("生成图像")
        print(image_paths)
        if image_paths:
            USER_LAST_IMAGES[user_id] = image_paths[0]

        self.clear_edit_image_state(user_id)
        # yield event.chain_result(cast(list[BaseMessageComponent], chain))
        event.stop_event()


# ***************************************************************************************************
# 临时模型切换
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
