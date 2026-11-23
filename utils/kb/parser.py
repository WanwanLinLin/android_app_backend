# -*- coding：utf-8 -*-
"""文档文本抽取与分块（切片方法对齐 RAGFlow 的 parser_id）。

抽取（pdf/docx 用 pypdf / python-docx）是同步 CPU/IO 操作，由解析任务经
asyncio.to_thread 卸载执行。

切片方法与 ragflow 对齐（ragflow 共 14 种，其中 Resume/Table/Picture/Email/
Audio 依赖简历结构解析、表格文件、OCR、邮件解析、ASR 等特殊格式或模型，本模块
输入仅 txt/md/pdf/docx，故落地以下 8 种，各自边界策略互不相同）：
  General  句读聚合分块（ragflow naive），通用文本
  Q&A      问答对切分，FAQ 文档
  Manual   按章节/标题边界分块，不跨标题切断
  Paper    按段落块（空行边界）分块，段落完整不拆句
  Book     同 Manual 但更积极合并相邻小节，块更大
  Laws     按「第X条」法条边界分块，条文完整
  One      整篇一个 chunk（超长截断），超短文本
  Tag      每行一个 chunk，标签/术语库
未识别/缺省一律回退 General。
"""
import io
import re

from utils.kb.tokenizer import rough_token_count

SUPPORTED_EXTS = {"txt", "md", "pdf", "docx"}

# 切片方法 → 下拉描述（前端 KnowledgeBaseDetail.vue 的列表与此保持一致）
PARSER_METHODS = {
    "General": "通用：按句读聚合分块，适合大多数文档",
    "Q&A": "问答：按问答对切分，适合 FAQ 文档（识别不足时自动回退通用）",
    "Manual": "手册：按章节/标题分块，不跨标题切断",
    "Paper": "论文：按段落块分块，段落保持完整",
    "Book": "书籍：按章节分块并合并相邻小节，块更大",
    "Laws": "法条：按「第X条」分块，条文保持完整",
    "One": "单篇：整篇作为一个切片（超长自动截断）",
    "Tag": "标签：每行作为一个切片，适合标签/术语库",
}
DEFAULT_PARSER = "General"

# One 模式整篇上限（超出截断，防止 embedding 输入超限报错）
_ONE_MAX_TOKENS = 4000

_SENT_SPLIT = re.compile(r"(?<=[。！？；!?;\n])|(?<=\.)\s+")

# 标题/边界行
_HEADING_RE = re.compile(
    r"^\s*(#{1,6}\s|第[零〇一二三四五六七八九十百千万0-9]+[章节篇部]"
    r"|[一二三四五六七八九十]+、|\d+(?:\.\d+)*[\s.、．]\s*\S)")
_LAW_ARTICLE_RE = re.compile(r"^\s*第[零〇一二三四五六七八九十百千万0-9]+条")


def extract_text(data: bytes, ext: str) -> str:
    ext = (ext or "").lower()
    if ext in ("txt", "md"):
        return data.decode("utf-8", errors="ignore")
    if ext == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if ext == "docx":
        import docx
        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        for table in d.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells):
                    parts.append("\t".join(cells))
        return "\n".join(parts)
    raise ValueError(f"不支持的文件类型: {ext}")


def split_chunks(text: str, chunk_token_num: int = 256,
                 parser_id: str = None) -> list:
    """按切片方法分块，返回 [(chunk_text, token_count, position)]，position 从 1 开始。"""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    parser_id = (parser_id or DEFAULT_PARSER).strip()
    if parser_id not in PARSER_METHODS:
        parser_id = DEFAULT_PARSER
    if parser_id == "Q&A":
        units = _split_qa(text, chunk_token_num)
    elif parser_id in ("Manual", "Book"):
        # Book 更积极合并相邻小节（合并目标放大 1.5 倍，块更大）
        units = _split_by_headings(text, chunk_token_num,
                                   merge_target=int(chunk_token_num * (1.5 if parser_id == "Book" else 1)))
    elif parser_id == "Paper":
        units = _split_by_paragraphs(text, chunk_token_num)
    elif parser_id == "Laws":
        units = _split_by_pattern(text, chunk_token_num, _LAW_ARTICLE_RE)
    elif parser_id == "One":
        units = _split_one(text)
    elif parser_id == "Tag":
        units = _split_tag(text, chunk_token_num)
    else:
        units = _split_general(text, chunk_token_num)
    return [(u, rough_token_count(u), i + 1) for i, u in enumerate(units)]


# ---------------- General（原实现） ----------------

def _split_general(text: str, chunk_token_num: int = 256) -> list:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    # 段落切句
    sentences = []
    for p in paragraphs:
        for s in _SENT_SPLIT.split(p):
            s = (s or "").strip()
            if s:
                sentences.append(s)

    chunks, buf, buf_tokens = [], [], 0
    for s in sentences:
        st = rough_token_count(s)
        # 超长单句硬切
        while st > chunk_token_num * 2:
            cut = _cut_by_tokens(s, chunk_token_num)
            if buf:
                chunks.append(" ".join(buf))
                buf, buf_tokens = [], 0
            chunks.append(cut[0])
            s = cut[1]
            st = rough_token_count(s)
        if buf_tokens + st > chunk_token_num and buf:
            chunks.append(" ".join(buf))
            buf, buf_tokens = [], 0
        buf.append(s)
        buf_tokens += st
    if buf:
        chunks.append(" ".join(buf))
    return chunks


