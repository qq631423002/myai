<template>
  聊天
  <div id="chat-container">
    <div v-for="msg in messages" :key="msg">
      {{ msg.role }} : {{ msg.content }}
    </div>
  </div>
  <div id="chat-input-container">
    <input v-model="input" type="text" id="chat-input" @keypress.enter="sendMessage" placeholder="请输入消息">
    <button id="chat-send-btn" @click="sendMessage">发送</button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { fetchEventSource } from '@microsoft/fetch-event-source'

const input = ref('')
const messages = ref([])
const content = ref('')

function sendMessage() {
  const inputMsg = input.value
  messages.value.push({ role: 'user', content: inputMsg })
  input.value = ''
  content.value = ''
  fetchEventSource("/api/demo03", {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      "input": inputMsg
    }),
    onmessage: (event) => {
      // 传输完成
      if (event.event === 'done') {
        messages.value.push({ role: 'assistant', content: content.value })
        return
      }
      // 处理消息
      content.value += event.data
    }
  })
}
</script>