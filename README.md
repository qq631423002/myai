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
│   ├── models/              # 实体类：User / Conversation / Message / Book
│   ├── uploads/avatars/     # 用户上传的头像（对外静态访问）
│   ├── data/                # 私有数据（不走静态服务，别人下载不到）
│   │   ├── books/           #   上传的书原文（txt/md）
│   │   └── rag/             #   Chroma 向量库（读书陪读的检索索引）
│   ├── rag/                 # RAG 能力层（读书陪读用）
│   │   ├── reader.py        #   文本解码 + 章节识别 + 切块 + 页码换算
│   │   ├── embedding.py     #   本地中文向量模型（bge-small-zh）
│   │   └── store.py         #   Chroma 读写：建索引 / 检索
│   └── routers/
│       ├── demo.py          # SSE 示例 demo01~demo04
│       ├── auth.py          # 注册 / 登录 / 个人资料 / 头像
│       ├── chat.py          # 会话/消息 CRUD + 删除 + 流式聊天
│       └── book.py          # AI 读书陪读：上传书 + 建索引 + 带页码引用问答
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
| GET | `/api/books` | 书架列表（含建索引进度） |
| GET | `/api/books/{id}` | 书详情 + 章节目录 |
| GET | `/api/books/{id}/chapter/{n}` | 读第 n 章的原文 |
| POST | `/api/books/upload` | 上传 txt/md 书（后台建向量索引） |
| POST | `/api/books/rebuild` | 重建向量索引 |
| DELETE | `/api/books/{id}` | 删书（含向量库与原始文件） |
| POST | `/api/books/ask` | 对书提问，流式回答（带章节/页码引用） |

## 六、AI 读书陪读（RAG）

这是与「AI 聊天 / 天气 / 路线 / 海龟汤」并列的第五个功能：**上传一本书，按章节问答，回答带页码定位**。

### 6.1 它和「AI 聊天」有什么本质区别

聊天页是把历史消息直接喂给模型；读书页**不能**这么做 —— 一本长篇几十万字，远超上下文。
所以这里走的是 RAG（检索增强生成）：

```
上传 txt ──▶ 解析章节、切块 ──▶ 逐块向量化 ──▶ 存进 Chroma 向量库
                                                    │
用户提问 ──▶ 问题向量化 ──▶ 在向量库里找最相关的 6 块 ──▶ 拼进提示词 ──▶ 模型作答并标注页码
```

关键点：**模型只看到被检索出来的那几段原文**，而不是整本书。这也意味着它必须靠检索，
不能凭记忆瞎编 —— 提示词里明确要求「片段里没有的就直说书里没提到」，并照抄片段给出的章节和页码。

### 6.2 为什么用本地 embedding 模型

DeepSeek **没有公开的 embedding 接口**，做 RAG 必须有另一个向量化方案。这里选本地模型：

| 方案 | 结论 |
|---|---|
| OpenAI embedding | 中文效果好，但要再申请一个 Key、按量计费 |
| **本地 sentence-transformers** | **本项目采用**：免费、离线、中文够用，纯 CPU 可跑 |
| Chroma 自带的默认模型 | 是英文 onnx 模型，中文检索效果差，不推荐 |

默认模型 `BAAI/bge-small-zh-v1.5`（512 维），首次使用会自动下载约 100MB 权重。
国内直连 huggingface.co 基本超时，所以**默认走 `hf-mirror.com` 镜像**（可在 `.env` 里改）。

> 首次上传书时会有一次模型加载（几秒），之后常驻内存，检索很快。
> 纯 CPU 建索引速度约 26 块/秒，一本 30 万字的书大约 1 分钟。

### 6.3 页码是怎么来的（重要）

txt 文件本身**没有分页信息**，所以这里的页码是**按字数估算**的：

- 约定 1000 字 = 1 页（中文电子书的常见密度），换算函数在 `rag/reader.py` 的 `char_to_page()`
- 每个检索块都记录了它在全文里的字符偏移 → 偏移换算成页码 → 拼进提示词供模型引用

