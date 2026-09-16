# AI 聊天项目（FastAPI 后端 + Vue 前端）

按 `0910 笔记.md` 复刻的前后端项目，AI 接口接 **DeepSeek**。

## 目录结构

```
vue-project/
├── backend/                 # FastAPI 后端
│   ├── requirements.txt     # Python 依赖
│   ├── .env.example         # 环境变量示例（复制为 .env 使用）
│   ├── main.py              # 入口：中间件 + 注册路由
│   ├── database.py          # SQLAlchemy 引擎 / Session / Base
│   ├── common/
│   │   ├── config.py        # 读取 .env 的 api_key、base_url、model_name 等
│   │   ├── openapi.py       # SSE 响应声明（给 Swagger / Apifox 用）
│   │   ├── sse.py           # sse_frame()：把文本安全地包成 SSE 帧
│   │   └── paths.py         # 上传目录等路径（绝对路径，不受启动目录影响）
│   ├── models/              # 实体类：User / Conversation / Message
│   ├── uploads/avatars/     # 用户上传的头像（运行时生成）
│   └── routers/
│       ├── demo.py          # SSE 示例 demo01~demo04
│       ├── auth.py          # 注册 / 登录 / 个人资料 / 头像
│       └── chat.py          # 会话/消息 CRUD + 删除 + 流式聊天
└── frontend/                # Vue 前端
    ├── src/
    │   ├── App.vue          # 聊天页（登录/注册 + 流式对话 + 个人资料 + 删会话）
    │   └── main.ts          # 入口：注册 Element Plus + 图标
    ├── public/              # 静态资源（含 AI 头像 ai-avatar.svg）
    ├── vite.config.ts       # /api 代理到 127.0.0.1:8000
    └── package.json         # 前端依赖与脚本
```

## 一、后端启动

```bash
cd backend

# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
copy .env.example .env        # Windows
# cp .env.example .env        # macOS / Linux

# 3. 启动（必须在 backend 目录下运行）
python main.py
# 或
uvicorn main:app --host 127.0.0.1 --port 8000
```

