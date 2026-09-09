# KabarBaik-App 改进总结

## 2026-09: 输入格式扩展（pdf/doc/gdoc/链接）

**新增依赖（系统级，非 pip）** — 已记入 `requirements.txt` 注释区：

| 工具 | 用途 | 必需性 | 安装 |
|---|---|---|---|
| `poppler` (`pdftotext`) | AI 读取上传的 PDF | 上传 PDF 时必需 | `pkg install poppler`（Debian: `poppler-utils`）|
| `curl` | Google Docs/Sheets/Slides/Drive 链接导出下载（docx/xlsx/pptx）| 链接导入时必需 | `pkg install curl` |
| `antiword` / `catdoc` / `soffice` | 旧格式 `.doc/.ppt/.xls/.odt` 转换 | 可选 — 缺失时写入 `[BINARY SOURCE]` 占位并提示客户重新导出 | `pkg install antiword`（Termux 无 catdoc/soffice 包）|

**无新增 Python 依赖**：rtf/eml 解析用标准库（`email` + 正则），下载走 `curl` 子进程。

## 已修复的问题

### 1. Pydantic 版本不匹配 (主要原因)
**问题**: FastAPI 1.10.26 与系统 pydantic v1 不兼容，导致导入失败，应用无法启动
**解决**: 在 main.py 中添加 venv 自动检测机制，启动时自动切换到 .venv 中的 pydantic v2

### 2. NameError: request is not defined
**问题**: run_stage 和 monthly 函数中使用了未定义的 `request` 变量（参数名是 `project_request`）
**解决**: 
- 第160行: `request` → `project_request`
- 第194行: `request` → `project_request`

### 3. 缺少输出文档
**问题**: discovery.md 未生成，BRD/PRD 模板为空
**解决**:
- 从 inbox/BI Dashboard & Report Objectives.md 手动创建 discovery.md (92行)
- 创建 BRD 和 PRD 模板文件

## 当前状态
- 项目: powerbi-dashboard (stage 1 - brd_prd)
- discovery: ✅ completed
- brd_prd: ⏳ ready to run
- 生成的文档:
  - docs/discovery/discovery.md (92行)
  - docs/brd/brd.md (模板)
  - docs/prd/prd.md (模板)

## 测试步骤
1. 启动服务: `python3 main.py` 或 `.venv/bin/python main.py`
2. 访问: http://127.0.0.1:8021/
3. 运行阶段: POST /projects/1/stage/0 (discovery) 或 /stage/1 (brd_prd)

## 代码变更
- main.py: +19 行 (venv auto-detection, bug fixes)
- ai_runner.py: 重构为 async 版本
- workflow.py: 简化输出处理
- docs/: 新增 brd/ 和 prd/ 模板目录
