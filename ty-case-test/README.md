# ty-case-test

`ty-case-test` 是一个用于生成 QA 测试用例的 Codex skill。它把需求内容拆解成结构化测试用例，并通过脚本生成 XMind 文件。

## 能力范围

适合处理：

- 根据需求文本生成测试用例。
- 根据 Word 文档提取出的需求内容生成测试用例。
- 根据 H5 或网页需求内容生成测试点。
- 将测试用例输出为 `.xmind` 文件。
- 补充异常、边界、缓存、权限、兼容性等测试场景。

当前版本的脚本只负责“结构化 JSON 到 XMind”。Word 和 H5 内容需要先由 Codex、浏览器工具或用户提供的文本完成提取。

## 多端拆分规则

当需求正文显式提到端名时，必须先按端拆分测试用例，不能把不同端合并成同一条 case。适用的标准端标签为：

- `iOS`
- `Android内发包`
- `Android外发包`
- `Android`
- `小程序`
- `H5`

执行规则：

- 需求里点名的端，每个端单独建一级分组。
- 即使业务流程看起来一致，也要分别生成该端自己的用例。
- 当需求已点名多个端时，共性场景要分别落到每个已识别端下面，不生成一条通用 case。
- 如果同一需求里同时出现 `Android内发包`、`Android外发包` 和笼统的 `Android`/`安卓` 表述，则笼统 Android 场景默认同时分摊到内发包和外发包，除非原文明确限制。

## 目录结构

```text
ty-case-test/
├── SKILL.md
├── README.md
├── examples/
│   ├── sample_requirement.md
│   └── sample_cases.json
├── references/
│   └── xmind_template.md
└── scripts/
    └── generate_xmind.py
```

## 快速开始

在 skill 目录下运行：

```powershell
python -B scripts/generate_xmind.py --input examples/sample_cases.json --output TEMP/sample_test_cases.xmind --overwrite
```

生成成功后，脚本会输出端数、模块数、用例数、topic 数和文件路径。

只校验输入 JSON，不生成 XMind：

```powershell
python -B scripts/generate_xmind.py --input examples/sample_cases.json --validate-only
```

生成内置 demo：

```powershell
python -B scripts/generate_xmind.py --demo --output TEMP/demo_test_cases.xmind --overwrite
```

## 输入 JSON 格式

脚本同时支持新版“端优先”结构和旧版单层结构。

### 新版结构

```json
{
  "project_name": "搜索功能测试用例",
  "platforms": [
    {
      "name": "iOS",
      "modules": [
        {
          "name": "入口",
          "cases": [
            {
              "title": "验证首页搜索入口展示",
              "purpose": "验证 iOS 端首页顶部搜索入口按配置正常展示",
              "steps": ["打开 iOS 端 App 并进入首页", "查看页面顶部搜索区域"],
              "expected": ["首页加载完成", "顶部展示搜索框、购物车入口和消息入口"]
            }
          ]
        }
      ]
    }
  ]
}
```

### 旧版兼容结构

```json
{
  "project_name": "搜索功能测试用例",
  "modules": [
    {
      "name": "入口",
      "cases": [
        {
          "title": "验证首页搜索入口展示",
          "purpose": "验证首页顶部搜索入口按配置正常展示",
          "steps": ["进入首页", "查看页面顶部搜索区域"],
          "expected": ["页面顶部展示搜索框", "搜索框旁展示购物车和消息入口"]
        }
      ]
    }
  ]
}
```

接口规则：

- 新结构使用 `platforms[].name -> modules[].name -> cases[]`。
- 旧结构继续支持 `modules[].name -> cases[]`。
- 顶层 `platforms` 和 `modules` 不能同时出现；同时出现时脚本会直接报错。

完整字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `project_name` | 是 | XMind 根主题 |
| `platforms[].name` | 新结构必填 | 端名称 |
| `platforms[].modules[].name` | 新结构必填 | 业务模块名称 |
| `modules[].name` | 旧结构必填 | 模块名称 |
| `cases[].title` | 是 | 用例标题，仅用于 JSON 可读性，不输出到 XMind |
| `cases[].purpose` | 是 | 测试目的 |
| `cases[].prerequisites` | 否 | 前置条件，字符串或数组；为空时输出 `前置条件：无` |
| `cases[].steps` | 是 | 测试步骤，非空数组 |
| `cases[].expected` | 是 | 预期结果，非空数组 |

## 输出结构

新版端优先结构生成的 XMind 层级：

```text
项目名称
├── iOS
│   ├── 入口
│   │   └── 测试目的：...
│   └── 异常场景
└── Android内发包
    └── 入口
```

旧版兼容结构生成的 XMind 层级：

```text
项目名称
├── 模块
│   └── 测试目的：...
└── ...
```

XMind 输出不包含用例编号、优先级、标签或备注节点。每条用例固定按 `测试目的 -> 前置条件 -> 测试步骤 -> 预期结果` 递进展示；`测试步骤` 和 `预期结果` 都是单个 XMind 节点，节点标题内用多行文本展示序号列表，不为每一步或每条结果单独生成子节点。

## 验证规则

脚本会在生成前检查：

- `project_name` 是否存在。
- 是否只使用一种顶层结构。
- 新结构中的 `platforms` 是否是非空数组。
- 旧结构中的 `modules` 是否是非空数组。
- 每个端、模块是否有 `name`。
- 每条用例是否有 `title`、`purpose`、`steps`、`expected`。
- `steps` 和 `expected` 是否为非空数组。

脚本会在生成后检查：

- 输出文件是否是 zip。
- 是否包含 `content.xml`、`meta.xml`、`styles.xml`、`META-INF/manifest.xml`。
- `content.xml` 是否能解析。
- topic 数量是否大于 0。

## 常见问题

### 生成的文件打不开

先确认脚本输出没有验证失败。如果文件被旧版本 XMind 拒绝打开，可解压检查 `content.xml` 是否存在，并确认 XMind 客户端支持该格式。

### 预期结果和步骤数量不一致

脚本会给出 warning，但仍会生成文件。建议人工确认是否需要补充缺失的预期结果。

### 能否直接传 Word 或 H5 链接

当前脚本不能直接解析 Word 或抓取网页。应先提取需求正文，再生成结构化 JSON，最后调用脚本生成 XMind。

## 已知限制

- 不直接解析 `.docx`、`.doc` 或网页链接。
- 不验证 XMind 客户端是否能渲染每个样式属性。
- 不根据需求自动判断所有业务规则，复杂规则仍需要人工确认。
