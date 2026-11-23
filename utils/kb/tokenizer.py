# -*- coding：utf-8 -*-
"""中文分词：入库与查询共用同一管线（jieba）。

ES 索引里 content_ltks 存分词后用空格连接的结果，查询侧同样分词后以
query_string 组装，保证词条可命中；不依赖任何 ES 分析器插件（ik 等），
私有化部署只要求裸 ES。
"""
import functools
import re

import jieba
import jieba.analyse

STOPWORDS = set(
    "的 了 和 是 在 我 有 就 不 人 都 一 也 很 到 说 要 去 你 会 着 没有 看 好 "
    "自己 这 那 他 她 它 们 个 上 下 中 里 为 与 及 或 等 之 而 并 若 因 所 以 "
    "the a an and or of to in is are was were be been this that it for with on at as by"
    .split())

_token_re = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9_.%+-]+")


@functools.lru_cache(maxsize=200000)
def _cut_cached(text: str) -> tuple:
    return tuple(jieba.cut(text, cut_all=False))


def tokenize(text: str) -> list:
    """细粒度分词 + 去停用词 + 英文小写。"""
    out = []
    for t in _cut_cached(text or ""):
        t = t.strip().lower()
        if not t or t in STOPWORDS:
            continue
        # 标点/空白不索引（词必须含汉字或字母数字）
        if not _token_re.search(t):
            continue
        out.append(t)
    return out


def tokenize_join(text: str) -> str:
    return " ".join(tokenize(text))


def build_query_string(text: str, max_tokens: int = 24) -> str:
    """查询侧：分词后取前 N 个词，OR 组装（BM25 自然按词频/IDF 打分）。"""
    toks = tokenize(text)[:max_tokens]
    if not toks:
        # 整句兜底：全部是停用词时按原始串里的词元查
        toks = [m.group(0) for m in _token_re.finditer((text or "").lower())][:max_tokens]
    if not toks:
        return ""
    return " OR ".join(toks)


def rough_token_count(text: str) -> int:
    """token 估算：汉字按字计，其余按空白/词元计（与分块尺寸控制同口径）。"""
    if not text:
        return 0
    han = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    rest = len(re.findall(r"[a-zA-Z0-9]+", text))
    return han + rest
