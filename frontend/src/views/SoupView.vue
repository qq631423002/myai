<template>
  <div class="page">
    <!-- ===== AI 正在出题 ===== -->
    <div v-if="generating" class="generating">
      <div class="gen-icon">🎲</div>
      <div class="gen-text">
        <b>AI 正在现场出题…</b>
        <p>它要先编一个离奇的情境，再想一个自洽的真相，大概要半分钟</p>
      </div>
      <span class="dots"><span></span><span></span><span></span></span>
    </div>

    <!-- ===== 汤面卡片 ===== -->
    <div v-if="soup && !generating" class="puzzle" :class="{ solved }">
      <div class="puzzle-head">
        <span class="badge-difficulty">{{ soup.difficulty }}</span>
        <span v-for="t in soup.tags" :key="t" class="badge-tag">{{ t }}</span>
        <span v-if="source" class="badge-source">{{ source }}</span>
        <span class="spacer"></span>
        <div class="head-actions">
          <select v-model="pickedDifficulty" class="select">
            <option value="">随机难度</option>
            <option v-for="d in difficulties" :key="d" :value="d">{{ d }}</option>
          </select>
          <button
            class="ghost-btn ai-btn"
            :disabled="asking || generating"
            @click="generatePuzzle"
          >
            🎲 AI 现场出题
          </button>
          <button
            class="ghost-btn"
            :disabled="asking || generating"
            @click="newPuzzle(pickedDifficulty)"
          >
            🔄 换一题
          </button>
          <button
            class="ghost-btn"
            :disabled="asking || generating || !!revealed"
            @click="giveUp"
          >
            🏳️ 认输看汤底
          </button>
        </div>
      </div>

      <div class="puzzle-body">
        <div class="puzzle-icon">🐢</div>
        <div class="puzzle-text">
          <h2 class="puzzle-title">{{ soup.title }}</h2>
          <p class="surface">{{ soup.surface }}</p>
        </div>
      </div>
      <p class="puzzle-tip">
        你只能问<strong>是非题</strong>（AI 只会回答「是」「否」「无关」）。
        推理清楚了就说出你的完整猜测，AI 会告诉你对不对。
      </p>
    </div>

    <!-- ===== 认输 / 揭晓 ===== -->
    <div v-if="revealed" class="reveal">
      <div class="reveal-head">🧩 汤底（真相）</div>
      <p class="reveal-text">{{ revealed }}</p>
    </div>

    <div v-if="error" class="panel-err">⚠️ {{ error }}</div>

    <!-- ===== 问答区 ===== -->
    <div ref="scrollRef" class="chat-area">
      <div v-if="turns.length === 0 && !asking" class="empty">
        <div class="empty-icon">🤔</div>
        <p>开始提问吧，比如「他是自杀的吗？」</p>
      </div>

      <div v-for="(t, i) in turns" :key="i" class="turn" :class="t.role">
        <div v-if="t.role === 'assistant'" class="verdict" :class="verdictMeta(t.verdict).cls">
          {{ verdictMeta(t.verdict).label }}
        </div>
        <div class="bubble" :class="[t.role, t.verdict || '']">{{ t.content }}</div>
      </div>

      <!-- 主持人正在回答 -->
      <div v-if="asking" class="turn assistant">
        <div v-if="!answer" class="bubble assistant thinking">
          <span class="dots"><span></span><span></span><span></span></span>
        </div>
        <template v-else>
          <div class="verdict" :class="verdictMeta(parseVerdict(answer)).cls">
            {{ verdictMeta(parseVerdict(answer)).label }}
          </div>
          <div class="bubble assistant">{{ answer }}<span class="cursor"></span></div>
        </template>
      </div>
    </div>

    <!-- ===== 输入栏 ===== -->
    <div class="input-bar">
      <input
        v-model="question"
        class="chat-input"
        :placeholder="solved ? '已经猜对啦，点“换一题”继续' : '问一个是非题，或说出你的完整猜测…'"
        :disabled="asking || solved"
        @keypress.enter="send"
      />
      <button class="send-btn" :disabled="asking || solved || !question.trim()" @click="send">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
          <path d="M3.4 20.4 21.85 12 3.4 3.6l-.01 6.53L14 12 3.39 13.87l.01 6.53z" />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { nextTick, onMounted, ref, watch } from 'vue'

