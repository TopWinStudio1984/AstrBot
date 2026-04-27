import requests
import json
from .util import format_gpts_key

class OneNav:
    
    def __init__(self, onenav_cfg, nav_type, prompt = ""):
        self.nav_type = nav_type
        self.prompt = prompt
        self.onenav = onenav_cfg
        self.host  = self.onenav['host']
        self.token = self.onenav['token']
        
        print(self.onenav, self.host, self.token)
        
    def help(self, username):
        help_content = "nav命令用法\n" \
            "[查看分类]                  命令格式: /n cat\n" \
            "[查看链接]                  命令格式: /n link keyword/catid\n"
        return help_content

    def dispatch(self):
        print(self.nav_type, self.prompt)
        nav_type = self.nav_type
        content = self.prompt
        
        if(nav_type == "cat"):
            return self.category_list()
        elif(nav_type == "link"):
            return self.link(content)
        else:
            return self.help(self.username)    
       
    def category_list(self):
        url = f'{self.host}/index.php?c=api&method=category_list&page=1&limit=50'
        # data=json.dumps({'token': self.token})
        response = requests.post(url, {'token': self.token})
        result = json.loads(response.text)
        # print(result)
        if result['code'] == 0:
            content = "分类目录列表如下:\n"
            data = result['data']
            dics = {}
            for i in range(len(data)):
                r = data[i]
                # content += f'[ {r['id']} ] {r['name']}      '
                dics[r['id']] = r['name']
            
            content += format_gpts_key(dics, 3, False)
            return content
        else:
            return result['msg']
    
    # 查看全部链接以及模糊搜素
    def link(self, content):
        limit = 200
        cat_id = 0  # 分类id
        if len(content) > 0:
            try:
                cat_id = int(content)
            except Exception as ex:
                print("非数字")
            
            if cat_id == 0: 
                limit = 20000
            
        if cat_id == 0:
            # 汉字模糊查询
            url = f'{self.host}/index.php?c=api&method=link_list&page=1&limit={limit}'
        else:
            # 分类链接查询
            url = f'{self.host}/index.php?c=api&method=q_category_link&page=1&limit={limit}'
            
        # print(url)
        # data=json.dumps({'token': self.token})
        response = requests.post(url, {'token': self.token, 'category_id': cat_id})
        result = json.loads(response.text)
        if result['code'] == 0:
            keyword = content.lower() if cat_id == 0 else ""
            content = "全部链接列表如下:\n"
            data = result['data']
            for i in range(len(data)):
                r = data[i]
                t = r['title']
                u = r['url']
                d = r['description']
                lkeyword = keyword.lower()

                if len(keyword) == 0:
                    content += f"[ {r['id']} ] {r['title']} {r['url']}\n"
                else:
                    if t.lower().find(lkeyword) != -1 or u.lower().find(lkeyword) != -1:
                        content += f"[ {r['id']} ] {r['title']} {r['url']}\n"
                    elif d is not None and d.lower().find(lkeyword) != -1:
                        content += f"[ {r['id']} ] {r['title']} {r['url']}\n"
            return content    
        else:
            return result['msg']
            
    # TODO:: 添加链接接口: https://doc.xiaoz.org/books/onenav/page/6ea9a
    # TODO:: 修改链接接口: https://doc.xiaoz.org/books/onenav/page/dc6a6
    
    def del_link(self, id):
        url = f'{self.host}/index.php?c=api&method=del_link'
        response = requests.post(url, {'token': self.token, 'id': id})
        result = json.loads(response.text)
        if result['code'] == 0:
            # itchat.send(f'删除id={id}链接成功!', self.username)
            pass
        else:
            # itchat.send(result['err_msg'], self.username)
            pass