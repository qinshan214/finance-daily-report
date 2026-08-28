# 每日财经日报 · AI定时任务指令（两步强制流程版）

> **核心原则：脚本优先，AI增强，强制流程，禁止跳过**
> 
> 本任务采用两步强制流程，AI必须严格按照顺序执行，禁止跳过第一步直接自己采集数据。

---

## ⚠️ 强制执行规则（AI必须遵守）

### 规则1：第一步必须执行脚本
- AI **必须** 先执行 `run_daily.py --no-email --no-feishu`
- **禁止** 跳过脚本，直接用 web.fetch 自己采集数据
- **禁止** 部分用脚本数据，部分自己采集
- **只有** 第一步脚本完全失败时，才允许AI降级为自己采集

### 规则2：第二步只做AI增强
- AI **只能** 读取脚本生成的 JSON 和 Markdown 文件
- AI **只能** 做深度分析和内容增强
- AI **禁止** 重新采集数据
- AI **禁止** 修改脚本生成的基础数据

### 规则3：数据一致性
- 所有数据必须来自脚本生成的 JSON 文件
- AI生成的分析必须基于脚本数据，不得编造
- 如果脚本数据缺失，AI必须标注"数据缺失"，不得编造

### 规则4：降级机制
- 第一步脚本成功 → 执行第二步AI增强
- 第一步脚本失败 → AI才允许降级为自己采集（作为兜底）
- 第二步AI失败 → 自动使用纯脚本版日报，不影响推送

---

## 📋 两步强制执行流程

### 第一步（强制）：脚本采集 + 生成基础日报

**AI必须执行以下命令：**

```bash
cd /path/to/finance-daily-report
python3 scripts/run_daily.py --no-email --no-feishu --date YYYY-MM-DD
```

**脚本会自动完成：**
1. ✅ 调用 collect_data.py 采集6大数据源
   - 国家统计局
   - A股行情（腾讯财经API）
   - 行业板块（49个板块）
   - 全球市场
   - 财经新闻（新浪财经，50条）
   - 数据采集说明
2. ✅ 调用 generate_report.py 生成基础版日报
3. ✅ 保存数据文件：`output/data_YYYY-MM-DD.json`
4. ✅ 保存日报文件：`output/report_YYYY-MM-DD.md`
5. ✅ 验证数据文件有效性

**AI必须验证第一步成功：**
- 检查 `output/data_YYYY-MM-DD.json` 是否存在
- 检查 `output/report_YYYY-MM-DD.md` 是否存在
- 检查 JSON 文件中的 `summary` 字段
- 如果文件不存在或无效，视为第一步失败

**第一步失败时的降级处理：**
- AI才允许使用 web.fetch 自己采集数据（作为兜底）
- AI必须在日报中标注"脚本采集失败，使用AI兜底采集"
- AI必须记录失败原因

---

### 第二步（AI增强）：读取脚本数据 + 深度分析 + 推送

**AI必须执行以下命令：**

```bash
cd /path/to/finance-daily-report
python3 scripts/ai_enhance_full.py --date YYYY-MM-DD
```

**脚本会自动完成：**
1. ✅ 读取第一步生成的 JSON 和 Markdown
2. ✅ 调用AI生成深度分析（AI优先，失败自动降级）
   - 市场总览和核心观点
   - 板块轮动分析
   - 重点新闻深度解读
   - 投资策略建议
3. ✅ 合并基础日报和AI分析
4. ✅ 创建飞书文档（自动设置权限+添加协作者）
5. ✅ 发送增强版邮件（包含日报摘要+飞书文档链接+Markdown附件）

**AI增强的限制：**
- AI只能读取脚本生成的数据，不得重新采集
- AI只能做分析和解读，不得修改基础数据
- AI生成的分析必须基于脚本数据，不得编造
- AI输出长度限制在1500 tokens以内，减少消耗

---

## 🔧 环境变量配置

