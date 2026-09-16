<template>
  <div class="page">
    <div class="shell">
      <!-- ===== 左侧：书架 + 目录 ===== -->
      <aside class="sidebar">
        <button class="upload-btn" :disabled="uploading || indexing" @click="pickFile">
          {{ uploading ? '正在上传…' : '＋ 上传一本书' }}
        </button>
        <input ref="fileRef" type="file" accept=".txt,.md" class="hidden-input" @change="onFileChange" />

        <div class="shelf">
          <p v-if="books.length === 0" class="shelf-empty">
            书架还空着<br />上传一个 txt 文件开始
          </p>
          <div
            v-for="b in books"
            :key="b.id"
            class="book-item"
            :class="{ active: b.id === current?.id }"
            @click="selectBook(b.id)"
          >
            <span class="book-icon">📖</span>
            <div class="book-meta">
              <span class="book-title" :title="b.title">{{ b.title }}</span>
              <span class="book-sub">
                <template v-if="b.status === 'indexing'">建索引中 {{ b.progress }}%</template>
                <template v-else-if="b.status === 'failed'">
                  <span class="fail">索引失败</span>
                </template>
                <template v-else>{{ b.chapter_count }} 章 · {{ b.page_count }} 页</template>
              </span>
            </div>
            <button class="del-btn" title="删除这本书" @click.stop="removeBook(b.id)">✕</button>
          </div>
        </div>

        <!-- 目录：点了在右侧看原文 -->
        <div v-if="current && chapters.length" class="toc">
          <!-- 点标题栏收起 / 展开目录。目录固定在侧栏底部，展开时章节列表向上生长 -->
          <button
            class="toc-head"
            :title="tocOpen ? '收起目录' : '展开目录'"
            :aria-expanded="tocOpen"
            @click="tocOpen = !tocOpen"
          >
            <span class="toc-head-text">目录</span>
            <span class="toc-count">{{ chapters.length }} 章</span>
            <span class="spacer"></span>
            <span class="chev" :class="{ up: !tocOpen }">⌄</span>
          </button>
          <div v-show="tocOpen" class="toc-list">
            <div
              v-for="c in chapters"
              :key="c.index"
              class="toc-item"
              :class="{ active: readingChapter === c.index }"
              @click="openChapter(c.index)"
            >
              <span class="toc-title">{{ c.title }}</span>
              <span class="toc-page">P{{ c.start_page }}</span>
            </div>
          </div>
        </div>
      </aside>

      <!-- ===== 右侧：问答 / 原文 ===== -->
      <section class="main">
        <!-- 没选书时的引导 -->
        <div v-if="!current" class="welcome">
          <div class="welcome-icon">📚</div>
          <h2>AI 读书陪读</h2>
          <p>
            上传一本 <code>.txt</code> 书，AI 会把它切成片段建好索引。<br />
            之后你问任何问题，它都<strong>只依据书里的原文</strong>回答，并标出<strong>第几章 · 第几页</strong>。
          </p>
          <ul class="welcome-list">
            <li>「这本书讲了什么？」——先来一份全书概览</li>
            <li>「第三章主角为什么离开？」——带页码定位</li>
            <li>「点左边的目录」——直接读原文对照</li>
          </ul>
        </div>

        <template v-else>
          <!-- 顶部：书名 + 状态 -->
          <header class="bar">
            <div class="bar-left">
              <h1 :title="current.title">{{ current.title }}</h1>
              <span class="bar-sub">
                {{ current.char_count.toLocaleString() }} 字 · {{ current.page_count }} 页 ·
                {{ current.chapter_count }} 章 · {{ current.chunk_count }} 个检索块
              </span>
            </div>
            <div class="bar-right">
              <button class="ghost-btn" :disabled="asking" @click="rebuild">🔁 重建索引</button>
              <button class="ghost-btn" :disabled="asking" @click="clearChat">🧹 清空问答</button>
            </div>
          </header>

          <!-- 索引中 / 失败 -->
          <div v-if="current.status === 'indexing'" class="notice">
            <b>正在把这本书切成片段并建索引…</b>
            <p>长篇小说要几十秒，请稍等。建好之后就能提问了。</p>
          </div>
          <div v-else-if="current.status === 'failed'" class="notice err">
            <b>索引没有建立成功</b>
            <p>{{ current.error || '未知原因' }}</p>
            <p class="notice-act">
              多半是中断或网络问题，点右上角
              <button class="inline-btn" :disabled="asking" @click="rebuild">🔁 重建索引</button>
              重试即可。
            </p>
          </div>

          <!-- 原文阅读模式 -->
          <div v-if="reading" class="reader">
            <div class="reader-head">
              <span class="reader-title">{{ reading.title }}</span>
              <span class="reader-page">
                第 {{ reading.start_page }}–{{ reading.end_page }} 页 · {{ reading.char_count }} 字
              </span>
              <span class="spacer"></span>
              <button class="ghost-btn" @click="reading = null">✕ 回到问答</button>
            </div>
            <pre class="reader-body">{{ reading.content }}</pre>
          </div>

          <!-- 问答模式 -->
          <template v-else>
            <div ref="scrollRef" class="chat-area">
              <div v-if="turns.length === 0 && !asking" class="empty">
                <div class="empty-icon">💡</div>
                <p>试试问它几个问题，回答里会带章节和页码：</p>
                <div class="chips">
                  <button v-for="q in examples" :key="q" class="chip" @click="ask(q)">{{ q }}</button>
                </div>
              </div>

              <div v-for="(t, i) in turns" :key="i" class="turn" :class="t.role">
                <div class="bubble" :class="t.role">
                  <!-- 历史轮次的思考过程：默认折叠，想看再点开 -->
                  <details v-if="t.thinking" class="thinking">
                    <summary class="thinking-label">💭 思考过程</summary>
                    <div class="thinking-text">{{ t.thinking }}</div>
                  </details>
                  <MarkdownRender
                    v-if="t.role === 'assistant'"
                    class="md"
                    mode="chat"
                    :content="t.content"
                    :final="true"
                  />
                  <template v-else>{{ t.content }}</template>
                </div>
                <!-- 展示这一轮检索到哪些片段，让「引用」可核对 -->
                <div v-if="t.role === 'assistant' && t.sources?.length" class="sources">
                  <span class="sources-label">📎 依据</span>
                  <!-- 章节号有效时可点击，直接跳到那一章的原文核对 -->
                  <button
                    v-for="s in t.sources"
                    :key="s.chapter_index + '-' + s.page"
                    class="source-chip"
                    :disabled="s.chapter_index <= 0"
                    @click="openChapter(s.chapter_index)"
                  >
                    第{{ s.chapter_index }}章 · 第{{ s.page }}页
                  </button>
                </div>
              </div>

              <div v-if="asking" class="turn assistant">
                <div class="bubble assistant">
                  <!-- 模型正在思考：把过程实时滚出来，别让用户干等 -->
                  <div v-if="thinking" class="thinking live">
                    <span class="thinking-label">💭 思考过程</span>
                    <div class="thinking-text">{{ thinking }}</div>
                  </div>

                  <!-- 还没收到任何内容：显示三个跳动的点（与聊天页同款） -->
                  <div v-if="!answer && !thinking" class="dots">
                    <span></span><span></span><span></span>
                  </div>

                  <!-- 正文流式渲染 -->
                  <MarkdownRender
                    v-if="answer"
                    class="md"
                    mode="chat"
                    :content="answer"
                    :final="false"
                  />
                </div>
              </div>
            </div>

            <div class="input-bar">
              <input
                v-model="question"
                class="chat-input"
                :disabled="asking || current?.status !== 'ready'"
                :placeholder="
                  current?.status === 'ready'
                    ? '问这本书的任何问题，例如「第三章主角为什么离开？」'
                    : '索引还没建好，暂时不能提问'
                "
                @keypress.enter="send"
              />
              <button
                class="send-btn"
                :disabled="asking || !question.trim() || current?.status !== 'ready'"
                @click="send"
              >
                <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                  <path d="M3.4 20.4 21.85 12 3.4 3.6l-.01 6.53L14 12 3.39 13.87l.01 6.53z" />
                </svg>
              </button>
            </div>
          </template>
        </template>

        <div v-if="error" class="panel-err">⚠️ {{ error }}</div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { fetchEventSource } from '@microsoft/fetch-event-source'