interface Soup {
  id: string
  title: string
  difficulty: string
  tags: string[]
  surface: string
}

type Verdict = 'yes' | 'no' | 'irrelevant' | 'solved' | 'unknown'

interface Turn {
  role: 'user' | 'assistant'
  content: string
  verdict?: Verdict
}

const soup = ref<Soup | null>(null)
const difficulties = ref<string[]>([])
const pickedDifficulty = ref('')
const turns = ref<Turn[]>([])
const question = ref('')
const asking = ref(false)
const generating = ref(false) // AI 正在现场出题
const source = ref('') // 题目来源：内置题库 / AI 现场出题
const answer = ref('')
const revealed = ref('')
const error = ref('')
const solved = ref(false)
const scrollRef = ref<HTMLElement | null>(null)
const askedIds = ref<string[]>([]) // 抽过的题，避免连着重复

const VERDICT_META: Record<Verdict, { label: string; cls: string }> = {
  yes: { label: '是', cls: 'v-yes' },
  no: { label: '否', cls: 'v-no' },
  irrelevant: { label: '无关', cls: 'v-meh' },
  solved: { label: '猜对了', cls: 'v-win' },
  unknown: { label: '', cls: '' },
}

function verdictMeta(v?: Verdict) {
  return VERDICT_META[v ?? 'unknown']
}

/** 从主持人的回答里解析出判定（模型会以「是」「否」「无关」「猜对了！」开头） */
function parseVerdict(text: string): Verdict {
  // 去掉各种括号、空白、标点，避免"【是】，…"这种写法解析不出来
  const t = text.replace(/[【】\[\]\s：:，,。！!]/g, '')
  if (t.startsWith('猜对了')) return 'solved'
  if (t.startsWith('无关') || t.startsWith('不相关')) return 'irrelevant'
  if (t.startsWith('否') || t.startsWith('不是') || t.startsWith('并非')) return 'no'
  if (t.startsWith('是') || t.startsWith('对') || t.startsWith('没错')) return 'yes'
  return 'unknown'
}

async function newPuzzle(difficulty?: string) {
  revealed.value = ''
  turns.value = []
  answer.value = ''
  error.value = ''
  solved.value = false

  try {
    const params = new URLSearchParams()
    if (difficulty) params.set('difficulty', difficulty)
    if (askedIds.value.length) params.set('exclude', askedIds.value.slice(-5).join(','))

    const res = await fetch(`/api/soup/new?${params.toString()}`)
    // 后端没启动时响应体是空的，直接 res.json() 会抛出看不懂的错
    const text = await res.text()
    if (!text) throw new Error(`请求失败（HTTP ${res.status}），后端可能没启动`)
    const json = JSON.parse(text)
    if (!res.ok) throw new Error(json.detail || '抽题失败')

    soup.value = json.题目 as Soup
    difficulties.value = (json.可选难度 as string[]) ?? []
    source.value = (json.来源 as string) ?? ''
    askedIds.value = [...askedIds.value, json.题目.id as string]
  } catch (e) {
    error.value = e instanceof Error ? e.message : '网络错误'
    soup.value = null
  }
}

/** 让 AI 现场编一道题（后端存库，只把汤面发回来） */
async function generatePuzzle() {
  if (asking.value || generating.value) return

  generating.value = true
  error.value = ''
  revealed.value = ''
  turns.value = []
  answer.value = ''
  solved.value = false

  try {
    const res = await fetch('/api/soup/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ difficulty: pickedDifficulty.value || null }),
    })
    const text = await res.text()
    if (!text) throw new Error(`请求失败（HTTP ${res.status}），后端可能没启动`)
    const json = JSON.parse(text)
    if (!res.ok) throw new Error(json.detail || 'AI 出题失败')
    soup.value = json.题目 as Soup
    source.value = (json.来源 as string) ?? 'AI 现场出题'
  } catch (e) {
    error.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    generating.value = false
  }
}

