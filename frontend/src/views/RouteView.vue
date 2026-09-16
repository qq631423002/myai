<template>
  <div class="page">
    <!-- ===== 输入区 ===== -->
    <div class="panel form-panel">
      <div class="form-row">
        <div class="field">
          <span class="field-label">起点</span>
          <input v-model="origin" class="input" placeholder="例如 北京" @keypress.enter="search()" />
        </div>
        <span class="arrow">→</span>
        <div class="field">
          <span class="field-label">终点</span>
          <input
            v-model="destination"
            class="input"
            placeholder="例如 上海"
            @keypress.enter="search()"
          />
        </div>
        <select v-model="mode" class="select">
          <option value="driving">🚗 驾车</option>
          <option value="cycling">🚴 骑行</option>
          <option value="walking">🚶 步行</option>
        </select>
        <button class="btn" :disabled="loading" @click="search()">
          {{ loading ? '规划中…' : '规划路线' }}
        </button>
      </div>

      <div class="chips">
        <button
          v-for="p in quickPairs"
          :key="p.label"
          class="chip"
          @click="search(p.origin, p.destination)"
        >
          {{ p.label }}
        </button>
      </div>
    </div>

    <div v-if="error" class="panel err">⚠️ {{ error }}</div>

    <template v-if="data">
      <!-- ===== 数据卡 ===== -->
      <div class="stats">
        <div class="panel stat">
          <span class="stat-label">总距离</span>
          <b class="stat-value">{{ data.总距离 }}</b>
        </div>
        <div class="panel stat">
          <span class="stat-label">预计耗时</span>
          <b class="stat-value">{{ data.预计耗时 }}</b>
        </div>
        <div class="panel stat">
          <span class="stat-label">出行方式</span>
          <b class="stat-value">{{ data.出行方式 }}</b>
        </div>
        <div class="panel stat">
          <span class="stat-label">路线</span>
          <b class="stat-value route-name">{{ data.起点 }} → {{ data.终点 }}</b>
        </div>
      </div>

      <div v-if="data.注意" class="panel warn">ℹ️ {{ data.注意 }}</div>

      <!-- ===== 地图 ===== -->
      <div class="panel">
        <div class="map-head">
          <h3 class="panel-title">路线地图</h3>
          <span class="map-hint">可拖动、滚轮缩放</span>
        </div>
        <div ref="mapEl" class="map"></div>
        <p class="map-note">
          底图：高德地图（GCJ-02 坐标）· 路线：OSRM（WGS-84）·
          已做坐标纠偏，否则路线会整体偏离道路
        </p>
      </div>

      <!-- ===== 转向指引 ===== -->
      <div v-if="data.转向指引?.length" class="panel steps-panel">
        <h3 class="panel-title">转向指引（{{ data.转向指引.length }} 步）</h3>
        <ol class="steps">
          <li v-for="(s, i) in data.转向指引" :key="i" class="step">
            <span class="step-no">{{ i + 1 }}</span>
            <span class="step-text">{{ s }}</span>
          </li>
        </ol>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { wgs84ToGcj02 } from '@/utils/coord'

interface RouteData {
  起点: string
  终点: string
  出行方式: string
  总距离: string
  预计耗时: string
  数据来源: string
  注意?: string
  轨迹?: [number, number][] // [[经度, 纬度], ...] WGS-84
  转向指引?: string[]
  起终点坐标?: { 起点: [number, number]; 终点: [number, number] }
}

// 高德矢量瓦片：中文地名、国内路网最全。{s} 是 1~4 四个镜像域名轮询
const TILE_URL =
  'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}'

const origin = ref('北京')
const destination = ref('上海')
const mode = ref('driving')

const quickPairs = [
  { label: '北京 → 上海', origin: '北京', destination: '上海' },
  { label: '广州 → 深圳', origin: '广州', destination: '深圳' },
  { label: '杭州 → 苏州', origin: '杭州', destination: '苏州' },
  { label: '成都 → 重庆', origin: '成都', destination: '重庆' },
]

const data = ref<RouteData | null>(null)
const loading = ref(false)
const error = ref('')

const mapEl = ref<HTMLElement | null>(null)
let map: L.Map | null = null

async function search(o?: string, d?: string) {
  if (o) origin.value = o
  if (d) destination.value = d

  const from = origin.value.trim()
  const to = destination.value.trim()
  if (!from || !to) {
    error.value = '起点和终点都要填'
    return
  }

  loading.value = true
  error.value = ''
  try {
    const res = await fetch(
      `/api/route?origin=${encodeURIComponent(from)}&destination=${encodeURIComponent(to)}&mode=${mode.value}`,
    )
    const text = await res.text()
    if (!text) throw new Error(`请求失败（HTTP ${res.status}），后端可能没启动`)
    const json = JSON.parse(text)
    if (!res.ok) throw new Error(json.detail || '规划失败')
    data.value = json as RouteData
    await drawMap()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '网络错误'
    data.value = null
    map?.remove()
    map = null
  } finally {
    loading.value = false
  }
}

