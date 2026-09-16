<template>
  <div class="page">
    <!-- ===== 搜索区 ===== -->
    <div class="panel search-panel">
      <div class="search-row">
        <span class="search-icon">🔍</span>
        <input
          v-model="city"
          class="search-input"
          placeholder="输入城市名，例如 北京"
          @keypress.enter="search()"
        />
        <select v-model.number="days" class="days-select" @change="search()">
          <option :value="3">3 天</option>
          <option :value="5">5 天</option>
          <option :value="7">7 天</option>
        </select>
        <button class="btn" :disabled="loading" @click="search()">
          {{ loading ? '查询中…' : '查询' }}
        </button>
      </div>
      <div class="chips">
        <button
          v-for="c in quickCities"
          :key="c"
          class="chip"
          :class="{ active: c === city }"
          @click="search(c)"
        >
          {{ c }}
        </button>
      </div>
    </div>

    <div v-if="error" class="panel err">⚠️ {{ error }}</div>

    <template v-if="data">
      <!-- ===== 当前天气大卡 ===== -->
      <div class="panel current" :style="{ background: currentBg }">
        <div class="cur-main">
          <div class="cur-city">📍 {{ data.地点 }}</div>
          <div class="cur-temp">{{ data.当前.温度 }}</div>
          <div class="cur-desc">{{ data.当前.天气 }}</div>
          <div class="cur-time">观测时间 {{ (data.当前.观测时间 || '').replace('T', ' ') }}</div>
        </div>
        <div class="cur-icon">{{ iconOf(data.当前.天气) }}</div>
      </div>

      <!-- ===== 详情小卡 ===== -->
      <div class="stats">
        <div class="panel stat">
          <span class="stat-label">体感温度</span>
          <b class="stat-value">{{ data.当前.体感温度 }}</b>
        </div>
        <div class="panel stat">
          <span class="stat-label">相对湿度</span>
          <b class="stat-value">{{ data.当前.湿度 }}</b>
        </div>
        <div class="panel stat">
          <span class="stat-label">风速</span>
          <b class="stat-value">{{ data.当前.风速 }}</b>
        </div>
        <div class="panel stat">
          <span class="stat-label">今日降水概率</span>
          <b class="stat-value">{{ todayRain }}</b>
        </div>
      </div>

      <!-- ===== 未来预报 ===== -->
      <div class="panel">
        <h3 class="panel-title">未来 {{ data.预报.length }} 天</h3>
        <div class="forecast">
          <div
            v-for="(d, i) in data.预报"
            :key="d.日期"
            class="fc-card"
            :class="{ today: i === 0 }"
          >
            <span class="fc-day">{{ dayLabel(d.日期, i) }}</span>
            <span class="fc-date">{{ d.日期.slice(5).replace('-', '/') }}</span>
            <span class="fc-icon">{{ iconOf(d.天气) }}</span>
            <span class="fc-weather">{{ d.天气 }}</span>
            <span class="fc-temp"><b>{{ d.最高温 }}°</b> / {{ d.最低温 }}°</span>
            <span class="fc-rain">💧 {{ d.降水概率 }}</span>
          </div>
        </div>

        <!-- 温度趋势：纯 SVG 手画，不依赖图表库 -->
        <svg v-if="trend.highPath" class="trend" :viewBox="`0 0 ${trend.w} ${trend.h}`">
          <path :d="trend.lowPath" class="trend-low" />
          <path :d="trend.highPath" class="trend-high" />
          <g v-for="(p, i) in trend.dots" :key="i">
            <circle :cx="p.x" :cy="p.y" r="3.5" class="trend-dot" />
            <text :x="p.x" :y="p.y - 9" class="trend-text">{{ p.label }}</text>
          </g>
        </svg>
      </div>

      <p class="source">数据来源：{{ data.数据来源 }}（免费、无需 API Key）</p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

interface CurrentWeather {
  天气: string
  温度: string
  体感温度: string
  湿度: string
  风速: string
  观测时间?: string
}

interface ForecastDay {
  日期: string
  天气: string
  最高温: number
  最低温: number
  降水概率: string
}

interface WeatherData {
  地点: string
  当前: CurrentWeather
  预报: ForecastDay[]
  数据来源: string
}

const quickCities = ['北京', '上海', '广州', '深圳', '成都', '杭州', '西安', '武汉']

const city = ref('北京')
const days = ref(3)
const data = ref<WeatherData | null>(null)
const loading = ref(false)
const error = ref('')

