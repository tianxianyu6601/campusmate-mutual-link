# CampusMate 平台数据字典（阶段 3）

版本：4
适用后端：本地 SQLite、线上 PostgreSQL
时间字段：统一保存 Unix 秒级时间戳；所有业务时间在页面层显示为北京时间。

## 设计约定

- 用户邮箱统一转为小写，是账号和资料的稳定主键。
- 业务实体使用带前缀的 UUID 文本主键，例如 `act_...`、`round_...`。
- 页面不能直接写数据库，必须调用 `services/platform_service.py`。
- PostgreSQL 审批使用行锁；SQLite 使用 `BEGIN IMMEDIATE`。活动容量检查、成员写入、申请状态更新和邮件任务入队在同一事务内完成。
- JSON 只保存结构会变化且不需要数据库筛选的数据；需要筛选或唯一约束的数据均拆成关系表。

## 账号与登录

### `users`

| 字段 | 类型 | 约束 / 含义 |
|---|---|---|
| `email` | TEXT | 主键，规范化邮箱 |
| `user_id` | TEXT | 唯一，旧匹配算法使用的匿名编号 |
| `password_hash` | TEXT | PBKDF2 密码摘要 |
| `salt` | TEXT | 每个账号独立盐值 |
| `verified` | INTEGER | 0/1，邮箱是否验证 |
| `created_at` | INTEGER | 创建时间 |

### `verification_codes`

短期邮箱验证码。每个邮箱只有一个有效记录；保存验证码摘要、过期时间和失败次数。

### `login_sessions`

服务端登录会话。主键是浏览器随机令牌的 SHA-256 摘要，不保存明文令牌；包含可恢复页面状态和过期时间。

### `user_profiles`

兼容旧匹配算法的原始问卷 JSON。阶段 2 保留此表；新平台资料使用下方规范化表。

### `notifications`

兼容旧即时匹配邮件记录。新异步通知统一写入 `email_tasks`。

## 个人资料

### `profiles`

每个用户一条规范化资料，主键 `email` 外键关联 `users`。包含：

- 昵称、头像 Data URL、学校、院系、年级、身份、简介；
- MBTI、内外向、计划方式、慢热程度、群体规模偏好；
- “我是什么样的人”和“我想找什么样的人”；
- 邮箱/微信联系方式；
- 空闲时间 JSON、常用地点 JSON、最大距离、跨校偏好；
- 资料完整度、创建时间、更新时间。

头像仅接受 PNG、JPEG 或 WebP，服务层按文件签名校验且解码后不得超过 750 KB。资料完整度由服务端依据十组信息计算，客户端提交值不会被采用。

参加周期匹配前必须具备：昵称、学校、至少一个兴趣、至少一个空闲时间、至少一个常用地点，以及两段“自我描述/期待对象”文字。报名服务会再次校验这些条件，不能只靠页面提示绕过。

### `profile_interests`

复合主键 `(email, category, tag)`，防止重复标签。分类为 `study`、`sport`、`social`、`entertainment`、`travel`、`share` 或 `custom`；其中 `share` 对应“拼一切”。

### `profile_privacy`

复合主键 `(email, field_name)`。可见范围：`private`（仅自己）、`matched`（已匹配搭子）、`activity_members`（共同活动成员）、`public`（所有已登录用户）。头像、院校身份、简介、兴趣、性格、时间地点、两段描述及联系方式均可独立设置。服务层会根据真实活动成员和匹配结果过滤字段，不能由前端自行决定是否显示。

## 自由组局

### `activities`

| 关键字段 | 含义 |
|---|---|
| `activity_id` | 活动 UUID |
| `organizer_email` | 发起人，只允许此人修改/审批/取消 |
| `category` / `custom_category` | 标准分类或自定义分类 |
| `title` / `description` / `image_url` | 展示内容 |
| `starts_at` / `ends_at` | 开始和结束时间 |
| `location_text` | 活动地点 |
| `capacity` | 2–100，包含发起人 |
| `visibility` | `campus`、`public`、`invite` |
| `approval_required` | 是否需要发起人审批 |
| `status` | `draft`、`published`、`full`、`ended`、`cancelled` |
| `version` | 更新版本，供后续乐观并发控制 |

阶段 4 约定：

- 创建时只允许 `draft` 或 `published`；草稿仅发起人可见，发布后所有符合可见范围的已登录用户立即可见。
- `invite` 活动仅发起人和正式成员可见；`campus`、`public` 在当前登录后平台中均对已登录用户开放。
- 编辑仅允许发起人执行，并核对 `version` 防止旧页面覆盖新数据；活动人数不能调低到当前成员数以下。
- 到达已填写的结束时间后，列表或详情读取会将 `published/full` 自动转换为 `ended`；发起人也可主动结束或取消。
- 第一版活动封面以 PNG/JPEG/WebP Data URL 保存，解码后不超过 1 MB；未上传时页面使用分类图标。

### `activity_applications`

主键 `application_id`；`(activity_id, applicant_email)` 唯一，数据库层阻止重复申请。状态为 `pending`、`approved`、`rejected`、`withdrawn`。

### `activity_members`

复合主键 `(activity_id, member_email)`，数据库层阻止重复入组。角色为 `organizer` 或 `member`。创建活动时发起人立即作为成员写入，因此容量始终按总人数计算。

## 周期匹配

### `match_rounds`

保存报名开放、报名截止和结果发布时间。状态为 `planned`、`open`、`closed`、`matching`、`published`、`cancelled`。

### `match_enrollments`

复合主键 `(round_id, email)`，保证每轮每人只能报名一次。状态为 `enrolled`、`withdrawn`、`matched`、`unmatched`。

### `match_profile_snapshots`

报名时冻结该轮使用的资料和兴趣 JSON，并保存 SHA-256 摘要。之后修改个人资料不会悄悄改变已经开始的匹配输入。

### `match_results`

保存一组匹配的 0–100 分数和可解释结果 JSON。

### `match_result_members`

保存每组的两个席位。`(result_id, seat)` 唯一；`(round_id, email)` 唯一，数据库层保证同一轮一个人最多出现在一个结果中。

## 通知与审计

### `email_tasks`

持久邮件任务队列。`idempotency_key` 唯一，避免页面刷新或重复请求造成重复邮件。状态为 `queued`、`sending`、`sent`、`failed`、`dead`；保存重试次数、下次重试时间和最后错误，但不保存邮箱服务密钥。

### `audit_log`

不可由普通页面修改的业务审计记录，包含操作人、动作、实体类型、实体 ID、非敏感详情 JSON 和时间。密码、验证码、会话令牌、邮件密钥不得进入审计详情。

### `schema_migrations`

数据库迁移版本表。当前最新版本为 3；迁移脚本可重复执行，已经成功应用的版本不会再次执行。版本 3 新增头像字段，并在保留原有兴趣数据的前提下加入 `share` 分类。

## 关键关系与删除规则

- 删除用户时，其新资料、兴趣和隐私设置级联删除。
- 删除活动时，申请和成员级联删除。
- 删除匹配轮次时，报名、快照、结果及结果成员级联删除。
- 活动发起人、申请人、成员、轮次创建者和匹配参与人必须是已存在用户。
