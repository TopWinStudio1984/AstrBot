# from lib import itchat
from .object import Suno, Record
from .api import API,URL
from .util import current_time, remove_emoji
import re

class MySQL:

    def __init__(self, mmapi_cfg = None):
        self.recordIds = []

        if mmapi_cfg is None:
            print("未配置MMAPI相关信息")
            return 
        
        host = mmapi_cfg['host']
        authorization = mmapi_cfg['authorization']
        self.api = API(host, authorization)
        
    def help(self):
        help_content = self.api.get_dict_value("help_content_mysql", True)
        return help_content
    
    # lastRecord记录最后一次记录的记录
    def dispatch(self, type, prompt, lastRecord = None):
        cmd = type
        content = prompt

        if(cmd == "help"):
            # 命令帮助文件
            return self.help()
        elif(cmd.startswith('save')):
            # 收藏最后一条或者指定id的gpt记录
            return self.saveFavorite(content, lastRecord)
        elif(cmd.startswith('search')):
            # 收藏最后一条或者指定id的gpt记录
            return self.search(content)
        elif(cmd.startswith('detail')):
            # 查看指定id的gpt记录
            return self.detail(content)
        elif(cmd.startswith('delete')):
            # 删除指定id的gpt记录
            return self.delete(content)
        elif(cmd.startswith('saadd')):
            # 添加SimpleAnalyse记录
            return self.simple_analyse_add(content)
        elif(cmd.startswith('sa')):
            # 查询SimpleAnalyse记录
            return self.simple_analyse(content)
        elif(cmd.startswith('token')):
            # 查询GPT token记录
            return self.gpt_token(content)
        elif(cmd.startswith('tadd')):
            # 添加GPT token记录
            return self.gpt_token_add(content)
            
    # 查询SimpleAnalyse记录
    def simple_analyse(self, content):
        # if len(content) == 0:
        #     strSQL = f"select * from simple_analyse order by reg_date desc"
        # else:
        #     strSQL = f"select * from simple_analyse where name like '%{content}%' or mac_code like '%{content}%' order by reg_date desc"
        # records = db.fetch_all(strSQL)
        records = self.api.get_simple_analyse(content)
        content = ""
        for r in records:
            content += f"[ {r['id']} ] {r['dept']} {r['name']} {r['regDate']} {r['macCode']} {r['regCode']} {r['regDuration']}\n"
            # content += f"[ {r['id']} ] {r['dept']} {r['name']} {r['reg_date']} {r['mac_code']} {r['reg_code']} {r['reg_duration']}\n"

        return content
    
    # 添加SimpleAnalyse记录
    def simple_analyse_add(self, content):
        arr = content.split(",")
        if len(arr) != 6:
            # itchat.send("内容格式不正确,正确格式为[mysql saadd 部门,姓名,注册时间,机器码,注册码,时长]", toUserName=self.username)
            return
        
        name = arr[1]
        # strSQL = f"insert into simple_analyse (部门,姓名,注册时间,机器码,注册码,注册时长) values ('{arr[0]}','{arr[1]}','{arr[2]}','{arr[3]}','{arr[4]}','{arr[5]}')"
        # db.execute(strSQL)
        data = {'dept': arr[0], 'name': arr[1], 'regDate': arr[2], 'macCode': arr[3],'regCode': arr[4], 'regDuration': arr[5]}
        self.api.modify(URL.SIMPLE_ANALYSE_MODIFY, data)

        self.simple_analyse(name)

    # 删除问答记录
    def delete(self, content):
        # # 修改成根据id删除
        # id = 0
        # try:
        #     id = int(content)
        # except Exception as ex:
        #     return "命令错误,正确格式为/m delete [数据库id]!"
        
        # try:
        #     strSQL = f"delete from gpt_record_favorite where id={id}"
        #     record = db.execute(strSQL)
        # except Exception as ex:
        #     return f"删除收藏记录失败,{ex}!"
        
        # return f"删除 id = {id}的记录成功!"
        pass


    # 查询问答详情
    def detail(self, content):
        index = 0
        try:
            index = int(content)
        except Exception as ex:
            return "命令错误,请采用mysql detail [index数字]进行查看!"
        
        print(index, len(self.recordIds))
        if(index < 1 or index > len(self.recordIds)):
            return "索引不存在,请采用mysql detail [index数字]进行查看!"
        
        id = self.recordIds[index - 1]
        # strSQL = f"select * from favorite_record where id={id}"
        # record = db.fetch_one(strSQL)
        record  = self.api.get_detail(URL.RECORD_FAVORITE_MODIFY, id)
        if record is None:
            return f"没有找到对应id={id}的记录!"

        prompt = record.get('prompt', '')
        reply = record.get('reply', '')
        content = f"【 {prompt} 】\n{reply} [ {id} ] 链接地址: http://s.net11.cn/db/{id}"
        return content

    # 查询问答内容
    def search(self, content):
        # if len(content) == 0:
        #     strSQL = f"select * from favorite_record order by create_time desc limit 50"
        # else:
        #     strSQL = f"select * from favorite_record where (prompt like '%{content}%' or reply like '%{content}%') order by create_time desc limit 50"

        # records = db.fetch_all(strSQL)
        records = self.api.get_favorite_records(content)
        if(records == None or len(records) == 0):
            return f"没有相关的搜索记录!"
        
        content = ""
        index = 0
        self.recordIds.clear()
        for r in records:
            content += f"[ {index+1:02d} ] [{r['createTime']}] {r['prompt']} http://s.net11.cn/db/{r['id']} \n"
            # content += f"[ {index+1:02d} ] [{r['create_time']}] {r['prompt']} http://s.net11.cn/db/{r['id']} \n"
            self.recordIds.append(r['id'])
            index += 1

        return content

    # 查询GPT token记录
    def gpt_token(self, content):
        # if len(content) == 0:
        #     strSQL = f"select * from gpt_token order by create_time desc limit 50"
        # else:
        #     strSQL = f"select * from gpt_token where (title like '%{content}%' or base_url like '%{content}%' or api_key like '%{content}%') order by create_time desc limit 50"

        # records = db.fetch_all(strSQL)
        records = self.api.get_token(content)
        if(records == None or len(records) == 0):
            # itchat.send(f"没有相关的搜索记录!", toUserName=self.username)
            return
        
        content = ""
        index = 0
        for r in records:
            content += f"[ {index+1:02d} ] [{r['createTime']}] {r['title']}  {r['baseUrl']}  {r['apiKey']} \n"
            # content += f"[ {index+1:02d} ] [{r['create_time']}] {r['title']}  {r['base_url']}  {r['api_key']} \n"
            index += 1
            
        return content

    # 添加GPT token记录
    def gpt_token_add(self, content):
        arr = content.split(",")
        if len(arr) != 3:
            return "内容格式不正确,正确格式为[mysql tadd 标题,基地址,api_key]"
        
        name = arr[0]
        update_time = current_time()
        # strSQL = f"insert into gpt_token (title,base_url,api_key,create_time) values ('{arr[0]}','{arr[1]}','{arr[2]}','{update_time }')"
        # db.execute(strSQL)
        data = {'title': arr[0], 'baseUrl': arr[1], 'apiKey': arr[2]}
        self.api.modify(URL.TOKEN_MODIFY, data)

        return self.gpt_token(name)
        
    # 收藏问答内容
    def saveFavorite(self, content, lastRecord):
        # 如果没有参数,则保留最后一条记录
        id = 0
        if(len(content) == 0):
            if lastRecord is not None:
                id = lastRecord.id
            else:
                return "请先问答最后再进行保存!"
        else:
            try:
                id = int(content)
            except Exception as ex:
                return "格式不正确,mysql save 数字id!"

        if id > 0:
            record = self.api.get_detail(URL.RECORD_TMP_MODIFY, id)
            print(record)
            if(record == None):
                return f"没有找到对应id={id}的记录!"
            
            record = Record().from_dict(record)
            record.id = 0
            # id = self.saveClass('favorite_record', record)
            id = self.saveRecordFavorite(record)
            return f"[ {id} ]记录已收藏! [ http://s.net11.cn/db/{id} ]"
                
    def saveClass(self, table, classes):
        # dic = classes.to_dict(classes)

        # # print(dic)
        
        # fields = []
        # holders = []  # %s占位符
        # values = []
        # for k, v in dic.items():
        #     if(k == "id" and v == 0):
        #         continue
            
        #     fields.append(k)
        #     holders.append("%s")
        #     # 删除emoji字符
        #     if isinstance(v, str):
        #         v = remove_emoji(v)
        #     values.append(v)

        # strSQL = f"insert into {table} ({','.join(fields)}) values ({','.join(holders)})"
        # # print(strSQL)
        # id = db.execute(strSQL, values)

        # print("保存完成")
        # return id
        return ""

    # 搜索Suno数据库中创作历史,is_distinct表示是否进行重复判断
    def queryHistory(self, is_distinct = False):
        # if is_distinct:
        #     strSQL = f"SELECT DISTINCT `query`, MAX(create_time) AS create_time, id FROM suno GROUP BY `query` order by create_time desc limit 50"
        # else:
        #     strSQL = F"select `query`,create_time,id from suno order by create_time desc limit 50"
        # records = db.fetch_all(strSQL)
        # return records
        pass
    
    # 搜索Suno数据库中存放的数据
    def querySuno(self, content):
        # k = content
        # if len(k) > 0:
        #     strSQL = f"select * from suno where query like '%{k}%' or title like '%{k}%' or lyric like '%{k}%' order by create_time desc"
        # else:
        #     strSQL = f"select * from suno order by create_time desc limit 50"

        # records = db.fetch_all(strSQL)
        # return records
        pass
    
    # 保存SunoApi作曲的相关信息
    def saveSuno(self, suno : Suno):
        return self.saveClass("suno", suno)
    
    # 根据需要保存GPT提示词和回复内容
    def saveRecordTmp(self, record: Record):
        # return self.saveClass("tmp_record", record)
        r = record
        data = {"gptType": r.gpt_type, "gptsModelName": r.gpts_model_name, "gptsModelKey": r.gpts_model_key, 
                "userId": r.user_id, "userNickname": r.user_nickname, "prompt": r.prompt, "reply": r.reply}
        id = self.api.modify(URL.RECORD_TMP_MODIFY, data)
        return id
    
    # 根据需要保存GPT提示词和回复内容
    def saveRecordFavorite(self, record: Record):
        # return self.saveClass("tmp_record", record)
        r = record
        data = {"gptType": r.gpt_type, "gptsModelName": r.gpts_model_name, "gptsModelKey": r.gpts_model_key, 
                "userId": r.user_id, "userNickname": r.user_nickname, "prompt": r.prompt, "reply": r.reply}
        id = self.api.modify(URL.RECORD_FAVORITE_MODIFY, data)
        return id