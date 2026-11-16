"""LLM 自动化测试报告 PDF 生成（reportlab + 系统中文字体）。

字体候选按顺序探测：DroidSansFallbackFull（TrueType 轮廓，reportlab 直接
支持）→ arphic ukai。系统 Noto Sans CJK 为 CFF/PostScript 轮廓，reportlab
的 TTFont 不支持，不在候选内。找不到任何中文字体时抛错，由路由层转成
友好提示（而不是产出满页方块的 PDF）。
"""
import os
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

# (路径, TTC 子字体号)。字体实测结论：系统 Noto Sans CJK 是 CFF/PostScript
# 轮廓，reportlab 的 TTFont 直接报错；DroidSansFallbackFull 能注册但子集化后
# 丢 ASCII 字形（数字/英文全空白）。arphic ukai 中英混排完整，为首选。
FONT_CANDIDATES = (
    ("/usr/share/fonts/truetype/arphic/ukai.ttc", 0),
    ("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf", None),
)

_FONT = None


def _resolve_font() -> str:
    """注册并返回可用的中文字体名（模块级缓存，只注册一次）。"""
    global _FONT
    if _FONT:
        return _FONT
    for i, (path, idx) in enumerate(FONT_CANDIDATES):
        if not os.path.exists(path):
            continue
        try:
            name = f"CJK{i}"
            pdfmetrics.registerFont(
                TTFont(name, path, subfontIndex=idx) if idx is not None else TTFont(name, path))
            _FONT = name
            return name
        except Exception:
            continue
    raise RuntimeError("服务器缺少可用的中文字体（arphic ukai / Droid Sans Fallback），无法生成中文 PDF 报告")


def _esc(text) -> str:
    """转义 XML 特殊字符并保留换行，供 Paragraph 使用。

    先去勾叉符号（✔✘ 字体多缺字形→空白方块），状态一律用中文词 +
    背景/文字颜色表达，不依赖符号字形。常规中文标点（、·…｜）ukai 有字形，保留。
    """
    s = str(text if text is not None else "")
    s = s.replace("✔", "").replace("✘", "")
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\n", "<br/>"))


PASS_COLOR = colors.HexColor("#1a9c56")
FAIL_COLOR = colors.HexColor("#d64541")
MUTED = colors.HexColor("#6b7280")


