# CampusMate

CampusMate 是一款面向北京大学学生的校园行动搭子匹配应用。用户先选择学习、运动或兴趣活动场景，再填写本周行动卡；系统根据活动、连续空闲时间、地点、目标、水平、相处方式和双向偏好寻找真正可以一起行动的搭子。

> 当前进度更新日期：2026-08-04  
> 用户画像 Schema：`1.0.0`  
> 当前界面语言：简体中文

## 一、交接前先看这里

- `README.md`：项目完整结构、实时完成状态、接口、运行和打包方式。
- [`HANDOFF.md`](HANDOFF.md)：Part1 数据契约、禁止破坏的字段规则和各成员接入要求。
- [`docs/INTEGRATION_GUIDE.md`](docs/INTEGRATION_GUIDE.md)：算法、界面和 AI 模块的接入说明。
- [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md)：用户画像全部字段及取值。
- 如果文档与实现不一致，以 `data/schema.py`、`data/vocabulary.py` 和自动测试为准。

任何成员或协作 AI 在修改用户字段、算法入口或结果结构前，都应先阅读以上文件并运行完整测试。

## 二、最终 `content.zip` 打包结构

最终提交建议采用以下结构。实验报告 PDF 与源码文件夹并列放置：

```text
content.zip
├── CampusMate/                         # 完整源代码
│   ├── README.md
│   ├── HANDOFF.md
│   ├── requirements.txt
│   ├── app.py
│   ├── data/
│   ├── questionnaire/
│   ├── algorithm/
│   ├── services/
│   ├── pages/
│   ├── visualization/
│   ├── ai/
│   ├── evaluation/
│   ├── docs/
│   ├── examples/
│   └── tests/
└── CampusMate实验报告.pdf              # 四人共同完成的实验报告
```

最终压缩包不要包含：

- `.venv/` 或 `venv/`；
- `__pycache__/`、`.pytest_cache/`；
- `.DS_Store`；
- 本地 IDE 配置；
- 临时截图、录屏原文件；
- 真实姓名、手机号、微信号、精确宿舍等敏感信息。

两分钟介绍视频按照课程要求单独上传网盘，不放进 `content.zip`，除非老师之后另有要求。

## 三、完整项目结构与完成状态

图例：`✅ 已完成`、`🚧 已完成一部分`、`⬜ 尚未完成`。

```text
CampusMate/
├── ✅ README.md                         项目总览、状态、接口、运行和打包说明
├── ✅ HANDOFF.md                        Part1正式交接与不可破坏契约
├── ✅ requirements.txt                  Python依赖
├── ✅ app.py                            Streamlit入口、导航、样式和共享状态
├── ✅ .streamlit/config.toml            Streamlit本地配置
├── ✅ .gitignore                        排除缓存、虚拟环境等本地文件
│
├── data/                                Part1：数据和Schema
│   ├── ✅ __init__.py
│   ├── ✅ vocabulary.py                 英文编码与中文标签唯一来源
│   ├── ✅ schema.py                     用户画像Schema 1.0.0与校验
│   ├── ✅ mock_data.py                  50/100/200人模拟数据生成
│   ├── ✅ data_loader.py                CSV加载、保存和质量校验
│   ├── ✅ users.csv                     50人标准基准数据
│   └── generated/
│       ├── ✅ users_050.csv             开发和界面演示
│       ├── ✅ users_100.csv             主要算法实验
│       ├── ✅ users_200.csv             规模与性能实验
│       └── ✅ quality_report.json       数据质量与生成信息
│
├── questionnaire/                       Part1：问卷和画像构建
│   ├── ✅ __init__.py
│   ├── ✅ questions.py                  三类场景各20道动态问卷
│   └── ✅ profile_builder.py            问卷答案转标准画像
│
├── algorithm/                           Part2：核心匹配算法
│   ├── ✅ __init__.py
│   ├── ✅ hard_filter.py                硬条件过滤与连续时间判断
│   ├── ✅ scoring.py                    各维度方向分
│   ├── ✅ reciprocal_score.py           双向满意度与调和平均
│   ├── ✅ graph_matching.py             最大权图匹配
│   ├── ✅ baseline.py                   随机和兴趣贪心基准
│   └── ✅ pipeline.py                   提供给前端的统一入口
│
├── services/                            跨模块连接层
│   ├── ✅ __init__.py
│   ├── ✅ i18n.py                       保留标准编码的界面标签工具
│   └── ✅ matching_adapter.py           Part2与前端之间的稳定适配层
│
├── pages/                               Part3：Streamlit页面
│   ├── ✅ __init__.py
│   ├── ✅ home.py                       首页与三类搭子选择
│   ├── ✅ questionnaire.py              动态问卷、校验和画像生成
│   ├── ⬜ matching.py                   匹配运行页面
│   └── ⬜ result.py                     匹配结果页面
│
├── visualization/                       Part3：可视化（目录尚未创建）
│   ├── ⬜ __init__.py
│   ├── ⬜ radar_chart.py                多维匹配分雷达图
│   ├── ⬜ network_graph.py              匹配关系网络图
│   └── ⬜ statistics_chart.py           算法实验统计图
│
├── ai/                                  Part4：AI能力
│   ├── ✅ __init__.py
│   ├── ✅ text_similarity.py            离线双向 TF-IDF 文本相似度
│   ├── ✅ explanation.py                可核验的匹配理由生成
│   └── ✅ icebreaker.py                 隐私友好的破冰问题生成
│
├── evaluation/                          Part4：实验评估
│   ├── ✅ __init__.py
│   ├── ✅ metrics.py                    匹配质量与完整性指标
│   ├── ✅ experiment.py                 三种算法对比实验
│   └── ✅ feedback.py                   匿名用户反馈与汇总
│
├── docs/                                Part1设计与接入文档
│   ├── ✅ DATA_DICTIONARY.md
│   ├── ✅ INTEGRATION_GUIDE.md
│   ├── ✅ MEMBER4_EXPERIMENT_GUIDE.md   AI、实验与答辩讲稿
│   └── ✅ QUESTIONNAIRE_DESIGN.md
│
├── examples/                            Part1最小使用示例
│   ├── ✅ build_profile_example.py
│   └── ✅ load_users_example.py
│
├── tests/
│   ├── ✅ __init__.py
│   ├── ✅ test_questions.py
│   ├── ✅ test_profile_builder.py
│   ├── ✅ test_mock_data.py
│   ├── ✅ test_data_loader.py
│   ├── ✅ test_dataset_quality.py
│   ├── ✅ test_matching_adapter.py
│   ├── ✅ test_ai_features.py            Part4 AI功能测试
│   ├── ✅ test_evaluation.py             Part4 评估功能测试
│   ├── ✅ test_filter.py                 Part2硬过滤测试
│   ├── ✅ test_scoring.py                Part2评分测试
│   ├── ✅ test_matching.py               Part2匹配流程测试
│   ├── ⬜ test_ui_helpers.py             Part3待补
│   └── ⬜ test_visualizations.py          Part3待补
│
├── ✅ 项目简介.md
└── ✅ 项目分工.md
```

