# AI Cooker

AI Cooker 是一个面向家庭烹饪场景的全栈智能助手。项目将多轮 Agent、约束感知的 Recipe RAG、图片上传、社区论坛和长期偏好记忆整合到一套应用中，帮助用户根据现有食材、忌口、过敏原、厨具和口味偏好获得更贴合实际条件的烹饪建议。

## 主要能力

- 基于 FastAPI 与 LangGraph 的流式对话 Agent
- 使用 PostgreSQL + pgvector 的配方知识库检索，并在检索不可用时安全降级
- 对食材、过敏原、饮食禁忌、设备和长期偏好进行确定性约束检查
- MySQL 持久化的对话检查点、摘要与用户记忆
- Spring Boot 提供用户、会话、图片和论坛等业务接口
- Vue 3 前端提供聊天、历史记录、图片输入和社区界面
- 私有 OSS 图片存储及短时签名 URL

## 技术架构

```text
Vue 3 + TypeScript (5173)
          |
Spring Boot + MySQL (8080) ---- Private OSS
          |
FastAPI + LangGraph (8000) ---- PostgreSQL + pgvector
          |                      Recipe Knowledge Base
  Model providers / optional Tavily fallback
```

主要技术栈：

- AI 服务：Python、FastAPI、LangChain、LangGraph
- 业务服务：Java 21、Spring Boot 3.5、Flyway、MySQL
- 前端：Vue 3、TypeScript、Vite、Pinia、Vitest
- Recipe RAG：PostgreSQL、pgvector、multilingual-e5-small

## 本地运行

### 1. 准备配置

所有凭据只应保存在本地配置文件或安全的环境变量中：

```powershell
Copy-Item .env.example .env
Copy-Item backend/.env.local.example backend/.env.local
Copy-Item frontend/.env.example frontend/.env
```

按注释填写占位符。不要提交 `.env`、`backend/.env.local` 或任何真实的模型、Tavily、数据库及 OSS 凭据。

本地需要预先创建：

- Agent 状态数据库：MySQL 数据库 `agent_web`
- Java 业务数据库：MySQL 数据库 `ai_cooker_business`
- Recipe RAG 数据库：PostgreSQL + pgvector，配置与导入步骤见 [Recipe Knowledge Base 文档](recipe_pipeline/recipe_kb/README.md)

### 2. 启动 Python AI 服务

安装 `requirements.txt` 中的依赖后，在项目根目录运行：

```powershell
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 3. 启动 Spring Boot 业务服务

另开一个 PowerShell 窗口：

```powershell
.\scripts\run-backend-local.ps1
```

脚本会读取 `backend/.env.local`，校验配置，并在启动 Java 服务前检查 AI 服务是否可用。

### 4. 启动前端

```powershell
Set-Location frontend
npm install
npm run dev -- --host 127.0.0.1
```

浏览器访问 `http://127.0.0.1:5173`。

## 测试

```powershell
# Python
& .\.venv\Scripts\python.exe -m pytest -q

# Java
Set-Location backend
mvn test

# Vue
Set-Location frontend
npm test
npm run build
```

Recipe 数据生成和离线评估是独立子系统，详见 [Recipe Pipeline 文档](recipe_pipeline/README.md)。生成结果、向量缓存、数据库状态和提供商请求标识默认不会纳入 Git。

## 安全说明

- 仓库仅提供脱敏的 `.env.example` 示例，不包含可用凭据。
- 图片存储应使用私有 OSS Bucket；前端通过后端获取短时签名 URL。
- 生产部署请使用密钥管理服务或平台 Secret，不要把密钥写入源码、镜像或日志。
- 如果凭据曾意外进入 Git 历史，应立即在提供商处轮换，而不只是删除文件。

## License

本项目采用 [MIT License](LICENSE)。
