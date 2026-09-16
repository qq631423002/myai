import { createRouter, createWebHistory } from 'vue-router'

import ChatView from '@/views/ChatView.vue'

/**
 * 路由表 —— 以后加新功能页面，就往这里加一条。
 * 天气/路线这种「按需才看」的页面用动态 import，打包时会单独切成一个 chunk，
 * 首屏不用把它们（还有 leaflet 那种大库）都下载下来。
 */
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'chat', component: ChatView },
    { path: '/weather', name: 'weather', component: () => import('@/views/WeatherView.vue') },
    { path: '/route', name: 'route', component: () => import('@/views/RouteView.vue') },
    { path: '/soup', name: 'soup', component: () => import('@/views/SoupView.vue') },
  ],
})

export default router
