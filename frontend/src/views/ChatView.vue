<template>
  <div class="page">
    <!-- ===== 聊天主界面（游客不登录也能直接用）===== -->
    <div class="app-shell">
      <!-- 侧边栏：历史会话 -->
      <aside class="sidebar">
        <button class="new-chat-btn" :disabled="streaming" @click="newConversation">
          ＋ 新建对话
        </button>
        <div class="conv-list">
          <div
            v-for="conv in conversations"
            :key="conv.id"
            class="conv-item"
            :class="{ active: conv.id === currentConvId, editing: editingId === conv.id }"
            @click="selectConversation(conv.id)"
          >
            <!-- 重命名中：变成一个输入框（回车保存 / Esc 取消 / 失焦保存）-->
            <template v-if="editingId === conv.id">
              <input
                :ref="bindEditInput"
                v-model="editingTitle"
                class="conv-edit-input"
                maxlength="50"
                placeholder="对话名称"
                @click.stop
                @keypress.enter="saveTitle(conv.id)"
                @keydown.esc="cancelEdit"
                @blur="saveTitle(conv.id)"
              />
            </template>

            <template v-else>
              <span class="conv-title" :title="conv.title">💬 {{ conv.title }}</span>
              <button
                class="conv-edit"
                title="重命名"
                :disabled="streaming"
                @click.stop="startEdit(conv)"
              >
                <!-- 线条 SVG 铅笔，和麦克风 / 发送按钮一个风格（彩色 emoji 太跳） -->
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
                </svg>
              </button>
              <button
                class="conv-del"
                title="删除这个对话"
                :disabled="streaming && conv.id === currentConvId"
                @click.stop="deleteConversation(conv.id)"
              >
                ×
              </button>
            </template>
          </div>
          <p v-if="conversations.length === 0" class="conv-empty">暂无历史对话</p>
        </div>
        <div class="sidebar-footer">
          <button
            class="profile-btn"
            :title="user ? '修改头像和姓名' : '点这里登录 / 注册'"
            @click="onAvatarClick"
          >
            <img v-if="user?.avatar" class="mini-avatar" :src="user.avatar" alt="头像" />
            <span v-else class="mini-avatar fallback">👤</span>
            <span class="username">{{ displayName }}</span>
          </button>
          <button v-if="user" class="logout-btn" @click="logout">退出</button>
          <button v-else class="logout-btn" @click="showAuth = true">登录</button>
        </div>
      </aside>

      <!-- 聊天区 -->
      <div class="chat-card">
        <header class="chat-header">
          <div class="logo">
            <img class="logo-img" src="/my-ai.png" alt="AI 助手" />
          </div>
          <div class="header-text">
            <h1>大肥鱼 AI 助手</h1>
            <p class="status">
              <span class="dot" :class="{ busy: streaming }"></span>
              {{ streaming ? '正在输入…' : '在线' }}
            </p>
          </div>
        </header>

        <div ref="containerRef" class="chat-body">
          <div v-if="messages.length === 0 && !streaming" class="empty">
            <div class="empty-logo">
              <img class="logo-img" src="/my-ai2.png" alt="AI 助手" />
            </div>
            <h2>有什么可以帮你的？</h2>
            <p>输入你的问题，或点击下方示例快速开始</p>
            <div class="chips">
              <button v-for="q in examples" :key="q" class="chip" @click="ask(q)">{{ q }}</button>
            </div>
          </div>

          <div v-for="(msg, index) in messages" :key="index" class="msg" :class="msg.role">
            <!-- AI 头像用 AI_AVATAR 常量；用户头像用自己上传的，没有就显示「我」 -->
            <div class="avatar" :class="msg.role">
              <img v-if="msg.role === 'assistant' && AI_AVATAR" class="avatar-img" :src="AI_AVATAR" alt="AI" />
              <img v-else-if="user?.avatar" class="avatar-img" :src="user.avatar" alt="我" />
              <template v-else>{{ msg.role === 'user' ? '我' : '✦' }}</template>
            </div>
            <div class="bubble">
              <div v-if="msg.thinking" class="thinking">
                <span class="thinking-label">💭 思考过程</span>
                {{ msg.thinking }}
              </div>
              <!-- AI 回答用 markstream 渲染 Markdown；用户消息保持纯文本 -->
              <MarkdownRender
                v-if="msg.role === 'assistant'"
                class="content"
                mode="chat"
                :content="msg.content"
                :final="true"
              />
              <div v-else class="content">{{ msg.content }}</div>
            </div>
          </div>

          <div v-if="streaming" class="msg assistant">
            <div class="avatar assistant">
              <img v-if="AI_AVATAR" class="avatar-img" :src="AI_AVATAR" alt="AI" />
              <template v-else>✦</template>
            </div>
            <div class="bubble">
              <div v-if="thinking" class="thinking">
                <span class="thinking-label">💭 思考过程</span>
                {{ thinking }}
              </div>
              <div v-if="!answer" class="dots"><span></span><span></span><span></span></div>
              <!-- 流式输出中：final=false，markstream 会平滑地增量渲染不完整的 Markdown -->
              <MarkdownRender v-else class="content" mode="chat" :content="answer" :final="false" />
            </div>
          </div>
        </div>

        <!-- 输入区：结构照 deepai 那版 —— 一个圆角容器里装「输入框 + 右侧按钮组」，
             点麦克风后**输入框本身不变色**，只有麦克风按钮变蓝 + 光环 + 声波条。 -->
        <div class="input-bar">
          <div class="composer">
            <input
              v-model="input"
              type="text"
              class="chat-input"
              placeholder="输入消息，或点右侧麦克风语音输入…"
              @keypress.enter="sendMessage"
            />

            <div class="composer-btns">
              <!-- 麦克风：点一下开始说话，再点一下结束 -->
              <button
                class="mic-btn"
                :class="{ recording: listening }"
                :title="micTitle"
                :disabled="streaming"
                @click="toggleVoice"
              >
                <!-- 聆听时的双层扩散光环 -->
                <span v-if="listening" class="ring"></span>
                <span v-if="listening" class="ring r2"></span>

                <!-- 平时是麦克风图标 -->
                <svg
                  v-if="!listening"
                  class="mic-icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <rect x="9" y="2" width="6" height="12" rx="3" />
                  <path d="M5 10a7 7 0 0 0 14 0" />
                  <line x1="12" y1="19" x2="12" y2="22" />
                </svg>

                <!-- 聆听时换成跟着真实音量跳动的声波条 -->
                <span v-if="listening" class="mic-bars">
                  <span
                    v-for="(level, i) in barLevels"
                    :key="i"
                    :style="{ transform: `scaleY(${level.toFixed(2)})` }"
                  ></span>
                </span>
              </button>

              <!-- 发送键：AI 正在生成时变成「停止」键 -->
              <button
                class="send-btn"
                :class="{ stop: streaming }"
                :title="streaming ? '停止生成' : '发送（Enter）'"
                :disabled="!streaming && !input.trim()"
                @click="streaming ? stopGenerating() : sendMessage()"
              >
                <!-- 生成中：方块（停止）；平时：纸飞机 -->
                <svg
                  v-if="streaming"
                  viewBox="0 0 24 24"
                  width="15"
                  height="15"
                  fill="currentColor"
                >
                  <rect x="6" y="6" width="12" height="12" rx="2.5" />
                </svg>
                <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                  <path d="M3.4 20.4 21.85 12 3.4 3.6l-.01 6.53L14 12 3.39 13.87l.01 6.53z" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        <!-- 语音状态提示 -->
        <p v-if="voiceStatus" class="voice-status" :class="voiceStatusMode">{{ voiceStatus }}</p>
      </div>
    </div>

    <!-- ===== 登录 / 注册弹窗（游客点左下角头像/登录按钮打开）===== -->
    <div v-if="showAuth" class="modal-mask" @click.self="showAuth = false">
      <div class="auth-card">
        <div class="auth-logo">
          <img class="logo-img" src="/my-ai.png" alt="AI 助手" />
        </div>
        <h1 class="auth-title">登录 / 注册</h1>
        <div class="auth-tabs">
          <button :class="{ active: authMode === 'login' }" @click="switchMode('login')">登录</button>
          <button :class="{ active: authMode === 'register' }" @click="switchMode('register')">
            注册
          </button>
        </div>
        <input
          v-model="authForm.username"
          class="auth-input"
          placeholder="用户名"
          @keypress.enter="submitAuth"
        />
        <input
          v-model="authForm.password"
          class="auth-input"
          type="password"
          placeholder="密码"
          @keypress.enter="submitAuth"
        />
        <p v-if="authError" class="auth-error">{{ authError }}</p>
        <button class="auth-submit" :disabled="authLoading" @click="submitAuth">
          {{ authLoading ? '请稍候…' : authMode === 'login' ? '登 录' : '注册并登录' }}
        </button>
        <p class="auth-hint">
          不登录也能聊天，但记录只存在当前浏览器里（关掉浏览器就没了）；登录后记录会存到你的账号，换设备也能看到。
        </p>
      </div>
    </div>

    <!-- ===== 个人资料弹窗：改头像 / 改姓名 ===== -->
    <div v-if="user && profileOpen" class="modal-mask" @click.self="profileOpen = false">
      <div class="modal">
        <h3 class="modal-title">个人资料</h3>

        <div class="modal-avatar">
          <img v-if="user.avatar" class="big-avatar" :src="user.avatar" alt="头像" />
          <span v-else class="big-avatar fallback">👤</span>
          <label class="upload-btn">
            {{ avatarUploading ? '上传中…' : '更换头像' }}
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              hidden
              :disabled="avatarUploading"
              @change="onAvatarPicked"
            />
          </label>
        </div>

        <label class="field">
          <span class="field-label">姓名</span>
          <input
            v-model="profileForm.display_name"
            class="field-input"
            maxlength="20"
            placeholder="显示的名字"
            @keypress.enter="saveProfile"
          />
        </label>
        <p class="field-hint">登录用户名 {{ user.username }} 不可修改；姓名留空则显示用户名。</p>

        <p v-if="profileError" class="auth-error">{{ profileError }}</p>

        <div class="modal-actions">
          <button class="logout-btn" @click="profileOpen = false">取消</button>
          <button class="save-btn" :disabled="profileSaving" @click="saveProfile">
            {{ profileSaving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted, onBeforeUnmount } from 'vue'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { ElMessage } from 'element-plus'
import MarkdownRender from 'markstream-vue'
import 'markstream-vue/index.css'

import { MicMeter } from '@/utils/micMeter'
import { getSpeechRecognition } from '@/utils/speech'
import type { SpeechRecognitionCtor, SpeechRecognitionLike } from '@/utils/speech'

interface Message {
  role: 'user' | 'assistant'
  content: string
  thinking?: string
}

interface Conversation {
  // 登录用户是数据库自增 id（number），游客是本地生成的 id（string）
  id: number | string
  title: string
}

interface StoredMessage {
  role: 'user' | 'assistant'
  content: string
  thinking?: string
}

// 游客的会话：只存在浏览器里，不进数据库
interface GuestConversation {
  id: string
  title: string
  messages: StoredMessage[]
}

interface UserInfo {
  user_id: number
  username: string
  display_name?: string | null
  avatar?: string | null
}

// ===== 登录态 =====
// user 为 null 就是「游客」：页面照样能聊天，只是记录不进数据库
const user = ref<UserInfo | null>(null)
const showAuth = ref(false) // 登录/注册弹窗（游客点左下角头像打开）
const authMode = ref<'login' | 'register'>('login')
const authForm = ref({ username: '', password: '' })
const authError = ref('')
const authLoading = ref(false)

// ===== 游客会话：存在浏览器里 =====
// 用 sessionStorage：刷新页面还在，关掉浏览器就没了（对应「重启就没了」）。
// 想让它跨重启也保留，把下面两处 sessionStorage 换成 localStorage 即可。
const GUEST_STORE_KEY = 'guest_conversations'

function loadGuestStore(): GuestConversation[] {
  try {
    const raw = sessionStorage.getItem(GUEST_STORE_KEY)
    return raw ? (JSON.parse(raw) as GuestConversation[]) : []
  } catch {
    return []
  }
}

const guestConversations = ref<GuestConversation[]>(loadGuestStore())

function saveGuestStore() {
  try {
    sessionStorage.setItem(GUEST_STORE_KEY, JSON.stringify(guestConversations.value))
  } catch {
    /* 隐私模式等存不下就算了，不影响聊天 */
  }
}

// ===== AI 头像 =====
// 想换 AI 头像：① 直接替换 public/ai-avatar.svg 这个文件（最省事，什么都不用改）
//                  ② 或者把别的图片放进 public/，再把下面这行的路径改成 '/你的图片名.png'
//                  ③ 想退回以前那个文字「✦」，把这里改成空字符串 '' 即可
const AI_AVATAR = '/my-ai3.png'

// ===== 个人资料（头像 / 姓名）=====
const profileOpen = ref(false)
const profileForm = ref({ display_name: '' })
const profileError = ref('')
const profileSaving = ref(false)
const avatarUploading = ref(false)

// 界面显示的姓名：优先用 display_name，没设置就回退到登录用户名；游客显示「游客」
const displayName = computed(() => user.value?.display_name || user.value?.username || '游客')

// 点左下角头像：已登录 → 打开个人资料；游客 → 打开登录/注册弹窗
function onAvatarClick() {
  if (user.value) openProfile()
  else showAuth.value = true
}

function openProfile() {
  if (!user.value) return
  profileForm.value.display_name = user.value.display_name || user.value.username
  profileError.value = ''
  profileOpen.value = true
}

// 后端没启动时响应体是空的，直接 await res.json() 会抛出
// "Unexpected end of JSON input" 这种看不懂的错，这里统一换成能看懂的话
async function readJson(res: Response) {
  const text = await res.text()
  if (!text) {
    throw new Error(res.ok ? '服务器返回了空响应' : `请求失败（HTTP ${res.status}），后端可能没启动`)
  }
  try {
    return JSON.parse(text)
  } catch {
    throw new Error(`服务器返回的不是 JSON：${text.slice(0, 80)}`)
  }
}

async function saveProfile() {
  if (!user.value) return
  profileError.value = ''
  profileSaving.value = true
  try {
    const res = await fetch('/api/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: profileForm.value.display_name }),
    })
    const data = await readJson(res)
    if (!res.ok) throw new Error(data.detail || '保存失败')
    user.value = data as UserInfo
    profileOpen.value = false
  } catch (e) {
    profileError.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    profileSaving.value = false
  }
}

