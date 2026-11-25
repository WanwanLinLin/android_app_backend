# -*- coding：utf-8 -*-
"""文档视觉解析：整页 OCR 转录 + 内嵌照片理解，均由视觉大模型完成。

PDF（extract_pdf_vision，utils/kb/parser.py 的 pdf 分支调用，输出按页拼进
全文后再走切片/向量化）三层提取：
  1. pypdf/pymupdf 文本层  —— 免费、100% 保真（不在本模块）
  2. 整页渲染 → VLM 转录   —— 文本层近乎为空且含图片（扫描件/图片页），或整本
                              呈表格特征时逐页转录（OCR 模式：压幻觉提示词，
                              表格还原 markdown）
  3. 内嵌原图 → VLM 分析   —— 现场照片等无文字图片的结构化描述（理解模式：
                              输出「[照片] …」段落；按 xref 去重、按尺寸过滤图标）

DOCX（describe_photos，docx 分支调用）只做第 3 层：Word 是文本性格式不存在
扫描问题，但内嵌照片同样值得理解；照片按文档顺序编号「图N」，接口与 PDF 的
images 清单同构，配图入库/检索/前端链路共用。

模型复用 config.yaml THIRD_PARTY_SERVICES -> generic_llm 的键名（kb.vision.llm）。
同步函数设计为在 asyncio.to_thread 中调用：渲染/提图是 CPU 操作，模型调用在其
内部 asyncio.run 的独立事件循环里异步并发，解析任务所在的主事件循环不被阻塞。

降级策略：单页/单图失败仅记日志跳过；全部失败时文档仍按文本层入库。
"""
import asyncio
import base64
import io

import httpx

from setting import config_data
from utils.getLogs import kb_logger
from utils.kb.es_client import kb_cfg

# 整页转录（OCR）：实测「禁止总结/翻译」提示词下零幻觉、表格还原完整
_OCR_PROMPT = (
    "你是OCR引擎。逐字转录图片页面中的全部可见文字（包括表格单元格、照片上的"
    "标注），保持原文顺序，用 markdown 表格还原表格结构。不要总结、不要翻译、"
    "不要解释。无法辨认的用[?]表示。只输出转录内容。")

# 照片理解（视觉描述）：约束「只描述真实可见内容」以压幻觉
_DESCRIBE_PROMPT = (
    "你是道路/桥梁管养现场的照片分析引擎。观察图片并输出：\n"
    "1. 拍摄对象与部位（如：沥青路面、梁板底、伸缩缝）\n"
    "2. 可见的病害或状况（类型+大致程度，如：纵向裂缝，缝宽约1~2mm）\n"
    "3. 画面中可辨认的标尺读数、标记数字或文字\n"
    "只描述画面中真实可见的内容，不确定就用“疑似”。输出为不超过4行的短列表，"
    "不要客套话。")

# kb.vision 可配项与默认值
_DEFAULTS = {
    "llm": None,               # generic_llm 键名，未配置=功能整体关闭
    "enabled": False,          # 总开关
    "page_ocr": "scan",        # 整页转录范围：scan=仅低文本含图页(扫描件) / all=全文档逐页
                               # (表格密集型手册转录质量胜过文本层) / off=关
    "photo_describe": True,    # 内嵌照片结构化描述
    "concurrency": 2,          # 单文档 VLM 请求并发
    "min_text_chars": 100,     # 页文本层低于该字符数视为近乎为空
    "dpi": 150,                # 整页渲染分辨率
    "max_pages": 400,          # 参与视觉处理的页数上限
    "max_photos": 300,         # 单文档照片分析上限
    "min_side": 160,           # 照片最短边下限（过滤图标/装饰）
    "min_area": 40000,         # 照片面积下限
    "max_side": 1600,          # 送模型前等比缩放上限
    "page_timeout": 180,       # 单页/单图请求超时（秒）
    "ocr_max_tokens": 1500,
    "photo_max_tokens": 400,
}


class ParseCancelled(Exception):
    """解析被用户取消（tasks.py 定义取消检查、捕获处理；本模块只在检查点抛出）。"""