import MarkdownRender from 'markstream-vue'
import 'markstream-vue/index.css'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

interface BookSummary {
  id: number
  title: string
  filename: string
  char_count: number
  page_count: number
  chapter_count: number
  chunk_count: number
  status: 'indexing' | 'ready' | 'failed'
  progress: number
  error: string
  created_at: string
}

interface Chapter {
  index: number
  title: string
  start_page: number
  end_page: number
}

interface Source {
  chapter_index: number
  page: number
}

interface Turn {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  thinking?: string
}

const books = ref<BookSummary[]>([])
const current = ref<BookSummary | null>(null)
const chapters = ref<Chapter[]>([])
const turns = ref<Turn[]>([])
const question = ref('')
const answer = ref('')
const thinking = ref('')
// 当前区段：模型可能先思考再作答，用这个区分内容该进哪一块
const phase = ref<'thinking' | 'answering'>('thinking')
const answerSources = ref<Source[]>([])
const asking = ref(false)
const uploading = ref(false)
const error = ref('')
const reading = ref<{ title: string; content: string; start_page: number; end_page: number; char_count: number } | null>(null)
const readingChapter = ref<number | null>(null)
const tocOpen = ref(true) // 目录是否展开（折叠后书架撑满左侧）
const scrollRef = ref<HTMLElement | null>(null)
const fileRef = ref<HTMLInputElement | null>(null)