async function onAvatarPicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || !user.value) return
  profileError.value = ''
  avatarUploading.value = true
  try {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch('/api/profile/avatar', { method: 'POST', body: form })
    const data = await readJson(res)
    if (!res.ok) throw new Error(data.detail || '上传失败')
    user.value = data as UserInfo
  } catch (e) {
    profileError.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    avatarUploading.value = false
    input.value = '' // 清空后才能连续选同一个文件
  }
}

// ===== 会话与消息 =====
const conversations = ref<Conversation[]>([])
// 登录用户是数据库 id（number），游客是本地生成的 id（string）
const currentConvId = ref<number | string | null>(null)
const messages = ref<Message[]>([])

const input = ref('')
const streaming = ref(false)
const phase = ref<'thinking' | 'answering'>('thinking')
const thinking = ref('')
const answer = ref('')

// 停止生成：生成过程中点发送键（已变成停止键）就中断这一轮请求
let abortController: AbortController | null = null
const stopped = ref(false) // 区分「正常结束」和「用户点了停止」

const containerRef = ref<HTMLElement>()
const examples = ['用一句话解释什么是人工智能', '给我讲个冷笑话', '帮我写一首关于秋天的小诗']

// ===== 语音输入（Web Speech API，做法和 deepai 那版一样）=====
// ⚠️ 这个 API **不是本地识别**：浏览器会把音频传给云端（Chrome 用 Google、
//    Edge 用微软）识别，所以必须能连上那些服务器，否则会触发 onerror 的
//    "network" 错误（下面有对应的中文提示）。
const SpeechRecognitionImpl = getSpeechRecognition()
const micSupported = Boolean(SpeechRecognitionImpl)

