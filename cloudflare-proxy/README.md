# Cloudflare Workers 反向代理部署指南

## 功能说明

本Cloudflare Workers用于代理火山引擎API请求，解决GitHub Actions（国外服务器）访问火山引擎API（国内）慢/超时的问题。

## 工作原理

```
GitHub Actions → Cloudflare Workers（全球CDN）→ 火山引擎API
```

Cloudflare Workers在全球有大量节点，可以加速访问国内API。

## 部署步骤

### 第1步：注册Cloudflare账号

1. 访问 https://dash.cloudflare.com/sign-up
2. 注册一个免费账号
3. 登录控制台

### 第2步：创建Worker

1. 登录Cloudflare控制台
2. 左侧菜单点击"Workers & Pages"
3. 点击"Create application"
4. 选择"Create Worker"
5. 填写Worker名称（如 `doubao-api-proxy`）
6. 点击"Deploy"

### 第3步：编辑Worker代码

1. 部署完成后，点击"Edit code"
2. 删除默认代码
3. 复制 `worker.js` 文件中的全部代码
4. 粘贴到编辑器中
5. 点击"Save and deploy"

### 第4步：获取Worker地址

1. 部署完成后，在Worker详情页可以看到Worker地址
2. 地址格式如：`https://doubao-api-proxy.你的用户名.workers.dev`
3. 复制这个地址

### 第5步：测试代理是否正常

在浏览器中访问：
```
https://你的Worker地址/api/v3/chat/completions
```

如果返回 `{"error":{"code":"MissingAuthenticationToken"...}}` 或类似的JSON响应，说明代理正常工作。

### 第6步：配置GitHub Secrets

1. 访问GitHub仓库：https://github.com/qinshan214/finance-daily-report/settings/secrets/actions
2. 点击"New repository secret"
3. 添加以下Secret：

| Secret名称 | 值 | 说明 |
|-----------|-----|------|
| `DOUBAO_API_PROXY` | `https://你的Worker地址` | Cloudflare Workers代理地址 |

**示例**：
```
DOUBAO_API_PROXY=https://doubao-api-proxy.yourname.workers.dev
```

### 第7步：触发工作流测试

1. 访问GitHub仓库的Actions页面
2. 点击"每日财经日报"工作流
3. 点击"Run workflow"
4. 等待工作流执行完成
5. 查看日志，确认AI调用成功

## 费用说明

| 项目 | 费用 |
|------|------|
| Cloudflare Workers免费版 | ✅ 免费（每天10万次请求） |
| GitHub Actions | ✅ 免费 |
| 豆包API | 按token计费（新用户有免费额度） |

**总成本：基本0元/月**

## 常见问题

### Q1: Worker地址是什么格式？
A: 格式为 `https://worker-name.username.workers.dev`，在Worker详情页可以看到。

### Q2: 如何确认代理正常工作？
A: 在浏览器中访问 `https://你的Worker地址/api/v3/chat/completions`，如果返回JSON响应（即使是错误响应），说明代理正常。

### Q3: AI调用还是超时怎么办？
A: 
1. 检查Worker地址是否正确
2. 检查GitHub Secrets是否配置正确
3. 查看Worker日志（Cloudflare控制台 → Workers → 你的Worker → Logs）
4. 尝试增加AI超时时间（修改ai_enhance_report.py中的AI_TIMEOUT）

### Q4: 可以自定义域名吗？
A: 可以。在Worker详情页 → "Custom Domains" → "Add Custom Domain"，绑定你自己的域名。

### Q5: 代理安全吗？
A: 
- API Key在请求头中传输，HTTPS加密
- Cloudflare Workers不会存储请求内容
- 建议定期轮换API Key
- 可以在Worker代码中添加来源IP限制，只允许GitHub Actions的IP访问

## 技术支持

如有问题，请检查：
1. Worker代码是否正确部署
2. Worker地址是否可访问
3. GitHub Secrets是否配置正确
4. 豆包API Key是否有效