在执行任务前，确保以下环境变量已配置：

### 飞书配置（必选）
```bash
export FEISHU_APP_ID="cli_xxxxxxxx"
export FEISHU_APP_SECRET="xxxxxxxx"
export FEISHU_DOC_PERMISSION="tenant_readable"
export FEISHU_DOC_COLLABORATOR_ID="user_open_id"
export FEISHU_DOC_COLLABORATOR_TYPE="userid"
export FEISHU_DOC_COLLABORATOR_PERM="full_access"
```

### 邮件配置（必选）
```bash
export SMTP_SERVER="smtp.qq.com"
export SMTP_PORT="465"
export SMTP_USER="xxx@qq.com"
export SMTP_PASSWORD="授权码"
export MAIL_TO="xxx@qq.com"
```

### AI配置（可选，不配置则使用纯脚本版）
```bash
export DOUBAO_API_KEY="ark-xxxxxxxx"
export DOUBAO_MODEL="ep-xxxxxxxx"
```

---

## 📊 收益对比

| 指标 | 旧方案（AI自觉） | 新方案（强制流程） | 提升 |
|------|----------------|------------------|------|
| AI协同可靠性 | 依赖自觉，可能跳过脚本 | 强制两步流程，必须先执行脚本 | ⭐⭐⭐⭐⭐ |
| Token消耗 | 高（AI可能自己采集） | 低（只做分析，1500 tokens限制） | 降低70% |
| 数据一致性 | 可能不一致（部分脚本部分AI） | 完全一致（所有数据来自脚本） | 100%一致 |
| 降级机制 | 无明确降级 | 脚本失败才降级，AI失败自动用纯脚本 | 完善 |
| 可维护性 | 脆弱，依赖prompt约束 | 强制流程，代码保障 | 健壮 |

---

## ⚠️ 常见错误及处理

### 错误1：AI跳过第一步直接自己采集
**处理**：这是严重违规！AI必须先执行脚本，只有脚本完全失败时才允许降级。

### 错误2：AI修改脚本生成的基础数据
**处理**：AI只能做分析和解读，不得修改基础数据。如果发现数据错误，应标注"数据可能有误"，而不是直接修改。

### 错误3：AI编造数据
**处理**：所有数据必须来自脚本生成的JSON文件。如果脚本数据缺失，AI必须标注"数据缺失"，不得编造。

### 错误4：第一步脚本失败后AI不降级
**处理**：第一步脚本失败后，AI必须降级为自己采集（作为兜底），并在日报中标注降级原因。

### 错误5：第二步AI失败后不使用纯脚本版
**处理**：第二步AI失败后，必须自动使用纯脚本版日报，确保日报必达。

---

## 📝 执行检查清单

AI在执行任务时，必须按照以下清单检查：

- [ ] 第一步：执行 `run_daily.py --no-email --no-feishu`
- [ ] 验证 `output/data_YYYY-MM-DD.json` 存在且有效
- [ ] 验证 `output/report_YYYY-MM-DD.md` 存在
- [ ] 第一步成功 → 执行第二步
- [ ] 第一步失败 → 降级为AI自己采集（标注降级原因）
- [ ] 第二步：执行 `ai_enhance_full.py --date YYYY-MM-DD`
- [ ] 验证飞书文档创建成功
- [ ] 验证邮件发送成功
- [ ] 在对话中输出飞书文档链接（不输出完整日报内容）

---

## 🎯 最终输出要求

任务完成后，AI必须在对话中输出：
1. ✅ 执行模式（AI增强版 / 纯脚本版 / 降级版）
2. ✅ 飞书文档链接
3. ✅ 邮件发送状态
4. ✅ 数据采集状态（成功/失败/降级）

**禁止**输出完整日报内容（日报内容已在飞书文档和邮件中）。

---

*本指令模板为强制流程版本，AI必须严格遵守，不得跳过任何步骤。*