def vision_cfg(override: dict = None) -> dict:
    """kb.vision 配置段合并默认值（可整段缺省），再叠加知识库级覆盖。

    override 来自 KbDataset.vision_config（JSON），仅 page_ocr / photo_describe
    两键可库级覆盖（值为 None 或缺失=跟随全局）。全局 enabled=false 时库级无法
    单独开启——平台未提供该能力时库级设置无效，需在 config.yaml 先打开。
    """
    user = (kb_cfg() or {}).get("vision") or {}
    merged = {k: user.get(k, v) for k, v in _DEFAULTS.items()}
    if override:
        po = override.get("page_ocr")
        if po in ("all", "scan", "off"):
            merged["page_ocr"] = po
        pd = override.get("photo_describe")
        if pd is not None:
            merged["photo_describe"] = bool(pd)
    return merged


def _llm_conf(key: str) -> dict:
    """按 kb.vision.llm 指向的键名取 generic_llm 配置（列表嵌 dict，同 get_service）。"""
    for svc in config_data["THIRD_PARTY_SERVICES"]:
        generic = svc.get("generic_llm") if isinstance(svc, dict) else None
        if generic and key in generic:
            return generic[key]
    raise KeyError(f"THIRD_PARTY_SERVICES.generic_llm 缺少 {key}")


