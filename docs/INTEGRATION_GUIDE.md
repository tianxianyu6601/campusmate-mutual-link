# CampusMate 模块接入指南

## 通用原则

1. 先调用 `data.data_loader.load_users()`，不要直接用CSV字符串。
2. 以 `user_id` 标识用户，不使用行号。
3. 不修改输入画像。
4. 新增输出字段应放在各模块自己的结果对象中，不塞回用户画像。
5. 需要改变用户Schema时，先修改 `data/schema.py` 并升级版本。

## 成员二：匹配算法

```python
from data.data_loader import load_users

users = load_users("data/generated/users_100.csv")
```

硬条件至少检查：

- `match_type` 相同；
- `activity` 相同或由算法明确定义为兼容；
- 双方有满足最短时长的连续共同 `available_times`；
- `acceptable_locations` 有交集；
- 双方的 `self_level` 都在对方 `acceptable_partner_levels` 中；
- 人数偏好和 `hard_restrictions` 不冲突。

方向分 `A -> B` 应使用A的 `preference_weights`。反方向使用B的权重，不能把两人的权重先平均。

组织角色适合按互补性计算：`organizer` 与 `participant` 可以比完全相同获得更高分；其他多数软偏好适合按相似度计算。

## 成员三：Streamlit界面

```python
from questionnaire.questions import get_questions
from questionnaire.profile_builder import build_profile

questions = get_questions(selected_match_type)
profile = build_profile(form_answers, user_id=assigned_user_id)
```

页面流程：

1. 先选择 `match_type`；
2. 再调用 `get_questions(match_type)` 获得正确活动和目标选项；
3. UI提交值使用每个选项的 `value`，显示 `label`；
4. 捕获 `ProfileValidationError`；
5. 从 `error.result.issues` 读取字段和中文错误；
6. 构建成功后再保存或传给算法。

题目中的 `input_type` 可直接映射到Streamlit控件：

```text
single_select -> st.selectbox / st.radio
multi_select  -> st.multiselect
rating        -> st.slider
long_text     -> st.text_area
```

## 成员四：AI解释与实验

文本语义字段：

- 用户A对B的期望匹配：`A.partner_expectation` 与 `B.self_description`；
- 用户B对A的期望匹配：`B.partner_expectation` 与 `A.self_description`。

兴趣相似度使用 `interests`，不要从中文描述中重复提取标准标签。

实验数据：

- 50人：开发和界面演示；
- 100人：主要实验；
- 200人：规模与运行时间实验。

`data/generated/quality_report.json` 提供每套数据的分布与校验结果。

## 推荐匹配结果接口

其他模块最终应向前端提供类似结构：

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
}
```

这不是用户画像Schema的一部分，应由算法或解释模块自行定义模型。