const meter = new MicMeter()
const listening = ref(false)
const voiceStarting = ref(false)
const voiceStatus = ref('')
const voiceStatusMode = ref<'' | 'active' | 'error'>('')
// 声波条高度（0.22 ~ 1），静音时也保留一点高度
const barLevels = ref<number[]>([0.22, 0.22, 0.22, 0.22, 0.22])

let recognition: SpeechRecognitionLike | null = null
let barTimer: number | null = null
let cooldown = false // 刚停过不能立刻重启，否则 Chrome 会报「already started」
let baseText = '' // 开始说话前输入框里已有的文字
let finalText = '' // 已经确定下来的识别结果
let interimText = '' // 还在识别中的临时结果

function setVoiceStatus(text: string, mode: '' | 'active' | 'error' = '') {
  voiceStatus.value = text
  voiceStatusMode.value = mode
}

/** 把「原有文字 + 已确定 + 临时的」拼进输入框，边说边显示 */
function renderTranscript() {
  const live = `${finalText}${interimText}`
  input.value = baseText && live ? `${baseText} ${live}` : `${baseText}${live}`
}

// 用 requestAnimationFrame 不断读麦克风音量，驱动那 5 根声波条
function startBars() {
  stopBars()
  const tick = () => {
    if (!listening.value) return
    barLevels.value = meter.getLevels(5)
    barTimer = requestAnimationFrame(tick)
  }
  barTimer = requestAnimationFrame(tick)
}

function stopBars() {
  if (barTimer !== null) cancelAnimationFrame(barTimer)
  barTimer = null
  barLevels.value = [0.22, 0.22, 0.22, 0.22, 0.22]
}

function startCooldown(ms = 800) {
  cooldown = true
  window.setTimeout(() => {
    cooldown = false
  }, ms)
}

function resetVoiceUI() {
  listening.value = false
  voiceStarting.value = false
  stopBars()
  void meter.stop()
  recognition = null
}

