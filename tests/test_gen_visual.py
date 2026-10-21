#!/usr/bin/env python3
"""project-onboarding skill 功能测试 — 黑盒实跑 gen_visual.py 并探测输出 HTML 结构。

被测对象: ~/.agents/skills/project-onboarding/scripts/gen_visual.py
运行: python3 test_gen_visual.py -v

本套件即回归门槛：TestListNesting / TestFlowParsing / TestFenceRobustness
表达的是预期正确行为，修复后应全部通过。
"""
import re
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

_GEN_CANDIDATES = [
    Path(__file__).resolve().parent.parent / 'scripts' / 'gen_visual.py',  # 仓库内
    Path('/home/aij2022/.agents/skills/project-onboarding/scripts/gen_visual.py'),
]
GEN = next(p for p in _GEN_CANDIDATES if p.exists())
REAL_DOC = Path('/vol2/1000/docs/code/wechat-bot/wechat-bot-agent-onboarding.md')


def run_gen(md_text, extra_args=(), src_name='in.md', dst_name='out.html'):
    """在临时目录实跑生成器，返回 (returncode, 合并输出, html文本或None)。"""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        src = td / src_name
        dst = td / dst_name
        src.write_text(md_text, encoding='utf-8')
        cmd = [sys.executable, str(GEN), '--in', str(src), '--out', str(dst), *extra_args]
        p = subprocess.run(cmd, capture_output=True, text=True)
        html_text = dst.read_text(encoding='utf-8') if dst.exists() else None
        return p.returncode, p.stdout + p.stderr, html_text


class TreeProbe(HTMLParser):
    """还原输出树的父子关系: records = [(文本, 父文本或None), ...]。

    覆盖两类节点: details>summary(有子分支) 与 div.leaf(叶子)。
    """

    def __init__(self):
        super().__init__()
        self.stack = []          # 已打开且已读到 summary 文本的 details
        self.records = []
        self._pending_parent = None
        self._in_summary = False
        self._buf = []
        self._in_leaf = False
        self._lbuf = []

    def handle_starttag(self, tag, attrs):
        if tag == 'details':
            self._pending_parent = self.stack[-1] if self.stack else None
        elif tag == 'summary':
            self._in_summary, self._buf = True, []
        elif tag == 'div':
            cls = dict(attrs).get('class', '')
            if 'leaf' in cls:
                self._in_leaf, self._lbuf = True, []

    def handle_data(self, data):
        if self._in_summary:
            self._buf.append(data)
        elif self._in_leaf:
            self._lbuf.append(data)

    def handle_endtag(self, tag):
        if tag == 'summary':
            self._in_summary = False
            text = ''.join(self._buf).strip()
            self.records.append((text, self._pending_parent))
            self.stack.append(text)
        elif tag == 'details':
            if self.stack:
                self.stack.pop()
        elif tag == 'div' and self._in_leaf:
            self._in_leaf = False
            parent = self.stack[-1] if self.stack else None
            self.records.append((''.join(self._lbuf).strip(), parent))


def parents_map(html_text):
    probe = TreeProbe()
    probe.feed(html_text)
    probe.close()
    return dict(probe.records)


def tag_balance(html_text):
    return {
        'details': (html_text.count('<details'), html_text.count('</details>')),
        'div': (len(re.findall(r'<div[ >]', html_text)), html_text.count('</div>')),
        'summary': (html_text.count('<summary'), html_text.count('</summary>')),
    }


def strip_fences(text):
    """粗粒度剔除围栏块，返回普通行（用于统计应出现在 HTML 的标题/列表文本）。"""
    out, inf = [], False
    for ln in text.splitlines():
        if re.match(r'^(```|~~~)', ln):
            inf = not inf
            continue
        if not inf:
            out.append(ln)
    return out


def tree_texts_of(md_text):
    """提取普通区所有应投影的标题/列表文本。"""
    texts = []
    for ln in strip_fences(md_text):
        hm = re.match(r'^#{1,6}\s+(.*)$', ln)
        lm = re.match(r'^(\s*)[-*]\s+(.*)$', ln)
        if hm:
            texts.append(hm.group(1).strip())
        elif lm:
            texts.append(lm.group(2).strip())
    return [t for t in texts if t]


