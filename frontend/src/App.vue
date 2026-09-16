<template>
  <div class="app-shell">
    <!-- 顶部导航栏（可上下拉出收回），以后加功能就往 AppNav 的 items 里加一项 -->
    <AppNav />

    <!-- 当前页面的内容。overflow: auto 让天气/路线这种长页面能滚动；
         聊天页会自己撑满这块区域（它的 .page 用的是 height: 100%） -->
    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { RouterView } from 'vue-router'

import AppNav from '@/components/AppNav.vue'
</script>

<style scoped>
.app-shell {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.app-main {
  flex: 1;
  /* 关键：不加 min-height: 0，里面的 height: 100% 会把 flex 容器撑破 */
  min-height: 0;
  overflow: auto;
}
</style>