const micTitle = computed(() => {
  if (!micSupported) return '当前浏览器不支持语音输入，请用 Chrome 或 Edge'
  if (listening.value) return '点一下结束语音输入'
  if (voiceStarting.value) return '正在启动麦克风…'
  return '点一下开始说话（由浏览器识别，需要联网）'
})

const VOICE_ERRORS: Record<string, string> = {
  'not-allowed': '麦克风权限被拒绝。点地址栏的麦克风图标允许后再试。',
  'service-not-allowed': '浏览器禁止了语音识别服务，请检查浏览器设置。',
  'no-speech': '没听到声音，再说一次试试。',
  'audio-capture': '没检测到麦克风设备，请检查麦克风。',
  network:
    '语音识别需要联网（音频要发给 Google / 微软的服务器），当前网络连不上。可以试试 Edge 浏览器，或者直接用文字输入。',
}

function createRecognition(): SpeechRecognitionLike {
  const Impl = SpeechRecognitionImpl as SpeechRecognitionCtor
  const r = new Impl()
  r.lang = 'zh-CN'
  r.continuous = true
  r.interimResults = true
  r.maxAlternatives = 1

  r.onstart = () => {
    voiceStarting.value = false
    listening.value = true
    startBars()
    setVoiceStatus('正在聆听，请说话…（说完再点一下麦克风）', 'active')
  }

  r.onresult = (event) => {
    interimText = ''
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const item = event.results[i]
      if (!item) continue
      const text = item[0]?.transcript ?? ''
      if (item.isFinal) finalText += text
      else interimText += text
    }
    renderTranscript()
  }

  r.onerror = (event) => {
    // aborted 是用户主动取消，不用报错
    if (event.error !== 'aborted') {
      setVoiceStatus(VOICE_ERRORS[event.error] ?? `语音识别出错：${event.error}`, 'error')
    }
    resetVoiceUI()
    startCooldown()
  }

  r.onend = () => {
    const done = finalText.trim()
    const hadError = voiceStatusMode.value === 'error'
    resetVoiceUI()
    startCooldown()
    if (done) {
      setVoiceStatus('语音输入完成，确认后按回车发送', '')
    } else if (!hadError) {
      setVoiceStatus('没有识别到内容，再试一次', 'error')
    }
    finalText = ''
    interimText = ''
    baseText = ''
  }

  return r
}

async function startVoice() {
  if (!micSupported) {
    setVoiceStatus('当前浏览器不支持语音输入，请用 Chrome 或 Edge 打开', 'error')
    return
  }
  if (listening.value || voiceStarting.value || cooldown) return

  voiceStarting.value = true
  baseText = input.value.trim()
  finalText = ''
  interimText = ''
  setVoiceStatus('正在启动麦克风…', 'active')

  try {
    recognition = createRecognition()
    recognition.start()
  } catch (e) {
    resetVoiceUI()
    startCooldown()
    setVoiceStatus(`启动语音识别失败：${e instanceof Error ? e.message : '未知错误'}`, 'error')
  }
}

function stopVoice() {
  if (!recognition) return
  setVoiceStatus('正在结束…', '')
  try {
    recognition.stop()
  } catch {
    /* 已经停了就忽略 */
  }
}

function toggleVoice() {
  if (streaming.value) return
  if (listening.value || voiceStarting.value) stopVoice()
  else void startVoice()
}

// 离开页面时别让麦克风一直开着
onBeforeUnmount(() => {
  stopBars()
  void meter.stop()
  try {
    recognition?.abort()
  } catch {
    /* 忽略 */
  }
  recognition = null
})

// 页面打开时给一行默认提示
onMounted(() => {
  setVoiceStatus(
    micSupported
      ? '点麦克风开始说话（识别由浏览器完成，需要联网）'
      : '当前浏览器不支持语音输入，请用 Chrome 或 Edge 打开',
    micSupported ? '' : 'error',
  )
})

// ===== 页面打开时：看看有没有登录；没登录就是游客，照样直接进聊天界面 =====
onMounted(async () => {
  try {
    const res = await fetch('/api/me')
    if (res.ok) user.value = await res.json()
  } catch {
    /* 后端没启动也不拦着，先按游客进去 */
  }
  await loadConversations()
})

// ===== 登录 / 注册 =====
function switchMode(mode: 'login' | 'register') {
  authMode.value = mode
  authError.value = ''
}

