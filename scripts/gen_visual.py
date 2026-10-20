#!/usr/bin/env python3
"""gen_visual.py — 把面向 agent 的项目导览 markdown 机械生成自包含思维导图/流程图 HTML。

用法:
  python3 gen_visual.py --in 导览.md --out 图谱.html --title "XX 项目导览" [--meta "快照 2026-10-20"]

解析规则:
  # 标题            → 页面标题(--title 优先)
  ## / ### / ####   → 思维导图分支层级
  - 或 * 列表项     → 叶子(两空格缩进 = 下一层)
  ```flow 围栏块    → 流程图(每行一条链: 标签: A -> B -> C；无箭头的行整行视为单节点)

输出: 单文件 HTML(details/summary 折叠树 + CSS 流程行)，零外部依赖，离线可开。
纪律: 可视化是导览的投影——本脚本不添加、不改写任何内容。
"""
import argparse, html, re, datetime


def split_fences(text):
    """分离普通行与 ```flow 围栏块。返回 (tree_lines, flows)。"""
    tree, flows = [], []
    inf, buf = None, []
    for ln in text.splitlines():
        m = re.match(r'^(```|~~~)\s*(\w*)\s*$', ln)
        if m:
            if inf is None:
                inf, buf = m.group(2) or '', []
            else:
                if inf == 'flow':
                    flows.append(parse_flow(buf))
                else:  # 其它围栏原样保留为叶子文本
                    tree.append('    ' + ln)
                    tree.extend('    ' + b for b in buf)
                    tree.append('    ' + ln)
                inf = None
            continue
        (buf if inf is not None else tree).append(ln)
    return tree, flows


def parse_flow(buf):
    name, chains = None, []
    for ln in buf:
        s = ln.strip()
        if not s or s.startswith('#'):
            continue
        m = re.match(r'^([^:：]+):\s*(.+)$', s)
        if m and '->' in m.group(2):
            name, s = m.group(1).strip(), m.group(2)
        chains.append([p.strip() for p in re.split(r'\s*->\s*', s) if p.strip()])
    return {'name': name, 'chains': chains}


def build_tree(lines):
    root = {'text': None, 'children': [], 'kind': 'root'}
    stack = [(-1, root)]
    hdepth = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 4}
    for ln in lines:
        if not ln.strip():
            continue
        m = re.match(r'^(#{1,6})\s+(.*)$', ln)
        if m:
            lvl = hdepth[len(m.group(1))]
            node = {'text': m.group(2).strip(), 'children': [], 'kind': 'h'}
        else:
            m2 = re.match(r'^(\s*)[-*]\s+(.*)$', ln)
            if m2:
                lvl = stack[-1][0] + 1 + len(m2.group(1)) // 2
                node = {'text': m2.group(2).strip(), 'children': [], 'kind': 'li'}
            else:
                lvl = stack[-1][0] + 1
                node = {'text': ln.strip(), 'children': [], 'kind': 'p'}
        while len(stack) > 1 and stack[-1][0] >= lvl:
            stack.pop()
        stack[-1][1]['children'].append(node)
        stack.append((lvl, node))
    return root


def render_node(node, depth):
    text = html.escape(node['text'])
    cls = {'h': 'branch', 'li': 'item', 'p': 'leaf'}.get(node['kind'], 'leaf')
    if not node['children']:
        return f'<div class="leaf d{min(depth, 4)}">{text}</div>'
    open_attr = ' open' if depth <= 1 else ''
    kids = ''.join(render_node(c, depth + 1) for c in node['children'])
    return f'<details{open_attr} class="{cls} d{min(depth, 4)}"><summary>{text}</summary>{kids}</details>'


def render_flow(fl, idx):
    name = fl.get('name') or f'流程 {idx}'
    rows = []
    for chain in fl['chains']:
        if not chain:
            continue
        parts = []
        for n in chain[:-1]:
            parts.append(f'<span class="fbox">{html.escape(n)}</span><span class="farr">→</span>')
        parts.append(f'<span class="fbox fend">{html.escape(chain[-1])}</span>')
        rows.append(f'<div class="frow">{"".join(parts)}</div>')
    cap = f'<div class="fcap">{html.escape(name)}</div>' if fl.get('name') else ''
    return f'<div class="fblock">{cap}{"".join(rows)}</div>'


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
.leaf,.item,.fbox{padding:5px 10px;margin:3px 10px;border-left:3px solid #c9d4e3;background:#fbfcfe;
border-radius:0 6px 6px 0;font-size:14.5px}
.d4{border-left-color:#e8d3a2}
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

    text = open(a.src, encoding='utf-8').read()
    tree_lines, flows = split_fences(text)
    root = build_tree(tree_lines)

    title = a.title
    if not title:
        m = re.search(r'^#\s+(.+)$', text, re.M)
        title = m.group(1).strip() if m else '项目导览'
    meta = a.meta or ('快照生成于 ' + datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))

    body = ''.join(render_node(c, 0) for c in root['children'])
    flows_html = ''
    for i, fl in enumerate(flows, 1):
        flows_html += render_flow(fl, i)
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
    open(a.dst, 'w', encoding='utf-8').write(doc)
    n_branch = doc.count('<details')
    print(f'OK {a.dst} ({len(doc)} bytes, {n_branch} 折叠分支, {len(flows)} 流程图块)')


if __name__ == '__main__':
    main()
