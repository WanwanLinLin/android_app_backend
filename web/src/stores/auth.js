import { defineStore } from 'pinia'
import { ref } from 'vue'
import { login as apiLogin } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('dh_token') || '')
  const username = ref(localStorage.getItem('dh_username') || '')

  function setAuth(tok, name) {
    token.value = tok
    username.value = name
    localStorage.setItem('dh_token', tok)
    localStorage.setItem('dh_username', name)
  }

  function clear() {
    token.value = ''
    username.value = ''
    localStorage.removeItem('dh_token')
    localStorage.removeItem('dh_username')
  }

  async function login(payload) {
    const data = await apiLogin(payload)
    setAuth(data.access_token, payload.username)
    return data
  }

  return { token, username, setAuth, clear, login }
})