所以它是「**定位用的估算页**」，不是 PDF 的真实页码。这样做的好处是不依赖任何外部信息，
任何 txt 都能给出一个稳定、可跳转的定位。

### 6.4 章节是怎么识别出来的

同样不靠 AI 猜，而是用排版结构正则匹配（`rag/reader.py`）：

- 强标记：`第一章`、`第 12 节`、`Chapter 3`、`楔子`、`尾声`、`后记`……
- 弱标记：`1、xxx`、`§3 xxx`（额外要求整行很短、且不以句号结尾，避免把正文里的编号列表当成章节）

一本书**完全没有章节标记**也能用：整本当作一章「全文」，检索问答照样正常，只是没有章节维度。

### 6.5 怎么用

1. 后端启动（第一次会自动下载 embedding 模型，耐心等）
2. 前端进「读书陪读」页 → **上传一本书**（`.txt` / `.md`，最大 50MB）
3. 等左侧书架上的进度从「建索引中 x%」变成「N 章 · M 页」
4. 提问，例如「第三章主角为什么离开？」，回答会标注 `（第3章·第45页）`
5. 回答下方有「📎 依据」小标签，**点它可以直接跳到那一章的原文**核对
6. 左侧目录任意点一章，右侧就切换成原文阅读模式；目录标题栏可点击**折叠/展开**
7. 提问后模型会先「思考」，思考过程实时滚动显示（历史轮次里折叠起来，点开可看）

### 6.6 数据存在哪

| 内容 | 位置 |
|---|---|
| 书籍元数据、章节目录、索引进度 | 数据库 `books` 表 |
| 原始 txt 文件 | `backend/data/books/<随机名>.txt` |
| 向量索引 | `backend/data/rag/`（Chroma 持久化目录） |

一本书对应一个 Chroma collection（`book_{id}`），所以**删书 = 删 collection + 删文件 + 删记录**。
`backend/data/` 已在 `.gitignore` 里，这些本地数据不会进版本库。

> 为什么书不放 `uploads/`：`main.py` 把 `uploads/` 整个挂成了静态目录（给头像用），
> 书和向量库放进去的话，任何人知道文件名就能直接下载别人的书。
> 所以私有数据统一放 `backend/data/`，只通过带权限校验的接口访问。

### 6.7 谁的书归谁

和聊天一样支持**游客免登录**：登录用户按 `user_id` 存书，游客按 session 里的随机 `guest_key` 存书，
彼此看不到对方的书架。游客的书在浏览器会话失效后会失去归属（不会被自动清理，需要手动清目录）。

### 6.8 流式协议

和聊天页一样是 SSE，每帧形如 `data: xxx`。读书问答额外多一个 `[SOURCES]` 帧：

| 帧 | 含义 |
|---|---|
| `[SOURCES]{...}` | 本轮检索到的章节/页码（JSON），前端渲染成「📎 依据」标签 |
| `[THINK]` | 之后的帧是**思考过程**（推理内容，和正式回答分块渲染） |
| `[ANSWER]` | 之后的帧是**正式回答**正文 |
| `[DONE]` | 结束 |

为什么要转发思考过程：模型回答前会先推理，问整本书或某一章时往往要思考几十秒。
早期版本只转发正文，用户在推理期间看不到任何输出，体验上就是「提了问半天没反应」。
现在推理的字会先滚出来，等待期间有明确反馈。

> 注意：正文和思考是**分开渲染**的两个区，思考过程不会混进正式回答里。

### 6.9 常见问题

- **问什么都答「书里没有明确提到」**：说明检索没命中。换更贴近原文的说法再问；确认书里确实有相关内容。
- **上传后一直停在「建索引中」**：看后端控制台。第一次要下载模型；下载失败会变成「索引失败」并显示原因。
- **想换更准的模型**：`.env` 里改 `EMBEDDING_MODEL=BAAI/bge-base-zh-v1.5`（768 维，慢一倍），改完要**重建索引**。
- **换过 embedding 模型后**：必须对每本书点「重建索引」，因为旧向量和新模型不在同一个向量空间里。

## 七、与原笔记的差异

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