## 四、各成员完成情况

| 成员 | 负责模块 | 当前状态 | 已完成或待完成内容 |
|---|---|---|---|
| Part1 | 用户画像与数据 | ✅ 已完成 | 问卷、Schema、画像构建、校验、模拟数据、数据加载、质量报告、文档和测试 |
| Part2 | 核心匹配算法 | ✅ 已完成 | 硬过滤、方向分、双向分、图匹配、基准算法和统一入口 |
| Part3 | 界面与可视化 | 🚧 进行中 | 已完成应用入口、首页、问卷页和匹配适配层；待完成匹配页、结果页和三个图表 |
| Part4 | AI解释与实验 | ✅ 已完成 | 离线文本语义匹配、可解释推荐、破冰问题、匿名反馈、实验指标与自动测试 |

### Part3 当前已经完成的工作

- 建立 `app.py`，统一管理页面配置、导航、侧栏样式和跨页面状态；
- 完成中文首页，可选择学习、运动或兴趣活动搭子；
- 完成动态问卷页面，不复制 Part1 题目或词表；
- 问卷提交值使用 Part1 英文编码，页面显示中文标签；
- 使用 `build_profile()` 生成并严格校验 Schema 1.0.0 用户画像；
- 使用匿名编号，不收集姓名、手机号、微信号和精确宿舍；
- 优化首页、侧栏、选项标签和提交按钮样式；
- 新增 `services/matching_adapter.py`，隔离 Part2 算法与页面；
- 支持 Part2 缺失检测、输入校验、结果规范化和显式演示模式；
- 新增适配层自动测试；当前完整测试共 26 项，全部通过。

## 五、安装与启动

以下命令都从项目根目录 `CampusMate/` 执行。

### 1. 创建环境并安装依赖

macOS / Linux：

```bash
cd "/Users/fengxinyi/Documents/FIN/CampusMate"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell：

```powershell
cd "你的路径\CampusMate"
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果项目已经有可用的 `.venv`，无需重复创建，直接激活即可。

### 2. 启动 Streamlit 应用

```bash
streamlit run app.py
```

也可以不激活环境，直接运行：

```bash
.venv/bin/streamlit run app.py
```

终端出现 `Local URL` 后在浏览器打开。当前可使用首页和问卷页；`matching.py` 与 `result.py` 创建后，`app.py` 会自动把它们加入导航。

### 3. Streamlit Cloud 邮件验证码配置