async function send() {
  const q = question.value.trim()
  if (!q || asking.value || !soup.value || solved.value) return

  turns.value.push({ role: 'user', content: q })
  // 之前的问答带上去当上下文（后端不存游戏状态）
  const history = turns.value
    .slice(0, -1)
    .map((t) => ({ role: t.role, content: t.content }))

  question.value = ''
  asking.value = true
  answer.value = ''
  error.value = ''
  await nextTick()
  scrollToBottom()

  try {
    await fetchEventSource('/api/soup/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: soup.value.id, question: q, history }),
      onmessage(ev) {
        const data = ev.data
        if (data === '[DONE]' || data === '[ANSWER]') return
        answer.value += data
      },
      onclose() {
        // 服务端正常关闭：抛异常阻止自动重连（否则会重复提问）
        throw new Error('stream-closed')
      },
      onerror(err) {
        // 题目过期（比如 AI 出的题被清掉了）后端会返回 404，给个明确提示
        const status = (err as { status?: number } | undefined)?.status
        if (status === 404) throw new Error('soup-expired')
        throw err
      },
    })
  } catch (e) {
    if (e instanceof Error && e.message === 'stream-closed') {
      // 正常结束，什么都不做
    } else if (e instanceof Error && e.message === 'soup-expired') {
      error.value = '这道题已经过期了（AI 出的题只保留最近 200 道），点「换一题」重开一局'
    } else {
      error.value = '主持人没回应，请检查后端或网络后重试'
    }
  } finally {
    const text = answer.value.trim()
    if (text) {
      const verdict = parseVerdict(text)
      turns.value.push({ role: 'assistant', content: text, verdict })
      if (verdict === 'solved') solved.value = true
    }
    asking.value = false
    answer.value = ''
    await nextTick()
    scrollToBottom()
  }
}

async function giveUp() {
  if (!soup.value) return
  try {
    const res = await fetch(`/api/soup/${soup.value.id}/answer`)
    const json = await res.json()
    if (!res.ok) throw new Error(json.detail || '获取失败')
    revealed.value = json.汤底 as string
    solved.value = true
  } catch (e) {
    error.value = e instanceof Error ? e.message : '网络错误'
  }
}

function scrollToBottom() {
  const el = scrollRef.value
  if (el) el.scrollTop = el.scrollHeight
}

watch([turns, answer], scrollToBottom, { deep: true })

onMounted(() => newPuzzle())
</script>

