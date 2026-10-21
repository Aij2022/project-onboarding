#!/usr/bin/env python3
"""gen_visual.py — 把面向 agent 的项目导览 markdown 机械生成自包含思维导图/流程图 HTML。

用法:
  python3 gen_visual.py --in 导览.md --out 图谱.html --title "XX 项目导览" [--meta "快照 2026-10-20"]

解析规则:
  # 标题            → 页面标题(--title 优先；树中不再重复出现)
  ## / ### / ####   → 思维导图分支层级
  - 或 * 列表项     → 叶子(两空格缩进 = 下一层；层级相对最近一级标题，同级项互为兄弟)
  其余文本行        → 最近一级标题下的平级叶子
  ```flow 围栏块    → 流程图(每行一条链: 标签: A -> B -> C；标签为该链命名，
                      同块多条链可各带标签；无箭头的行整行视为单节点)
  其它围栏块        → 原样保留为 <pre> 代码块
  围栏未闭合        → 内容照常投影，stderr 告警(不静默丢弃)

输出: 单文件 HTML(details/summary 折叠树 + CSS 流程行)，零外部依赖，离线可开；
      页头按快照日期自动渲染 FRESH/AGING/STALE 新鲜度徽章。
门禁: --check 导览.md —— 校验九节骨架、快照块三要素、新鲜度自评与日期一致、
      扫描疑似凭据值；任一不过非零退出，不生成 HTML。
纪律: 可视化是导览的投影——本脚本不添加、不改写任何内容。
"""
import argparse, html, re, sys, datetime

HDEPTH = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 4}
FRESH_DAYS, STALE_DAYS = 30, 90
FENCE_RE = re.compile(r'^(```|~~~)\s*(\w*)\s*$')
H_RE = re.compile(r'^(#{1,6})\s+(.*)$')
H1_RE = re.compile(r'^#\s+(.*)$')
LI_RE = re.compile(r'^([ \t]*)[-*]\s+(.*)$')
LABEL_RE = re.compile(r'^([^:：]+):\s*(.+)$')
DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')
COMMIT_RE = re.compile(r'\b[0-9a-f]{7,40}\b')
LEVEL_RE = re.compile(r'\b(FRESH|AGING|STALE)\b')
SECTION_PATTERNS = [
    ('这是什么项目', r'这是什么项目|项目简介|项目是什么'),
    ('30 秒现状', r'30\s*秒|现状速览|当前现状'),
    ('文档地图', r'文档地图|阅读顺序|文档索引|文档导航'),
    ('纪律红线', r'纪律|红线'),
    ('操作配方', r'配方|常用操作|操作手册'),
    ('实施轮清单', r'实施轮|checklist|检查清单|实施清单'),
    ('代码地图', r'代码地图|模块地图|代码结构|代码导览'),
    ('日志事件字典', r'日志'),
    ('陷阱清单', r'陷阱|踩坑|坑'),
]
CRED_PATTERNS = [
    re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
    re.compile(r'\b(?:sk|ghp|gho|github_pat)_[A-Za-z0-9_]{16,}\b'),
    re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    re.compile(r'(?i)\b(api[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=：]\s*["\']?([^\s"\']{8,})'),
]


def split_fences(text):
    """分离普通行与围栏。返回 (items, flows)。

    items 为 ('line', 文本行) 或 ('pre', [围栏内各行])；flows 为 parse_flow 结果。
    文件在围栏内结束时内容照常投影并向 stderr 告警——不静默丢弃。
    """
    items, flows = [], []
    inf, buf = None, []
    for ln in text.splitlines():
        m = FENCE_RE.match(ln)
        if m:
            if inf is None:
                inf, buf = m.group(2) or '', []
            else:
                _emit_fence(inf, buf, items, flows)
                inf = None
            continue
        if inf is None:
            items.append(('line', ln))
        else:
            buf.append(ln)
    if inf is not None:
        sys.stderr.write(f'警告: {inf or "代码"} 围栏未闭合，内容已按原文保留\n')
        _emit_fence(inf, buf, items, flows)
    return items, flows