async function submitAuth() {
  authError.value = ''
  const username = authForm.value.username.trim()
  const password = authForm.value.password
  if (!username || !password) {
    authError.value = '请输入用户名和密码'
    return
  }
  authLoading.value = true
  try {
    const res = await fetch(`/api/${authMode.value}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '操作失败')
    // 整个对象都存下来，display_name / avatar 才不会丢
    user.value = data as UserInfo
    authForm.value = { username: '', password: '' }
    showAuth.value = false
    // 换成账号自己的历史（数据库里那份）；游客那份还留在浏览器里，退出后能再看到
    currentConvId.value = null
    messages.value = []
    await loadConversations()
  } catch (e) {
    authError.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    authLoading.value = false
  }
}

async function logout() {
  await fetch('/api/logout', { method: 'POST' })
  user.value = null
  currentConvId.value = null
  messages.value = []
  // 回到游客模式：侧边栏换回浏览器里那份记录
  await loadConversations()
}

// ===== 会话管理（登录用户走数据库，游客走浏览器本地）=====
async function loadConversations() {
  if (user.value) {
    const res = await fetch('/api/conversations')
    if (res.ok) conversations.value = await res.json()
  } else {
    // 游客：直接用浏览器里存的那份
    conversations.value = guestConversations.value.map((c) => ({ id: c.id, title: c.title }))
  }
}

function newConversation() {
  if (streaming.value) return
  if (!user.value) {
    createGuestConversation()
    return
  }
  currentConvId.value = null
  messages.value = []
}

// 游客：新建一个本地会话（第一条消息发出去时才会有内容）
function createGuestConversation() {
  const conv: GuestConversation = {
    id: `local-${Date.now()}`,
    title: '新对话',
    messages: [],
  }
  guestConversations.value.unshift(conv) // 最新地排最前面
  saveGuestStore()
  currentConvId.value = conv.id
  messages.value = []
  conversations.value = guestConversations.value.map((c) => ({ id: c.id, title: c.title }))
}

// 游客：把界面上的消息写回浏览器存储；标题取第一条用户消息的前 20 个字
function persistGuest() {
  if (user.value) return
  const id = currentConvId.value
  if (typeof id !== 'string') return
  const conv = guestConversations.value.find((c) => c.id === id)
  if (!conv) return
  conv.messages = messages.value.map((m) => ({
    role: m.role,
    content: m.content,
    thinking: m.thinking,
  }))
  const firstUser = messages.value.find((m) => m.role === 'user')
  if (firstUser) conv.title = firstUser.content.slice(0, 20)
  saveGuestStore()
  conversations.value = guestConversations.value.map((c) => ({ id: c.id, title: c.title }))
}

async function selectConversation(id: number | string) {
  if (streaming.value || id === currentConvId.value) return

  if (typeof id === 'string') {
    // 游客：从浏览器本地读
    const conv = guestConversations.value.find((c) => c.id === id)
    if (!conv) return
    messages.value = conv.messages.map((m) => ({
      role: m.role,
      content: m.content,
      thinking: m.thinking,
    }))
    currentConvId.value = id
    return
  }

  const res = await fetch(`/api/conversations/${id}/messages`)
  if (!res.ok) return
  const msgs = await res.json()
  messages.value = msgs.map((m: { role: 'user' | 'assistant'; content: string }) => ({
    role: m.role,
    content: m.content,
  }))
  currentConvId.value = id
}

async function deleteConversation(id: number | string) {
  if (streaming.value) return
  // 删除是破坏性操作，先确认一下，避免手滑点掉整段历史
  if (!window.confirm('删除这个对话？它的聊天记录也会一起删掉。')) return

  if (typeof id === 'string') {
    // 游客：只删浏览器里那份
    guestConversations.value = guestConversations.value.filter((c) => c.id !== id)
    saveGuestStore()
    conversations.value = guestConversations.value.map((c) => ({ id: c.id, title: c.title }))
  } else {
    const res = await fetch(`/api/conversations/${id}`, { method: 'DELETE' })
    if (!res.ok) return
    conversations.value = conversations.value.filter((c) => c.id !== id)
  }

  // 如果删的是当前正在看的会话，就回到「新建对话」的空状态
  if (currentConvId.value === id) {
    currentConvId.value = null
    messages.value = []
  }
}

// ===== 重命名会话标题 =====

const editingId = ref<number | string | null>(null) // 正在改名的是哪一条
const editingTitle = ref('')
let editInputEl: HTMLInputElement | null = null

/** 输入框的 ref：v-for 里同时只有一个会被渲染，所以直接接住当前这个就行 */
function bindEditInput(el: unknown) {
  editInputEl = (el as HTMLInputElement | null) ?? null
}

function startEdit(conv: { id: number | string; title: string }) {
  if (streaming.value) return
  editingId.value = conv.id
  editingTitle.value = conv.title
  // 等输入框渲染出来再聚焦、全选（全选后可以直接打字覆盖）
  nextTick(() => {
    editInputEl?.focus()
    editInputEl?.select()
  })
}

function cancelEdit() {
  editingId.value = null
  editingTitle.value = ''
}

async function saveTitle(id: number | string) {
  // 回车和失焦都会触发，这里挡掉第二次
  if (editingId.value !== id) return

  const conv = conversations.value.find((c) => c.id === id)
  const title = editingTitle.value.trim()

  // 没改、或者清空了，就当成取消（不允许改成空标题）
  if (!conv || !title || title === conv.title) {
    cancelEdit()
    return
  }

  const oldTitle = conv.title
  cancelEdit()

  try {
    if (typeof id === 'string') {
      // 游客：改浏览器本地那份
      const guest = guestConversations.value.find((c) => c.id === id)
      if (guest) guest.title = title
      saveGuestStore()
      conversations.value = guestConversations.value.map((c) => ({ id: c.id, title: c.title }))
    } else {
      const res = await fetch(`/api/conversations/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      })
      const data = await readJson(res)
      if (!res.ok) throw new Error(data.detail || '重命名失败')
      conv.title = (data.title as string) ?? title
    }
  } catch (e) {
    conv.title = oldTitle // 失败就还原，别让界面显示一个没存上的名字
    ElMessage.error(e instanceof Error ? e.message : '重命名失败')
  }
}

// ===== 发送消息（流式）=====
function ask(question: string) {
  input.value = question
  sendMessage()
}

async function scrollToBottom() {
  await nextTick()
  const el = containerRef.value
  if (el) el.scrollTop = el.scrollHeight
}

watch([messages, thinking, answer], scrollToBottom, { deep: true })

