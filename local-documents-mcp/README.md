# local_documents：校招培训课后作业

把本地工作目录变成 AI Agent 可调用的文件搜索 MCP 服务。Python 实现，使用官方 MCP Python SDK 的 FastMCP 和 stdio，无 HTTP 服务和端口。

## 作业要求与完成情况

| 课件要求 | 实现 |
|---|---|
| 先想目标、写需求 | requirement.md |
| 配置多个目录、隐藏文件开关 | config.json |
| 启动索引、配置定时刷新 | index.py / server.py |
| 浏览直接子项，目录在前 | local_browse |
| 文件名/路径模糊搜、类型/扩展名过滤 | local_search |
| 最近修改/最近访问排序 | modified / accessed |
| 单文件元数据 | local_metadata |
| 文件变化后重建 | local_rebuild_index + 定时刷新 |
| stdio 接入 Agent | 下方配置 |
| schema、错误、上下文控制 | 枚举/分页/上限/统一业务错误 |
| 高危操作审批 | 只读工具，无源文件修改操作 |

## Windows 运行

将本项目文件夹放到 `D:\工作文件\校招培训课后作业\local-documents-mcp`。需 Python 3.10 或以上。

```powershell
cd 'D:\工作文件\校招培训课后作业\local-documents-mcp'
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe test_smoke.py
```

`config.json` 已设置扫描 `D:\工作文件\校招培训课后作业`，默认排除隐藏项，600 秒刷新一次。可改为多个已有目录；JSON 中反斜线要写为 `\\`。如果项目放在其他位置，修改下方服务脚本路径。

手动启动（等待输入属于正常现象，stdio 服务由 Agent 发消息驱动）：

```powershell
.\.venv\Scripts\python.exe server.py --config config.json
```

## 挂到 Agent

支持 `mcpServers` JSON 的客户端，将以下对象合并到现有配置，不要覆盖其他服务：

```json
{
  "mcpServers": {
    "local_documents": {
      "command": "D:\\工作文件\\校招培训课后作业\\local-documents-mcp\\.venv\\Scripts\\python.exe",
      "args": [
        "D:\\工作文件\\校招培训课后作业\\local-documents-mcp\\server.py",
        "--config",
        "D:\\工作文件\\校招培训课后作业\\local-documents-mcp\\config.json"
      ]
    }
  }
}
```

不同 Agent 配置格式不同；以上不是 Codex TOML。Codex 用户可将以下段落合并进自己的 `config.toml`，保留原内容：

```toml
[mcp_servers.local_documents]
command = 'D:\工作文件\校招培训课后作业\local-documents-mcp\.venv\Scripts\python.exe'
args = ['D:\工作文件\校招培训课后作业\local-documents-mcp\server.py', '--config', 'D:\工作文件\校招培训课后作业\local-documents-mcp\config.json']
```

重启客户端，确认出现四个 `local_*` 工具。可问：“列出配置目录下的直接子目录”“找最近修改的 PDF”“查询这个文件的元数据”。连接后的实际工具名称可能额外带客户端命名空间。

## 无 LLM 验收

`python test_smoke.py` 自动创建临时测试数据，通过真实 stdio 完成初始化、工具发现与调用，验证目录优先、分页、模糊搜索、隐藏项、目录越界、schema 范围、定时刷新和手动重建。不会扫描测试者真实文档。

也可先安装 Node.js，再启动 MCP Inspector：

```powershell
npx -y @modelcontextprotocol/inspector .\.venv\Scripts\python.exe server.py --config config.json
```

Inspector 中依次调用 `local_browse`、`local_search`、`local_metadata`、`local_rebuild_index`，再挂载 Agent。Inspector 需下载第三方 npm 包。

## 工具示例

- `local_browse({"limit":20})`：根目录列表。
- `local_search({"query":"培训","kind":"file","extension":"pdf","sort_by":"modified","limit":10})`。
- `local_metadata({"path":"D:\\工作文件\\校招培训课后作业\\示例.pdf"})`：路径必须真实存在并已索引。
- `local_rebuild_index({})`：重新读取配置并扫描。

业务结果为 `{"ok":true,"data":...,"error":null}`。业务错误返回 `ok:false`；输入 schema 错误由 SDK 返回 MCP 工具错误。

## 设计与限制

`server.py` 负责 MCP 和定时任务；`index.py` 负责配置、扫描、查询；依赖只有 MCP SDK（传递依赖由 pip 安装）。SDK 限定 `<2` 保持 FastMCP v1 API 兼容。

索引仅在本地进程内存保存；工具返回的路径、文件名和元数据会进入调用它的 Agent 上下文。没有读取文件正文工具。stdout 专用于 MCP，日志走 stderr。

“最近打开”以系统 `atime` 近似：Windows 可能禁用/延迟更新，其他程序读取也可能更新它，不能当成精确的用户打开记录。索引变化最迟在下次刷新可见，需即时更新时调用重建。分页 offset 在两次刷新之间可能变化。

采用全量扫描和线性搜索；大目录会增加内存与查询耗时。跳过符号链接；常规路径越界受校验，但不声称能防御本机恶意进程同时替换目录的竞态。建议仅配置自己信任、确需检索的目录。

## 仓库与本地目录

本作业位于 `Cacacarlos1221/HW` 仓库的 `local-documents-mcp/` 子目录。

```powershell
cd 'D:\工作文件\校招培训课后作业'
git clone https://github.com/Cacacarlos1221/HW.git
cd .\HW\local-documents-mcp
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe test_smoke.py
```

若采用 git clone 后的目录布局，上方 Agent 配置中服务脚本和 Python 路径应增加 `HW` 这一层，即 `D:\工作文件\校招培训课后作业\HW\local-documents-mcp`。扫描目标仍由 config.json 决定。也可直接下载并将子目录放到前文约定的位置。

源码已在 Linux/Python 3.12 环境通过真实 stdio 集成测试；Windows 上的实际目录扫描与 Agent 挂载需要在本机执行以上步骤验收。
