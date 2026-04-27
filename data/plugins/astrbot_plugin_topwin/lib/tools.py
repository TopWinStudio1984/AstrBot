# from lib import itchat
import requests
import json
from .api import API
from .util import parse_rss
import feedparser
from datetime import datetime
import re
from yahoo_fin.stock_info import tickers_dow
import math

class Tools():

    def __init__(self, mmapi_cfg = None):
        if mmapi_cfg is None:
            print("未配置MMAPI相关信息")
            return 
        
        host = mmapi_cfg['host']
        authorization = mmapi_cfg['authorization']
        self.api = API(host, authorization)
        self.rss_base = mmapi_cfg['rss_base']

        self.pearktrue_api = 'https://api.pearktrue.cn/api'
    
    def help(self):
        help_content = "tools命令用法\n" \
            "[翻译]                  命令格式: tools 翻译 内容\n" \
            "[菜谱]                  命令格式: tools 菜谱 内容\n" \
            "[音乐]                  命令格式: tools 音乐 内容\n" \
            "[单词]                  命令格式: tools 单词 内容\n" \
            "[Linux]                  命令格式: tools linux 命令\n" \
            "[科技]                  命令格式: tools 科技\n" \
            "[60s图]                  命令格式: tools 60s [day/baidu/weibo]\n" \
            "[新闻]                  命令格式: tools news [数字]\n" \
            "[老赖]                  命令格式: tools laolai 姓名\n" \
            "[天气]                  命令格式: tools 天气 地区\n" \
            "[词语字典]                  命令格式: tools 词典 内容\n" \
            "[古诗]                  命令格式: tools 古诗 内容\n" \
            "[高校]                  命令格式: tools 高校 内容\n" \
            "[RSS]                  命令格式: tools rss 内容\n" \
            "[计算缸径]              命令格式: tools 缸径 kN值,MPa值,立柱个数\n" 
        return help_content

    def dispatch(self, tools_type, prompt, param):
        tools = tools_type
        content = prompt
        param = param

        if(tools == "翻译"):
            return self.translate(content)
        elif(tools == "菜谱"):
            return self.cookbook(content)
        elif(tools.startswith("音乐")):
            return self.music(tools, content)
        elif(tools == "单词"):
            return self.word(content)
        elif(tools == "linux"):
            return self.linux(content)
        elif(tools == "科技"):
            return self.science(content)
        elif(tools == "60s"):
            return self.SixtyS(content)
        elif(tools == "news"):
            return self.news(content)
        elif(tools == "laolai"):
            return self.laolai(content)
        elif(tools == "天气"):
            return self.weather(content)
        elif(tools == "词典"):
            return self.dictionary(content)
        elif(tools == "古诗"):
            return self.poetry(content)
        elif(tools == "高校"):
            return self.school(content)
        elif(tools == "rss"):
            return self.read_rss(content, param)
        elif(tools == "缸径"):
            return self.calc_radius(content)
    
    def calc_radius(self, content):
        # kN值,MPa值,立柱个数
        arr = content.split(',')
        if len(arr) != 3:
            # itchat.send("格式不正确,命令格式: tools 缸径 kN值,MPa值,立柱个数!", toUserName=self.username)
            return
    
        kN,MPa,pole = 0,2,0
        try:
            kN = float(arr[0])
            MPa = float(arr[1])
            pole = float(arr[2])
        except Exception as ex:
            return "格式不正确,命令格式: tools 缸径 kN值,MPa值,立柱个数!"
        
        radius = round(math.sqrt(kN * math.pow(10,3) / (MPa * math.pow(10, 6)) / 3.14 / pole) * 1000)
        return f"计算缸径值: {radius}"
        
    def sdad(self, short):
        dow_tickers = tickers_dow()

    # 通用根据索引调用对应的rss地址函数,地址列表,数字
    def decode_rss_route(self, base_url, route, content):
        invalid = False
        # category = ['kx', 'yw', 'gs', 'company','data','gsxw','gsdt','zj']
        try:
            content = int(content)
            invalid = content < 1 or content > len(route)
        except:
            invalid = True
            
        if invalid:
            self.read_rss("")
            return
        
        rss_url = f"{base_url}{route[content - 1]}"
        self.decode_rss_url(rss_url)

    # 通用根据数据调用rss地址的函数,分类列表,数字
    def decode_rss_category(self, base_url, category, content):
        invalid = False
        # category = ['kx', 'yw', 'gs', 'company','data','gsxw','gsdt','zj']
        try:
            content = int(content)
            invalid = content < 1 or content > len(category)
        except:
            invalid = True
            
        if invalid:
            self.read_rss("")
            return
        
        rss_url = f"{base_url}{category[content - 1]}"
        return self.decode_rss_url(rss_url)
    
    # 通过rss_url地址解析内容
    def decode_rss_url(self, rss_url):
        # 2024.05.11 自定义函数
        entries = parse_rss(rss_url)
        if entries is None:
            # itchat.send(f"解析rss地址超时,[ {rss_url} ]", toUserName=self.username)
            return

        # feed = feedparser.parse(rss_url)
        # entries = feed.entries

        content = ""
        # print(entries)
        for entry in entries:
            title = entry['title'] # 如果采用feedparser，则使用entry.title
            title = re.sub(r'<em>(.*?)</em>', r'\1', title)
            link = entry['link']
            link = self.api.replace_urls_with_placeholder(link)
            desc = entry['description']
            
            datetime_object = datetime.strptime(entry['published'], '%a, %d %b %Y %H:%M:%S %Z')
            formatted_date = datetime_object.strftime('%Y-%m-%d %H:%M:%S')
            pubtime = formatted_date
            content += f"[ {pubtime} ] {title} {link}\n"
        return content
    
    #  读取rss
    def read_rss(self, cmd, param):
        print("read_rss", cmd, param)
        if(len(param) == 0):
            # https://docs.rsshub.app/zh/routes/new-media#%E9%87%8F%E5%AD%90%E4%BD%8D
            content = self.api.get_dict_value("help_content_tools", True)
            return content
        content  = param
        
        result = ""
        if cmd == "1":
            # 东方财富搜索
            result = self.decode_rss_url(f"{self.rss_base}/eastmoney/search/{content}")
        elif cmd == "2":
            # 报告研究
            category = ['strategyreport', 'macresearch', 'brokerreport', 'industry']
            result = self.decode_rss_category(f"{self.rss_base}/eastmoney/report/", category, content)
        elif cmd == "3":
            # 法布财经
            category = ['express-news', 'news']
            result = self.decode_rss_category(f"{self.rss_base}/fastbull/", category, content)
        elif cmd == "4":
            # 证券时报网
            category = ['kx', 'yw', 'gs', 'company','data','gsxw','gsdt','zj']
            result = self.decode_rss_category(f"{self.rss_base}/stcn/", category, content)
        elif cmd == "5":
            # 雪球股票评论
            result = self.decode_rss_url(f"{self.rss_base}/xueqiu/stock_comments/{content}")
        elif cmd == "6":
            # 量子位
            category = ['资讯', 'ebandeng', 'auto', 'zhiku', 'huodong']
            if content.isdigit():
                result = self.decode_rss_category(f"{self.rss_base}/qbitai/category/", category, content)
            else:
                result = self.decode_rss_url(f"{self.rss_base}/qbitai/tag/{content}")
        elif cmd == "7":
            # 36kr资讯热榜
            category = ['24', 'renqi', 'zonghe', 'shoucang']
            result = self.decode_rss_category(f"{self.rss_base}/36kr/hot-list/", category, content)
        elif cmd == "8":
            # 36kr分类资讯
            category = ['news', 'newsflashes', 'recommend', 'life', 'estate', 'workplace']
            if content.isdigit():
                result = self.decode_rss_category(f"{self.rss_base}/36kr/", category, content)
            else:
                result = self.decode_rss_url(f"{self.rss_base}/36kr/search/articles/{content}")
        elif cmd == "9":
            # 华尔街见闻实时快讯
            category = ['global', 'a-stock', 'us-stock', 'hk-stock', 'forex', 'commodity', 'financing']
            if content.isdigit():
                result = self.decode_rss_category(f"{self.rss_base}/wallstreetcn/live/", category, content)
            else:
                result = self.decode_rss_url(f"{self.rss_base}/wallstreetcn/hot/{content}")
        elif cmd == "10":
            # 地产专栏
            route = ['/china/finance/dichan', '/yicai/news/loushi', '/thepaper/list/25433', '/cls/depth/1006', '/36kr/estate']
            result = self.decode_rss_category(f"{self.rss_base}", route, content)
        
        return result
        
    # 单个变量格式化默认%s, head表示回复内容的头部行
    def common_api(self, content, path, fields, head = "", format = '%s', has_index = False):
        try:
            response = requests.get(f'{self.pearktrue_api}{path}', timeout=5)
        except requests.exceptions.Timeout:
            return f"[ {path} ]请求超时,请稍后重试"
        except requests.exceptions.RequestException as e:
            return f"[ {path} ]请求出错：{e}"

        result = json.loads(response.text)
        print(result)
        if(int(result['code']) == 200):
            if('data' in result.keys()):
                data = result['data']
            else:
                data = result
                
            # 头部内容
            if len(head) > 0:
                if(head == "update"):
                    update = result['update']
                    content = f"更新时间: {update}\n"
                else:
                    content = f"【{content}】{head}：\n"
            
            # 如果对象是一个字典,则取值
            if isinstance(data, dict):
                values = []
                for x in fields:
                    v = self.api.replace_urls_with_placeholder(data[x])
                    values.append(v)
                values = tuple(values)
                # values = tuple([data[x] for x in fields])
                content = format % values
            else:
                # 如果对象是一个列表
                if has_index:
                    format = '[ %s ] ' + format
                        
                for i in range(len(data)):
                    d = data[i]
                    values = []
                    for x in fields:
                        # 如果字段中含有#,则进行分割，并截取后部num个字节
                        arr = x.split('#')
                        if(len(arr) > 1):
                            x = arr[0]
                            values.append(d[x][-int(arr[1]):])
                        else:
                            values.append(d[x])
                    
                    tmp_values = []
                    for v in values:
                        v = self.api.replace_urls_with_placeholder(v)
                        tmp_values.append(v)
                        
                    values = tuple(tmp_values)
                    # values = tuple([d[x] for x in fields])
                    # 如果需要显示索引
                    if has_index:
                        values = (i + 1,) + values
                
                    content += format % values
            
            return content
            # itchat.send(content, toUserName=self.username)
        else:
            # itchat.send(result['msg'], toUserName=self.username)
            return result['msg']
    
    # 全国高校查询
    def school(self, content):
        format = '[ %s %s ] [ %s ] %s %s %s\n'
        fields = ['level', 'remark', 'city', 'name', 'department', 'code']
        return self.common_api(content, f'/college/?keyword={content}', fields, "包含的相关高校如下", format)
        
    # 全诗古诗文检索
    def poetry(self, content):
        format = '[ %s ] %s.%s\n%s\n\n'
        fields = ['title', 'author', 'dynasty', 'content']
        return self.common_api(content, f'/shiwen/?keyword={content}', fields, "包含的相关古诗如下", format)
                 
    # 词典查询
    def dictionary(self, content):
        return self.common_api(content, f'/word/mean.php?word={content}', ['mean'])
            
    # 天气查询
    def weather(self, content):
        format = '[ %s ] %s %s %s %s 空气质量:%s\n'
        fields = ['date', 'weather', 'temperature', 'wind', 'wind_level', 'air_quality']
        return self.common_api(content, f'/weather/?city={content}&id=1', fields, "天气信息如下", format)
            
    # 老赖查询
    def laolai(self, content):
        format = '%s %s %s\n'
        fields = ['province', 'profile', 'idcard']
        return self.common_api(content, f'/laolai/?name={content}', fields, "姓名的老赖信息如下", format, True)
            
    # 查看各大榜单的今日热榜排行
    def news(self, content):
        # 哔哩哔哩，百度，知乎，百度贴吧，少数派，IT之家，澎湃新闻，今日头条，微博热搜，36氪，稀土掘金，腾讯新闻
        names = '哔哩哔哩,百度,知乎,百度贴吧,少数派,IT之家,澎湃新闻,今日头条,微博热搜,36氪,稀土掘金,腾讯新闻'
        if(len(content) == 0):
            arr = names.split(",")
            for i in range(len(arr)):
                content += f"[ {i + 1} ] {arr[i]}       "
            return content
        else:
            try:
                content = int(content)
                arr = names.split(",")
                for i in range(len(arr)):
                    if(i + 1 == content):
                        content = arr[i]
            except Exception as ex:
                # print(ex)
                print(f"发生错误.{ex}")
            
            return self.common_api(content, f"/dailyhot/?title={content}", ['title','url'], "信息如下", '%s %s\n', True)
    
    # 图片新闻 PearAI独家
    def SixtyS(self, content):
        if(content == "day"):
            # 每日60s图
            return "https://api.pearktrue.cn/api/60s/image/"
        elif(content == "baidu"):
            # 每日60s热榜(百度)
            return "https://api.pearktrue.cn/api/60s/image/hot/?type=baidu"
        elif(content == "weibo"):
            # 每日60s热榜(微博)
            return "https://api.pearktrue.cn/api/60s/image/hot/?type=weibo"
        
        return None
        
    # 实时科技资讯
    def science(self, content):
        return self.common_api(content, "/sciencenews/", ['time#5', 'title'], "update", "[ %s ] %s\n", True)

    #  Linux命令查询
    def linux(self, content):
        return self.common_api(content, f'/linux/?keyword={content}', ['linux','content','link'], "", '[ %s ] [ %s ] %s')

    #  单词
    def word(self, content):
        return self.common_api(content, f'/word/english/parse.php?word={content}', ['definition'])

    # 音乐全能聚合(查询结果只有一条，效果不是太好)
    def music_bak(self, tools, content):
        # 聚合音乐全能解析 https://api.pearktrue.cn/info?id=118
        response = requests.get(f'{self.pearktrue_api}/music/wanneng.php', {'num': 5, 'name': content})
        result = json.loads(response.text)
        # 非常诡异，这里的代码是字符串200
        if(result['code'] == 200):
            data = result['data']
            # print(data)
            # for i in range(len(data)):
            content = f"【{content}】搜索结果：\n"
            d = data
            i = 0
            if len(d['music_link']) > 0:
                content += f"[ {i + 1} ] [{d['songname']}] [{d['music_link']}]\n"
                content += f"\n【歌词】\n{d['lrcs']} \n"
            # itchat.send(content, toUserName=self.username)
        else:
            # itchat.send(result['msg'], toUserName=self.username)
            pass
            
    # 音乐聚合
    def music(self, tools, content):
        # 聚合音乐解析 https://api.pearktrue.cn/info?id=45
        # netease,qq,kugou,kuwo
        # page 页数(1页等于10首,不填默认1页)
        music_type = 'netease'
        if tools == "音乐" or tools == "音乐1":
            music_type = 'netease'
        elif tools == "音乐2":
            music_type = 'qq'
        elif tools == "音乐3":
            music_type = 'kugou'
        elif tools == "音乐4":
            music_type = 'kuwo'

        format = "[%s - %s] [%s]\n"
        fields = ['author', 'title', 'playurl']
        head = "支持平台: [音乐/音乐1]netease,[音乐2]qq,[音乐3]kugou,[音乐4]kuwo"
        return self.common_api(content, f'/music/search.php?type={music_type}&name={content}', fields, head, format, True)

    # 翻译
    def translate(self, content):
        # 万能翻译，支持各种语言
        return self.common_api(content, f'/translate/?type=auto&text={content}', ['translate'], "")

        # google 翻译，只支持中英文
        # self.common_api(content, f'/googletranslate/?type=auto&text={content}', ['result'], "")

       
    
    # 菜谱,结构有点复杂,先不使用通用解析方法
    def cookbook(self, content):
        response = requests.get(f'{self.pearktrue_api}/cookbook/', {'search': content})
        result = json.loads(response.text)
        if(result['code'] == 200):
            records = result['data']
            content = ""
            for r in records:
                tmp = r['practice']
                practice = ""
                for i in range(len(tmp)):
                    practice += f"({i + 1}) {tmp[i]}\n"
                    
                content += f"【名称】: {r['name']} \n【照片】: \n {r['image']} \n【材料】: \n {r['materials'][0]}\n【步骤】: \n {practice}"
                content += "\n"
                
        return content