async function sendMessage() {
  const inputMsg = input.value.trim()
  if (!inputMsg || streaming.value) return

  // 正在语音输入的话先把麦克风关掉，免得边说边发
  if (listening.value || voiceStarting.value) stopVoice()

  // 游客：还没有本地会话就先建一个
  if (!user.value && typeof currentConvId.value !== 'string') {
    createGuestConversation()
  }

  // 游客的历史上下文由前端传上去（后端不落库），先取「发这条之前」的消息
  const priorHistory = messages.value.map((m) => ({ role: m.role, content: m.content }))

  messages.value.push({ role: 'user', content: inputMsg })
  persistGuest()
  input.value = ''
  streaming.value = true
  phase.value = 'thinking'
  thinking.value = ''
  answer.value = ''

  const isGuest = !user.value
  // 生成过程中点「停止」就靠这个中断请求
  abortController = new AbortController()
  stopped.value = false

  try {
    await fetchEventSource(isGuest ? '/api/chat/guest' : '/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(
        isGuest
          ? { input: inputMsg, history: priorHistory }
          : { input: inputMsg, conversation_id: currentConvId.value },
      ),
      signal: abortController.signal, // ← 用户点停止时用它中断
      onmessage(event) {
        const data = event.data

        // 服务端下发的会话 id（只有登录用户会收到，自动新建会话时用）
        if (data.startsWith('[CONV]')) {
          currentConvId.value = Number(data.slice(6))
          loadConversations() // 刷新侧边栏标题
          return
        }
        // 工具调用进度（比如「正在查询北京的天气…」）
        // 直接追加到思考区，这样用户能看到 AI 正在干什么，而不是干等
        if (data.startsWith('[TOOL]')) {
          thinking.value += (thinking.value ? '\n' : '') + '🔧 ' + data.slice(6)
          return
        }
        if (data === '[DONE]') {
          messages.value.push({
            role: 'assistant',
            content: answer.value,
            thinking: thinking.value || undefined,
          })
          persistGuest() // 游客：把这一轮问答写回浏览器
          return
        }
        if (data === '[THINK]') {
          phase.value = 'thinking'
          return
        }
        if (data === '[ANSWER]') {
          phase.value = 'answering'
          return
        }

        if (phase.value === 'thinking') {
          thinking.value += data
        } else {
          answer.value += data
        }
      },
      onclose() {
        // 服务端正常关闭：抛异常阻止 fetchEventSource 自动重连（否则会重复发送）
        throw new Error('stream-closed')
      },
      onerror(err) {
        throw err // 出错也不重连
      },
    })
  } catch (e) {
    if (stopped.value) {
      // 用户自己点的停止，不算错误
    } else if (!(e instanceof Error && e.message === 'stream-closed')) {
      messages.value.push({
        role: 'assistant',
        content: '⚠️ 出错了，请检查后端服务或网络后重试。',
      })
      persistGuest()
    }
  } finally {
    // 被停止时 [DONE] 不会来，界面上的半截回答要留下来（后端也已经存了同样的内容）
    const partial = answer.value.trim()
    if (stopped.value && partial) {
      messages.value.push({
        role: 'assistant',
        content: partial,
        thinking: thinking.value || undefined,
      })
      persistGuest()
    }
    abortController = null
    streaming.value = false
    thinking.value = ''
    answer.value = ''
  }
}

/** 点「停止」：中断当前这一轮生成，已经生成的内容保留 */
function stopGenerating() {
  if (!abortController) return
  stopped.value = true
  abortController.abort()
}
</script>

<style scoped>
/* ===== 整体布局 =====
   注意：这里用 100%（而不是 100vh）——顶部导航栏占了高度，
   如果还用 100vh 会超出屏幕、把底部输入框挤到屏幕外。 */
.page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: linear-gradient(160deg, #eef2ff 0%, #f5f7fb 45%, #fdf2f8 100%);
}