const examples = ['这本书讲了什么？', '第一章讲了什么？', '全书的主要人物有哪些？']
const indexing = computed(() => books.value.some((b) => b.status === 'indexing'))

/** 后端没启动时响应体是空的，直接 res.json() 会抛出看不懂的错 */
async function readJson(res: Response) {
  const text = await res.text()
  if (!text) {
    throw new Error(res.ok ? '服务器返回了空响应' : `请求失败（HTTP ${res.status}），后端可能没启动`)
  }
  const json = JSON.parse(text)
  if (!res.ok) throw new Error(json.detail || '请求失败')
  return json
}

function pickFile() {
  fileRef.value?.click()
}

async function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  error.value = ''
  uploading.value = true
  try {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch('/api/books/upload', { method: 'POST', body: form })
    const json = await readJson(res)
    await loadBooks()
    await selectBook(json.book_id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '上传失败'
  } finally {
    uploading.value = false
  }
}

async function loadBooks() {
  try {
    const res = await fetch('/api/books')
    books.value = await readJson(res)
    // 同步当前书的索引状态（后台建完索引后，状态会从 indexing 变成 ready）
    if (current.value) {
      const fresh = books.value.find((b) => b.id === current.value?.id)
      if (fresh) current.value = fresh
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '读取书架失败'
  }
}

async function selectBook(id: number) {
  error.value = ''
  reading.value = null
  readingChapter.value = null
  turns.value = []
  try {
    const res = await fetch(`/api/books/${id}`)
    const json = await readJson(res)
    current.value = json as BookSummary
    chapters.value = (json.chapters ?? []) as Chapter[]
  } catch (err) {
    error.value = err instanceof Error ? err.message : '打开书失败'
  }
}

async function removeBook(id: number) {
  try {
    const res = await fetch(`/api/books/${id}`, { method: 'DELETE' })
    await readJson(res)
    if (current.value?.id === id) {
      current.value = null
      chapters.value = []
      turns.value = []
      reading.value = null
    }
    await loadBooks()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除失败'
  }
}

async function rebuild() {
  if (!current.value) return
  error.value = ''
  try {
    const res = await fetch('/api/books/rebuild', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ book_id: current.value.id }),
    })
    await readJson(res)
    await loadBooks()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '重建索引失败'
  }
}

function clearChat() {
  turns.value = []
  answer.value = ''
}