def build_report_pdf(report: dict) -> bytes:
    """任务报告 dict（runner.run_task 产物）→ PDF 字节串。"""
    font = _resolve_font()
    st_title = ParagraphStyle("t", fontName=font, fontSize=17, leading=22,
                              spaceAfter=4, textColor=colors.HexColor("#1f2430"))
    st_sub = ParagraphStyle("s", fontName=font, fontSize=9.5, leading=14, color=MUTED)
    st_h = ParagraphStyle("h", fontName=font, fontSize=12, leading=16,
                          spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#2b3350"))
    st_body = ParagraphStyle("b", fontName=font, fontSize=9.5, leading=14)
    st_out = ParagraphStyle("o", fontName=font, fontSize=9, leading=13.5,
                            backColor=colors.HexColor("#f5f6fa"), borderPadding=5,
                            leftIndent=2, rightIndent=2)
    st_cell = ParagraphStyle("c", fontName=font, fontSize=9, leading=13)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"LLM自动化测试报告 - {report.get('task_name', '')}")
    story = []

    s = report.get("summary") or {}
    story.append(Paragraph(_esc(f"LLM 自动化测试报告 · {report.get('task_name', '')}"), st_title))
    trig = {"manual": "手动运行", "scheduled": "定时运行"}.get(report.get("trigger"),
                                                               report.get("trigger", "—"))
    story.append(Paragraph(
        _esc(f"任务 #{report.get('task_id')} ｜ 触发方式：{trig} ｜ "
             f"运行时间：{report.get('run_time') or report.get('last_run_time') or '—'} ｜ "
             f"结果：共 {s.get('total', 0)} 项，通过 {s.get('ok', 0)}，失败 {s.get('fail', 0)}"), st_sub))

    # 测试问题（多轮）与规则
    prompts = report.get("prompts") or ([report.get("prompt")] if report.get("prompt") else [])
    story.append(Paragraph(f"测试问题（共 {len(prompts)} 轮连续对话）", st_h))
    qa_rows = [[Paragraph("轮次", st_cell), Paragraph("问题", st_cell)]]
    for i, p in enumerate(prompts, start=1):
        qa_rows.append([Paragraph(f"第{i}轮", st_cell), Paragraph(_esc(p), st_cell)])
    qt = Table(qa_rows, colWidths=[20 * mm, 138 * mm])
    qt.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe3ee")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(qt)
    rules = report.get("rules") or []
    rule_label = {"contains": "包含", "not_contains": "不包含",
                  "regex": "正则匹配", "llm_judge": "AI 判定"}
    story.append(Paragraph("结果校验规则（针对全部对话内容）", st_h))
    if rules:
        rows = [[Paragraph("类型", st_cell), Paragraph("规则内容", st_cell)]]
        for r in rules:
            rows.append([Paragraph(rule_label.get((r or {}).get("type"), (r or {}).get("type", "—")), st_cell),
                         Paragraph(_esc((r or {}).get("value")), st_cell)])
        t = Table(rows, colWidths=[28 * mm, 130 * mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe3ee")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f8")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        story.append(t)
    else:
        story.append(Paragraph("（未配置规则，仅测联通性与输出非空）", st_sub))

    # 各插件结果
    story.append(Paragraph("插件测试明细", st_h))
    for it in report.get("items") or []:
        ok = bool(it.get("ok"))
        head = Table([[Paragraph(_esc(f"{'✔ 通过' if ok else '✘ 失败'} ｜ "
                                      f"#{it.get('plugin_id')} {it.get('plugin_name', '')}"
                                      f"（基础插件 {it.get('base_plugin') or '—'}）"), st_cell),
                       Paragraph(f"耗时 {it.get('seconds', '—')}s"
                                 f"{'，首 token ' + str(it.get('first_token_seconds')) + 's'
                                  if it.get('first_token_seconds') else ''}", st_cell)]],
                     colWidths=[120 * mm, 38 * mm])
        head.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("TEXTCOLOR", (0, 0), (0, 0), PASS_COLOR if ok else FAIL_COLOR),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0faf4" if ok else "#fdf1f0")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#dfe3ee")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))

        # 短明细（无长输出）用 KeepTogether 防表头拆页；带长输出的整段允许跨页，
        # 否则 KeepTogether 装不下会整块推到下一页，留下大片空白
        blocks = []
        if it.get("url"):
            blocks.append(Paragraph(_esc(f"服务地址：{it['url']}"), st_sub))
            blocks.append(Spacer(1, 1.5 * mm))
        if it.get("error"):
            blocks.append(Paragraph(_esc(f"错误：{it['error']}"),
                                    ParagraphStyle("e", parent=st_body, textColor=FAIL_COLOR)))
        turns = it.get("turns") or []
        if turns:
            blocks.append(Paragraph(f"对话记录（{len(turns)} 轮）：", st_body))
            for t in turns:
                head_t = ParagraphStyle("th", parent=st_sub, textColor=colors.HexColor("#2b3350"))
                blocks.append(Paragraph(_esc(f"第{t.get('index')}轮 问：{t.get('prompt')}"), head_t))
                if t.get("output"):
                    blocks.append(Paragraph(_esc("答：" + t["output"]), st_out))
                elif t.get("error"):
                    blocks.append(Paragraph(_esc(f"答：（失败：{t['error']}）"),
                                              ParagraphStyle("te", parent=st_out, textColor=FAIL_COLOR)))
                blocks.append(Spacer(1, 1.5 * mm))
        elif it.get("output"):  # 旧版单轮报告兼容
            blocks.append(Paragraph("模型输出：", st_body))
            blocks.append(Paragraph(_esc(it["output"]), st_out))
        checks = it.get("checks") or []
        if checks:
            crows = [[Paragraph("规则", st_cell), Paragraph("结果", st_cell),
                      Paragraph("说明", st_cell)]]
            for c in checks:
                crows.append([
                    Paragraph(_esc(f"{rule_label.get(c.get('type'), c.get('type'))}："
                                   f"{c.get('value')}"), st_cell),
                    Paragraph(_esc("✘ 判定模型故障" if c.get("error") and not c.get("passed")
                                   else ("✔ 通过" if c.get("passed") else "✘ 未通过")), st_cell),
                    Paragraph(_esc(c.get("detail")), st_cell)])
            ct = Table(crows, colWidths=[62 * mm, 24 * mm, 72 * mm])
            ct.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe3ee")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
            blocks += [Spacer(1, 1.5 * mm), ct]
        # 表头单独打包防拆页；正文（含长输出）平铺允许自然跨页
        story.append(KeepTogether([head, Spacer(1, 2 * mm)]))
        story.extend(blocks)
        story.append(Spacer(1, 4 * mm))

    doc.build(story)
    return buf.getvalue()
