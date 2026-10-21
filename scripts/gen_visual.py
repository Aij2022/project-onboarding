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

输出: 单文件 HTML(details/summary 折叠树 + CSS 流程行)，零外部依赖，离线可开。
纪律: 可视化是导览的投影——本脚本不添加、不改写任何内容。
"""
import argparse, html, re, sys, datetime

HDEPTH = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 4}
FENCE_RE = re.compile(r'^(```|~~~)\s*(\w*)\s*$')
H_RE = re.compile(r'^(#{1,6})\s+(.*)$')
H1_RE = re.compile(r'^#\s+(.*)$')
LI_RE = re.compile(r'^([ \t]*)[-*]\s+(.*)$')
LABEL_RE = re.compile(r'^([^:：]+):\s*(.+)$')


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
@media print{details{page-break-inside:avoid}.frow{page-break-inside:avoid}}"""


def main():
    ap = argparse.ArgumentParser(description='导览 markdown → 自包含思维导图/流程图 HTML')
    ap.add_argument('--in', dest='src', required=True)
    ap.add_argument('--out', dest='dst', required=True)
    ap.add_argument('--title', default=None)
    ap.add_argument('--meta', default=None)
    a = ap.parse_args()

    try:
        text = open(a.src, encoding='utf-8').read()
    except OSError as e:
        sys.exit(f'gen_visual: 读不了输入文件 {a.src}: {e}')

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

    body = ''.join(render_node(c, 0) for c in root['children'])
    flows_html = ''.join(render_flow(fl) for fl in flows)
    flows_sec = (f'<h2 class="page">流程图</h2>{flows_html}') if flows else ''

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head><body>
<h1 class="page">{html.escape(title)}</h1>
<div class="meta">{html.escape(meta)} · 本页由导览 markdown 机械生成，内容以导览为准</div>
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