async def _vlm(conf: dict, prompt: str, img_b64: str,
               max_tokens: int, timeout: float) -> str:
    """OpenAI 兼容多模态消息调视觉模型，返回转录/描述文本。"""
    body = {
        "model": conf["model"], "temperature": 0, "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{img_b64}"}}]}],
    }
    headers = {"Authorization": f"Bearer {conf.get('apikey') or 'none'}"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        r = await client.post(conf["url"], json=body, headers=headers)
        r.raise_for_status()
        return (r.json()["choices"][0]["message"]["content"] or "").strip()


def _png_b64(data: bytes, max_side: int) -> str:
    """内嵌原图统一转 PNG base64；超尺寸等比缩小。"""
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if max(img.size) > max_side:
        ratio = max_side / max(img.size)
        img = img.resize((max(1, int(img.width * ratio)),
                          max(1, int(img.height * ratio))))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def describe_photos(photos: list, kb_vision: dict = None,
                    progress_cb=None, cancel_cb=None) -> tuple:
    """对一批内嵌照片跑 VLM 理解（DOCX 等无页概念文档复用，同 PDF 第 3 层）。

    photos: [{"uid": 唯一标识, "label": 正文标记名(如 图1),
              "data": 原图bytes, "ext": str}, ...]（调用方已完成去重/尺寸过滤）
    返回 (annotated, images)：
      annotated [(label, 描述), ...]（仅成功项，喂回正文拼接）
      images    与 PDF extract_pdf_vision 的 images 同构（附 salt 后由
                tasks.py 上传配图、attach_image_ids 回填 img_id）
    视觉未启用返回 ([], [])；单图失败跳过。
    cancel_cb: 无参可调用，返回 True 表示用户已取消——每个 VLM 项发起前检查，
    命中即抛 ParseCancelled（asyncio.run 收尾会取消在途请求）。
    """
    cfg = vision_cfg(kb_vision)
    if not cfg["enabled"] or not cfg["llm"] or not cfg["photo_describe"]:
        return [], []
    if not photos:
        return [], []
    try:
        conf = _llm_conf(cfg["llm"])
    except KeyError as e:
        kb_logger.error(f"kb 视觉解析未启用: {e}")
        return [], []

    items = []
    for ph in photos[:int(cfg["max_photos"])]:
        try:
            items.append((ph, _png_b64(ph["data"], cfg["max_side"])))
        except Exception as e:
            kb_logger.info(f"kb 视觉照片 {ph.get('label')} 预处理失败: {e}")
    if not items:
        return [], []
    kb_logger.info(f"kb 视觉照片（文档内嵌）：待分析 {len(items)} 张")

    async def _run():
        sem = asyncio.Semaphore(max(1, int(cfg["concurrency"])))
        out, fails = {}, [0]
        state = {"done": 0, "total": len(items)}

        def _emit():
            if progress_cb:
                try:
                    progress_cb(state["done"], state["total"])
                except Exception:
                    pass

        async def one(i, ph, b64):
            if cancel_cb and cancel_cb():
                raise ParseCancelled()
            async with sem:
                if cancel_cb and cancel_cb():
                    raise ParseCancelled()
                try:
                    desc = await _vlm(conf, _DESCRIBE_PROMPT, b64,
                                      int(cfg["photo_max_tokens"]),
                                      cfg["page_timeout"])
                    if desc:
                        out[i] = (ph, desc)
                except ParseCancelled:
                    raise
                except Exception as e:
                    fails[0] += 1
                    kb_logger.error(f"kb 视觉照片({ph.get('label')})失败: {e}")
                state["done"] += 1
                _emit()

        _emit()
        await asyncio.gather(*[one(i, ph, b) for i, (ph, b) in enumerate(items)])
        if fails[0]:
            kb_logger.info(f"kb 视觉解析降级：{fails[0]} 项失败已跳过，其余照常入库")
        return out

    out = asyncio.run(_run())
    annotated, images = [], []
    for i in sorted(out):
        ph, desc = out[i]
        annotated.append((ph["label"], desc))
        images.append({"label": ph["label"], "uid": ph["uid"],
                       "ext": ph.get("ext") or "png", "data": ph["data"]})
    return annotated, images


def _page_likely_blank(doc, pno: int) -> bool:
    """无文本、无内嵌图、无矢量绘制的页视为空白页（不值得烧 VLM）。"""
    try:
        if doc[pno].get_text().strip():
            return False
        if doc[pno].get_images():
            return False
        return not doc[pno].get_drawings()
    except Exception:
        return True


def extract_pdf_vision(data: bytes, progress_cb=None, kb_vision: dict = None,
                       cancel_cb=None) -> list:
    """同步入口（在 asyncio.to_thread 中执行）。返回 (pages, images)：

    pages   按页组织：[{"page": 1-based, "ocr": "整页转录" 或 None,
                       "photos": [(label, 描述), ...]}, ...]，仅含实际产出内容的页
    images  扁平照片清单（供上传对象存储、作为 chunk 配图）：
            [{"page": 1-based, "xref": int, "ext": str, "data": bytes}, ...]

    progress_cb(done, total) 由工作线程回调，实现方需自行保证线程安全（如只写
    共享 dict）。kb_vision 为知识库级 vision_config（覆盖全局 page_ocr / photo_describe）。
    cancel_cb: 无参可调用，返回 True 表示用户已取消——每个 VLM 项发起前检查，
    命中即抛 ParseCancelled。
    """
    cfg = vision_cfg(kb_vision)
    if not cfg["enabled"] or not cfg["llm"]:
        return [], []
    # page_ocr 兼容布尔与字符串：True→scan / False→off / "all"|"scan"|"off"
    po = cfg["page_ocr"]
    if isinstance(po, bool):
        ocr_mode = "scan" if po else "off"
    else:
        ocr_mode = str(po).lower().strip()
        if ocr_mode in ("true", "1", "yes"):
            ocr_mode = "scan"
        elif ocr_mode in ("false", "0", "no"):
            ocr_mode = "off"
    photos_on = bool(cfg["photo_describe"])
    if ocr_mode == "off" and not photos_on:
        return [], []
    try:
        conf = _llm_conf(cfg["llm"])
    except KeyError as e:
        kb_logger.error(f"kb 视觉解析未启用: {e}")
        return [], []

    import pymupdf
    doc = pymupdf.open(stream=data, filetype="pdf")
    total = min(len(doc), int(cfg["max_pages"]))

    # ---- 页级摸底：文本长度 / 是否含图 ----
    lens, has_img = [], []
    for pno in range(total):
        try:
            lens.append(len(doc[pno].get_text().strip()))
            has_img.append(bool(doc[pno].get_images()))
        except Exception:
            lens.append(0)
            has_img.append(False)

    # ---- 选整页转录的页 ----
    # scan：仅「低文本且含图」的页（扫描件/整页图片）；all：全文档逐页（表格
    # 密集手册，转录还原表格结构、避开文本层字形误读）；off/False：不转录。
    # 空白页任何模式都跳过。
    ocr_pages = []
    if ocr_mode == "all":
        ocr_pages = [i for i in range(total) if not _page_likely_blank(doc, i)]
    elif ocr_mode == "scan":
        ocr_pages = [i for i in range(total)
                     if lens[i] < cfg["min_text_chars"] and has_img[i]]
    if ocr_pages:
        kb_logger.info(f"kb 视觉OCR：{total} 页中选 {len(ocr_pages)} 页转录"
                       f"（模式={ocr_mode}，平均文本 {sum(lens) // max(total, 1)} 字/页）")

    # ---- 选内嵌照片（按 xref 去重，尺寸过滤图标；记录首次出现页） ----
    photos = []  # [(xref, 首次页0-based, png_b64, 原图bytes, ext)]
    if photos_on:
        seen = set()
        for pno in range(total):
            try:
                imgs = doc.get_page_images(pno)
            except Exception:
                continue
            for img in imgs:
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)
                try:
                    info = doc.extract_image(xref)
                    w, h = info["width"], info["height"]
                    if min(w, h) < cfg["min_side"] or w * h < cfg["min_area"]:
                        continue
                    # 除送模型的缩放 PNG 外，保留原图字节+格式，供上传 MinIO
                    # 作为 chunk 配图（tasks.py 消费，img_id 关联进 ES）
                    photos.append((xref, pno,
                                   _png_b64(info["image"], cfg["max_side"]),
                                   info["image"], info.get("ext") or "png"))
                except Exception as e:
                    kb_logger.info(f"kb 视觉照片 xref={xref} 预处理失败: {e}")
                if len(photos) >= int(cfg["max_photos"]):
                    break
            if len(photos) >= int(cfg["max_photos"]):
                kb_logger.info(f"kb 视觉照片达单文档上限 {cfg['max_photos']}，其余跳过")
                break
        kb_logger.info(f"kb 视觉照片：待分析 {len(photos)} 张")

    if not ocr_pages and not photos:
        doc.close()
        return [], []

    async def _run():
        sem = asyncio.Semaphore(max(1, int(cfg["concurrency"])))
        loop = asyncio.get_running_loop()
        ocr_out, photo_out = {}, {}
        fails = [0]
        state = {"done": 0, "total": len(ocr_pages) + len(photos)}

        def _emit():
            if progress_cb:
                try:
                    progress_cb(state["done"], state["total"])
                except Exception:
                    pass

        async def one_ocr(pno):
            if cancel_cb and cancel_cb():
                raise ParseCancelled()
            async with sem:
                if cancel_cb and cancel_cb():
                    raise ParseCancelled()
                try:
                    pm = await loop.run_in_executor(
                        None, lambda p=pno: doc[p].get_pixmap(dpi=int(cfg["dpi"])))
                    b64 = base64.b64encode(pm.tobytes("png")).decode()
                    txt = await _vlm(conf, _OCR_PROMPT, b64,
                                     int(cfg["ocr_max_tokens"]), cfg["page_timeout"])
                    if txt and txt not in ("[?]", "无", "本页无文字"):
                        ocr_out[pno] = txt
                except Exception as e:
                    fails[0] += 1
                    kb_logger.error(f"kb 视觉OCR 第{pno + 1}页失败: {e}")
                state["done"] += 1
                _emit()

        async def one_photo(idx, xref, pno, b64, raw, ext):
            if cancel_cb and cancel_cb():
                raise ParseCancelled()
            async with sem:
                if cancel_cb and cancel_cb():
                    raise ParseCancelled()
                try:
                    desc = await _vlm(conf, _DESCRIBE_PROMPT, b64,
                                      int(cfg["photo_max_tokens"]), cfg["page_timeout"])
                    if desc:
                        label = f"第{pno + 1}页 照片{xref}"
                        photo_out[idx] = {"label": label, "desc": desc,
                                          "img": {"label": label,
                                                  "uid": f"p{pno + 1}_{xref}",
                                                  "page": pno + 1, "xref": xref,
                                                  "ext": ext, "data": raw}}
                except ParseCancelled:
                    raise
                except Exception as e:
                    fails[0] += 1
                    kb_logger.error(f"kb 视觉照片(第{pno + 1}页 xref={xref})失败: {e}")
                state["done"] += 1
                _emit()

        _emit()
        await asyncio.gather(*[one_ocr(p) for p in ocr_pages],
                             *[one_photo(i, *ph)
                               for i, ph in enumerate(photos)])
        if fails[0]:
            kb_logger.info(f"kb 视觉解析降级：{fails[0]} 项失败已跳过，其余照常入库")
        return ocr_out, photo_out

    ocr_out, photo_out = asyncio.run(_run())

    # ---- 按页组织：转录 + 照片描述；照片原图信息另出扁平清单供配图存储 ----
    page_idx = {}
    images = []

    def _entry(p1):
        e = page_idx.get(p1)
        if e is None:
            e = {"page": p1, "ocr": None, "photos": []}
            page_idx[p1] = e
        return e

    for pno, txt in ocr_out.items():
        _entry(pno + 1)["ocr"] = txt
    for _, pobj in sorted(photo_out.items()):
        label, desc, img = pobj["label"], pobj["desc"], pobj["img"]
        _entry(img["page"])["photos"].append((label, desc))
        images.append(img)
    out = sorted(page_idx.values(), key=lambda x: x["page"])
    doc.close()
    return out, images
