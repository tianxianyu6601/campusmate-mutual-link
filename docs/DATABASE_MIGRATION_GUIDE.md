# 数据库迁移与部署说明

## 当前策略

- 本地开发：未配置 `database_url` 时使用项目根目录的 `campusmate_app.db`。
- Streamlit Cloud：必须在应用 Secrets 中配置托管 PostgreSQL 的 `database_url`。
- 同一套迁移和服务接口支持两种后端；业务代码不判断具体供应商。
- 不把真实连接串写入仓库、日志或页面。

## 1. 本地检查迁移

在项目根目录执行：

```powershell
python -m scripts.migrate_database
```

预期输出只包含后端、结构版本和本次应用的版本号，不包含账号或连接串。例如：

```text
backend=sqlite schema_version=4 applied=none
```

本地已配置 PostgreSQL、但需要运行隔离的 SQLite 自动化测试时，可仅为该测试进程设置 `CAMPUSMATE_FORCE_SQLITE=1`。线上环境不要设置此变量。

## 2. 配置线上 PostgreSQL

在 Streamlit Cloud 的应用设置中打开 Secrets，把下列占位值替换为托管 PostgreSQL 提供的真实连接串：

```toml
database_url = "postgresql://user:password@host:5432/campusmate?sslmode=require"
```

项目也支持本地环境变量 `CAMPUSMATE_DATABASE_URL`，便于在部署前运行迁移；不要在共享终端中打印该变量。

## 3. 创建线上结构

安装 `requirements.txt` 后，在已经安全配置连接串的环境中执行：

```powershell
python -m scripts.migrate_database
```

当输出 `backend=postgresql schema_version=4` 时，表示结构迁移完成。迁移是幂等的，可再次运行确认 `applied=none`。

## 4. 导入现有 SQLite 账号

先只预览源库记录数：

```powershell
python -m scripts.import_legacy_sqlite
```

确认已经配置 PostgreSQL 连接串后，显式执行导入：

```powershell
python -m scripts.import_legacy_sqlite --apply
```

该工具只迁移账号与个人资料：`users`、`user_profiles`、`profiles`、`profile_interests`、`profile_privacy`。不会迁移验证码、登录会话、活动、活动申请、活动成员、站内通知或邮件任务；用户首次访问新版时需要重新登录。导入使用 upsert，可安全重试。

## 5. 部署前验收

```powershell
python -m unittest discover -s tests -q
```

随后在浏览器验证：注册/登录、刷新保持当前页面、退出立即失效。阶段 3 及之后接入业务页面时，再验证资料保存和活动申请闭环。

## 回滚原则

- 执行线上导入前保留原 SQLite 备份。
- 迁移只新增表和索引，不删除旧账号、问卷或通知表。
- 发现异常时先停止部署并切回上一个 Git 提交；不要直接删除线上表。
- 当前没有自动降级迁移，避免错误回滚造成不可恢复的数据删除。