<style scoped>
.page {
  height: 100%;
  box-sizing: border-box;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  background: linear-gradient(160deg, #eef2ff 0%, #f5f7fb 45%, #fdf2f8 100%);
}

/* ===== 汤面卡片 ===== */
.puzzle {
  flex-shrink: 0;
  padding: 18px 20px;
  border-radius: 18px;
  color: #fff;
  background: linear-gradient(135deg, #4b3f72, #6b4f8f 55%, #8a5a9e);
  box-shadow: 0 10px 30px rgba(75, 63, 114, 0.28);
  transition: background 0.4s;
}

.puzzle.solved {
  background: linear-gradient(135deg, #b8860b, #d4a017 55%, #e6b422);
}

.puzzle-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.badge-difficulty {
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.24);
}

.badge-tag {
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11px;
  background: rgba(255, 255, 255, 0.14);
}

/* 题目来源徽章：内置题库 / AI 现场出题 */
.badge-source {
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11px;
  background: rgba(255, 255, 255, 0.22);
  border: 1px solid rgba(255, 255, 255, 0.35);
}

/* 「AI 现场出题」按钮：用金色和别的按钮区分开 */
.ai-btn {
  border-color: rgba(255, 219, 120, 0.75);
  background: rgba(255, 214, 100, 0.2);
}

.ai-btn:hover:not(:disabled) {
  background: rgba(255, 214, 100, 0.36);
}

/* ===== AI 正在出题 ===== */
.generating {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 22px 24px;
  border-radius: 18px;
  color: #fff;
  background: linear-gradient(135deg, #4b3f72, #8a5a9e);
  box-shadow: 0 10px 30px rgba(75, 63, 114, 0.28);
}

.gen-icon {
  flex-shrink: 0;
  font-size: 40px;
  animation: roll 1.8s ease-in-out infinite;
}

@keyframes roll {
  0%,
  100% {
    transform: translateY(0) rotate(-14deg);
  }
  50% {
    transform: translateY(-8px) rotate(14deg);
  }
}

.gen-text b {
  font-size: 15px;
}

.gen-text p {
  margin: 4px 0 0;
  font-size: 12.5px;
  line-height: 1.6;
  opacity: 0.82;
}

.generating .dots {
  margin-left: auto;
}

.generating .dots span {
  background: rgba(255, 255, 255, 0.8);
}

.spacer {
  flex: 1;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.select {
  padding: 5px 8px;
  border: none;
  border-radius: 9px;
  font-size: 12px;
  color: #3b3b52;
  background: rgba(255, 255, 255, 0.9);
  outline: none;
  cursor: pointer;
}

.ghost-btn {
  padding: 6px 12px;
  border: 1px solid rgba(255, 255, 255, 0.4);
  border-radius: 999px;
  font-size: 12.5px;
  color: #fff;
  background: rgba(255, 255, 255, 0.12);
  cursor: pointer;
  transition: all 0.18s;
}

.ghost-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.26);
}

.ghost-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.puzzle-body {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.puzzle-icon {
  font-size: 44px;
  line-height: 1;
  flex-shrink: 0;
  animation: bob 3.4s ease-in-out infinite;
}

@keyframes bob {
  0%,
  100% {
    transform: translateY(0) rotate(-3deg);
  }
  50% {
    transform: translateY(-6px) rotate(3deg);
  }
}

.puzzle-title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 600;
}

.surface {
  margin: 0;
  font-size: 15px;
  line-height: 1.75;
}

.puzzle-tip {
  margin: 12px 0 0;
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.2);
  font-size: 12px;
  line-height: 1.6;
  opacity: 0.85;
}

/* ===== 汤底 ===== */
.reveal {
  flex-shrink: 0;
  padding: 16px 20px;
  border-radius: 16px;
  background: #fffdf3;
  border: 1px solid #f0dca6;
  box-shadow: 0 8px 24px rgba(200, 160, 60, 0.14);
}

.reveal-head {
  font-size: 13px;
  font-weight: 600;
  color: #a1791b;
  margin-bottom: 8px;
}

.reveal-text {
  margin: 0;
  font-size: 14.5px;
  line-height: 1.8;
  color: #4a3f22;
}

.panel-err {
  flex-shrink: 0;
  padding: 12px 16px;
  border-radius: 14px;
  background: #fff;
  color: #ef4444;
  font-size: 13.5px;
  box-shadow: 0 6px 20px rgba(80, 100, 200, 0.08);
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
  box-shadow: 0 8px 28px rgba(80, 100, 200, 0.1);
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

.turn {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  animation: fade-up 0.25s ease;
}

.turn.user {
  flex-direction: row-reverse;
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
  max-width: 76%;
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.bubble.user {
  background: linear-gradient(135deg, #4d6bfe, #6a8bff);
  color: #fff;
  border-top-right-radius: 4px;
}

.bubble.assistant {
  background: #f4f6fb;
  color: #2a3040;
  border-top-left-radius: 4px;
}

.bubble.assistant.solved {
  background: #fff7e0;
  border: 1px solid #f0dca6;
  color: #6b5314;
}

/* 判定徽章 */
.verdict {
  flex-shrink: 0;
  min-width: 34px;
  height: 26px;
  padding: 0 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 700;
  color: #fff;
  margin-top: 2px;
}

.v-yes {
  background: #22c55e;
}

.v-no {
  background: #ef4444;
}

.v-meh {
  background: #9aa1b5;
}

.v-win {
  background: linear-gradient(135deg, #f0a500, #e8890a);
  box-shadow: 0 3px 10px rgba(232, 137, 10, 0.4);
}

.v-unknown {
  display: none;
}

/* 等待动画 */
.thinking {
  padding: 12px 16px;
}

.dots {
  display: flex;
  gap: 5px;
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

.cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: -0.15em;
  background: #8b5cf6;
  animation: blink 0.8s step-end infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
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
  box-shadow: 0 6px 20px rgba(80, 100, 200, 0.1);
  outline: none;
  transition: all 0.2s;
}

.chat-input:focus {
  border-color: #8b5cf6;
  box-shadow: 0 0 0 4px rgba(139, 92, 246, 0.12);
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
  background: linear-gradient(135deg, #8b5cf6, #6b4f8f);
  box-shadow: 0 4px 14px rgba(139, 92, 246, 0.35);
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

@media (max-width: 560px) {
  .puzzle-body {
    flex-direction: column;
    gap: 8px;
  }
  .bubble {
    max-width: 84%;
  }
}
</style>