/* ===== 登录 / 注册卡片 ===== */
.auth-card {
  width: 100%;
  max-width: 380px;
  padding: 40px 32px;
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 12px 40px rgba(80, 100, 200, 0.12);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.auth-logo {
  width: 56px;
  height: 56px;
  margin: 0 auto;
  border-radius: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  color: #fff;
  background: linear-gradient(135deg, #4d6bfe, #8b5cf6);
  box-shadow: 0 8px 24px rgba(77, 107, 254, 0.3);
  overflow: hidden; /* 让图片被圆角裁切 */
}

/* 登录弹窗底部的说明文字 */
.auth-hint {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.7;
  color: #a6acc0;
  text-align: center;
}

.auth-title {
  text-align: center;
  font-size: 18px;
  font-weight: 600;
  color: #1f2430;
  margin-bottom: 6px;
}

.auth-tabs {
  display: flex;
  background: #f4f6fb;
  border-radius: 999px;
  padding: 4px;
}

.auth-tabs button {
  flex: 1;
  padding: 8px 0;
  border: none;
  border-radius: 999px;
  font-size: 14px;
  color: #8a90a3;
  background: transparent;
  cursor: pointer;
  transition: all 0.2s;
}

.auth-tabs button.active {
  background: #fff;
  color: #4d6bfe;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(80, 100, 200, 0.15);
}

.auth-input {
  padding: 12px 16px;
  font-size: 14px;
  color: #2a3040;
  background: #f4f6fb;
  border: 1.5px solid transparent;
  border-radius: 12px;
  outline: none;
  transition: all 0.2s;
}

.auth-input:focus {
  background: #fff;
  border-color: #4d6bfe;
  box-shadow: 0 0 0 4px rgba(77, 107, 254, 0.12);
}

.auth-error {
  font-size: 13px;
  color: #ef4444;
  text-align: center;
}

.auth-submit {
  padding: 12px 0;
  border: none;
  border-radius: 12px;
  font-size: 15px;
  color: #fff;
  background: linear-gradient(135deg, #4d6bfe, #8b5cf6);
  box-shadow: 0 4px 12px rgba(77, 107, 254, 0.35);
  cursor: pointer;
  transition: all 0.2s;
}

.auth-submit:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(77, 107, 254, 0.45);
}

.auth-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ===== 主界面布局（侧边栏 + 聊天区）===== */
.app-shell {
  width: 100%;
  max-width: 1100px;
  height: 100%;
  max-height: 760px;
  display: flex;
  gap: 16px;
}

.sidebar {
  width: 230px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 12px 40px rgba(80, 100, 200, 0.12);
  padding: 14px;
  gap: 12px;
}

.new-chat-btn {
  padding: 10px 0;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  color: #fff;
  background: linear-gradient(135deg, #4d6bfe, #8b5cf6);
  box-shadow: 0 4px 12px rgba(77, 107, 254, 0.3);
  cursor: pointer;
  transition: all 0.2s;
}

.new-chat-btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.new-chat-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.conv-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.conv-list::-webkit-scrollbar {
  width: 4px;
}

.conv-list::-webkit-scrollbar-thumb {
  background: #d9deeb;
  border-radius: 2px;
}

.conv-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 10px 9px 12px;
  border-radius: 10px;
  font-size: 13px;
  color: #5a6076;
  cursor: pointer;
  transition: background 0.15s;
}

.conv-title {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-del {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  font-size: 16px;
  line-height: 1;
  color: #8a90a3;
  background: transparent;
  opacity: 0.45; /* 半透明的小 × */
  cursor: pointer;
  transition: all 0.15s;
}

/* 重命名按钮：和删除键同一套（平时半透明灰，悬停变蓝） */
.conv-edit {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  color: #8a90a3;
  background: transparent;
  opacity: 0.45;
  cursor: pointer;
  transition: all 0.15s;
}

.conv-edit svg {
  width: 13px;
  height: 13px;
  display: block;
}

.conv-item:hover .conv-edit {
  opacity: 0.9;
}

.conv-edit:hover:not(:disabled) {
  color: #4d6bfe;
  background: #eef2ff;
  opacity: 1;
}

.conv-edit:disabled {
  opacity: 0.2;
  cursor: not-allowed;
}

/* 重命名中的输入框 */
.conv-edit-input {
  flex: 1;
  min-width: 0;
  padding: 4px 8px;
  border: 1.5px solid #4d6bfe;
  border-radius: 8px;
  background: #fff;
  font-size: 13px;
  font-family: inherit;
  color: #2a3040;
  outline: none;
  box-shadow: 0 0 0 3px rgba(77, 107, 254, 0.12);
}

.conv-item.editing {
  background: #f7f9ff;
  cursor: default;
}

.conv-item:hover .conv-del {
  opacity: 0.9;
}

.conv-del:hover {
  color: #ef4444;
  background: #fdecec;
  opacity: 1;
}

.conv-del:disabled {
  opacity: 0.2;
  cursor: not-allowed;
}

.conv-item:hover {
  background: #f4f6fb;
}

.conv-item.active {
  background: #eef2ff;
  color: #4d6bfe;
  font-weight: 600;
}

.conv-empty {
  padding: 12px;
  font-size: 12px;
  color: #a6acc0;
  text-align: center;
}

.sidebar-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 10px;
  border-top: 1px solid #eef0f6;
}

.username {
  font-size: 13px;
  color: #5a6076;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.logout-btn {
  flex-shrink: 0;
  padding: 5px 12px;
  border: 1px solid #e3e7f2;
  border-radius: 999px;
  font-size: 12px;
  color: #8a90a3;
  background: #fff;
  cursor: pointer;
  transition: all 0.2s;
}

.logout-btn:hover {
  color: #ef4444;
  border-color: #fecaca;
  background: #fef2f2;
}

/* ===== 聊天卡片 ===== */
.chat-card {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 12px 40px rgba(80, 100, 200, 0.12);
  overflow: hidden;
}

.chat-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid #eef0f6;
}

.logo {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: #fff;
  background: linear-gradient(135deg, #4d6bfe, #8b5cf6);
  box-shadow: 0 4px 12px rgba(77, 107, 254, 0.35);
  overflow: hidden; /* 让图片被圆角裁切 */
}

/* 头部 logo 图片：铺满 40x40 的圆角方块 */
.logo-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.header-text h1 {
  font-size: 16px;
  font-weight: 600;
  color: #1f2430;
}

.status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #8a90a3;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
}

.dot.busy {
  background: #f59e0b;
  animation: pulse 1s ease-in-out infinite;
}

@keyframes pulse {
  50% { opacity: 0.3; }
}

/* ===== 消息区 ===== */
.chat-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.chat-body::-webkit-scrollbar {
  width: 6px;
}

.chat-body::-webkit-scrollbar-thumb {
  background: #d9deeb;
  border-radius: 3px;
}

.empty {
  margin: auto;
  text-align: center;
  color: #8a90a3;
}

.empty-logo {
  width: 164px;
  height: 164px;
  margin: 0 auto 16px;
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  color: #fff;
  background: linear-gradient(135deg, #4d6bfe, #8b5cf6);
  box-shadow: 0 8px 24px rgba(77, 107, 254, 0.3);
}

.empty h2 {
  font-size: 20px;
  font-weight: 600;
  color: #1f2430;
  margin-bottom: 6px;
}

.empty p {
  font-size: 13px;
  margin-bottom: 20px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}

.chip {
  padding: 8px 14px;
  font-size: 13px;
  color: #4d6bfe;
  background: #eef2ff;
  border: 1px solid #dbe3ff;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.2s;
}

.chip:hover {
  background: #4d6bfe;
  color: #fff;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(77, 107, 254, 0.3);
}

.msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  animation: fade-up 0.25s ease;
}

@keyframes fade-up {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

.msg.user {
  flex-direction: row-reverse;
}

.avatar {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #4d6bfe, #8b5cf6);
}

.avatar.user {
  background: linear-gradient(135deg, #64748b, #94a3b8);
}

.bubble {
  max-width: 72%;
  padding: 10px 14px;
  border-radius: 16px;
  background: #f4f6fb;
  color: #2a3040;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.msg.assistant .bubble {
  border-top-left-radius: 4px;
}

.msg.user .bubble {
  background: linear-gradient(135deg, #4d6bfe, #6a8bff);
  color: #fff;
  border-top-right-radius: 4px;
  box-shadow: 0 4px 14px rgba(77, 107, 254, 0.25);
}

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

.dots span:nth-child(2) { animation-delay: 0.15s; }
.dots span:nth-child(3) { animation-delay: 0.3s; }

@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
  30% { transform: translateY(-5px); opacity: 1; }
}

.cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: -0.15em;
  background: #4d6bfe;
  animation: blink 0.8s step-end infinite;
}

@keyframes blink {
  50% { opacity: 0; }
}

/* ===== 底部输入栏 =====
   结构照 deepai 那版：一个圆角容器里装「输入框 + 右侧按钮组」，
   focus 时整个容器一起发光，输入框自己不加边框。 */
.input-bar {
  padding: 12px 16px 14px;
  border-top: 1px solid #eef0f6;
}

.composer {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fff;
  border: 1.5px solid #e3e7f2;
  border-radius: 22px;
  padding: 5px 5px 5px 16px;
  transition: border-color 0.2s, box-shadow 0.25s;
}

.composer:focus-within {
  border-color: #b9c6f5;
  box-shadow: 0 0 0 4px rgba(77, 107, 254, 0.12);
}

.composer-btns {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ===== 语音输入 =====
   图标 / 扩散光环 / 声波条的样式照搬 deepai 那版，配色跟着本项目走。
   注意：点麦克风后**输入框不换色**（那边就是这样的）。 */
.mic-btn {
  position: relative;
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #dbe3ff;
  border-radius: 50%;
  color: #4d6bfe;
  background: #eef2ff;
  cursor: pointer;
  transition: all 0.2s;
}

.mic-btn:hover:not(:disabled) {
  background: #e0e8ff;
  transform: translateY(-1px);
}

.mic-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  transform: none;
}

.mic-icon {
  width: 21px;
  height: 21px;
  display: block;
}

/* 录音中：变实心渐变 + 发光 */
.mic-btn.recording {
  border-color: transparent;
  color: #fff;
  background: linear-gradient(135deg, #4d6bfe, #6a8bff);
  box-shadow: 0 6px 18px rgba(77, 107, 254, 0.4);
}

/* 双层扩散光环 */
.mic-btn .ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid rgba(77, 107, 254, 0.5);
  opacity: 0;
  pointer-events: none;
}

.mic-btn.recording .ring {
  animation: ring-pulse 1.8s ease-out infinite;
}

.mic-btn.recording .ring.r2 {
  animation-delay: 0.9s;
}

@keyframes ring-pulse {
  0% {
    transform: scale(1);
    opacity: 0.85;
  }
  100% {
    transform: scale(1.95);
    opacity: 0;
  }
}

/* 5 根跟着真实音量跳动的声波条 */
.mic-bars {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3.5px;
}

.mic-bars span {
  width: 4px;
  height: 24px;
  border-radius: 4px;
  background: #fff;
  transform-origin: center;
  transform: scaleY(0.25);
  transition: transform 0.09s ease-out;
  box-shadow: 0 0 6px rgba(255, 255, 255, 0.65);
}

/* 识别中的转圈 */
.mic-loading {
  width: 16px;
  height: 16px;
  border: 2px solid #d9deeb;
  border-top-color: #4d6bfe;
  border-radius: 50%;
  animation: mic-spin 0.7s linear infinite;
}

@keyframes mic-spin {
  to {
    transform: rotate(360deg);
  }
}

/* 输入框下面那行语音状态 */
.voice-status {
  margin: 0;
  padding: 8px 18px 2px;
  font-size: 12.5px;
  color: #a6acc0;
  text-align: center;
}

.voice-status.active {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  color: #4d6bfe;
  font-weight: 600;
}

/* 正在聆听时前面加一个呼吸的小圆点 */
.voice-status.active::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #4d6bfe;
  animation: dot-pulse 1.2s ease-out infinite;
}

@keyframes dot-pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(77, 107, 254, 0.45);
  }
  100% {
    box-shadow: 0 0 0 9px rgba(77, 107, 254, 0);
  }
}

