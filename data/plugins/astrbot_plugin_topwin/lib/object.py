
class Article:
    def __init__(self, id=0, url="", title="", author="", publish_date="", source="", content="", cate_id="", create_time=""):
        self.id = id
        self.url = url
        self.title = title
        self.author = author
        self.publish_date = publish_date
        self.source = source
        self.content = content
        self.cate_id = cate_id
        self.create_time = create_time

    def __repr__(self):
        return f"Article(id={self.id}, url={self.url}, title={self.title}, author={self.author}, publish_date={self.publish_date}, source={self.source}, content={self.content}, cate_id={self.cate_id}, create_time={self.create_time}"


    # 将 Record 实例转换为字典
    def to_dict(self, record):
        return {
            "id": record.id,
            "url": record.url,
            "title": record.title,
            "author": record.author,
            "publish_date": record.publish_date,
            "source": record.source,
            "content": record.content,
            "cate_id": record.cate_id,
            "create_time": record.create_time
        }


    # 从字典创建 Record 实例
    def from_dict(self, data):
        return Article(
            data["id"],
            data["url"],
            data["title"],
            data["author"],
            data["publish_date"],
            data["source"],
            data["content"],
            data["cate_id"],
            data["create_time"]
        )



class Record:
    def __init__(self, id=0, gpt_type="", gpts_model_name="", gpts_model_key="", user_id="", user_nickname="", create_time="", prompt="", reply=""):
        self.id = id
        self.gpt_type = gpt_type
        self.gpts_model_name = gpts_model_name
        self.gpts_model_key = gpts_model_key
        self.user_id = user_id
        self.user_nickname = user_nickname
        self.create_time = create_time
        self.prompt = prompt
        self.reply = reply

    def __repr__(self):
        return f"Record(id={self.id}, gpt_type={self.gpt_type}, gpts_model_name={self.gpts_model_name}, gpts_model_key={self.gpts_model_key}, user_id={self.user_id}, user_nickname={self.user_nickname}, create_time={self.create_time}, prompt={self.prompt}, reply={self.reply}"


    # 将 Record 实例转换为字典
    def to_dict(self, record):
        return {
            "id": record.id,
            "gpt_type": record.gpt_type,
            "gpts_model_name": record.gpts_model_name,
            "gpts_model_key": record.gpts_model_key,
            "user_id": record.user_id,
            "user_nickname": record.user_nickname,
            "create_time": record.create_time,
            "prompt": record.prompt,
            "reply": record.reply
        }


    # 从字典创建 Record 实例
    def from_dict(self, data):
        return Record(
            data["id"],
            data["gptType"],
            data["gptsModelName"],
            data["gptsModelKey"],
            data["userId"],
            data["userNickname"],
            data["createTime"],
            data["prompt"],
            data["reply"],
        )
        
        # return Record(
        #     data["id"],
        #     data["gpt_type"],
        #     data["gpts_model_name"],
        #     data["gpts_model_key"],
        #     data["user_id"],
        #     data["user_nickname"],
        #     data["create_time"],
        #     data["prompt"],
        #     data["reply"],
        # )



class Suno:
    def __init__(self, id, query, title, lyric, user_id, user_nickname, create_time, id1, id2, filename1, filename2, url1, url2):
        self.id = id
        self.query = query
        self.title = title
        self.lyric = lyric
        self.user_id = user_id
        self.user_nickname = user_nickname
        self.create_time = create_time
        self.id1 = id1
        self.id2 = id2
        self.filename1 = filename1
        self.filename2 = filename2
        self.url1 = url1
        self.url2 = url2

    def __repr__(self):
        return f"Suno(id={self.id}, query={self.query}, title={self.title}, lyric={self.lyric}, user_id={self.user_id}, user_nickname={self.user_nickname}, create_time={self.create_time}, id1={self.id1}, id2={self.id2}, filename1={self.filename1}, filename2={self.filename2}, url1={self.url1}, url2={self.url2})"


    # 将 Suno 实例转换为字典
    def to_dict(self, suno):
        return {
            "id": suno.id,
            "query": suno.query,
            "title": suno.title,
            "lyric": suno.lyric,
            "user_id": suno.user_id,
            "user_nickname": suno.user_nickname,
            "create_time": suno.create_time,
            "id1": suno.id1,
            "id2": suno.id2,
            "filename1": suno.filename1,
            "filename2": suno.filename2,
            "url1": suno.url1,
            "url2": suno.url2,
        }


    # 从字典创建 Suno 实例
    def from_dict(self, data):
        return Suno(
            data["id"],
            data["query"],
            data["title"],
            data["lyric"],
            data["user_id"],
            data["user_nickname"],
            data["create_time"],
            data["id1"],
            data["id2"],
            data["filename1"],
            data["filename2"],
            data["url1"],
            data["url2"],
        )