def _emit_fence(lang, buf, items, flows):
    if lang == 'flow':
        fl = parse_flow(buf)
        if fl['chains']:
            flows.append(fl)
    elif buf:
        items.append(('pre', buf))


def parse_flow(buf):
    """每行一条链。行首 `标签:` 为该链命名——标签内不含 -> 且冒号后有箭头才算标签
    (节点文本自带冒号不受影响)；同块多条链各有题注；无箭头的行整行为单节点。"""
    chains = []
    for ln in buf:
        s = ln.strip()
        if not s or s.startswith('#'):
            continue
        name = None
        m = LABEL_RE.match(s)
        if m and '->' not in m.group(1) and '->' in m.group(2):
            name, s = m.group(1).strip(), m.group(2)
        nodes = [p.strip() for p in re.split(r'\s*->\s*', s) if p.strip()]
        if nodes:
            chains.append({'name': name, 'nodes': nodes})
    return {'chains': chains}


def build_tree(items):
    """items → 树。列表/段落取「最近一级标题层级 + 缩进」的绝对层级，配合 pop 落位，
    保证同级兄弟互为兄弟；段落与 pre 是纯叶子，不进祖先栈——后续章节不会被
    标题前的导语吞成子分支。"""
    root = {'text': None, 'children': [], 'kind': 'root'}
    stack = [(-1, root)]
    h_lvl = None
    for kind, payload in items:
        if kind == 'pre':
            lvl = (h_lvl if h_lvl is not None else -1) + 1
            node = {'text': '\n'.join(payload), 'children': [], 'kind': 'pre'}
        else:
            if not payload.strip():
                continue
            m = H_RE.match(payload)
            if m:
                h_lvl = HDEPTH[len(m.group(1))]
                lvl = h_lvl
                node = {'text': m.group(2).strip(), 'children': [], 'kind': 'h'}
            else:
                m2 = LI_RE.match(payload)
                base = (h_lvl if h_lvl is not None else -1) + 1
                if m2:
                    indent = len(m2.group(1).replace('\t', '  '))
                    lvl = base + indent // 2
                    node = {'text': m2.group(2).strip(), 'children': [], 'kind': 'li'}
                else:
                    lvl = base
                    node = {'text': payload.strip(), 'children': [], 'kind': 'p'}
        node['lvl'] = lvl
        while len(stack) > 1 and stack[-1][0] >= lvl:
            stack.pop()
        stack[-1][1]['children'].append(node)
        if node['kind'] in ('h', 'li'):
            stack.append((lvl, node))
    return root


def freshness(meta_text, today=None):
    """从快照文本提取日期计算新鲜度 → (级别, 距今天数)；无日期/异常/未来日期返回 None。"""
    m = DATE_RE.search(meta_text or '')
    if not m:
        return None
    try:
        d = datetime.date.fromisoformat(m.group(0))
    except ValueError:
        return None
    today = today or datetime.date.today()
    days = (today - d).days
    if days < 0:
        return None
    level = 'FRESH' if days < FRESH_DAYS else ('AGING' if days < STALE_DAYS else 'STALE')
    return level, days


