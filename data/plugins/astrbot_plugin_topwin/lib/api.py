import requests
from enum import Enum, auto
import json
import ast
from .util import generate_random_code, current_time
import re

# 地址常量记录
class URL(Enum):
    OPENAI_LIST = '/gpt/openai/list?pageSize=100'  # 获取Chatgpt openai的参数设置
    SHORT_CMDS = '/system/dict/data/list?dictType=gpt_short_cmds&pageSize=100'  # 获取微信命令缩写
    DICT_LABEL = '/system/dict/data/list?dictLabel={0}'  # 获取字典值+ ?
    TOKEN_LIST = '/gpt/token/list?pageSize=100'  # gpt token列表
    TOKEN_MODIFY = '/gpt/token'  # gpt token 添加,修改,删除, 分别method不同post,put,delete
    SIMPLE_ANALYSE_LIST = '/gpt/simple_analyse/list?pageSize=100'  # gpt simple_analyse列表
    SIMPLE_ANALYSE_MODIFY = '/gpt/simple_analyse'  # gpt simple_analyse 添加,修改,删除, 分别method不同post,put,delete
    SHORT_URL_LIST = '/gpt/short_url/list?code={0}&url={1}'  # 获取code和url对应的信息
    SHORT_URL_MODIFY = '/gpt/short_url'   # gpt short_url 添加,修改,删除, 分别method不同post,put,delete
    RECORD_TMP_MODIFY = '/gpt/record_tmp'   # gpt record_tmp 添加,修改,删除, 分别method不同post,put,delete
    RECORD_FAVORITE_LIST = '/gpt/record_favorite/list'  # gpt record_favorite列表
    RECORD_FAVORITE_LIST_PARAM = RECORD_FAVORITE_LIST + '?pageSize=100&prompt={0}'  # gpt record_favorite列表
    RECORD_FAVORITE_MODIFY = '/gpt/record_favorite'   # gpt record_favorite 添加,修改,删除, 分别method不同post,put,delete
    USER_EXTRA_LIST = '/gpt/user_extra/list?wechatUserId={0}'  # 获取wechat_user_id对应的信息
    USER_EXTRA_MODIFY = '/gpt/user_extra'  # gpt user_extra 添加,修改,删除, 分别method不同post,put,delete
    STOCK_GET_CODE = '/gpt/stock/get_code/{0}'  # 通过关键字获取代码
    STOCK_GET_RECORD = '/gpt/stock/get_record/{0}'  # 通过关键字获取记录列表
        
