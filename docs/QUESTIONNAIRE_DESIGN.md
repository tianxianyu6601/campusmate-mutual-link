# CampusMate 问卷设计

## 设计目标

问卷用于构建“本周行动画像”，回答用户是否真的能与另一名用户完成一次具体活动。每种匹配类型均展示20道题，题目定义位于 `questionnaire/questions.py`。

前端必须从 `get_questions(match_type)` 读取题目，不应复制题目文本或自行维护选项。

## 20道题

| 序号 | ID | 内容 | 类型 | 条件性质 |
|---:|---|---|---|---|
| 1 | `match_type` | 搭子类型 | 单选 | 硬条件 |
| 2 | `activity` | 本周具体活动 | 单选 | 硬条件 |
| 3 | `available_times` | 本周可用时间 | 多选 | 硬条件 |
| 4 | `acceptable_locations` | 可接受地点 | 多选 | 硬条件 |
| 5 | `group_size_preference` | 人数形式 | 单选 | 硬条件 |
| 6 | `self_level` | 自身水平 | 单选 | 硬条件 |
| 7 | `acceptable_partner_levels` | 可接受搭子水平 | 多选 | 硬条件 |
| 8 | `hard_restrictions` | 明确限制 | 多选，可空 | 硬条件 |
| 9 | `goal` | 活动目标 | 单选 | 软偏好 |
| 10 | `intensity` | 活动强度 | 1—5 | 软偏好 |
| 11 | `communication_style` | 交流方式 | 单选 | 软偏好 |
| 12 | `planning_style` | 规划方式 | 单选 | 软偏好 |
| 13 | `supervision_preference` | 监督程度 | 1—5 | 软偏好 |
| 14 | `punctuality_importance` | 准时重要性 | 1—5 | 软偏好 |
| 15 | `cancellation_tolerance` | 临时取消容忍度 | 1—5 | 软偏好 |
| 16 | `organization_role` | 组织角色 | 单选 | 软偏好 |
| 17 | `interests` | 兴趣标签 | 多选 | 软偏好 |
| 18 | `self_description` | 活动习惯描述 | 长文本 | 软偏好/AI |
| 19 | `partner_expectation` | 理想搭子描述 | 长文本 | 软偏好/AI |
| 20 | `preference_priorities` | 最重视的1—3个因素 | 多选 | 个性化权重 |

## 条件选项

`activity` 和 `goal` 的选项根据 `match_type` 动态变化：

- `study`：Python、高数、线代、英语、算法、课程项目等；
- `sport`：跑步、羽毛球、游泳、健身、骑行、篮球、乒乓球；
- `interest`：电影、展览、讲座、摄影、桌游、演出、探店、城市探索。

## 时间设计

时间以30分钟时间片保存，例如：

```text
wed_19_00  = 周三 19:00—19:30
wed_19_30  = 周三 19:30—20:00
```

Schema默认 `min_session_minutes=60`。成员二应检查双方是否存在至少两个连续共同时间片，而不是只判断集合交集非空。

## 权重设计

基础权重来自项目方案：

| 维度 | 基础权重 |
|---|---:|
| 时间 | 0.25 |
| 目标 | 0.20 |
| 水平 | 0.15 |
| 规划 | 0.15 |
| 兴趣 | 0.10 |
| 交流 | 0.10 |
| 文本 | 0.05 |

用户选择的重点维度会获得1.5倍提升，随后重新归一化。最终权重存入 `preference_weights`，总和严格为1。

## 隐私边界

问卷不得增加真实姓名、手机号、微信号、精确宿舍、照片、收入或家庭背景。系统以随机编号识别用户，演示仅展示匹配结果，不交换联系方式。