STANDARD_HANDBOOK = """# 示例项目导览

快照 2026-10-20，之后演进以仓库 README 为准。

## 这是什么项目

三句话说明。`run-all-tests.sh` 是测试入口。

## 30 秒现状

- 先跑体检脚本
- 看五项服务状态
  - 服务 A 正常与否
  - 服务 B 队列深度
- 再看审计日志

### 健康判读

全绿为健康。

#### 特例说明

仅有四级标题时也应有分支。

## 常用操作配方

```bash
# 重启服务 A（白名单内）
systemctl restart svc-a
echo "done"
```

## 流程

```flow
实施轮: 备份 -> 修改 -> 自测 -> 回归 -> 部署
无标签链 -> 单节点收尾
```

## 陷阱清单

- 热加载不生效时要手动 reload
- * 星号列表也应支持
"""


class TestHappyPath(unittest.TestCase):

    def test_standard_handbook_ok(self):
        """A1 正向: 标准九节式导览 → 退出码0、HTML完整、内容全投影、零外部依赖。"""
        rc, out, html_text = run_gen(STANDARD_HANDBOOK,
                                     ['--title', '示例项目导览', '--meta', '快照 2026-10-20'])
        self.assertEqual(rc, 0, out)
        self.assertIn('OK', out)
        self.assertIn('<meta charset="utf-8">', html_text)
        self.assertIn('<h1 class="page">示例项目导览</h1>', html_text)
        self.assertIn('快照 2026-10-20', html_text)
        bal = tag_balance(html_text)
        for tag, (o, c) in bal.items():
            self.assertEqual(o, c, f'{tag} 标签不配对: {bal}')
        pm = parents_map(html_text)
        for sec in ('这是什么项目', '30 秒现状', '常用操作配方', '陷阱清单'):
            self.assertIsNone(pm.get(sec), f'章节 {sec} 应为顶级分支, 实际 {pm}')
        self.assertEqual(pm.get('服务 B 队列深度'), '看五项服务状态', f'二级列表挂错父: {pm}')
        for t in tree_texts_of(STANDARD_HANDBOOK):
            needle = t
            if needle not in html_text:
                from html import escape
                needle = escape(t)
            self.assertIn(needle, html_text, f'导览内容丢失: {t}')
        self.assertNotRegex(html_text, r'(src|href)\s*=')

    def test_flow_single_label_and_unlabeled(self):
        """A2 正向: flow 带标签出题注，同块无标签链也正常渲染。"""
        rc, out, html_text = run_gen(STANDARD_HANDBOOK)
        self.assertEqual(rc, 0, out)
        self.assertIn('实施轮', html_text, '唯一标签未成为题注')
        self.assertIn('无标签链', html_text)
        self.assertIn('流程图</h2>', html_text)

    def test_h4_heading(self):
        """A5 正向: #### 四级标题成为分支。"""
        rc, out, html_text = run_gen('## A\n\n#### D\n\n文本\n')
        self.assertEqual(rc, 0, out)
        pm = parents_map(html_text)
        self.assertEqual(pm.get('D'), 'A', f'#### 应为 ## 子分支, 实际 {pm}')

    def test_title_auto_from_h1(self):
        """A6 正向: 不传 --title 时取 h1 做页面标题。"""
        rc, out, html_text = run_gen('# 我的标题\n\n## 节\n')
        self.assertEqual(rc, 0, out)
        self.assertIn('<title>我的标题</title>', html_text)

    def test_no_flow_section_without_flow(self):
        """A7 正向: 无 flow 块则无流程图小节。"""
        rc, out, html_text = run_gen('## 只有树\n- a\n')
        self.assertEqual(rc, 0, out)
        self.assertNotIn('流程图</h2>', html_text)


class TestListNesting(unittest.TestCase):
    """核心结构正确性: 兄弟列表项应互为兄弟而非链式嵌套。"""

    def test_flat_list_siblings(self):
        """B1: 三个同级 - 项应都挂在 ## A 下（父均为 A）。"""
        rc, out, html_text = run_gen('## A\n- a\n- b\n- c\n')
        self.assertEqual(rc, 0, out)
        pm = parents_map(html_text)
        self.assertEqual(pm.get('a'), 'A', f'a 的父应为 A, 实际 {pm}')
        self.assertEqual(pm.get('b'), 'A', f'b 的父应为 A(兄弟), 实际 {pm}')
        self.assertEqual(pm.get('c'), 'A', f'c 的父应为 A(兄弟), 实际 {pm}')

    def test_nested_list_two_space(self):
        """B2: 两空格缩进子项挂父项下，第二个子项与第一个互为兄弟。"""
        rc, out, html_text = run_gen('## A\n- x\n  - x1\n  - x2\n- y\n')
        self.assertEqual(rc, 0, out)
        pm = parents_map(html_text)
        self.assertEqual(pm.get('x1'), 'x', f'x1 父应为 x, 实际 {pm}')
        self.assertEqual(pm.get('x2'), 'x', f'x2 父应为 x(与x1兄弟), 实际 {pm}')
        self.assertEqual(pm.get('y'), 'A', f'y 父应为 A, 实际 {pm}')

    def test_fence_content_as_pre_block(self):
        """B3: bash 围栏整体渲染为一个 <pre>，围栏标记不得漏进正文。"""
        rc, out, html_text = run_gen('## 配方\n\n```bash\ncmd1\ncmd2\ncmd3\n```\n')
        self.assertEqual(rc, 0, out)
        self.assertNotIn('```', html_text, '围栏标记漏进了正文')
        self.assertIn('<pre>cmd1\ncmd2\ncmd3</pre>', html_text, '围栏内容未作为完整 <pre> 保留')


