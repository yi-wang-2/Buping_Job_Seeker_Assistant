# Notion MCP 接入指南

来源：Notion《Notion MCP 接入指南 (NOTION_MCP_SETUP)》  
Notion 更新时间：2026-06-14  
本地同步：2026-07-10

## 1. 创建 Notion Integration

1. 打开 <https://www.notion.so/profile/integrations>
2. 点击 `+ New integration`
3. 填写：
   - Name：任意名称
   - Associated workspace：选择你的工作区
   - Type：Internal Integration
   - Capabilities：
     - Read content
     - Update content
     - Insert content
     - Read user information
4. 点击 `Submit`
5. 复制 Internal Integration Secret

注意：新版 Notion token 通常以 `ntn_` 开头，旧版 `secret_` 建议重新生成。

## 2. 把页面授权给 Integration

这是最容易漏的一步。

1. 打开需要让 AI 操作的 Notion 页面。
2. 右上角 `...` -> `Connections` -> `Connect to`。
3. 选择刚创建的 integration。
4. 根页面必须手动授权，子页面通常继承权限。

## 3. VS Code / MCP 配置示例

仓库根目录可创建 `.vscode/mcp.json`：

```json
{
  "servers": {
    "notion": {
      "type": "http",
      "url": "https://mcp.notion.com/mcp",
      "headers": {
        "Authorization": "Bearer ${env:NOTION_TOKEN}"
      }
    }
  }
}
```

PowerShell 设置环境变量：

```powershell
[System.Environment]::SetEnvironmentVariable('NOTION_TOKEN','ntn_xxx','User')
```

## 4. 安全提醒

- 不要把 Notion token 直接提交到 git。
- 推荐使用环境变量。
- `.vscode/mcp.json` 若包含真实 token，应加入 `.gitignore`。

## 5. 常见问题

| 现象 | 原因 | 解法 |
| --- | --- | --- |
| `Unauthorized` | Token 错或缺少 `Bearer ` | 检查配置 |
| 搜索返回空 | 页面未授权给 Integration | 回到第 2 步 |
| 工具不可见 | 未启用 Agent/MCP | 检查客户端设置 |
| token 是 `secret_` | 旧版 token | 建议重新生成 `ntn_` token |