验证码邮件必须由一个“发件账号”或第三方邮件服务代发。用户输入的邮箱只是收件人邮箱，不能直接承担发信功能。

云端部署更推荐 SendGrid，因为它通过 HTTPS API 发信，不依赖云服务器连接 QQ SMTP：

```toml
mail_provider = "sendgrid"

[sendgrid]
api_key = "SG.xxxxxxxxxxxxxxxxx"
from_email = "已经在 SendGrid 验证通过的发件邮箱"
from_name = "CampusMate"
```

如果使用 QQ 邮箱 SMTP，则需要先在 QQ 邮箱网页版开启 SMTP 服务并生成 16 位授权码。这里的 `password` 不是 QQ 登录密码：

```toml
mail_provider = "smtp"

[smtp]
host = "smtp.qq.com"
port = 465
username = "真实QQ邮箱@qq.com"
password = "16位QQ邮箱SMTP授权码"
from_email = "真实QQ邮箱@qq.com"
use_tls = false
use_ssl = true
```

如果在 Streamlit Cloud 上使用 QQ 邮箱出现 `Connection unexpectedly closed`，通常是 QQ SMTP 服务端断开了云服务器连接。此时应改用 SendGrid，或换一个明确允许云服务器 SMTP 登录的发件邮箱服务。

### 4. 停止应用

回到运行 Streamlit 的终端，按：

```text
Control + C
```

## 六、Part1 稳定接口

### 1. 获取动态问卷

```python
from questionnaire.questions import get_questions

questions = get_questions("study")
```

`match_type` 只能是：

```text
study    学习搭子
sport    运动搭子
interest 兴趣活动搭子
```

每道题向页面提供 `label`、`value`、`input_type`、`required` 等信息。前端展示 `label`，保存和提交 `value`。

### 2. 构建用户画像

```python
from questionnaire.profile_builder import build_profile

profile = build_profile(form_answers, user_id="U0001")
```

失败时抛出：

```python
from data.schema import ProfileValidationError
```

页面可以从 `error.result.issues` 读取具体字段、错误代码和说明。

### 3. 校验画像

```python
from data.schema import validate_profile

result = validate_profile(profile)
if not result.is_valid:
    for issue in result.issues:
        print(issue.field, issue.code, issue.message)
```

### 4. 加载用户数据

```python
from data.data_loader import load_users

users = load_users("data/users.csv")
```

不要手动解析 CSV。列表、字典和布尔字段都应由 `load_users()` 还原并校验。

### 5. 重新生成模拟数据

```bash
python -m data.mock_data --sizes 50 100 200
```

默认随机种子为 `20260802`。

## 七、Part2 接入接口

Part2 不应让 Streamlit 页面直接导入 `hard_filter.py`、`scoring.py` 等内部文件。请提供以下任意一个统一入口：

```text
algorithm.pipeline.run_matching
```

或：

```text
algorithm.matching.run_matching
```

推荐函数签名：

```python
def run_matching(current_profile, candidates, *, top_k=3):
    ...
    return matches
```

参数含义：

| 参数 | 类型 | 说明 |
|---|---|---|
| `current_profile` | `dict` | 问卷刚生成的 Schema 1.0.0 当前用户画像 |
| `candidates` | `list[dict]` | 通过 `load_users()` 加载的候选画像 |
| `top_k` | `int` | 最多返回几名候选人 |

Part2 可以返回以下三种形式之一：

```python
# 单条结果
match

# 多条结果
[match_1, match_2]

# 带 matches 的结果
{"matches": [match_1, match_2]}
```

每条 `match` 的标准格式：

```python
{
    "user_a": "U0001",
    "user_b": "U0017",
    "score": 86.3,
    "dimension_scores": {
        "time": 95.0,
        "goal": 90.0,
        "level": 85.0,
        "planning": 82.0,
        "interest": 73.0,
        "communication": 78.0,
        "text": 70.0,
    },
    "reasons": ["空闲时间高度重合", "学习目标一致"],
    "common_times": ["wed_19_00", "wed_19_30"],
    "common_locations": ["pku_library"],
}
```

接口要求：

- `user_a` 和 `user_b` 必须是两个不同的匿名编号；
- 当前用户必须出现在 `user_a` 或 `user_b` 中；
- `score` 和所有维度分必须位于 `0—100`；
- `dimension_scores` 至少包含一个前端支持的维度；
- 支持的维度为 `time`、`goal`、`level`、`planning`、`interest`、`communication`、`text`；
- `reasons` 至少包含一条非空说明；
- 不要把匹配分和结果写回用户画像；
- 不要修改 Part1 Schema；
- 时间硬过滤必须检查连续共同时间达到双方 `min_session_minutes`，不能只检查一个共同半小时时间片。

Part3 统一通过适配层调用：

