# 成员四：AI 功能与实验评估

本模块完成 CampusMate 的可解释 AI 和实验评估部分，全部核心功能离线运行，不需要 API Key，也不会把行动卡文本上传到外部服务。

## 已完成的代码

| 文件 | 用途 |
| --- | --- |
| `ai/text_similarity.py` | 中文/英文兼容的 TF-IDF 与余弦相似度；按 A 的期望对 B 的自我描述、B 的期望对 A 的自我描述分别打分。 |
| `ai/explanation.py` | 从共同时间、地点、目标、兴趣、交流方式和文本契合度生成可核验理由。 |
| `ai/icebreaker.py` | 根据共同活动和兴趣生成不涉及联系方式的破冰问题。 |
| `evaluation/feedback.py` | 验证匿名反馈并统计匹配评分、解释帮助度与继续沟通意愿。 |
| `evaluation/metrics.py` | 统计匹配人数、覆盖率、平均分、最低分，并检测重复匹配和越界分数。 |
| `evaluation/experiment.py` | 将成员二的三种算法以相同数据集、相同指标比较，并导出 JSON 实验结果。 |

## 与成员二算法联调

成员二分别提供“随机匹配”“兴趣贪心”“双向全局匹配”三个函数。每个函数接收用户画像列表，返回如下列表：

```python
[
    {"user_a": "U0001", "user_b": "U0002", "score": 86.5},
]
```

然后在项目根目录运行：

```python
from data.data_loader import load_users
from evaluation.experiment import compare_algorithms, save_experiment_report

users = load_users("data/generated/users_100.csv")
report = compare_algorithms(
    users,
    {
        "随机匹配": random_match,
        "兴趣贪心": greedy_match,
        "双向全局匹配": reciprocal_global_match,
    },
)
save_experiment_report(report, "evaluation/results/users_100.json")
```

分别对 50、100、200 人数据运行一次。报告中比较平均匹配分、最低匹配分、匹配率、完整性违规数与运行时间；其中完整性违规数应为 0。

## 报告可直接使用的实验分析表述

本项目在同一组可复现模拟数据上比较三类匹配策略。随机匹配用于提供下限基准；兴趣贪心匹配只依据局部兴趣相似度；双向全局匹配同时考虑双方满意度，并在满足硬约束的候选图上寻求整体更优配对。除平均匹配分外，实验还报告最低匹配分、匹配覆盖率、运行时间和输出完整性。这样既能观察推荐质量，也能验证系统不会出现同一用户被重复匹配或分数越界等基本错误。

## 成员四答辩/视频讲稿（约 20 秒）

“我负责 AI 解释和实验评估。系统不用联网模型，而是用本地 TF-IDF 和余弦相似度，分别比较双方的搭子期待与自我描述，因此能得到双向的文本契合度。再结合共同时间、地点和兴趣，生成可核验的推荐理由与破冰问题。实验部分统一比较三种算法的平均分、覆盖率、运行时间，并自动检测重复匹配和异常分数，保证结果可靠。”
