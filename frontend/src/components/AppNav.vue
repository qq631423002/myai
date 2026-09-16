<template>
  <header class="nav" :class="{ open }">
    <!-- ===== 常驻细栏：品牌 + 快捷入口 + 展开/收起箭头 ===== -->
    <div class="nav-bar" @click="open = !open">
      <div class="brand">
        <img class="brand-logo" src="/my-ai.png" alt="" />
        <div class="brand-text">
          <span class="brand-title">AI 工具箱</span>
          <span class="brand-sub">{{ current?.label || '聊天' }}</span>
        </div>
      </div>

      <nav class="quick">
        <RouterLink
          v-for="item in items"
          :key="item.path"
          :to="item.path"
          class="quick-item"
          :class="{ active: isActive(item.path) }"
          @click.stop="open = false"
        >
          <span class="quick-icon">{{ item.icon }}</span>
          <span class="quick-label">{{ item.label }}</span>
        </RouterLink>
      </nav>

      <button class="toggle" :title="open ? '收起导航' : '展开导航'" :aria-expanded="open">
        <span class="chev" :class="{ up: open }">⌄</span>
      </button>
    </div>

    <!-- ===== 拉出的面板：大图标卡片。以后加功能就往 items 里加一项 ===== -->
    <div class="panel">
      <div class="panel-inner">
        <RouterLink
          v-for="item in items"
          :key="item.path"
          :to="item.path"
          class="card"
          :class="{ active: isActive(item.path) }"
          @click="open = false"
        >
          <span class="card-icon">{{ item.icon }}</span>
          <span class="card-title">{{ item.label }}</span>
          <span class="card-desc">{{ item.desc }}</span>
        </RouterLink>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

interface NavItem {
  path: string
  label: string
  icon: string
  desc: string
}

/**
 * 导航项 —— 加新功能页面只需要：
 *   1. 在 src/views/ 下建一个页面组件
 *   2. 在这里加一项，并在 src/router/index.ts 里加一条路由
 */
const items: NavItem[] = [
  { path: '/', label: 'AI 聊天', icon: '💬', desc: '和大模型对话，也能问天气、问路线' },
  { path: '/weather', label: '天气', icon: '🌤️', desc: '各城市实时天气与未来预报' },
  { path: '/route', label: '路线', icon: '🧭', desc: '两地距离、耗时与地图路线' },
  { path: '/soup', label: '海龟汤', icon: '🐢', desc: 'AI 出题当主持，你问是非题猜真相' },
  { path: '/book', label: '读书陪读', icon: '📚', desc: '上传一本txt，按章节问答并标注页码' },
]

const route = useRoute()
const open = ref(false) // false = 收起（只留细栏），true = 拉出面板

const current = computed(() => items.find((i) => i.path === route.path))
const isActive = (path: string) => route.path === path
</script>

<style scoped>
.nav {
  flex-shrink: 0;
  background: #fff;
  border-bottom: 1px solid #eef0f6;
  box-shadow: 0 2px 12px rgba(80, 100, 200, 0.06);
  position: relative;
  z-index: 20;
}

/* ---------- 常驻细栏 ---------- */
.nav-bar {
  height: 54px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
  cursor: pointer;
  user-select: none;
}

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.brand-logo {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  object-fit: cover;
  display: block;
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.brand-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2430;
}

.brand-sub {
  font-size: 11px;
  color: #9aa1b5;
}

/* 收起状态也能直接切页 */
.quick {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
}

.quick-item {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 13px;
  color: #5a6076;
  text-decoration: none;
  white-space: nowrap;
  transition: all 0.18s;
}

.quick-item:hover {
  background: #f4f6fb;
  color: #4d6bfe;
}

.quick-item.active {
  background: #eef2ff;
  color: #4d6bfe;
  font-weight: 600;
}

.quick-icon {
  font-size: 14px;
}

.toggle {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #e3e7f2;
  border-radius: 50%;
  background: #fff;
  color: #8a90a3;
  cursor: pointer;
  transition: all 0.2s;
}

.toggle:hover {
  border-color: #c7d0f5;
  color: #4d6bfe;
  background: #f7f9ff;
}

.chev {
  display: block;
  font-size: 18px;
  line-height: 1;
  transform: translateY(-2px);
  transition: transform 0.28s ease;
}

.chev.up {
  transform: translateY(2px) rotate(180deg);
}

/* ---------- 拉出的面板 ---------- */
.panel {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.3s ease;
}

.nav.open .panel {
  max-height: 300px;
}

.panel-inner {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 4px 16px 18px;
}

.card {
  width: 168px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 14px;
  border: 1px solid #e8ecf7;
  border-radius: 14px;
  background: #fafbff;
  text-decoration: none;
  transition: all 0.2s;
}

.card:hover {
  transform: translateY(-2px);
  border-color: #b9c6f5;
  box-shadow: 0 8px 20px rgba(77, 107, 254, 0.14);
}

.card.active {
  border-color: #4d6bfe;
  background: #eef2ff;
}

.card-icon {
  font-size: 24px;
  line-height: 1.2;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2430;
}

.card-desc {
  font-size: 11.5px;
  line-height: 1.5;
  color: #9aa1b5;
}

@media (max-width: 560px) {
  .quick-label {
    display: none;
  }
}
</style>