```python
from services.matching_adapter import load_candidate_pool, run_matching

candidates = load_candidate_pool()
matching_run = run_matching(
    current_profile,
    candidates,
    top_k=3,
)
```

适配层会自动校验 Part1 输入、检查 Part2 输出、按分数排序并限制结果数量。

## 八、Part2 接入检查与演示模式

检查真实算法是否已连接；当前应返回 `mode: "part2"` 和 `algorithm.pipeline.run_matching`：

```bash
python -m services.matching_adapter
```

`allow_demo=True` 只在 Part2 后端缺失时启用演示数据。当前真实算法已存在，因此以下命令仍会优先返回真实 Part2 结果：

```bash
python -m services.matching_adapter --demo --top-k 3
```

指定演示用户：

```bash
python -m services.matching_adapter --demo --user-id U0005 --top-k 3
```

如果未来临时移除 Part2，页面开发时必须显式开启演示模式：

```python
matching_run = run_matching(
    current_profile,
    candidates,
    top_k=3,
    allow_demo=True,
)
```

返回结果包含：

```python
{
    "contract_version": "1.0.0",
    "mode": "demo",          # 或真实算法的 part2
    "algorithm": "界面演示数据",
    "query_user_id": "U0001",
    "candidate_count": 49,
    "matches": [...],
    "warnings": [...],
}
```

`mode == "demo"` 时，页面必须明确显示“演示数据”，不能在报告、视频或答辩中当作真实算法结果。当前正常整合流程应使用 `mode == "part2"`。

## 九、Part3 页面状态接口

`app.py` 统一维护以下 `st.session_state`：

| 状态键 | 含义 |
|---|---|
| `selected_match_type` | 首页选择的 `study`、`sport` 或 `interest` |
| `questionnaire_answers` | 当前问卷原始答案 |
| `current_profile` | 通过 Part1 校验的当前用户画像 |
| `matching_run` | 适配层返回的一次完整匹配运行结果 |
| `current_match` | 用户正在查看的一条匹配结果 |

页面流程：

```text
home.py
  ↓ 选择搭子类型
questionnaire.py
  ↓ build_profile()生成current_profile
matching.py
  ↓ matching_adapter.run_matching()生成matching_run
result.py
  ↓ 展示current_match与可视化
```

更换搭子类型时，首页会清除旧问卷、画像和匹配结果，避免不同场景的数据混用。

## 十、运行测试

运行完整测试：

```bash
python -m unittest discover -s tests -p "test_*.py"
```

显示每项测试名称：

```bash
python -m unittest discover -s tests -v
```

当前状态：

```text
Ran 51 tests
OK
```

Part2 接入前后都必须重新运行完整测试。Part2 至少补充：

- 无共同连续时间时不能匹配；
- 地点无交集时不能匹配；
- 等级不在双方接受范围时不能匹配；
- 硬限制冲突时不能匹配；
- 双向分使用双方各自权重；
- 总分和维度分处于 `0—100`；
- 同一用户不能重复匹配；
- 奇数用户和完全无兼容对象时能安全返回；
- 50、100、200人数据均能运行。

## 十一、最终打包命令

先把最终报告命名为：

```text
CampusMate实验报告.pdf
```

并放到 `/Users/fengxinyi/Documents/FIN/`，与 `CampusMate/` 文件夹并列。然后执行：

```bash
cd "/Users/fengxinyi/Documents/FIN"
zip -r content.zip CampusMate CampusMate实验报告.pdf \
  -x "CampusMate/.venv/*" \
     "CampusMate/venv/*" \
     "*/__pycache__/*" \
     "*.pyc" \
     "*/.DS_Store" \
     "*/.pytest_cache/*"
```

检查压缩包内容：

```bash
unzip -l content.zip
```

打包前最后运行：

```bash
cd "/Users/fengxinyi/Documents/FIN/CampusMate"
python -m unittest discover -s tests -v
streamlit run app.py
```

确认首页、三类问卷、匹配流程、结果页和图表均可操作后，再生成最终 `content.zip`。

## 十二、团队协作规则

1. 不复制 `data/vocabulary.py` 中的活动、地点、等级和标签列表。
2. 不手动解析 CSV，统一调用 `load_users()`。
3. 不使用 `category` 代替 `match_type`。
4. 不改变用户编号 `U0001` 格式。
5. 不把算法输出字段塞回 Part1 用户画像。
6. 不在页面中直接依赖 Part2 内部实现，统一经过 `matching_adapter.py`。
7. 如确实需要修改 Schema，必须升级版本、同步数据字典、重建数据并更新测试。
8. 提交前四人共同检查 README、实验报告、视频内容和完整测试结果。

当前推荐的下一步是：Part3 完成 `pages/matching.py`、`pages/result.py` 和 `visualization/`，直接通过 `matching_adapter.py` 调用已接入的 Part2 真实算法。
