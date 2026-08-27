# 每日财经日报 · AI定时任务指令模板（增强版，含自动降级）

> 适用场景：每天自动抓取财经数据，生成飞书文档，推送邮件通知。
> 核心特性：AI优先，失败自动降级到脚本模式，确保每日必达。

---

## 一、任务配置（复制以下内容发给 AI）

```
创建定时任务，执行时间每天20:00。

任务工作内容：

【第一步：模式检测】
1. 调用模式控制器查询当前推荐模式：
   python3 scripts/mode_controller.py --query
2. 如果推荐模式为"脚本模式"，直接跳转到【第四步：脚本模式保底】
3. 如果推荐模式为"AI模式"，继续执行

【第二步：AI模式执行】
1. 访问国家统计局官网 https://www.stats.gov.cn/ ，抓取当天新发布信息
2. 访问同花顺网页 https://www.10jqka.com.cn/，获取上证指数、板块变化、资金流向
3. 访问新浪财经 https://finance.sina.com.cn/，整理当日重要新闻
4. 把以上内容整理完整，生成飞书文档，文档标题格式：财经日报-YYYY年MM月DD日
5. 将日报核心摘要和飞书文档链接通过邮件推送到用户邮箱

【第三步：AI模式结果检测】
1. 检查飞书文档是否成功创建
2. 检查邮件是否成功发送
3. 检查数据是否完整（三大板块是否都有内容）
4. 如果以上任何一项失败，记录失败原因，跳转到【第四步：脚本模式保底】
5. 如果全部成功，记录AI模式成功事件：
   python3 scripts/mode_controller.py --mode ai --status success --date YYYY-MM-DD

【第四步：脚本模式保底（自动降级）】
1. 记录AI模式失败事件（如果是从AI模式降级）：
   python3 scripts/mode_controller.py --mode ai --status failed --date YYYY-MM-DD --reason "失败原因"
2. 调用统一入口脚本执行脚本模式：
   python3 scripts/daily_runner.py --date YYYY-MM-DD --degraded-from ai --reason "失败原因" --notify
3. 脚本模式会自动完成：数据采集→日报生成→飞书文档→邮件推送
4. 如果脚本模式也失败，发送紧急告警邮件

【第五步：结果输出】
1. 仅将飞书文档链接和执行模式输出到当前对话窗口
2. 不输出完整日报内容
3. 格式示例：
   执行模式：AI模式 / 脚本模式（降级）
   飞书文档：https://bytedance.larkoffice.com/docx/xxxxx
   状态：成功 / 部分成功 / 失败

备注：
- 网站全部使用公开网页，不需要登录
- 某网站抓取失败则在日报中标注，禁止编造数据
- AI模式失败时必须自动降级到脚本模式，确保每日必达
- 脚本模式是最终保底，即使AI完全不可用也能正常推送
```

---

## 二、模式切换规则

### 降级触发条件（满足任一即降级）
1. **连续失败**：AI模式连续失败2次
2. **日失败率**：当日AI模式失败率超过30%（至少执行3次）
3. **冷却期**：降级后60分钟内强制使用脚本模式
4. **手动降级**：用户手动指定使用脚本模式

### 恢复AI模式条件
1. 冷却期结束（60分钟后）
2. 连续失败次数清零
3. 模式控制器推荐AI模式

### 模式统计
- 记录每次执行的模式、状态、时间、原因
- 统计AI模式和脚本模式的成功率
- 统计降级次数
- 查看统计：`python3 scripts/mode_controller.py --stats`

---

## 三、脚本模式说明

脚本模式（纯脚本保底）完全不依赖AI，0 token消耗：
- 数据采集：国家统计局、腾讯财经API、新浪财经
- 日报生成：基于模板自动生成Markdown日报
- 飞书文档：通过飞书开放API自动创建文档
- 邮件推送：精美HTML邮件 + Markdown附件
- 失败告警：执行失败自动发送告警邮件

脚本模式入口：
```bash
# 正常执行
python3 scripts/daily_runner.py --date YYYY-MM-DD

# AI模式失败后降级执行（含通知）
python3 scripts/daily_runner.py --date YYYY-MM-DD --degraded-from ai --reason "原因" --notify

# 仅测试，不发送邮件
python3 scripts/daily_runner.py --date YYYY-MM-DD --no-email
```

---

## 四、需替换的参数

| 参数 | 说明 | 获取方式 |
|---|---|---|
| 执行时间 `每天20:00` | 可按需调整 | 直接修改指令中的时间描述 |
| 邮箱账号 | 发件人邮箱 | 配置SMTP_USER环境变量 |
| 邮箱授权码 | 发件人邮箱授权码 | 配置SMTP_PASSWORD环境变量 |
| 飞书App ID | 飞书应用ID | 配置FEISHU_APP_ID环境变量 |
| 飞书App Secret | 飞书应用密钥 | 配置FEISHU_APP_SECRET环境变量 |

---

## 五、使用步骤

1. **配置环境变量**：设置SMTP_USER、SMTP_PASSWORD、FEISHU_APP_ID、FEISHU_APP_SECRET
2. **发送创建指令**：将完整的「任务配置」段落复制发给 AI 助手
3. **确认创建成功**：AI 会返回任务名称、执行时间、首次触发时间
4. **（可选）测试运行**：对 AI 说「现在执行测试」，验证全流程
5. **查看模式统计**：`python3 scripts/mode_controller.py --stats`

---

## 六、注意事项

- A股交易时间为 9:30—15:00，建议执行时间设在 **15:30 之后**
- 脚本模式是最终保底，即使AI完全不可用也能正常推送
- 降级后60分钟内强制使用脚本模式，避免频繁切换
- 禁止编造数据：某网站抓取失败时必须在日报中明确标注
- 模式切换日志保存在 `logs/mode_switch_log.json`