/** 把轨迹画到高德地图上 */
async function drawMap() {
  const geo = data.value?.轨迹
  if (!geo || geo.length < 2) return

  await nextTick() // 等 <div ref="mapEl"> 渲染出来
  if (!mapEl.value) return

  map?.remove() // 重复查询时先销毁旧地图，否则会报「容器已初始化」
  map = L.map(mapEl.value, {
    zoomControl: true,
    attributionControl: false,
    minZoom: 3,
    maxZoom: 18,
  })

  L.tileLayer(TILE_URL, { subdomains: '1234', minZoom: 3, maxZoom: 18 }).addTo(map)

  // 关键一步：OSRM 给的是 WGS-84，高德底图是 GCJ-02，不转换路线会整体偏几百米
  const points = geo.map(([lng, lat]) => {
    const [gLng, gLat] = wgs84ToGcj02(lng, lat)
    return L.latLng(gLat, gLng)
  })

  const line = L.polyline(points, { color: '#4d6bfe', weight: 5, opacity: 0.9 }).addTo(map)

  // 用 circleMarker 而不是默认图标：默认图标要额外的图片文件，容易 404
  const start = points[0]
  const end = points[points.length - 1]
  if (start) {
    L.circleMarker(start, {
      radius: 8,
      color: '#fff',
      weight: 3,
      fillColor: '#22c55e',
      fillOpacity: 1,
    })
      .addTo(map)
      .bindTooltip(`起点：${data.value?.起点 ?? ''}`)
  }
  if (end) {
    L.circleMarker(end, {
      radius: 8,
      color: '#fff',
      weight: 3,
      fillColor: '#ef4444',
      fillOpacity: 1,
    })
      .addTo(map)
      .bindTooltip(`终点：${data.value?.终点 ?? ''}`)
  }

  map.fitBounds(line.getBounds(), { padding: [36, 36] })
}

onMounted(() => search())

onBeforeUnmount(() => {
  map?.remove()
  map = null
})
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
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #1f2430;
}

/* ---------- 输入区 ---------- */
.form-panel {
  padding: 16px;
}

.form-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.field {
  flex: 1;
  min-width: 130px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.field-label {
  font-size: 12px;
  color: #9aa1b5;
}

.input {
  width: 100%;
  box-sizing: border-box;
  padding: 11px 14px;
  border: 1.5px solid transparent;
  border-radius: 12px;
  background: #f4f6fb;
  font-size: 14px;
  color: #2a3040;
  outline: none;
  transition: all 0.2s;
}

.input:focus {
  background: #fff;
  border-color: #4d6bfe;
  box-shadow: 0 0 0 4px rgba(77, 107, 254, 0.12);
}

.arrow {
  padding-bottom: 12px;
  font-size: 18px;
  color: #b9c6f5;
}

.select {
  padding: 11px 10px;
  border: 1.5px solid #e3e7f2;
  border-radius: 12px;
  background: #fff;
  font-size: 13.5px;
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

/* ---------- 数据卡 ---------- */
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
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

.route-name {
  font-size: 14px;
  line-height: 1.4;
}

.warn {
  padding: 13px 16px;
  font-size: 13px;
  line-height: 1.6;
  color: #a1651a;
  background: #fff8e8;
}

.err {
  padding: 16px;
  color: #ef4444;
  font-size: 13.5px;
}

/* ---------- 地图 ---------- */
.map-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px 10px;
}

.map-hint {
  font-size: 11.5px;
  color: #a6acc0;
}

.map {
  height: 420px;
  margin: 0 18px;
  border-radius: 14px;
  overflow: hidden;
  background: #eef2f7;
}

.map-note {
  margin: 10px 18px 16px;
  font-size: 11px;
  line-height: 1.6;
  color: #a6acc0;
}

/* ---------- 转向指引 ---------- */
.steps-panel {
  padding: 18px;
}

.steps {
  list-style: none;
  margin: 14px 0 0;
  padding: 0;
  max-height: 320px;
  overflow-y: auto;
}

.step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  font-size: 13px;
  color: #3a4152;
  line-height: 1.6;
}

.step:nth-child(odd) {
  background: #fafbff;
}

.step-no {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #eef2ff;
  color: #4d6bfe;
  font-size: 11px;
  font-weight: 600;
}

@media (max-width: 560px) {
  .map {
    height: 300px;
  }
}
</style>
