# GitHub Actions 配置指南

## 概述

本项目使用 GitHub Actions 实现每日自动生成财经日报，包含完整的重试机制和失败通知。

## 重试机制

### 1. 工作流层面（三重保障）

| 机制 | 说明 |
|------|------|
| **多时间点触发** | 每天 20:00、20:05、20:10 三次触发，前一次成功则后一次自动跳过 |
| **步骤级重试** | 使用 `nick-fields/retry` action，最多重试 3 次，每次间隔 60 秒 |
| **状态检查** | 每次执行前检查今日是否已成功，避免重复执行 |

### 2. 脚本层面

- `fetch_with_retry()` 函数实现指数退避重试
- 最多重试 3 次，延迟分别为 2s、4s、8s
- 处理超时、HTTP错误、网络连接异常
- 随机 User-Agent 避免被拦截

## GitHub Secrets 配置

### 配置步骤

1. 打开仓库页面：https://github.com/qinshan214/finance-daily-report
2. 点击 **Settings** → **Secrets and variables** → **Actions**
3. 点击 **New repository secret**
4. 依次添加以下 Secrets：

### 必需的 Secrets

| Secret 名称 | 说明 | 示例值 |
|-------------|------|--------|
| `FEISHU_APP_ID` | 飞书自建应用 App ID | `cli_aa1a06d6cd389bcf` |
| `FEISHU_APP_SECRET` | 飞书自建应用 App Secret | `4X3SrU8vEZD9XyC8Xl0Y4WRDAbvvyf03` |
| `FEISHU_DOC_PERMISSION` | 文档默认权限 | `tenant_readable` |
| `FEISHU_DOC_COLLABORATOR_ID` | 默认协作者ID | `d1542736` |
| `FEISHU_DOC_COLLABORATOR_TYPE` | 协作者ID类型 | `userid` |
| `FEISHU_DOC_COLLABORATOR_PERM` | 协作者权限 | `full_access` |
| `SMTP_SERVER` | SMTP服务器地址 | `smtp.qq.com` |
| `SMTP_PORT` | SMTP端口 | `465` |
| `SMTP_USER` | SMTP用户名（邮箱） | `161626837@qq.com` |
| `SMTP_PASSWORD` | SMTP授权码 | `noqadiemaigkbifj` |
| `MAIL_TO` | 日报接收邮箱 | `161626837@qq.com` |

### 权限说明

| 权限值 | 说明 |
|--------|------|
| `tenant_readable` | 组织内获得链接的人可阅读（推荐） |
| `tenant_editable` | 组织内获得链接的人可编辑 |
| `anyone_readable` | 互联网获得链接的人可阅读 |
| `anyone_editable` | 互联网获得链接的人可编辑 |
| `closed` | 关闭链接分享 |

### 协作者权限说明

| 权限值 | 说明 |
|--------|------|
| `view` | 可查看 |
| `edit` | 可编辑 |
| `full_access` | 可管理（完全控制，推荐） |

## 手动触发

除了定时触发，还可以手动触发工作流：

1. 打开仓库页面
2. 点击 **Actions** 标签
3. 选择 **每日财经日报** 工作流
4. 点击 **Run workflow**
5. 可选：指定日期（YYYY-MM-DD）
6. 点击 **Run workflow** 确认

## 查看执行结果

### 执行日志

1. 打开仓库页面
2. 点击 **Actions** 标签
3. 点击对应的工作流运行记录
4. 查看每个步骤的执行日志

### 产物下载

每次执行后，日报和数据文件会作为 Artifacts 保存 30 天：

1. 打开工作流运行记录页面
2. 滚动到页面底部
3. 在 **Artifacts** 区域下载 `finance-report-xxx` 文件

### 失败通知

如果工作流执行失败：
- GitHub 会自动发送邮件通知仓库所有者
- 可以在工作流日志中查看详细错误信息
- 下一个时间点（5分钟后）会自动重试

## 定时任务时间

工作流每天在以下时间点自动触发（北京时间）：

| 时间 | 说明 |
|------|------|
| 20:00 | 主要执行时间 |
| 20:05 | 第一次备份重试 |
| 20:10 | 第二次备份重试 |

如果 20:00 执行成功，20:05 和 20:10 会自动跳过（通过状态文件检查）。

## 修改定时时间

如需修改执行时间，编辑 `.github/workflows/daily-report.yml` 文件中的 `cron` 表达式：

```yaml
on:
  schedule:
    # UTC时间，北京时间 = UTC + 8
    - cron: '0 12 * * *'  # 北京时间20:00
    - cron: '5 12 * * *'  # 北京时间20:05
    - cron: '10 12 * * *' # 北京时间20:10
```

Cron 表达式格式：`分 时 日 月 周`

## 常见问题

### Q: 工作流执行失败怎么办？

A: 
1. 查看执行日志，定位错误原因
2. 5分钟后会自动重试
3. 如果连续失败，检查 Secrets 配置是否正确
4. 可以手动触发工作流进行测试

### Q: 如何测试工作流？

A: 
1. 打开 Actions 页面
2. 点击 **Run workflow** 手动触发
3. 查看执行日志和结果

### Q: 日报会重复发送吗？

A: 不会。每次执行前会检查今日状态文件，如果已成功生成，会自动跳过后续执行。

### Q: 如何修改接收邮箱？

A: 在 GitHub Secrets 中修改 `MAIL_TO` 的值即可。

### Q: 飞书文档权限如何修改？

A: 在 GitHub Secrets 中修改 `FEISHU_DOC_PERMISSION` 的值，参考上方权限说明表。
