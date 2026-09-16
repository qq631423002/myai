import './assets/main.css'
import ElementPlus from 'element-plus'                     // Element Plus 核心库
import zhCn from 'element-plus/es/locale/lang/zh-cn'       // 中文语言包
import * as ElementPlusIconsVue from '@element-plus/icons-vue' // 图标库
import 'element-plus/dist/index.css'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'   // 页面路由（聊天 / 天气 / 路线）

const app = createApp(App)

// Element Plus 组件 + 中文语言包
app.use(ElementPlus, { locale: zhCn })

// 路由
app.use(router)

// 全局注册所有图标，模板里可直接用 <el-icon><Plus /></el-icon> 之类
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.mount('#app')