/** 打开某一章的原文，和问答对照着看 */
async function openChapter(index: number) {
  if (!current.value || index <= 0) return
  // 索引过程中原始文件可能还没就绪；直接给出提示，别打无意义的请求
  if (!chapters.value.some((c) => c.index === index)) {
    error.value = '找不到这一章的目录信息，无法打开原文。'
    return
  }
  error.value = ''
  try {
    const res = await fetch(`/api/books/${current.value.id}/chapter/${index}`)
    const json = await readJson(res)
    reading.value = {
      title: json.title,
      content: json.content,
      start_page: json.start_page,
      end_page: json.end_page,
      char_count: json.char_count,
    }
    readingChapter.value = index
  } catch (err) {
    error.value = err instanceof Error ? err.message : '读取原文失败'
  }
}

function scrollToBottom() {
  const el = scrollRef.value
  if (el) el.scrollTop = el.scrollHeight
}

async function send() {
  const q = question.value.trim()
  if (!q || asking.value || !current.value || current.value.status !== 'ready') return
  await ask(q)
}

async function ask(q: string) {
  // 索引没建好就不能提问，否则后端会返回 409；这里先挡住，给出明确提示
  if (!current.value || asking.value) return
  if (current.value.status !== 'ready') {
    error.value = '这本书的索引还没建好（或建立失败），暂时不能提问。'
    return
  }

  const history = turns.value.map((t) => ({ role: t.role, content: t.content }))
  turns.value.push({ role: 'user', content: q })
  question.value = ''
  asking.value = true
  answer.value = ''
  thinking.value = ''
  phase.value = 'thinking'
  answerSources.value = []
  error.value = ''
  reading.value = null
  await nextTick()
  scrollToBottom()

  try {
    await fetchEventSource('/api/books/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ book_id: current.value.id, input: q, history }),
      onmessage(ev) {
        const data = ev.data
        if (data === '[DONE]') return
        // 切换区段：之后的内容是思考过程还是正式回答
        if (data === '[THINK]') {
          phase.value = 'thinking'
          return
        }
        if (data === '[ANSWER]') {
          phase.value = 'answering'
          return
        }
        // 服务端在正文之前先下发本轮检索到的来源（JSON），用于渲染「依据」标签
        if (data.startsWith('[SOURCES]')) {
          try {
            answerSources.value = JSON.parse(data.slice(9)) as Source[]
          } catch {
            answerSources.value = []
          }
          return
        }
        if (phase.value === 'thinking') thinking.value += data
        else answer.value += data
        scrollToBottom()
      },
      onclose() {
        // 服务端正常关闭：抛异常阻止 fetchEventSource 自动重连（否则会重复提问）
        throw new Error('stream-closed')
      },
      onerror(err) {
        throw err
      },
    })
  } catch (e) {
    if (!(e instanceof Error && e.message === 'stream-closed')) {
      error.value = '生成失败，请检查后端服务是否正常。'
    }
  } finally {
    const text = answer.value.trim()
    if (text) {
      turns.value.push({
        role: 'assistant',
        content: text,
        sources: answerSources.value,
        thinking: thinking.value.trim() || undefined,
      })
    }
    answer.value = ''
    thinking.value = ''
    answerSources.value = []
    asking.value = false
    await nextTick()
    scrollToBottom()
  }
}

// 上传后后台建索引：轮询状态，建好了自动变成可提问
let timer: number | undefined
onMounted(async () => {
  await loadBooks()
  const first = books.value[0]
  if (first) await selectBook(first.id)
  timer = window.setInterval(() => {
    if (indexing.value) loadBooks()
  }, 2000)
})
onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<style scoped>
.page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: linear-gradient(160deg, #eef7f0 0%, #f5f7fb 45%, #fdf2f8 100%);
}

.shell {
  width: 100%;
  max-width: 1180px;
  height: 100%;
  max-height: 780px;
  display: flex;
  gap: 16px;
}

/* ===== 侧边栏 ===== */
.sidebar {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 12px 40px rgba(60, 120, 90, 0.12);
  min-height: 0;
  /* 兜底：任何情况下内容都不溢出卡片 */
  overflow: hidden;
}

