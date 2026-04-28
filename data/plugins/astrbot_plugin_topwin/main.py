import asyncio
import json
import re
from pathlib import Path
from typing import Any, cast

import requests
from astrbot.api import logger
from astrbot.api.all import *
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import *
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star, register

from .lib import MySQL, Stock, Tools
from .lib.object import Record as DbRecord
from .lib.util import (
    common_image,
    current_time,
    edit_image_with_openai,
    format_formula,
    move_image,
)

# Used to track each user's image edit session.
USER_STATES: dict[str, float | None] = {}
USER_IMAGE_FILES: dict[str, str | None] = {}
USER_LAST_IMAGES: dict[str, str | None] = {}

@register("topwin_tools", "P.Dragon", "P.Dragon个人的自定义工具插件", "0.1")
class TopwinToolsPlugin(Star):
    def __init__(self, context: Context, config: dict[str, Any]):
        super().__init__(context)
        self.context: Context = context

        self.config = config
        self.image_cfg: dict[str, Any] = config.get("image_config") or {}
        self.mmapi_cfg: dict[str, Any] = config.get("mmapi_config") or {}
        self.share_cfg: dict[str, Any] = config.get("share_config") or {}
        self.editimage_dir = str(self.image_cfg.get("editimage_dir", "")).strip()

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

    def extract_image_prompt(self, message: str) -> tuple[str | None, str | None]:
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
                    return candidate[len(prefix) :].strip(), prefix

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

    def _extract_images_from_message_chain(self, chain: Any) -> list[str]:
        if hasattr(chain, "chain"):
            chain = getattr(chain, "chain")
        if not isinstance(chain, list):
            return []

        refs: list[str] = []
        for comp in chain:
            if isinstance(comp, dict):
                if str(comp.get("type", "")).lower() != "image":
                    continue
                for key in (
                    "url",
                    "file",
                    "path",
                    "src",
                    "image_url",
                    "file_url",
                    "pic_url",
                ):
                    value = comp.get(key)
                    if isinstance(value, str) and value.strip():
                        refs.append(value.strip())
                continue

            if isinstance(comp, Image) or comp.__class__.__name__.lower() == "image":
                for attr in ("url", "file", "path", "src"):
                    value = getattr(comp, attr, None)
                    if isinstance(value, str) and value.strip():
                        refs.append(value.strip())
        return refs

    def _extract_images_from_raw_message(self, raw: Any) -> list[str]:
        refs: list[str] = []
        if raw is None:
            return refs

        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return refs
            for match in re.findall(r"\[CQ:image,[^\]]*\]", text, flags=re.IGNORECASE):
                key_match = re.search(
                    r"url=([^,\]]+)", match, flags=re.IGNORECASE
                ) or re.search(r"file=([^,\]]+)", match, flags=re.IGNORECASE)
                if key_match:
                    refs.append(key_match.group(1).strip())
            try:
                raw = json.loads(text)
            except Exception:
                return refs

        def walk(obj: Any, depth: int = 0):
            if depth > 10:
                return
            if isinstance(obj, dict):
                obj_type = str(obj.get("type", "")).lower()
                if "image" in obj_type:
                    for key in (
                        "file",
                        "url",
                        "path",
                        "src",
                        "image_url",
                        "file_url",
                        "pic_url",
                    ):
                        value = obj.get(key)
                        if isinstance(value, str) and value.strip():
                            refs.append(value.strip())
                for key, value in obj.items():
                    if key in {
                        "file",
                        "url",
                        "path",
                        "src",
                        "image_url",
                        "file_url",
                        "pic_url",
                    }:
                        if isinstance(value, str) and value.strip():
                            refs.append(value.strip())
                    walk(value, depth + 1)
                return
            if isinstance(obj, list):
                for item in obj:
                    walk(item, depth + 1)

        walk(raw)
        return refs

    def _extract_aiocqhttp_image_file_ids(self, raw: Any) -> list[str]:
        ids: list[str] = []
        if raw is None:
            return ids

        if isinstance(raw, str):
            text = raw.strip()
            if text:
                for match in re.findall(
                    r"\[CQ:image,[^\]]*\]", text, flags=re.IGNORECASE
                ):
                    key_match = re.search(r"file=([^,\]]+)", match, flags=re.IGNORECASE)
                    if key_match:
                        ids.append(key_match.group(1).strip())
            try:
                raw = json.loads(text) if text else None
            except Exception:
                return list(dict.fromkeys([item for item in ids if item]))

        def walk(obj: Any, depth: int = 0):
            if depth > 10:
                return
            if isinstance(obj, dict):
                obj_type = str(obj.get("type", "")).lower()
                if obj_type == "image":
                    data = obj.get("data")
                    if isinstance(data, dict):
                        file_id = data.get("file")
                        if file_id is not None:
                            ids.append(str(file_id).strip())
                    file_id = obj.get("file")
                    if file_id is not None:
                        ids.append(str(file_id).strip())
                for value in obj.values():
                    walk(value, depth + 1)
                return
            if isinstance(obj, list):
                for item in obj:
                    walk(item, depth + 1)

        walk(raw)
        return list(dict.fromkeys([item for item in ids if item]))

    def _extract_reply_message_ids_from_event(
        self, event: AstrMessageEvent
    ) -> list[str]:
        ids: list[str] = []
        chain = getattr(getattr(event, "message_obj", None), "message", None)
        if hasattr(chain, "chain"):
            chain = getattr(chain, "chain")

        if isinstance(chain, list):
            for comp in chain:
                if isinstance(comp, dict):
                    if str(comp.get("type", "")).lower() == "reply":
                        for key in ("message_id", "id"):
                            value = comp.get(key)
                            if isinstance(value, (str, int)):
                                ids.append(str(value).strip())
                else:
                    if comp.__class__.__name__.lower() == "reply":
                        for attr in ("message_id", "id"):
                            value = getattr(comp, attr, None)
                            if isinstance(value, (str, int)):
                                ids.append(str(value).strip())

        raw = getattr(getattr(event, "message_obj", None), "raw_message", None)
        if raw is None:
            return list(dict.fromkeys([item for item in ids if item]))

        if isinstance(raw, str):
            text = raw.strip()
            if text:
                for match in re.findall(
                    r"\[CQ:reply,[^\]]*\]", text, flags=re.IGNORECASE
                ):
                    key_match = re.search(r"id=([^,\]]+)", match, flags=re.IGNORECASE)
                    if key_match:
                        ids.append(key_match.group(1).strip())
            try:
                raw = json.loads(text) if text else None
            except Exception:
                return list(dict.fromkeys([item for item in ids if item]))

        def walk(obj: Any, depth: int = 0):
            if depth > 10:
                return
            if isinstance(obj, dict):
                obj_type = str(obj.get("type", "")).lower()
                if obj_type == "reply":
                    data = obj.get("data")
                    if isinstance(data, dict):
                        reply_id = data.get("id") or data.get("message_id")
                        if reply_id is not None:
                            ids.append(str(reply_id).strip())
                    reply_id = obj.get("id") or obj.get("message_id")
                    if reply_id is not None:
                        ids.append(str(reply_id).strip())
                for value in obj.values():
                    walk(value, depth + 1)
                return
            if isinstance(obj, list):
                for item in obj:
                    walk(item, depth + 1)

        walk(raw)
        return list(dict.fromkeys([item for item in ids if item]))

    async def _call_aiocqhttp_action(
        self, event: AstrMessageEvent, action: str, **params: Any
    ) -> Any:
        get_platform_name = getattr(event, "get_platform_name", None)
        platform_name = ""
        if callable(get_platform_name):
            try:
                platform_name = str(get_platform_name()).lower()
            except Exception:
                platform_name = ""

        if platform_name != "aiocqhttp":
            return None

        bot = getattr(event, "bot", None)
        api = getattr(bot, "api", None) if bot is not None else None
        call_action = getattr(api, "call_action", None) if api is not None else None
        if call_action is None:
            return None

        try:
            result = await call_action(action, **params)
        except Exception:
            return None

        if not isinstance(result, dict):
            return result
        return result.get("data", result)

    async def _fetch_aiocqhttp_image_refs(
        self, event: AstrMessageEvent, file_ids: list[str]
    ) -> list[str]:
        refs: list[str] = []
        for file_id in file_ids[:6]:
            data = await self._call_aiocqhttp_action(event, "get_image", file=file_id)
            if not isinstance(data, dict):
                continue
            for key in ("file", "url", "path"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    refs.append(value.strip())
        return refs

    async def _fetch_message_image_refs_by_id(
        self, event: AstrMessageEvent, message_id: str
    ) -> list[str]:
        if not message_id:
            return []

        payload = await self._call_aiocqhttp_action(
            event, "get_msg", message_id=message_id
        )
        if (not isinstance(payload, dict)) or (not payload):
            try:
                payload = await self._call_aiocqhttp_action(
                    event, "get_msg", message_id=int(str(message_id))
                )
            except Exception:
                payload = payload

        if not payload:
            return []

        refs: list[str] = []
        refs.extend(self._extract_images_from_raw_message(payload.get("message")))
        refs.extend(self._extract_images_from_raw_message(payload))
        refs.extend(
            await self._fetch_aiocqhttp_image_refs(
                event, self._extract_aiocqhttp_image_file_ids(payload)
            )
        )
        return refs

    async def collect_edit_image_refs(self, event: AstrMessageEvent) -> list[str]:
        refs: list[str] = []
        message_obj = getattr(event, "message_obj", None)
        raw_message = getattr(message_obj, "raw_message", None)
        message_chain = getattr(message_obj, "message", None)

        refs.extend(self._extract_images_from_message_chain(message_chain))

        message_id = getattr(message_obj, "message_id", None)
        if message_id is not None:
            refs.extend(
                await self._fetch_message_image_refs_by_id(event, str(message_id))
            )

        refs.extend(self._extract_images_from_raw_message(raw_message))
        refs.extend(
            await self._fetch_aiocqhttp_image_refs(
                event, self._extract_aiocqhttp_image_file_ids(raw_message)
            )
        )

        reply_ids = self._extract_reply_message_ids_from_event(event)
        for reply_id in reply_ids[:3]:
            refs.extend(await self._fetch_message_image_refs_by_id(event, reply_id))

        normalized_refs: list[str] = []
        for ref in refs:
            value = str(ref).strip()
            if value:
                normalized_refs.append(value)
        return list(dict.fromkeys(normalized_refs))

    def extract_edit_image_prompt(
        self, message: str
    ) -> tuple[str | None, str | None]:
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
                    return candidate[len(prefix) :].strip(), prefix

        return None, None

    def clear_edit_image_state(self, state_key: str):
        USER_STATES.pop(state_key, None)
        USER_IMAGE_FILES.pop(state_key, None)
        USER_LAST_IMAGES.pop(state_key, None)

    def get_editimage_dir(self) -> str:
        return str(self.image_cfg.get("editimage_dir", "")).strip()

    def get_edit_image_state_key(self, event: AstrMessageEvent) -> str:
        session_id = event.get_session_id().strip()
        if session_id:
            return session_id
        sender_id = event.get_sender_id().strip()
        if sender_id:
            return sender_id
        return "default"

    async def expire_edit_image_state(
        self, event: AstrMessageEvent, state_key: str, timestamp: float
    ):
        await asyncio.sleep(30)
        if USER_STATES.get(state_key) != timestamp:
            return

        self.clear_edit_image_state(state_key)
        await event.send(event.plain_result("图生图已取消，请重新上传图片后再试。"))

    async def process_edit_image_prompt(self, event: AstrMessageEvent, prompt: str):
        state_key = self.get_edit_image_state_key(event)
        if state_key not in USER_STATES:
            return

        if not self.get_editimage_dir():
            self.clear_edit_image_state(state_key)
            yield event.plain_result(
                "未配置 image_config.editimage_dir，请先在插件配置中设置图像保存目录。"
            )
            event.stop_event()
            return

        if not prompt:
            yield event.plain_result(
                "请输入图像编辑指令，例如：图生图 把背景改成海边。"
            )
            event.stop_event()
            return

        image_file = USER_LAST_IMAGES.get(state_key)
        if not image_file:
            self.clear_edit_image_state(state_key)
            yield event.plain_result("未找到待处理的图片，请重新上传图片后再试。")
            event.stop_event()
            return

        print("收到图生图指令:", prompt)

        chain, image_paths = edit_image_with_openai(self.image_cfg, image_file, prompt)
        print("图生图生成完成:", image_paths)
        if image_paths:
            USER_LAST_IMAGES[state_key] = image_paths[0]

        self.clear_edit_image_state(state_key)
        yield event.chain_result(cast(list[BaseMessageComponent], chain))
        event.stop_event()

    async def render_common_image(self, event: AstrMessageEvent, prompt: str):
        image_cfg = dict(self.image_cfg)
        api_type = str(image_cfg.get("api_type", "image")).strip().lower() or "image"
        if api_type not in {"chat", "image"}:
            yield event.plain_result(
                "image_config.api_type 配置错误，请填写 chat 或 image"
            )
            return

        image_cfg["api_type"] = api_type
        chain = cast(
            list[BaseMessageComponent],
            common_image(image_cfg, "通用画图", prompt, False),
        )
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
    async def my_custom_hook_1(
        self, event: AstrMessageEvent, req: ProviderRequest
    ):  # 请注意有三个参数
        # print("收到LLM请求时", req.system_prompt) # 打印请求的文本
        print("收到LLM请求时")
        pass
        # req.system_prompt += "自定义 system_prompt"

    # 发送消息给消息平台适配器前
    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        print("发送消息给消息平台适配器前")  # 打印消息链   , event.get_result()
        pass

    # 发送消息给消息平台适配器后
    @filter.after_message_sent()
    async def after_message_sent(self, event: AstrMessageEvent):
        print("发送消息给消息平台适配器后")
        pass

    # LLM请求完成时
    @filter.on_llm_response()
    async def on_llm_resp(
        self, event: AstrMessageEvent, resp: LLMResponse
    ):  # 请注意有三个参数
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

        record = DbRecord(
            0, "astrbot", model, "", username, nickname, update_time, prompt, content
        )
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
        music = Video.fromFileSystem(path="data/test.mp4")
        # 更通用
        # music = Video.fromURL(
        #     url="https://example.com/video.mp4"
        # )
        yield event.chain_result(cast(list[BaseMessageComponent], [music]))

    @filter.command("v")
    async def jimeng_generator_video(self, event: AstrMessageEvent, prompt: str = ""):
        """即梦视频生成 命令格式: /v 内容"""

        url = "http://read.tdkc.com.cn:8101/jimeng/generate_video/"

        payload = json.dumps(
            {
                "prompt": "小马过河",
                "aspect_ratio": "16:9",
                "duration_ms": 5000,
                "fps": 24,
            }
        )

        headers = {
            "Authorization": "Bearer Qweasd@12345",
            "Content-Type": "application/json",
        }


        response = requests.request("POST", url, headers=headers, data=payload)
        result = response.json()

        if result["code"] == 200:
            # video = Video.fromFileSystem(result['file_path'])
            video = Video.fromURL(result["video_url"])
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
    @filter.command("图生图")
    async def edit_image_command(self, event: AstrMessageEvent, prompt: str = ""):
        async for result in self.process_edit_image_prompt(event, prompt):
            yield result

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_image_edit_request(self, event: AstrMessageEvent):
        print("handle_image_edit_request")
        state_key = self.get_edit_image_state_key(event)

        image_refs = await self.collect_edit_image_refs(event)
        image_file = image_refs[0] if image_refs else ""

        if image_file:
            editimage_dir = self.get_editimage_dir()
            if not editimage_dir:
                yield event.plain_result(
                    "未配置 image_config.editimage_dir，请先在插件配置中设置图像保存目录。"
                )
                event.stop_event()
                return

            moved_image_file = move_image(image_file, editimage_dir)
            if not moved_image_file:
                yield event.plain_result(
                    "读取引用图片失败，请重新发送或重新引用图片后再试。"
                )
                event.stop_event()
                return

            moved_path = Path(str(moved_image_file).strip())
            if not moved_path.exists() or not moved_path.is_file():
                yield event.plain_result(
                    "读取引用图片失败，请重新发送或重新引用图片后再试。"
                )
                event.stop_event()
                return

            print("收到图像文件:", str(moved_path)[:100])
            timestamp = asyncio.get_running_loop().time()
            USER_STATES[state_key] = timestamp
            USER_IMAGE_FILES[state_key] = str(moved_path)
            USER_LAST_IMAGES[state_key] = str(moved_path)

            prefixes_text = " / ".join(self.get_edit_image_command_prefixes())
            yield event.plain_result(
                f"已收到图片，请在30秒内发送“前缀 处理命令”进行图生图，例如：{prefixes_text} 把背景改成海边。"
            )
            asyncio.create_task(
                self.expire_edit_image_state(event, state_key, timestamp)
            )
            event.stop_event()
            return

        prompt, prefix = self.extract_edit_image_prompt(event.message_str)
        print("提示词")
        print(prompt)
        if prefix is None:
            return

        print("开始执行 process_edit_image_prompt")
        async for result in self.process_edit_image_prompt(event, prompt or ""):
            yield result

    # ***************************************************************************************************
    # 临时模型切换
    # ***************************************************************************************************
    @command_group("my")
    def mysql(self):
        """
        这是一个 MySQL 指令组，取缩写my
        [查看帮助] /my help
        [查找内容] /my search [内容]
        [查看详情] /my detail id
        [收藏记录] /my save [临时id]
        [删除记录] /my delete [收藏id]
        [token记录] /my token [内容]
        [token添加] /my tadd 标题,基地址,api_key
        """
        pass

    @mysql.command("help")
    async def mysql_help(self, event: AstrMessageEvent):
        result = self.mysql_handler.dispatch("help", "")
        yield event.plain_result(f"{result}")

    @mysql.command("search")
    async def mysql_search(self, event: AstrMessageEvent, prompt: str = ""):
        result = self.mysql_handler.dispatch("search", prompt)
        yield event.plain_result(f"{result}")

    @mysql.command("detail")
    async def mysql_detail(self, event: AstrMessageEvent, prompt: str = ""):
        result = self.mysql_handler.dispatch("detail", prompt)
        yield event.plain_result(f"{result}")


    @mysql.command("save")
    async def mysql_save(self, event: AstrMessageEvent, prompt: str = ""):
        result = self.mysql_handler.dispatch("save", prompt, self.lastRecord)
        yield event.plain_result(f"{result}")

    @mysql.command("delete")
    async def mysql_delete(self, event: AstrMessageEvent, prompt: str = ""):
        result = self.mysql_handler.dispatch("delete", prompt)
        yield event.plain_result(f"{result}")

    @mysql.command("token")
    async def mysql_token(self, event: AstrMessageEvent, prompt: str = ""):
        result = self.mysql_handler.dispatch("token", prompt)
        yield event.plain_result(f"{result}")

    @mysql.command("tadd")
    async def mysql_tadd(self, event: AstrMessageEvent, prompt: str = ""):
        result = self.mysql_handler.dispatch("tadd", prompt)
        yield event.plain_result(f"{result}")

    @mysql.command("sa")
    async def mysql_sa(self, event: AstrMessageEvent, prompt: str = ""):
        result = self.mysql_handler.dispatch("sa", prompt)
        yield event.plain_result(f"{result}")

    # ***************************************************************************************************
    # 工具的处理部分
    # ***************************************************************************************************
    @command_group("t")
    def tools(self):
        """
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
        """
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
        if url is not None and len(url) > 0 and "http" in url:
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
        """这是一个 hello world 指令"""
        user_name = event.get_sender_name()
        message_str = event.message_str  # 用户发的纯文本消息字符串
        message_chain = (
            event.get_messages()
        )  # 用户所发的消息的消息链 # from astrbot.api.message_components import *
        logger.info(message_chain)
        yield event.plain_result(
            f"Hello, {user_name}, 你发了 {message_str}!"
        )  # 发送一条纯文本消息
