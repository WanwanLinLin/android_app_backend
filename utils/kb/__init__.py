# 自研知识库模块基础设施：
#   es_client.py   Elasticsearch 异步客户端（AsyncElasticsearch）
#   minio_client.py MinIO 原生异步封装（miniopy-async，aiohttp 实现）
#   tokenizer.py   jieba 分词（索引与查询同管线，标准分析器即可处理中文）
#   embedding.py   openai 兼容 embeddings 异步客户端
#   parser.py      txt/md/pdf/docx 文本抽取与分块
#   retrieval.py   BM25 + KNN 混合检索与融合打分
#   tasks.py       文档解析后台任务（asyncio，信号量并发控制）