.upload-btn {
  padding: 10px 0;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  color: #fff;
  background: linear-gradient(135deg, #10b981, #059669);
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
  cursor: pointer;
  transition: all 0.2s;
}

.upload-btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.upload-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.hidden-input {
  display: none;
}

.shelf {
  display: flex;
  flex-direction: column;
  gap: 5px;
  /* 占据侧栏上半部分，自身滚动。
     留一个高度下限，保证目录展开时已上传的书不会被挤没。 */
  flex: 1 1 auto;
  /* 硬保证：不管目录展开多少，已上传的书至少露出这么多高度 */
  min-height: 84px;
  overflow-y: auto;
}

.shelf-empty {
  text-align: center;
  font-size: 12.5px;
  line-height: 1.9;
  color: #a6acc0;
  padding: 18px 0;
}

.book-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 11px;
  cursor: pointer;
  transition: all 0.16s;
}

.book-item:hover {
  background: #f2f7f4;
}

.book-item.active {
  background: #e8f7f0;
}

.book-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.book-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  line-height: 1.35;
}

.book-title {
  font-size: 13px;
  font-weight: 600;
  color: #1f2430;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.book-sub {
  font-size: 11px;
  color: #9aa1b5;
}

.fail {
  color: #ef4444;
}

.del-btn {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: #c2c7d6;
  font-size: 11px;
  cursor: pointer;
  opacity: 0;
  transition: all 0.15s;
}

.book-item:hover .del-btn {
  opacity: 1;
}

.del-btn:hover {
  background: #fee2e2;
  color: #ef4444;
}

/* ===== 目录 =====
   两条布局要求：
   1) 不管展开还是收起，目录都要贴在侧栏底部 —— 用 margin-top: auto
      把剩余空间全推给上面的书架。
   2) 展开时章节列表向上生长，标题栏（展开/收起按钮）位置不跳动，
      也不会盖住上面的书架 —— 用 column-reverse 把标题栏固定在底部。
   （不用绝对定位，所以不存在遮挡问题，只是各自占位。） */
.toc {
  /* 可收缩：章节特别多时自己让位（配合下面列表的滚动条），
     而不是把侧栏撑溢出、被 border-radius 裁掉 */
  flex: 0 1 auto;
  /* 靠 margin-top: auto 把剩余空间推给上面的书架，从而始终贴底 */
  margin-top: auto;
  /* 高度上限：最多占侧栏 55%，剩下留给书架 —— 这样展开目录绝不会
     把已上传的书挤没，也不会盖住它们 */
  max-height: 55%;
  min-height: 0;
  /* column-reverse：DOM 里是「标题栏 + 列表」，反转后标题栏落在底部，
     列表向上生长，所以点展开时按钮位置不跳动 */
  display: flex;
  flex-direction: column-reverse;
  border-top: 1px solid #eef1f6;
  padding-top: 10px;
}

/* 目录标题栏：本身是个按钮，点它收起 / 展开目录 */
.toc-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px 8px;
  border: none;
  background: transparent;
  font-size: 12.5px;
  font-weight: 600;
  color: #4b5563;
  cursor: pointer;
  border-radius: 8px;
  transition: background 0.15s;
}

.toc-head:hover {
  background: #f4f6fb;
}

.toc-head-text {
  flex-shrink: 0;
}

/* 折叠箭头：展开时朝下，收起时朝上 */
.toc-head .chev {
  flex-shrink: 0;
  font-size: 15px;
  line-height: 1;
  color: #9aa1b5;
  transition: transform 0.24s ease;
}

.toc-head .chev.up {
  transform: rotate(180deg);
}

.toc-count {
  font-size: 11px;
  font-weight: 400;
  color: #a6acc0;
}

.toc-list {
  /* 占满目录区剩余高度并自己滚动；min-height: 0 是让它在 flex 里
     真的能被压缩（否则内容多时会把标题栏顶出可视区） */
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
}

.toc-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 8px;
  font-size: 12.5px;
  color: #5a6076;
  cursor: pointer;
  transition: all 0.15s;
}

.toc-item:hover {
  background: #f4f6fb;
  color: #4d6bfe;
}

.toc-item.active {
  background: #eef2ff;
  color: #4d6bfe;
  font-weight: 600;
}

.toc-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.toc-page {
  flex-shrink: 0;
  font-size: 11px;
  color: #b6bde0;
}