// 天气文字 → emoji（后端返回的就是这些中文词）
const ICON_BY_WEATHER: Record<string, string> = {
  晴: '☀️',
  晴间多云: '🌤️',
  多云: '⛅',
  阴: '☁️',
  有雾: '🌫️',
  冻雾: '🌫️',
  小毛毛雨: '🌦️',
  毛毛雨: '🌦️',
  大毛毛雨: '🌦️',
  冻毛毛雨: '🌧️',
  强冻毛毛雨: '🌧️',
  小雨: '🌧️',
  中雨: '🌧️',
  大雨: '🌧️',
  冻雨: '🌧️',
  强冻雨: '🌧️',
  小雪: '🌨️',
  中雪: '🌨️',
  大雪: '❄️',
  雪粒: '🌨️',
  阵雨: '🌦️',
  强阵雨: '🌧️',
  暴雨: '⛈️',
  小阵雪: '🌨️',
  大阵雪: '❄️',
  雷阵雨: '⛈️',
  雷阵雨伴小冰雹: '⛈️',
  雷阵雨伴大冰雹: '⛈️',
}

function iconOf(weather: string): string {
  return ICON_BY_WEATHER[weather] || '🌡️'
}

// 卡片背景随天气变化，看起来「直观」一些
const currentBg = computed(() => {
  const w = data.value?.当前.天气 || ''
  if (w.includes('雷')) return 'linear-gradient(135deg, #4a4a6a, #2b2b45)'
  if (w.includes('雪') || w.includes('冰')) return 'linear-gradient(135deg, #7fb2e5, #4a7fc1)'
  if (w.includes('雨') || w.includes('毛毛')) return 'linear-gradient(135deg, #5b7cba, #3b5687)'
  if (w.includes('雾')) return 'linear-gradient(135deg, #9aa4b8, #6b7488)'
  if (w.includes('阴')) return 'linear-gradient(135deg, #8e9bb3, #66718c)'
  if (w.includes('云')) return 'linear-gradient(135deg, #6fa8dc, #4d7fb8)'
  if (w.includes('晴')) return 'linear-gradient(135deg, #f7b955, #ee8c4a)'
  return 'linear-gradient(135deg, #4d6bfe, #8b5cf6)'
})

const todayRain = computed(() => data.value?.预报[0]?.降水概率 || '—')

const WEEK = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

function dayLabel(date: string, index: number): string {
  if (index === 0) return '今天'
  if (index === 1) return '明天'
  const d = new Date(`${date}T00:00:00`)
  return Number.isNaN(d.getTime()) ? date : WEEK[d.getDay()]!
}

const EMPTY_TREND = {
  w: 320,
  h: 96,
  highPath: '',
  lowPath: '',
  dots: [] as { x: number; y: number; label: string }[],
}

