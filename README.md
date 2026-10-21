# project-onboarding · 项目上手手册 Skill

面向 AI 编码 agent（ZCode / Claude Code 等）的 skill：接手陌生项目时，产出**两件套**——

1. **项目导览**（markdown）：面向 AI 会话的上手手册，唯一事实源
2. **可视化 HTML**：思维导图折叠树 + 流程图，由 `scripts/gen_visual.py` 从导览**机械生成**，给项目负责人看

关键设计：可视化是导览的**投影**——不在 HTML 里手写任何导览没有的内容。没有手工排版、没有评审轮，导览改了重新跑一遍生成器即可。

## 文件

```
project-onboarding/
├── SKILL.md              # skill 本体：九节导览骨架 + 操作纪律（agent 读这个）
├── scripts/
│   └── gen_visual.py     # 导览 markdown → 自包含 HTML 生成器（纯标准库，零依赖）
├── tests/
│   └── test_gen_visual.py  # 黑盒回归套件（unittest，24 用例；python3 tests/test_gen_visual.py -v）
└── README.md
```

## 安装

把本目录放入 agent 的用户级 skills 目录（以 ZCode 为例）：

```bash
git clone https://github.com/Aij2022/project-onboarding.git ~/.agents/skills/project-onboarding
```

新开会话即生效；也可在会话中显式调用 `/project-onboarding`。

## 导览的九节骨架

1. 这是什么项目（3 句话）
2. 30 秒现状（指向体检脚本 + 健康判读）
3. 文档地图与阅读顺序（上下文经济学：明确哪些文档**别整读**）
4. 硬性纪律红线（凭据零暴露 / 备份命名法 / 操作白名单 / 登记义务）
5. 常用操作配方（可复制命令块）
6. 实施轮 checklist 模板
7. 代码地图（按函数/模块名锚点，**不写行号**）
8. 日志事件字典
9. 陷阱清单（本项目特有坑）

## 生成可视化

```bash
python3 scripts/gen_visual.py --in 导览.md --out 图谱.html --title "XX 项目导览" --meta "快照 2026-10-20"
```

解析规则（导览按此写，即可被机械生成）：

- `##` / `###` / `####` → 思维导图分支层级；同级列表项互为兄弟，段落与代码块是纯叶子
- `-` / `*` 列表项 → 叶子（两空格缩进 = 下一层）
- ` ```flow ` 围栏块 → 流程图，每行一条链：`节点A -> 节点B -> 节点C`，行首 `标签:` 为该链命名（同一块内多条链可各带标签）
- 其它代码围栏原样保留为 `<pre>` 代码块；围栏未闭合时内容照常投影并 stderr 告警

输出为单文件 HTML：`<details>/<summary>` 折叠树 + CSS 流程行，**零 JS 零外部依赖**，离线可开、打印友好。

```flow
示例流程: 摸底盘点 -> 配套脚本先行 -> 写导览 -> 生成可视化 -> 登记交付
```

## 设计原则

- **双读者**：导览给未来 AI 会话（省上下文、可验证），可视化给项目负责人
- **事实三源**：只写验证过的；引用不复制；编年史用指针不抄写
- **凭据只有路径与纪律，没有值**
- 导览头部放快照块（日期 / 快照 commit / FRESH-AGING-STALE 新鲜度），过期先复核再信