/* ===== 主区 ===== */
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.welcome {
  margin: auto;
  max-width: 460px;
  text-align: center;
  padding: 32px;
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 12px 40px rgba(60, 120, 90, 0.1);
}

.welcome-icon {
  font-size: 44px;
  margin-bottom: 10px;
}

.welcome h2 {
  margin: 0 0 10px;
  font-size: 19px;
  color: #1f2430;
}

.welcome p {
  margin: 0 0 14px;
  font-size: 13.5px;
  line-height: 1.8;
  color: #6b7280;
}

.welcome code {
  padding: 1px 5px;
  border-radius: 5px;
  background: #f1f5f9;
  font-size: 12.5px;
}

.welcome-list {
  margin: 0;
  padding: 0;
  list-style: none;
  text-align: left;
  font-size: 13px;
  line-height: 2;
  color: #8a90a3;
}

.bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 18px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 8px 28px rgba(60, 120, 90, 0.1);
}

.bar-left {
  flex: 1;
  min-width: 0;
}

.bar-left h1 {
  margin: 0 0 2px;
  font-size: 16px;
  font-weight: 600;
  color: #1f2430;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar-sub {
  font-size: 11.5px;
  color: #9aa1b5;
}

.bar-right {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.ghost-btn {
  padding: 6px 12px;
  border: 1px solid #e3e7f2;
  border-radius: 10px;
  background: #fff;
  color: #5a6076;
  font-size: 12.5px;
  cursor: pointer;
  transition: all 0.16s;
}

.ghost-btn:hover:not(:disabled) {
  border-color: #a7d8c0;
  color: #059669;
  background: #f2fbf7;
}

.ghost-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.notice {
  flex-shrink: 0;
  padding: 12px 16px;
  border-radius: 14px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  font-size: 13px;
  color: #92400e;
}

.notice b {
  display: block;
  margin-bottom: 3px;
}

.notice p {
  margin: 0;
  font-size: 12.5px;
  opacity: 0.85;
}

.notice.err {
  background: #fef2f2;
  border-color: #fecaca;
  color: #b91c1c;
}

.notice-act {
  margin-top: 6px !important;
}

/* 提示条里的内联按钮：看起来像链接，实际上就是那个操作 */
.inline-btn {
  padding: 2px 8px;
  border: 1px solid #f0a8a8;
  border-radius: 999px;
  background: #fff;
  color: #b91c1c;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.inline-btn:hover:not(:disabled) {
  background: #fee2e2;
}

.inline-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ===== 原文阅读 ===== */
.reader {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 8px 28px rgba(60, 120, 90, 0.1);
  overflow: hidden;
}

.reader-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 18px;
  border-bottom: 1px solid #eef1f6;
}

.reader-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2430;
}

.reader-page {
  font-size: 11.5px;
  color: #9aa1b5;
}

.spacer {
  flex: 1;
}

.reader-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin: 0;
  padding: 18px 22px;
  font-family: inherit;
  font-size: 14.5px;
  line-height: 2;
  color: #2a3040;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ===== 问答区 ===== */
.chat-area {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 8px 28px rgba(60, 120, 90, 0.1);
}

.empty {
  margin: auto;
  text-align: center;
  color: #a6acc0;
  font-size: 13px;
}

.empty-icon {
  font-size: 34px;
  margin-bottom: 8px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 12px;
}

.chip {
  padding: 6px 13px;
  border: 1px solid #d9e6de;
  border-radius: 999px;
  background: #f7fbf9;
  color: #4b7a63;
  font-size: 12.5px;
  cursor: pointer;
  transition: all 0.16s;
}

.chip:hover {
  border-color: #10b981;
  color: #059669;
  background: #ecfbf4;
}

.turn {
  display: flex;
  flex-direction: column;
  gap: 6px;
  animation: fade-up 0.25s ease;
}

.turn.user {
  align-items: flex-end;
}

