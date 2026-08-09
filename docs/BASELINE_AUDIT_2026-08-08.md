# CampusMate 阶段 0 基线审计报告

审计日期：2026-08-08
审计范围：Git 基线、线上可达性、Streamlit 页面与会话、SQLite 数据库、邮件服务、问卷、匹配算法、测试和部署约束。

## 1. 结论

- 当前代码基线可稳定回归：63 项自动化测试全部通过，Python 编译检查通过。
- 当前回滚基线为 `main` 分支提交 `972feb267244de9ae654e25d2e2f746a2c659852`，本地 `HEAD` 与 `origin/main` 一致。
- 线上网站 `https://campusmate-mutual-link.streamlit.app/` 可访问，显示 CampusMate 登录页，本次只读检查未发现浏览器控制台错误。
- 线上页面不公开构建 SHA，故不能仅凭页面证明当前运行实例的精确提交；后续部署必须展示版本号或提交短 SHA。
- 当前 SQLite 数据库完整性正常并已生成校验一致的本地备份，但 Streamlit Community Cloud 不保证本地文件持久性，不能继续把线上业务数据长期保存在应用目录。
- 阶段 0 没有修改任何 Python 业务代码、数据库内容、依赖或线上部署。

## 2. 可回滚基线

| 项目 | 基线 |
|---|---|
| Git 分支 | `main` |
| 本地 HEAD | `972feb267244de9ae654e25d2e2f746a2c659852` |
| `origin/main` | `972feb267244de9ae654e25d2e2f746a2c659852` |
| 提交说明 | `Fix password reset dialog overlay` |
| Python 依赖约束 | `streamlit>=1.36,<2.0`、`networkx>=3,<4` |
| 审计环境 | Streamlit `1.61.1`、NetworkX `3.6.1` |
| 线上健康检查 | 登录页可访问，浏览器控制台错误数为 0 |

后续每个实施阶段应独立提交；发现回归时，以该阶段开始前的提交为回滚点，不使用覆盖工作区的破坏性 Git 操作。

## 3. 现有模块盘点

| 模块 | 现状 | 阶段 0 结论 |
|---|---|---|
| 页面路由 | `app.py` 通过 `st.navigation` 加载登录、首页、问卷、匹配、结果、AI 洞察 | 可运行；阶段 1 再调整信息架构 |
| 权限入口 | 业务页调用 `require_login` | 可复用并补充自动化权限测试 |
| 登录态 | 仅使用 `st.session_state["auth_user"]` | 必须升级，当前刷新不能可靠恢复 |
| 注册与密码 | 验证码、盐化密码哈希、注册、认证、重置密码均已存在 | 可复用并加固会话与限流 |
| 数据库 | SQLite；启动时直接 `CREATE TABLE IF NOT EXISTS` | 需要版本化迁移和持久数据库 |
| 个人资料 | `user_profiles.profile_json` 保存问卷结果 | 可作为迁移来源，不作为最终扩展结构 |
| 邮件 | 支持 SendGrid、Resend、SMTP | 适配器可复用；需要任务、幂等和重试 |
| 问卷 | 问题元数据、资料构建器、三类问卷 | 可复用并扩展资料字段 |
| 匹配算法 | 硬过滤、评分、双向分数、图匹配、全局流水线 | 核心可复用；阶段 7 接入轮次快照 |
| AI 与评估 | 相似度、解释、破冰、反馈与实验指标 | 可复用 |
| 测试 | 63 项单元和集成测试 | 作为后续阶段回归基线 |

## 4. 数据库基线

### 4.1 完整性与结构

- 数据库文件：`campusmate_app.db`
- 文件大小：49,152 字节
- SHA-256：`4C9BE2187ED1B0BEC4C52AB47A6295E0BA5BC057405C54177F7E4B87BFF49233`
- `PRAGMA integrity_check`：`ok`
- `PRAGMA user_version`：`0`

### 4.2 表与数据量

| 表 | 行数 | 说明 |
|---|---:|---|
| `users` | 2 | 当前账号数据 |
| `verification_codes` | 1 | 验证码记录 |
| `user_profiles` | 0 | 当前无本地问卷资料 |
| `notifications` | 0 | 当前无本地通知记录 |
| `login_sessions` | 9 | 旧版本遗留，当前代码不再使用 |

审计报告只记录数量，不记录邮箱、密码哈希、验证码或任何密钥。

### 4.3 已识别缺口

- 没有迁移版本表或数据库升级脚本。
- 没有外键、检查约束和关键业务唯一约束。
- 没有明确的事务边界、并发容量校验、SQLite busy timeout 或 WAL 策略。
- `login_sessions` 与当前代码脱节，迁移前需要确认是否存在仍有价值的会话数据。