// 把每天的温差画成两条折线
const trend = computed(() => {
  const list = data.value?.预报 ?? []
  if (list.length < 2) return EMPTY_TREND

  const highs = list.map((d) => Number(d.最高温))
  const lows = list.map((d) => Number(d.最低温))
  const all = [...highs, ...lows]
  const min = Math.min(...all) - 2
  const max = Math.max(...all) + 2

  const w = 320
  const h = 96
  const padX = 22
  const padY = 22
  const x = (i: number) => padX + (i * (w - padX * 2)) / (list.length - 1)
  const y = (t: number) => h - padY - ((t - min) / (max - min || 1)) * (h - padY * 2)
  const path = (arr: number[]) =>
    arr.map((t, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(t).toFixed(1)}`).join(' ')

  return {
    w,
    h,
    highPath: path(highs),
    lowPath: path(lows),
    dots: highs.map((t, i) => ({ x: x(i), y: y(t), label: `${t}°` })),
  }
})

async function search(target?: string) {
  if (target) city.value = target
  const name = city.value.trim()
  if (!name) return

  loading.value = true
  error.value = ''
  try {
    const res = await fetch(`/api/weather?city=${encodeURIComponent(name)}&days=${days.value}`)
    // 后端没启动时响应体是空的，直接 res.json() 会抛出看不懂的错，这里统一处理
    const text = await res.text()
    if (!text) throw new Error(`请求失败（HTTP ${res.status}），后端可能没启动`)
    const json = JSON.parse(text)
    if (!res.ok) throw new Error(json.detail || '查询失败')
    data.value = json as WeatherData
  } catch (e) {
    error.value = e instanceof Error ? e.message : '网络错误'
    data.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => search())
</script>

<style scoped>
.page {
  min-height: 100%;
  box-sizing: border-box;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  background: linear-gradient(160deg, #eef2ff 0%, #f5f7fb 45%, #fdf2f8 100%);
}

.panel {
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 8px 28px rgba(80, 100, 200, 0.1);
}

.panel-title {
  margin: 0 0 14px;
  font-size: 15px;
  font-weight: 600;
  color: #1f2430;
}

/* ---------- 搜索区 ---------- */
.search-panel {
  padding: 16px;
}

.search-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.search-icon {
  font-size: 15px;
}

.search-input {
  flex: 1;
  min-width: 0;
  padding: 11px 14px;
  border: 1.5px solid transparent;
  border-radius: 12px;
  background: #f4f6fb;
  font-size: 14px;
  color: #2a3040;
  outline: none;
  transition: all 0.2s;
}

.search-input:focus {
  background: #fff;
  border-color: #4d6bfe;
  box-shadow: 0 0 0 4px rgba(77, 107, 254, 0.12);
}

.days-select {
  padding: 11px 10px;
  border: 1.5px solid #e3e7f2;
  border-radius: 12px;
  background: #fff;
  font-size: 13px;
  color: #5a6076;
  outline: none;
  cursor: pointer;
}

.btn {
  flex-shrink: 0;
  padding: 11px 22px;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  color: #fff;
  background: linear-gradient(135deg, #4d6bfe, #8b5cf6);
  box-shadow: 0 4px 12px rgba(77, 107, 254, 0.3);
  cursor: pointer;
  transition: all 0.2s;
}

.btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.chip {
  padding: 5px 13px;
  border: 1px solid #e3e7f2;
  border-radius: 999px;
  background: #fff;
  font-size: 12.5px;
  color: #5a6076;
  cursor: pointer;
  transition: all 0.18s;
}

.chip:hover {
  border-color: #b9c6f5;
  color: #4d6bfe;
}

.chip.active {
  border-color: #4d6bfe;
  background: #eef2ff;
  color: #4d6bfe;
  font-weight: 600;
}

/* ---------- 当前天气大卡 ---------- */
.current {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 26px 28px;
  color: #fff;
  transition: background 0.4s;
}

.cur-city {
  font-size: 15px;
  opacity: 0.92;
}

.cur-temp {
  font-size: 52px;
  font-weight: 700;
  line-height: 1.1;
  margin: 6px 0 2px;
  text-shadow: 0 3px 12px rgba(0, 0, 0, 0.15);
}

.cur-desc {
  font-size: 17px;
  font-weight: 600;
}

.cur-time {
  margin-top: 6px;
  font-size: 11.5px;
  opacity: 0.75;
}

.cur-icon {
  font-size: 76px;
  line-height: 1;
  filter: drop-shadow(0 6px 14px rgba(0, 0, 0, 0.18));
  animation: float 3s ease-in-out infinite;
}

@keyframes float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-8px);
  }
}

/* ---------- 详情小卡 ---------- */
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 12px;
}

.stat {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.stat-label {
  font-size: 12px;
  color: #9aa1b5;
}

.stat-value {
  font-size: 19px;
  color: #1f2430;
}

/* ---------- 预报 ---------- */
.panel > .panel-title {
  padding: 18px 18px 0;
}

.forecast {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(96px, 1fr));
  gap: 10px;
  padding: 0 18px;
}

.fc-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 12px 8px;
  border: 1px solid #eef0f6;
  border-radius: 14px;
  background: #fafbff;
}

.fc-card.today {
  border-color: #b9c6f5;
  background: #eef2ff;
}

.fc-day {
  font-size: 13px;
  font-weight: 600;
  color: #2a3040;
}

.fc-date {
  font-size: 11px;
  color: #9aa1b5;
}

.fc-icon {
  font-size: 30px;
  line-height: 1.3;
}

.fc-weather {
  font-size: 12px;
  color: #5a6076;
}

.fc-temp {
  font-size: 12.5px;
  color: #8a90a3;
}

.fc-temp b {
  color: #e8663d;
  font-size: 14px;
}

.fc-rain {
  font-size: 11.5px;
  color: #4d9bfe;
}

/* ---------- 温度曲线 ---------- */
.trend {
  width: calc(100% - 36px);
  height: 96px;
  margin: 16px 18px 18px;
}

.trend-high {
  fill: none;
  stroke: #ff7a59;
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.trend-low {
  fill: none;
  stroke: #4d9bfe;
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.trend-dot {
  fill: #fff;
  stroke: #ff7a59;
  stroke-width: 2;
}

.trend-text {
  font-size: 10px;
  fill: #ff7a59;
  text-anchor: middle;
}

/* ---------- 其它 ---------- */
.err {
  padding: 16px;
  color: #ef4444;
  font-size: 13.5px;
}

.source {
  margin: 0;
  font-size: 11.5px;
  color: #a6acc0;
  text-align: center;
}

@media (max-width: 560px) {
  .current {
    padding: 20px;
  }
  .cur-temp {
    font-size: 40px;
  }
  .cur-icon {
    font-size: 56px;
  }
}
</style>