@keyframes fade-up {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.bubble {
  max-width: 82%;
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.75;
  word-break: break-word;
}

.bubble.user {
  background: linear-gradient(135deg, #10b981, #34d399);
  color: #fff;
  border-top-right-radius: 4px;
  white-space: pre-wrap;
}

.bubble.assistant {
  background: #f4f6fb;
  color: #2a3040;
  border-top-left-radius: 4px;
}

.md {
  font-size: 14px;
  line-height: 1.75;
}

/* 引用来源 */
.sources {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding-left: 4px;
}

.sources-label {
  font-size: 11.5px;
  color: #9aa1b5;
}

.source-chip {
  padding: 3px 9px;
  border: 1px solid #d6e4f7;
  border-radius: 999px;
  background: #f4f8ff;
  color: #4d6bfe;
  font-size: 11.5px;
  cursor: pointer;
  transition: all 0.15s;
}

.source-chip:hover:not(:disabled) {
  border-color: #4d6bfe;
  background: #eef2ff;
}

.source-chip:disabled {
  color: #9aa1b5;
  background: #f4f6fb;
  border-color: #e3e7f2;
  cursor: default;
}

/* ===== 思考过程 =====
   与聊天页（ChatView）保持一致：同样的左边竖线、淡蓝底、斜体小字，
   让「推理内容」在两个页面里看起来是同一个东西。 */
.thinking {
  margin-bottom: 8px;
  padding: 8px 10px;
  border-left: 3px solid #c7d0f5;
  border-radius: 6px;
  background: rgba(77, 107, 254, 0.06);
  color: #7a8299;
  font-size: 12.5px;
  font-style: italic;
}

.thinking-label {
  display: block;
  margin-bottom: 4px;
  font-style: normal;
  font-weight: 600;
  color: #4d6bfe;
}

/* 还在生成时：内容会一直变长，给个滚动上限免得把气泡撑得没边 */
.thinking.live .thinking-text {
  max-height: 220px;
  overflow-y: auto;
}

/* 历史轮次里标题是 <summary>：去掉浏览器默认三角，换自己的箭头 */
summary.thinking-label {
  cursor: pointer;
  list-style: none;
  user-select: none;
}

summary.thinking-label::-webkit-details-marker {
  display: none;
}

summary.thinking-label::before {
  content: '▸ ';
}

details[open] > summary.thinking-label::before {
  content: '▾ ';
}

.thinking-text {
  margin-top: 4px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
}

/* 等待动画（与聊天页同款） */
.dots {
  display: flex;
  gap: 5px;
  padding: 6px 2px;
}

.dots span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #b6bde0;
  animation: bounce 1.2s ease-in-out infinite;
}

.dots span:nth-child(2) {
  animation-delay: 0.15s;
}

.dots span:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes bounce {
  0%,
  60%,
  100% {
    transform: translateY(0);
    opacity: 0.5;
  }
  30% {
    transform: translateY(-5px);
    opacity: 1;
  }
}

/* ===== 输入栏 ===== */
.input-bar {
  flex-shrink: 0;
  display: flex;
  gap: 10px;
}

.chat-input {
  flex: 1;
  padding: 13px 18px;
  font-size: 14px;
  color: #2a3040;
  background: #fff;
  border: 1.5px solid transparent;
  border-radius: 999px;
  box-shadow: 0 6px 20px rgba(60, 120, 90, 0.1);
  outline: none;
  transition: all 0.2s;
}

.chat-input:focus {
  border-color: #10b981;
  box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.12);
}

.chat-input:disabled {
  background: #f7f8fc;
  color: #a6acc0;
}

.send-btn {
  flex-shrink: 0;
  width: 46px;
  height: 46px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  color: #fff;
  background: linear-gradient(135deg, #10b981, #047857);
  box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35);
  cursor: pointer;
  transition: all 0.2s;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px) scale(1.05);
}

.send-btn:disabled {
  opacity: 0.4;
  box-shadow: none;
  cursor: not-allowed;
}

.panel-err {
  flex-shrink: 0;
  padding: 12px 16px;
  border-radius: 14px;
  background: #fff;
  color: #ef4444;
  font-size: 13.5px;
  box-shadow: 0 6px 20px rgba(60, 120, 90, 0.08);
}

@media (max-width: 720px) {
  .shell {
    flex-direction: column;
  }
  .sidebar {
    width: 100%;
    max-height: 40%;
  }
  .bubble {
    max-width: 92%;
  }
}
</style>