class API:

    def __init__(self, host, authorization):
        self.host = host
        self.authorization = authorization
    
    # 通过url地址获取json对象字典
    def get_json(self, api_url: URL, *args):
        url = api_url.value
        url = f"{self.host}{url}".format(*args)
        print(url)
        headers = {
            "accept": "*/*",
            # "Authorization": self.authorization
        }

        response = requests.get(url, headers=headers)
        return response.json()
    
    # 通过url地址获取json对象字典
    def modify(self, api_url: URL, data, method='post'):
        url = api_url.value
        url = f"{self.host}{url}"

        headers = {'Content-Type': 'application/json'}
        if method == 'post':  # 添加操作
            response = requests.post(url, json=data, headers=headers)
        elif method == 'put': # 更新操作
            response = requests.put(url, json=data, headers=headers)
        elif method == 'delete':  # 删除操作
            response = requests.delete(url, json=data, headers=headers)
        
        result = json.loads(response.text)
        id = ""
        # 如果成功,获取最后一个记录的id
        if(result['code'] == 200):
            list_url = f"{url}/list?orderByColumn=id&isAsc=desc&limit=1"
            response = requests.get(list_url, headers={"accept": "*/*"})
            ret = response.json()
            if ret['total'] > 0:
                record = ret['rows'][0]
                id = record['id']
        return id
    
    def get_detail(self, api_list_url: URL, id):
        url = api_list_url.value
        url = f"{self.host}{url}/{id}"
        print(url)
        response = requests.get(url, headers={"accept": "*/*"})
        ret = response.json()
        print(ret)
        if ret['code'] == 200:
            return ret['data']
        else:
            return None
                
    # 获取openai相关参数
    def get_openai(self):
        res = self.get_json(URL.OPENAI_LIST)
        data = res['rows']
        
        filtered_dict = {}
        for item in data:
            if item['isUse'] == 1:
                prefix = item['prefix']
                filtered_dict[prefix] = {
                    'api_base': item['apiBase'],
                    'api_key': item['apiKey'],
                    'model': item['model'],
                    'text_to_image': item['textToImage'],
                    'voice_to_text': item['voiceToText']
                }
                # 对gpts的特殊处理
                if(prefix == "gpts"):
                    remark = item['remark'].replace("\n","")
                    data_dict = json.loads("{" + remark + "}")

                    a = filtered_dict[prefix]
                    new_dict = {**a, **data_dict}
                    filtered_dict[prefix] = new_dict
        
        return filtered_dict
    
    # 获取字典键对应的值
    def get_dict_value(self, dict_label, is_remark = False, use_ast = False):
        res = self.get_json(URL.DICT_LABEL, dict_label)
        if res['total'] > 0:
            record = res['rows'][0]
            value = record['dictValue']
            if is_remark:
                value = record['remark']
            if use_ast:
                value = ast.literal_eval(value)
                
            return value
        else:
            return None
    
    # 获取微信命令缩写
    def get_short_cmds(self):
        res = self.get_json(URL.SHORT_CMDS)
        data = res['rows']
        
        # 按dictValue字段排序
        data = sorted(data, key=lambda x: x['dictValue'])
        
        filtered_dict = {}
        for item in data:
            if item['status'] == '0':  # status='0'表示正常
                key = item['dictLabel']
                value = item['dictValue']
                filtered_dict[key] = value
        
        return filtered_dict
    
    # 获取gpt token
    def get_token(self, keyword):
        res = self.get_json(URL.TOKEN_LIST)
        data = res['rows']
        
        filtered_list = []
        for item in data:
            title = item['title']
            base_url = item['baseUrl']
            api_key = item['apiKey']
            
            if (len(keyword) == 0) or (len(keyword) > 0 and (keyword in title or keyword in base_url or keyword in api_key)):
                filtered_list.append(item)
            
        return filtered_list
    
    # 获取simple analyse注册码
    def get_simple_analyse(self, keyword):
        res = self.get_json(URL.SIMPLE_ANALYSE_LIST)
        data = res['rows']
        
        filtered_list = []
        for item in data:
            name = item['name']
            mac_code = item['macCode']
            
            if (len(keyword) == 0) or (len(keyword) > 0 and (keyword in name or keyword in mac_code)):
                filtered_list.append(item)
            
        return filtered_list
    
    # 通过code获取short url
    def get_short_url(self, code, url):
        res = self.get_json(URL.SHORT_URL_LIST, code, url)
        if res['total'] > 0:
            record = res['rows'][0]
            return record
        else:
            return None
        
    # 通过keyword搜索record_favorite
    def get_favorite_records(self, keyword):
        res = self.get_json(URL.RECORD_FAVORITE_LIST_PARAM,keyword)
        if res['total'] > 0:
            records = res['rows']
            return records
        else:
            return None
        
    # 通过wechat_user_id获取user_extra
    def get_user_extra(self, wechatUserId):
        res = self.get_json(URL.USER_EXTRA_LIST, wechatUserId)
        if res['total'] > 0:
            record = res['rows'][0]
            return record
        else:
            return None
        
    # 通过keyword搜索证券代码
    def get_stock_code(self, keyword):
        res = self.get_json(URL.STOCK_GET_CODE,keyword)
        return res['msg']
    
    # 通过keyword搜索证券记录列表
    def get_stock_record(self, keyword):
        res = self.get_json(URL.STOCK_GET_RECORD,keyword)
        print(res)
        return res['data']
    
    # 将地址转换为短连接地址
    def goto_short_url(self, url, title = ""):
        # 2025.02.09 增加判断如果地址不长，则使用原始地址
        if len(url) <= 30:
            return url
        
        code = generate_random_code()
        record = self.get_short_url("", url)
        if(record is not None):
            code = record['code']
        else:
            data = {'title': title, 'code': code, 'url':url}
            self.modify(URL.SHORT_URL_MODIFY, data)
            
        # return f"http://s.net11.cn/s?c={code}"
        return f"http://s.net11.cn/s/{code}"
    
    def replace_urls_with_placeholder(self, text):
        # 定义 URL 匹配的正则表达式模式
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        # 使用正则表达式找到所有匹配的 URL 地址
        urls = re.findall(url_pattern, text)
        # 将找到的 URL 地址替换为指定的占位符
        for url in urls:
            placeholder = self.goto_short_url(url)
            text = text.replace(url, placeholder)
        return text