class TestFlowParsing(unittest.TestCase):

    def test_colon_inside_node(self):
        """B4: 节点文本含半角冒号时不应被误判为标签而截断链。"""
        rc, out, html_text = run_gen('```flow\n检查 -> 端口:8080 -> 启动\n```\n')
        self.assertEqual(rc, 0, out)
        boxes = html_text.count('class="fbox')
        self.assertEqual(boxes, 3, f'应渲染 3 个节点框, 实际 {boxes} (含冒号节点被截断)')
        self.assertIn('检查', html_text)
        self.assertIn('8080', html_text)
        self.assertIn('启动', html_text)

    def test_colon_label_without_arrows(self):
        """B4b: 冒号后无箭头的行不是标签，整行作为单节点保留。"""
        rc, out, html_text = run_gen('```flow\n说明: 无箭头说明\n```\n')
        self.assertEqual(rc, 0, out)
        self.assertEqual(html_text.count('class="fbox'), 1)
        self.assertIn('说明: 无箭头说明', html_text)

    def test_multiple_labels(self):
        """B5: 同一 flow 块内两条带标签链，两个标签都应保留为各自题注。"""
        rc, out, html_text = run_gen('```flow\n链一: A -> B\n链二: C -> D\n```\n')
        self.assertEqual(rc, 0, out)
        self.assertIn('<div class="fcap">链一</div>', html_text, '首个标签丢失')
        self.assertIn('<div class="fcap">链二</div>', html_text)
        self.assertIn('A', html_text)
        self.assertIn('D', html_text)


class TestFenceRobustness(unittest.TestCase):

    def test_unclosed_flow_fence(self):
        """B6: 未闭合 flow 围栏 → 内容照常投影 + stderr 告警。"""
        rc, out, html_text = run_gen('## 节\n\n```flow\nA -> B\n')
        self.assertIn('A', html_text, '未闭合 flow 的内容被丢弃')
        self.assertIn('警告', out, '未闭合围栏未告警')

    def test_unclosed_code_fence(self):
        """B7: 未闭合普通围栏 → 内容照常投影 + stderr 告警。"""
        rc, out, html_text = run_gen('## 节\n\n```bash\ncmd1\ncmd2\n')
        self.assertIn('<pre>cmd1\ncmd2</pre>', html_text, '未闭合围栏的内容被丢弃')
        self.assertIn('警告', out, '未闭合围栏未告警')

    def test_tilde_fence(self):
        """B8: ~~~ 围栏内容同样保留。"""
        rc, out, html_text = run_gen('## 节\n\n~~~bash\ncmd1\n~~~\n')
        self.assertEqual(rc, 0, out)
        self.assertIn('cmd1', html_text)


class TestSecurityAndEscaping(unittest.TestCase):

    def test_xss_escaped(self):
        """B9 安全: 标题/列表/页面title/meta 中的 HTML 均转义。"""
        payload = '## <script>alert(1)</script>\n- <img src=x onerror=alert(2)>\n'
        rc, out, html_text = run_gen(payload, ['--title', '<b>ttl</b>',
                                               '--meta', '" onmouseover=alert(3) x="'])
        self.assertEqual(rc, 0, out)
        self.assertNotIn('<script>alert', html_text, '标题分支未转义')
        self.assertNotIn('<img src=x', html_text, '列表项未转义')
        self.assertIn('&lt;script&gt;', html_text)
        self.assertNotIn('<title><b>', html_text)

    def test_flow_node_escaped(self):
        """B10 安全: flow 节点与 pre 代码块中的 HTML 均转义。"""
        rc, out, html_text = run_gen('```flow\n<x> -> y\n```\n')
        self.assertEqual(rc, 0, out)
        self.assertNotIn('<x>', html_text.replace('&lt;x&gt;', ''))
        self.assertIn('&lt;x&gt;', html_text)
        rc, out, html_text = run_gen('## 节\n\n```bash\necho "<b>hi</b>"\n```\n')
        self.assertEqual(rc, 0, out)
        self.assertNotIn('<b>hi</b>', html_text, 'pre 代码块未转义')
        self.assertIn('&lt;b&gt;hi&lt;/b&gt;', html_text)