def check_handbook(text):
    """--check 门禁：九节骨架 / 快照块三要素 / 新鲜度一致性 / 凭据特征。
    返回 (ok, findings, header新鲜度或None)。"""
    findings = []
    items, _ = split_fences(text)
    heads = [m.group(2) for k, p in items if k == 'line' and (m := H_RE.match(p))]
    for name, pat in SECTION_PATTERNS:
        if not any(re.search(pat, h) for h in heads):
            findings.append(f'[骨架] 缺「{name}」节（标题需含: {pat}）')

    header = []
    for k, p in items:
        if k == 'line' and (m := H_RE.match(p)) and len(m.group(1)) >= 2:
            break
        if k == 'line':
            header.append(p)
    head_text = '\n'.join(header)
    if not DATE_RE.search(head_text):
        findings.append('[快照块] 头部缺快照日期（YYYY-MM-DD）')
    if not COMMIT_RE.search(head_text):
        findings.append('[快照块] 头部缺快照 commit（7+ 位十六进制）')
    claimed = LEVEL_RE.search(head_text)
    if not claimed:
        findings.append('[快照块] 头部缺新鲜度自评（FRESH/AGING/STALE）')
    fr = freshness(head_text)
    if claimed and fr and claimed.group(1) != fr[0]:
        findings.append(f'[新鲜度] 自评 {claimed.group(1)}，按快照日期应为 {fr[0]}'
                        f'（{fr[1]} 天前；<30 天 FRESH / 30-90 AGING / ≥90 STALE）')

    for i, ln in enumerate(text.splitlines(), 1):
        for pat in CRED_PATTERNS:
            m = pat.search(ln)
            if not m:
                continue
            val = m.group(m.lastindex) if m.lastindex else m.group(0)
            if val and (val[0] in '<$' or 'your' in val.lower() or '…' in val):
                continue
            findings.append(f'[凭据] 第 {i} 行疑似凭据值，改为路径/环境变量引用')
            break
    return not findings, findings, fr


def render_node(node, depth):
    text = html.escape(node['text'])
    d = min(node.get('lvl', depth), 4)
    if node['kind'] == 'pre':
        return f'<div class="preleaf d{d}"><pre>{text}</pre></div>'
    cls = {'h': 'branch', 'li': 'item', 'p': 'leaf'}.get(node['kind'], 'leaf')
    if not node['children']:
        return f'<div class="leaf d{d}">{text}</div>'
    open_attr = ' open' if depth <= 1 else ''
    kids = ''.join(render_node(c, depth + 1) for c in node['children'])
    return f'<details{open_attr} class="{cls} d{d}"><summary>{text}</summary>{kids}</details>'


def render_flow(fl):
    rows = []
    for ch in fl['chains']:
        if not ch['nodes']:
            continue
        parts = []
        for n in ch['nodes'][:-1]:
            parts.append(f'<span class="fbox">{html.escape(n)}</span><span class="farr">→</span>')
        parts.append(f'<span class="fbox fend">{html.escape(ch["nodes"][-1])}</span>')
        cap = f'<div class="fcap">{html.escape(ch["name"])}</div>' if ch['name'] else ''
        rows.append(f'{cap}<div class="frow">{"".join(parts)}</div>')
    if not rows:
        return ''
    return f'<div class="fblock">{"".join(rows)}</div>'


CSS = """body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;margin:0 auto;
max-width:1080px;padding:24px;color:#1f2430;background:#f7f8fa;line-height:1.55}
h1.page{font-size:26px;border-bottom:3px solid #3b82c4;padding-bottom:10px}
.meta{color:#6b7280;font-size:13px;margin-bottom:18px}
details{margin:4px 0;border:1px solid #e3e6ec;border-radius:8px;background:#fff}
summary{cursor:pointer;padding:8px 12px;font-weight:600;border-radius:8px}
details[open]>summary{border-bottom:1px solid #eef0f4}
.branch.d1>summary{background:#eaf2fb;color:#1d4ed8}
.branch.d2>summary{background:#f0f7ee;color:#256029}
.branch>summary:hover{background:#f1f4f9}
details details{margin:6px 10px}
.leaf,.item{padding:5px 10px;margin:3px 10px;border-left:3px solid #c9d4e3;background:#fbfcfe;
border-radius:0 6px 6px 0;font-size:14.5px}
.d4{border-left-color:#e8d3a2}
.preleaf{padding:6px 10px;margin:3px 10px;border-left:3px solid #c9d4e3;background:#fbfcfe;
border-radius:0 6px 6px 0}
.preleaf pre{margin:0;white-space:pre-wrap;word-break:break-word;font-size:13px;
font-family:ui-monospace,SFMono-Regular,Consolas,'Courier New',monospace}
.fblock{border:1px solid #e3e6ec;border-radius:10px;background:#fff;padding:14px 18px;margin:14px 0;
overflow-x:auto}
.fcap{font-weight:700;margin-bottom:10px;color:#1d4ed8}
.frow{white-space:nowrap;padding:6px 0}
.fbox{display:inline-block;border:1.5px solid #3b82c4;border-radius:8px;padding:6px 12px;
background:#f4f9ff;font-size:14px}
.fend{border-color:#2f9e63;background:#f0faf4}
.farr{display:inline-block;margin:0 8px;color:#3b82c4;font-weight:700}
.badge{display:inline-block;margin:0 6px;padding:1px 8px;border-radius:99px;font-size:12px;
font-weight:700;vertical-align:1px}
.b-fresh{background:#f0faf4;color:#2f9e63;border:1px solid #b7e4c7}
.b-aging{background:#fef3c7;color:#b45309;border:1px solid #fde68a}
.b-stale{background:#fee2e2;color:#b91c1c;border:1px solid #fecaca}
@media print{details{page-break-inside:avoid}.frow{page-break-inside:avoid}}"""