# ---------------- 各切片方法 ----------------

def _split_qa(text: str, token_num: int) -> list:
    """问答对切分：问句行 + 后续答行 = 一个 chunk；问对太少回退 General。"""
    units, pre = [], []

    def is_question(s: str) -> bool:
        if s.endswith(("?", "？")):
            return True
        if re.match(r"^(问[:：]|Q[:：])", s):
            return True
        # 编号问句（1. xxx / 二、xxx），过长的更可能是正文
        if _HEADING_RE.match(s) and rough_token_count(s) <= 64:
            return True
        return False

    cur_q, cur_a = None, []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if is_question(s):
            if cur_q is not None:
                units.append((cur_q, cur_a))
            cur_q, cur_a = s, []
        elif cur_q is not None:
            cur_a.append(s)
        else:
            pre.append(s)
    if cur_q is not None:
        units.append((cur_q, cur_a))

    if len(units) < 2:
        return _split_general(text, token_num)

    chunks = []
    if pre:  # 首个问句之前的引言部分
        chunks.extend(_split_general(" ".join(pre), token_num))
    for q, answers in units:
        body = " ".join([q] + answers)
        if rough_token_count(body) > token_num * 2:
            chunks.extend(_split_general(body, token_num))
        else:
            chunks.append(body)
    return chunks


def _split_by_headings(text: str, token_num: int, merge_target: int) -> list:
    """标题边界分块：每个标题块不与其他块混合；块内仍超长按 General 细分。

    merge_target > token_num（Book）时，把连续的不足块合并到更大目标。
    """
    blocks, cur = [], []
    for line in text.split("\n"):
        if _HEADING_RE.match(line) and cur:
            blocks.append(cur)
            cur = [line]
        else:
            cur.append(line)
    if cur:
        blocks.append(cur)

    # 合并不足 merge_target 的相邻小块
    merged, buf, buf_t = [], [], 0
    for b in blocks:
        bt = rough_token_count("\n".join(b))
        if buf_t + bt > merge_target and buf:
            merged.append("\n".join(buf))
            buf, buf_t = [], 0
        buf.append("\n".join(b))
        buf_t += bt
    if buf:
        merged.append("\n".join(buf))

    # 超长块细分（句读聚合），保持 General 的句级输出形态
    chunks = []
    for m in merged:
        if rough_token_count(m) > token_num * 2:
            chunks.extend(_split_general(m, token_num))
        else:
            chunks.append(m)
    return chunks


def _split_by_paragraphs(text: str, token_num: int) -> list:
    """段落块分块（Paper）：空行/硬换行分段落，段落不拆句，短段合并到目标大小。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    return _pack(paragraphs, token_num)


def _split_by_pattern(text: str, token_num: int, boundary_re) -> list:
    """按行正则边界分块（Laws）：命中行为新块起点，每块保持完整不合并，超长块细分。"""
    blocks, cur = [], []
    for line in text.split("\n"):
        if boundary_re.match(line) and cur:
            blocks.append("\n".join(cur))
            cur = [line]
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    chunks = []
    for b in blocks:
        if rough_token_count(b) > token_num * 2:
            chunks.extend(_split_general(b, token_num))
        else:
            chunks.append(b)
    return chunks


def _split_one(text: str) -> list:
    """整篇一个 chunk；超过 embedding 输入上限时按 token 截断。"""
    if rough_token_count(text) > _ONE_MAX_TOKENS:
        text = _cut_by_tokens(text, _ONE_MAX_TOKENS)[0]
    return [text]


def _split_tag(text: str, token_num: int) -> list:
    """每行一个 chunk（标签/术语库）；超长行按 General 细分。"""
    units = []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if rough_token_count(s) > token_num * 2:
            units.extend(_split_general(s, token_num))
        else:
            units.append(s)
    return units


# ---------------- 公共辅助 ----------------

def _pack(segments: list, token_num: int) -> list:
    """把边界段聚合到 ~token_num：不足合并、超过 2 倍的段用 General 细分。"""
    chunks, buf, buf_t = [], [], 0
    for seg in segments:
        st = rough_token_count(seg)
        if st > token_num * 2:
            if buf:
                chunks.append("\n".join(buf))
                buf, buf_t = [], 0
            chunks.extend(_split_general(seg, token_num))
            continue
        if buf_t + st > token_num and buf:
            chunks.append("\n".join(buf))
            buf, buf_t = [], 0
        buf.append(seg)
        buf_t += st
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def _cut_by_tokens(s: str, max_tokens: int) -> tuple:
    """把超长串按 token 数截成 (head, tail)。token≈汉字数+英文词数，用字符数近似折算。"""
    acc, cut_at = 0, len(s)
    i = 0
    while i < len(s):
        ch = s[i]
        if "\u4e00" <= ch <= "\u9fff":
            acc += 1
            i += 1
        else:
            m = re.match(r"[a-zA-Z0-9]+", s[i:])
            if m:
                acc += 1
                i += len(m.group(0))
            else:
                i += 1
        if acc >= max_tokens:
            cut_at = i
            break
    return s[:cut_at], s[cut_at:]