> ⚠️ **务必把 `.env` 里的 `API_KEY` 换成真实的 DeepSeek Key**（[申请地址](https://platform.deepseek.com/api_keys)）。
> 默认值 `myapiky` 是占位符，不换的话 `demo02`/`demo03`/`demo04`/`chat` 会返回 401 鉴权失败。

- 不配置 `DATABASE_URL` 也能启动：数据库回退到本地 `backend/app.db`（SQLite），demo 接口不依赖数据库。
- `demo01` 不需要 API Key（纯字符串模拟），可用来先验证链路通不通。

## 二、前端启动

```bash
cd frontend

# 1. 安装依赖（项目按 pnpm 管理，别用 npm 混装）
pnpm install

# 2. 只启动前端
pnpm dev
# 或：一条命令同时启动前后端
pnpm dev:all
```

浏览器打开 `http://localhost:8080`，即可在聊天页与后端 `/api/chat` 流式对话（AI 回答已用 markstream-vue 渲染 Markdown）。

## 三、AI 接口（DeepSeek）

| 项 | 值 |
|---|---|
| base_url | `https://api.deepseek.com` |
| 模型 | `deepseek-flash`（当前推荐）/ `deepseek-v4-pro`（更强） |
| 兼容性 | OpenAI 兼容格式，直接用 `openai` SDK |

DeepSeek 同时支持两种调用形态，本项目两种都给了例子：

- **Responses API**（`client.responses.create`）——笔记里用的就是这种，`demo02`/`demo03`/`chat` 走这条。
  流式事件名和 OpenAI 一致：`response.reasoning_text.delta`（思考）、`response.output_text.delta`（正文）。
- **Chat Completions**（`client.chat.completions.create`）——`demo04` 走这条，返回标准 OpenAI 格式，
  **Apifox 能自动合并**，调试体验最好。

## 四、用 Apifox 查看 / 调试接口

### 4.1 先分清两个地址（最容易踩的坑）

| 场景 | 地址 | 说明 |
|---|---|---|
| 浏览器前端 | `http://localhost:8080/api/...` | 走 Vite 代理，转发到 8000 |
| **Apifox** | **`http://127.0.0.1:8000/api/...`** | **直连 FastAPI，不要走 8080** |

Apifox 是独立客户端，直接访问后端本身即可，不需要经过 Vite 代理。所以 Apifox 里的地址是
`http://127.0.0.1:8000`，路径照抄后端路由（带 `/api` 前缀）。

### 4.2 自动导入接口文档（推荐）

FastAPI 会自动生成 OpenAPI 文档，Apifox 可以直接导入：

- Swagger UI（浏览器里先看看）：`http://127.0.0.1:8000/docs`
- OpenAPI JSON：`http://127.0.0.1:8000/openapi.json`

Apifox 里的操作：**项目设置 → 导入数据 → OpenAPI/Swagger → 通过 URL 导入**，
填 `http://127.0.0.1:8000/openapi.json`，确定即可。之后所有接口会自动出现在项目里。

> `http://127.0.0.1` 是本地地址，**Apifox 网页版访问不到**，请用 Apifox 桌面版；
> 或者给浏览器装 Apifox 扩展，让网页版也能访问本地接口。

### 4.3 手动建接口（不想导入时）

在 Apifox 里新建一个 HTTP 接口，例如测试 `demo03`：

- 方法 / 地址：`POST` `http://127.0.0.1:8000/api/demo03`
- Body（JSON）：
  ```json
  { "input": "你好，介绍一下自己" }
  ```
- Header：`Content-Type: application/json`

发送即可。`demo02`/`demo03`/`demo04` 的请求体都是同一个结构 `{ "input": "..." }`；
`/api/chat` 多一个可选字段 `conversation_id`。

### 4.4 看流式（SSE）响应

Apifox **≥ 2.6.49** 会自动识别响应头里的 `Content-Type: text/event-stream`，
并把响应按 SSE 事件解析，在**「时间线」视图**里实时滚动显示。

- `demo02` / `demo03`：返回的 `data:` 里是**纯文本或 Responses API 的 JSON**，
  Apifox 只会原样展示事件流（**不会**自动合并成一段完整的话）——这是正常的，看时间线即可。
- `demo04`：返回标准 **OpenAI Chat Completions** 格式，Apifox 内置规则会
  **自动把碎片合并成可读文本**，还能展示 DeepSeek 的思考过程。**想在 Apifox 里看得舒服，就调 demo04。**

### 4.5 如果想让 demo03 也自动合并

`demo03` 下发的是纯文本 + `[THINK]` / `[ANSWER]` / `[DONE]` 三种标记，不属于 Apifox 内置识别的格式。
可以在该接口的 **后置操作 → 自定义脚本** 里加一段合并逻辑：

```javascript
// 把 [THINK]/[ANSWER] 标记的纯文本 SSE 合并成可读文本
const sseContent = pm.response.text();
let thinking = '';
let answer = '';
let phase = '';

sseContent.split('\n').forEach((line) => {
  const m = line.match(/^data:\s?(.*)$/);
  if (!m) return;
  const data = m[1];
  if (data === '[THINK]') { phase = 'think'; return; }
  if (data === '[ANSWER]') { phase = 'answer'; return; }
  if (data === '[DONE]') return;
  if (phase === 'think') thinking += data;
  else if (phase === 'answer') answer += data;
});

pm.visualizer.set(`【思考过程】\n${thinking}\n\n【回答】\n${answer}`);
```

脚本结果会显示在响应体的 **Visualize** 标签页里。

## 五、接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/demo01` | SSE：简单字符串流式返回（不需要 API Key） |
| POST | `/api/demo02` | SSE：DeepSeek Responses API 原始流式 |
| POST | `/api/demo03` | SSE：分类思考过程与回答（前端在用这个） |
| POST | `/api/demo04` | SSE：DeepSeek Chat Completions 流式（Apifox 可自动合并） |
| POST | `/api/login` | Session 登录（演示） |
| GET | `/api/me` | 读取当前 session 用户 |
| POST | `/api/logout` | 退出登录 |
| GET | `/api/conversations` | 会话列表 |
| POST | `/api/conversations` | 新建会话 |
| GET | `/api/conversations/{id}/messages` | 会话消息列表 |
| POST | `/api/chat` | 流式聊天（带消息持久化） |

## 六、与原笔记的差异

1. **代理 rewrite**：笔记里 `vite.config.ts` 的代理写了
   `rewrite: (path) => path.replace(/^\/api/, '')`，但后端路由本身定义的是
   `/api/demo03` 这类带 `/api` 前缀的路径，两者冲突会导致 404。
   本项目保留后端的 `/api` 前缀，**去掉了代理里的 rewrite**。

2. **结束标记判断**：笔记前端用 `event.event === 'done'` 判断结束，但后端下发的是
   `data: [DONE]`（在 data 字段里，没有 `event:` 字段）。前端改为判断
   `event.data === '[DONE]'`。

3. **请求体用 Pydantic 模型**：笔记里是 `params: dict`，FastAPI 无法据此生成字段说明，
   导入 Apifox / Swagger 后 body 是空的。本项目改成 `ChatParams` / `ChatRequest` 模型类，
   文档里能看到 `input`、`conversation_id` 字段。

4. **AI 换成 DeepSeek**：`base_url` 改为 `https://api.deepseek.com`，模型改为 DeepSeek 系列。
   代码里仍用 `client.responses.create(...)`——因为 DeepSeek 原生支持 Responses API，
   且流式事件名与 OpenAI 一致，所以 `demo.py` / `chat.py` 的处理逻辑无需改动。

5. **SSE 分帧（会被截断的坑）**：笔记里直接 `yield f"data: {event.delta}\n\n"`，
   但模型输出的 markdown 里几乎必然有换行。SSE 规范要求每一行都以 `data:` 开头，
   换行后的内容会被解析器当成「未知字段」**直接丢掉，回答被截断**。
   本项目改用 `common/sse.py` 的 `sse_frame()`：把多行文本拆成多个 `data:` 行
   （`"a\nb"` → `data: a\ndata: b\n\n`，SSE 解析后仍是 `"a\nb"`）。
   单行内容的输出与原来**完全一致**，所以前端无需改动。
