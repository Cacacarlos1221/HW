# 需求：local_documents

目标：把配置指定的本地目录变成供 AI Agent 调用的文件检索 MCP 服务。

1. 使用 Python，以 stdio 启动；服务名 local_documents，工具统一 local_ 前缀。
2. config.json 支持多个 dirs、exclude_hidden、refresh_interval_seconds（默认 600 秒）。配置相对路径相对于配置文件所在目录；Windows 绝对路径直接使用。
3. 启动时递归建立文件和目录的内存元数据索引；定时全量刷新；手动重建时重新加载配置。扫描失败计数，完整新索引完成后替换旧索引。
4. local_browse 从索引返回目录直接子项，目录优先；未指定目录时列出配置根目录。
5. local_search 支持名称/路径子串与文件名模糊匹配，kind、extension、modified_since、accessed_since 过滤，按相关度/修改时间/访问时间排序。
6. local_metadata 查询已索引文件/目录当前的名称、路径、类型、大小、后缀、修改时间与访问时间。时间使用 Unix 秒；访问时间不等于可靠的应用打开历史。
7. local_rebuild_index 手动重建索引，不更改被扫描文件。
8. 浏览和搜索默认每页 20 项，最多 100 项，返回 total、offset、next_offset；按需调用元数据工具，避免返回文件正文占用上下文。
9. 输入 schema 使用类型、枚举、范围；业务错误统一为 ok=false、data=null、error={code,message}。协议/schema 验证错误由 MCP SDK 返回工具错误。
10. 路径限定在配置根目录内；跳过符号链接；默认排除点文件及 Windows hidden 属性。不存在的根目录启动失败，不静默扫描其他路径。
11. 不提供写入、删除、执行、读取正文工具，因此无原文件高危修改操作，也不需要为本作业另加审批工具。
12. 交付需求、源码、配置、Agent 挂载说明、验证脚本。先通过真实 MCP stdio 测试，再由用户在 Windows 上接入 Agent 验收。

实现边界：只建立名称/路径/元数据索引，无全文或语义检索；使用内存索引和定时全量扫描，适用于培训作业及中小目录。大量文件时再考虑 SQLite 和增量监听。