## 5. 数据库备份与恢复

### 5.1 已生成备份

- 备份文件：`.local_backups/campusmate_app.pre-refactor-972feb2-20260808.db`
- 文件大小：49,152 字节
- SHA-256：`4C9BE2187ED1B0BEC4C52AB47A6295E0BA5BC057405C54177F7E4B87BFF49233`
- 只读完整性检查：`ok`
- `.local_backups/` 已加入 `.gitignore`，避免账号数据进入 Git。

### 5.2 本地恢复步骤

1. 停止本地 Streamlit 进程，避免恢复期间仍有写入。
2. 先把当前 `campusmate_app.db` 另存为一个带时间戳的安全副本。
3. 将上述备份复制为 `campusmate_app.db`。
4. 比较 SHA-256，并运行 `PRAGMA integrity_check`。
5. 启动应用，只用测试账号执行登录和匹配回归测试。

该备份是本机恢复点，不是线上备份。后续上线前需要为外部持久数据库建立独立的自动备份和恢复演练。

## 6. 升级与迁移策略

1. 阶段 1 不迁移数据，只调整登录后页面结构并补齐登录、刷新、退出回归测试。
2. 阶段 2 先确定外部持久数据库，再编写版本化、幂等的迁移脚本。
3. 迁移脚本只从旧库读取，写入新结构后核对用户数、主键、必填字段和资料 JSON 解析结果。
4. 每次迁移先备份、后执行、再校验；任一校验失败即停止切换，不覆盖旧库。
5. 新结构至少包含迁移版本、外键、唯一约束、时间字段和关键状态约束。
6. `login_sessions` 只在确认全部旧会话可安全失效后处理，不在普通页面改造中顺带删除。
7. 线上切换前使用真实结构的副本演练迁移，并保留旧库只读回退窗口。

## 7. 改造影响范围

### 可以直接复用

- `services/auth.py` 中的账号、验证码、密码和邮件供应商适配逻辑。
- `questionnaire/` 中的问题元数据和资料构建逻辑。
- `algorithm/` 中的硬过滤、评分、互惠分数、图匹配和全局匹配流水线。
- `ai/`、`evaluation/` 和现有测试数据集。

### 需要升级

- 登录态：从进程内会话升级为可过期、可撤销、刷新可恢复的服务端会话。
- 数据层：从启动时建表升级为版本化迁移与持久数据库。
- 资料层：从单个 JSON 扩展为可查询字段、兴趣标签和字段级隐私。
- 组局层：新增活动、申请、成员、名额事务和权限校验。
- 周期匹配：新增轮次、报名、问卷快照、任务幂等和历史结果。
- 通知层：新增邮件任务状态、失败原因、重试次数和幂等键。
- 前端：逐步迁移旧式 `pages/` 组织和弃用参数，不在阶段 0 改动。

## 8. 测试基线与缺口

### 已通过

- `python -m unittest discover -s tests -v`：63 项全部通过，最终复跑用时约 3.9 秒。
- `python -m compileall -q`：通过。
- SQLite 源库和备份：完整性检查均为 `ok`。
- 线上登录页：可达，控制台错误数为 0。

### 后续必须新增

- 单击登录、浏览器刷新保持当前页、退出立即失效。
- 会话过期、撤销和跨页面权限。
- 数据库迁移成功、失败回滚和重复运行。
- 资料隐私、活动越权、重复申请、并发满员。
- 周期任务重复触发、匹配结果幂等、邮件失败重试。

## 9. 部署约束

- Streamlit Community Cloud 不保证应用本地文件持久性，SQLite 和上传图片不能作为线上长期存储。
- 应用可能休眠，不能依赖页面进程执行固定时间的周期匹配。
- 密钥必须放在 Streamlit Secrets 中，不得提交到仓库。
- Git 推送会更新应用；后续发布必须保留可识别版本号、独立提交和回滚说明。

官方依据：

- https://docs.streamlit.io/develop/concepts/connections/connecting-to-data
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
- https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app
- https://docs.streamlit.io/develop/concepts/configuration/serving-static-files

## 10. 阶段 0 验收结果

- [x] Git、线上可达性和回滚提交已确认。
- [x] 登录、数据库、邮件、问卷、算法和页面路由已盘点。
- [x] 可复用与需升级代码已分类。
- [x] 数据库备份已生成并通过哈希与只读完整性校验。
- [x] 升级策略与影响范围已记录。

阶段 0 完成。进入阶段 1 前仍需用户单独批准。