class TestCliErrorsAndEdges(unittest.TestCase):

    def test_missing_input(self):
        """B11 异常: 输入文件不存在 → 非零退出。"""
        with tempfile.TemporaryDirectory() as td:
            p = subprocess.run([sys.executable, str(GEN), '--in', str(Path(td) / 'nope.md'),
                                '--out', str(Path(td) / 'o.html')], capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)

    def test_output_dir_missing(self):
        """B12 异常: 输出目录不存在 → 非零退出。"""
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / 'i.md'
            src.write_text('## a\n', encoding='utf-8')
            p = subprocess.run([sys.executable, str(GEN), '--in', str(src),
                                '--out', str(Path(td) / 'nodir' / 'o.html')],
                               capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)

    def test_empty_md(self):
        """B13 边界: 空文件 → 仍产出默认标题 HTML。"""
        rc, out, html_text = run_gen('')
        self.assertEqual(rc, 0, out)
        self.assertIn('项目导览', html_text)

    def test_ordered_list_and_inline_md(self):
        """B14 边界: 有序列表按段落叶子处理; 行内 **加粗**/`代码` 原样保留不渲染。"""
        rc, out, html_text = run_gen('## 节\n\n1. 第一步\n\n**加粗**与`代码`\n')
        self.assertEqual(rc, 0, out)
        self.assertIn('第一步', html_text)
        self.assertIn('**加粗**', html_text)
        self.assertIn('`代码`', html_text)

    def test_h1_not_duplicated_when_title_given(self):
        """B15: h1 用作页面标题后不再作为分支重复出现。"""
        rc, out, html_text = run_gen('# 手册\n\n## 节\n- a\n', ['--title', '手册'])
        self.assertEqual(rc, 0, out)
        pm = parents_map(html_text)
        self.assertNotIn('手册', pm, f'h1 仍在树中重复: {list(pm)}')
        self.assertIn('<h1 class="page">手册</h1>', html_text)
        self.assertIsNone(pm.get('节'))
        self.assertEqual(pm.get('a'), '节', f'a 的父应为 节, 实际 {pm}')

    def test_h1_kept_when_title_differs(self):
        """B15b: --title 与 h1 不同名时，h1 是导览内容，保留为顶级分支。"""
        rc, out, html_text = run_gen('# 真手册\n\n## 节\n- a\n', ['--title', '另起的标题'])
        self.assertEqual(rc, 0, out)
        pm = parents_map(html_text)
        self.assertIn('真手册', pm, '不同名 h1 被误删')
        self.assertEqual(pm.get('节'), '真手册', f'## 应收进 h1 分支, 实际 {pm}')


class TestRealDocE2E(unittest.TestCase):

    def test_wechat_bot_onboarding(self):
        """C1 E2E: 真实 20KB 导览文档 → 完整性/标签平衡/零外部依赖。"""
        if not REAL_DOC.exists():
            self.skipTest('真实文档不存在')
        md = REAL_DOC.read_text(encoding='utf-8')
        rc, out, html_text = run_gen(md, ['--title', 'wechat-bot 项目导览'])
        self.assertEqual(rc, 0, out)
        print(f'\n    [E2E] {out.strip()}')
        bal = tag_balance(html_text)
        for tag, (o, c) in bal.items():
            self.assertEqual(o, c, f'{tag} 标签不配对: {bal}')
        from html import escape
        missing = []
        for t in tree_texts_of(md):
            if t not in html_text and escape(t) not in html_text:
                missing.append(t)
        self.assertEqual(missing, [], f'真实文档投影丢失 {len(missing)} 项: {missing[:10]}')
        self.assertNotRegex(html_text, r'(src|href)\s*=')

    def test_paragraph_before_sections_not_parent(self):
        """B16: 标题前的导语段落是纯叶子，不得成为后续章节的父分支。"""
        rc, out, html_text = run_gen('# 手册\n\n导语一句话。\n\n## A\n- x\n')
        self.assertEqual(rc, 0, out)
        pm = parents_map(html_text)
        self.assertIsNone(pm.get('A'), f'A 应为顶级分支, 实际 {pm}')
        self.assertEqual(pm.get('x'), 'A', f'x 的父应为 A, 实际 {pm}')
        self.assertIn('导语一句话。', pm)
        self.assertIsNone(pm['导语一句话。'], f'导语段落不应有子节点: {pm}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