def main():
    ap = argparse.ArgumentParser(description='导览 markdown → 自包含思维导图/流程图 HTML')
    ap.add_argument('--in', dest='src', required=True)
    ap.add_argument('--out', dest='dst', default=None, help='输出 HTML 路径（--check 时可省）')
    ap.add_argument('--title', default=None)
    ap.add_argument('--meta', default=None)
    ap.add_argument('--check', action='store_true',
                    help='只做门禁校验（九节/快照块/新鲜度/凭据），不生成 HTML')
    a = ap.parse_args()
    if not a.check and not a.dst:
        ap.error('--out 必填（或用 --check 只做校验）')

    try:
        text = open(a.src, encoding='utf-8').read()
    except OSError as e:
        sys.exit(f'gen_visual: 读不了输入文件 {a.src}: {e}')

    if a.check:
        ok, findings, fr = check_handbook(text)
        for f in findings:
            print(f)
        tail = f'（新鲜度 {fr[0]}，快照 {fr[1]} 天前）' if fr else ''
        print(('检查通过：九节齐 / 快照块齐 / 无凭据特征' if ok
               else f'检查未通过，共 {len(findings)} 项') + tail)
        sys.exit(0 if ok else 1)

    items, flows = split_fences(text)
    first_h1 = next((m.group(1).strip() for k, p in items
                     if k == 'line' and (m := H1_RE.match(p))), None)
    title = a.title or first_h1 or '项目导览'
    if first_h1 is not None and first_h1 == title.strip():
        # h1 已用作页面标题（--title 与其一致），从树中剔除以免重复；
        # 两者不同名时 h1 是导览内容，照常投影。
        items.pop(next(i for i, (k, p) in enumerate(items)
                       if k == 'line' and H1_RE.match(p)))
    root = build_tree(items)
    meta = a.meta or ('生成于 ' + datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
    badge = ''
    if a.meta:
        fr = freshness(a.meta)
        if fr:
            level, days = fr
            day_txt = '今天' if days == 0 else f'{days} 天前'
            badge = f' <span class="badge b-{level.lower()}">{level} · 快照 {day_txt}</span>'

    body = ''.join(render_node(c, 0) for c in root['children'])
    flows_html = ''.join(render_flow(fl) for fl in flows)
    flows_sec = (f'<h2 class="page">流程图</h2>{flows_html}') if flows else ''

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head><body>
<h1 class="page">{html.escape(title)}</h1>
<div class="meta">{html.escape(meta)}{badge} · 本页由导览 markdown 机械生成，内容以导览为准</div>
{body}
{flows_sec}
</body></html>"""
    try:
        open(a.dst, 'w', encoding='utf-8').write(doc)
    except OSError as e:
        sys.exit(f'gen_visual: 写不了输出文件 {a.dst}: {e}')
    n_branch = doc.count('<details')
    print(f'OK {a.dst} ({len(doc)} bytes, {n_branch} 折叠分支, {len(flows)} 流程图块)')


if __name__ == '__main__':
    main()
