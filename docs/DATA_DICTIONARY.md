# CampusMate 数据字典

## 契约信息

- Schema版本：`1.0.0`
- 用户ID：`U0001` 格式
- Python交换类型：`dict[str, object]`
- CSV编码：UTF-8
- CSV复合字段：JSON字符串
- 程序编码：英文小写 `snake_case`
- 中文标签：仅用于界面显示

## 字段表

| 字段 | Python类型 | CSV形式 | 必填 | 用途 |
|---|---|---|---|---|
| `schema_version` | `str` | 文本 | 是 | 数据契约版本，固定为`1.0.0` |
| `user_id` | `str` | 文本 | 是 | 匿名用户编号 |
| `match_type` | `str` | 文本 | 是 | `study`、`sport`、`interest` |
| `activity` | `str` | 文本 | 是 | 具体活动，必须属于搭子类型 |
| `available_times` | `list[str]` | JSON | 是 | 30分钟可用时间片 |
| `min_session_minutes` | `int` | 整数 | 是 | 最短连续活动时长，默认60 |
| `acceptable_locations` | `list[str]` | JSON | 是 | 可接受地点编码 |
| `allow_off_campus` | `bool` | `true/false` | 是 | 由地点列表自动推导 |
| `group_size_preference` | `str` | 文本 | 是 | 一对一、小组或均可 |
| `self_level` | `str` | 文本 | 是 | 用户自身水平 |
| `acceptable_partner_levels` | `list[str]` | JSON | 是 | 可接受对方水平 |
| `hard_restrictions` | `list[str]` | JSON | 是，可空列表 | 明确不可接受条件 |
| `goal` | `str` | 文本 | 是 | 活动目标，必须属于搭子类型 |
| `intensity` | `int` | 整数 | 是 | 期望强度，1—5 |
| `communication_style` | `str` | 文本 | 是 | 安静、平衡或互动 |
| `planning_style` | `str` | 文本 | 是 | 提前计划、灵活或临时 |
| `supervision_preference` | `int` | 整数 | 是 | 监督偏好，1—5 |
| `punctuality_importance` | `int` | 整数 | 是 | 准时重要性，1—5 |
| `cancellation_tolerance` | `int` | 整数 | 是 | 取消容忍度，1—5 |
| `organization_role` | `str` | 文本 | 是 | 组织者、平衡或配合者 |
| `interests` | `list[str]` | JSON | 是 | 标准兴趣标签 |
| `self_description` | `str` | 文本 | 是 | 用户活动习惯文本 |
| `partner_expectation` | `str` | 文本 | 是 | 对搭子的期望文本 |
| `preference_weights` | `dict[str,float]` | JSON | 是 | 七个软评分维度，总和为1 |

## 主要枚举

完整枚举及中文标签以 `data/vocabulary.py` 为唯一事实来源。其他模块不得复制维护另一套列表。

### 搭子类型

```text
study
sport
interest
```

### 水平

```text
novice
basic
intermediate
advanced
```

### 地点

```text
pku_library
teaching_building
sports_field
gymnasium
campus_common_area
off_campus_haidian
online
```

### 权重键

```text
time
goal
level
planning
interest
communication
text
```

## 画像示例

```python
{
    "schema_version": "1.0.0",
    "user_id": "U0001",
    "match_type": "study",
    "activity": "python",
    "available_times": ["wed_19_00", "wed_19_30", "wed_20_00"],
    "min_session_minutes": 60,
    "acceptable_locations": ["pku_library", "online"],
    "allow_off_campus": False,
    "group_size_preference": "one_to_one",
    "self_level": "basic",
    "acceptable_partner_levels": ["novice", "basic", "intermediate"],
    "hard_restrictions": ["no_off_campus"],
    "goal": "exam_prep",
    "intensity": 3,
    "communication_style": "balanced",
    "planning_style": "planned",
    "supervision_preference": 4,
    "punctuality_importance": 5,
    "cancellation_tolerance": 2,
    "organization_role": "balanced",
    "interests": ["programming", "ai"],
    "self_description": "我习惯在晚间按计划完成学习任务。",
    "partner_expectation": "希望对方守时，并愿意交流学习进度。",
    "preference_weights": {
        "time": 0.28846154,
        "goal": 0.23076923,
        "level": 0.11538462,
        "planning": 0.17307692,
        "interest": 0.07692308,
        "communication": 0.07692308,
        "text": 0.03846153
    }
}
```

实际权重应由 `build_profile()` 生成，不要手工填写近似值。
