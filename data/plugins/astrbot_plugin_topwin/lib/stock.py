import requests
import json
from .api import API
from cryptography.fernet import Fernet # type: ignore
from .util import timestamp_to_time, current_time,format_gpts_key
import urllib.parse
from bs4 import BeautifulSoup # type: ignore
import time
import html
import re
import akshare as ak
import pandas as pd
import plotly.express as px
from astrbot.api.message_components import *

class Stock:

    def __init__(self, mmapi_cfg = None):
        if mmapi_cfg is None:
            print("未配置MMAPI相关信息")
            return 
        
        host = mmapi_cfg['host']
        authorization = mmapi_cfg['authorization']
        self.api = API(host, authorization)
        
        self.update_cmds = {
            "stock_info_sh": "股票列表-上证",
            "stock_info_sz": "股票列表- 深证",
            "stock_zh_a_hist": "历史行情数据-东财"
        }

    def help(self):
        help_content = self.api.get_dict_value("help_content_stock", True)
        return help_content    

    def update_help(self):
        content = format_gpts_key(self.update_cmds, 3, True)
        return content

    def dispatch(self, type, prompt):
        stock = type
        content = prompt
    
        if(stock == "news"):
            return self.news(content)
        elif(stock == "help"):
            return self.help()
        elif(stock == "update"):  # 2025.02.09 暂时未迁移
            return self.update(content)
        elif(stock == "stat"):
            return self.stat(content)
        elif(stock == "search"):
            return self.search(content)
        elif(stock == "t"):
            return self.recommended(content)
        elif(stock == "cm"):
            return self.chip_distribution(content)

    # 统计信息
    def stat(self, content):
        invalid = False
        try:
            content = int(content)
            invalid = content <1 or content > 2
        except:
            invalid = True
            
        if invalid:
            return "数字索引不正确,范围[1-9]!"
        
        if content == 1:
            df = ak.stock_sse_summary()

        return df.to_string(index=False)

    # 筹码分布
    def chip_distribution(self, keyword):
        keyword = self.api.get_stock_code(keyword)
        df = ak.stock_cyq_em(symbol=keyword, adjust="")

        # 选择要绘制直方图的数据列
        columns_to_plot = ['获利比例', '平均成本', '90成本-低', '90成本-高', '70成本-低', '70成本-高']

        # 将选中的列合并成一个长列
        df_long = df.melt(value_vars=columns_to_plot, var_name='指标', value_name='值')

        # 创建直方图
        fig = px.histogram(df_long, x='值', color='指标', title=f'{keyword} 筹码分布直方图')

        # 更新布局
        fig.update_layout(
            xaxis_title_text='值',
            yaxis_title_text='频率',
            bargap=0.1,  # 直方柱之间的间距
            bargroupgap=0.1  # 直方柱组之间的间距
        )
        
        # 保存直方图到本地文件
        file_path = f'筹码分布直方图.png'
        fig.write_image(file_path)
        chain = [Image.fromFileSystem(file_path), Plain(df.to_string(index=False))]
        return chain

    # 机构推荐池
    def recommended(self, content):
        invalid = False
        category = ['最新投资评级', '上调评级股票', '下调评级股票', '股票综合评级', '首次评级股票', '目标涨幅排名', '机构关注度', '行业关注度', '投资评级选股']
        try:
            content = int(content)
            invalid = content <1 or content > 9
        except:
            invalid = True
            
        if invalid:
            return "数字索引不正确,范围[1-9]!"
        symbol = category[content - 1]
        df = ak.stock_institute_recommend(symbol=symbol)
        df = df.head(20)
        return df.to_string(index=False)

    # 通过关键字或者首字母搜索
    def search(self, content):
        if len(content) == 0:
            return f"搜索内容为空,命令格式为：[ stock search 内容]!"
        
        records = self.api.get_stock_record(content)

        content = "股票列表:\n"
        content += "股票代码 简称   上市时间    总股本  流通股本    拼音缩写\n"    
        for r in records:
            content += f"[ {r['股票代码']} ] {r['股票简称']} {r['上市日期']} {r['总股本']} {r['流通股本']} {r['拼音缩写'].upper()}\n"

        return content

    # 查看指定个股的新闻
    def news(self, keyword):
        code = self.api.get_stock_code(keyword)
        df = ak.stock_news_em(symbol=code)

        df['发布时间'] = pd.to_datetime(df['发布时间'])
        df_sorted = df.sort_values(by='发布时间', ascending=False)
        top_record = df_sorted.head(10)

        content = ""
        for index, row in top_record.iterrows():
            content += f"[ {row['发布时间']} ]  {row['新闻标题']} {self.api.goto_short_url(row['新闻链接'])}\n"

        if(len(content) > 0):
            return content
        else:
            return f"没有找到[ {keyword} ]相关的新闻!"
        
    # 更新数据库数据
    def update(self, content):
        # if len(content) == 0:
        #     self.update_help()
        #     return
        
        # other = ""
        # # 如果content是数字,则按索引处理
        # try:
        #     arr = content.split(" ")
        #     if len(arr) > 1:
        #         other = content[len(arr[0]):].strip()
        #         content = arr[0]
                
        #     cur_index = int(content)

        #     index = 1
        #     currentKey = ""
        #     for k, v in self.update_cmds.items():
        #         if(cur_index == index):
        #             currentKey = k
        #             break
        #         index += 1

        #     if len(currentKey) == 0:
        #         return f"所选择模型的索引数字不存在: [ {cur_index} ],输入key查看列表!"

        #     content = currentKey
        # except:
        #     pass

        # # 判断更新的操作是否在命令列表当中    
        # if content not in self.update_cmds.keys():
        #     return f"没有找到[ {content} ]的相关更新操作!"
        
        # if content == "stock_info_sh":
        #     st.stock_info_sh()
        # elif content == "stock_info_sz":
        #     st.stock_info_sz()
        # elif content == 'stock_zh_a_hist':
        #     if len(other) == 0:
        #         return f"更新历史数据需要指定号码,命令格式:[ stock update stock_zh_a_hist code]!"
            
        #     code = other
        #     code = self.api.get_stock_code(code)
        #     st.stock_zh_a_hist(code)

        # return f"[ {content} ]的相关更新操作完成!"
        pass