.voice-status.error {
  color: #ef4444;
}

/* 输入框：在 composer 里面，所以自己不要边框和背景 */
.chat-input {
  flex: 1;
  min-width: 0;
  padding: 10px 2px;
  font-size: 14px;
  color: #2a3040;
  background: transparent;
  border: none;
  outline: none;
}

.chat-input::placeholder {
  color: #a6acc0;
}

.send-btn {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  color: #fff;
  background: linear-gradient(135deg, #4d6bfe, #8b5cf6);
  box-shadow: 0 4px 12px rgba(77, 107, 254, 0.35);
  cursor: pointer;
  transition: all 0.2s;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px) scale(1.05);
  box-shadow: 0 6px 16px rgba(77, 107, 254, 0.45);
}

.send-btn:disabled {
  opacity: 0.4;
  box-shadow: none;
  cursor: not-allowed;
}

/* 生成中：发送键变成深色的「停止」键（方块图标） */
.send-btn.stop {
  background: #2a3040;
  box-shadow: 0 4px 12px rgba(42, 48, 64, 0.3);
}

.send-btn.stop:hover:not(:disabled) {
  transform: translateY(-1px) scale(1.05);
  box-shadow: 0 6px 16px rgba(42, 48, 64, 0.4);
}

/* ===== 头像（用户上传的图片 / AI 头像图片）===== */
.avatar {
  overflow: hidden; /* 让方形图片被裁成圆形 */
}

.avatar-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 侧边栏底部：头像 + 姓名，点一下打开个人资料弹窗 */
.profile-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 4px 6px;
  border: none;
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  transition: background 0.15s;
}

.profile-btn:hover {
  background: #f4f6fb;
}

.mini-avatar {
  flex-shrink: 0;
  display: block;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  object-fit: cover;
}

.mini-avatar.fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  background: #eef2ff;
}

/* ===== 个人资料弹窗 ===== */
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(24, 30, 50, 0.45);
}

.modal {
  width: 320px;
  padding: 22px;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 24px 60px rgba(20, 30, 60, 0.25);
}

.modal-title {
  margin: 0 0 16px;
  font-size: 16px;
  color: #2a3040;
}

.modal-avatar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
}

.big-avatar {
  display: block;
  width: 72px;
  height: 72px;
  border-radius: 50%;
  object-fit: cover;
  box-shadow: 0 6px 18px rgba(77, 107, 254, 0.25);
}

.big-avatar.fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  background: #eef2ff;
}

.upload-btn {
  padding: 5px 14px;
  border: 1px solid #d9e0f5;
  border-radius: 999px;
  font-size: 12.5px;
  color: #4d6bfe;
  background: #f7f9ff;
  cursor: pointer;
  transition: background 0.2s;
}

.upload-btn:hover {
  background: #eef2ff;
}

.field {
  display: block;
}

.field-label {
  display: block;
  margin-bottom: 6px;
  font-size: 12.5px;
  color: #8a90a3;
}

.field-input {
  box-sizing: border-box;
  width: 100%;
  padding: 9px 12px;
  border: 1px solid #e3e7f2;
  border-radius: 10px;
  font-size: 14px;
  color: #2a3040;
  outline: none;
  transition: border-color 0.2s;
}

.field-input:focus {
  border-color: #4d6bfe;
}

.field-hint {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: #a6acc0;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}

.save-btn {
  padding: 6px 16px;
  border: none;
  border-radius: 999px;
  font-size: 13px;
  color: #fff;
  background: linear-gradient(135deg, #4d6bfe, #6a8bff);
  cursor: pointer;
  transition: opacity 0.2s;
}

.save-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
