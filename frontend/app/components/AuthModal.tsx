'use client'

import { useState } from 'react'
import { api } from '@/lib/api'
import { useAuthStore } from '@/lib/authStore'

interface Props {
  onClose: () => void
}

function friendlyError(message: string, mode: 'login' | 'register'): string {
  if (message.includes('이미 사용 중인 이메일')) return '이미 가입된 이메일입니다. 로그인해 주세요.'
  if (message.includes('이메일 또는 비밀번호')) return '이메일 또는 비밀번호가 올바르지 않습니다.'
  if (message.includes('8자')) return '비밀번호는 8자 이상이어야 합니다.'
  if (message.includes('영문자')) return '비밀번호에 영문자를 포함해야 합니다.'
  if (message.includes('숫자')) return '비밀번호에 숫자를 포함해야 합니다.'
  if (message.includes('429')) return '요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.'
  if (message.includes('Failed to fetch') || message.includes('NetworkError')) return '네트워크 연결을 확인해 주세요.'
  return mode === 'login' ? '로그인에 실패했습니다.' : '회원가입에 실패했습니다.'
}

export default function AuthModal({ onClose }: Props) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const { setTokens, setUser } = useAuthStore()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      if (mode === 'register') {
        await api.register(email, password)
      }

      const { access_token, refresh_token } = await api.login(email, password)
      setTokens(access_token, refresh_token)

      const me = await api.getMe()
      setUser(me)

      onClose()
    } catch (err: unknown) {
      const raw = err instanceof Error ? err.message : '오류가 발생했습니다'
      setError(friendlyError(raw, mode))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-sm shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 탭 */}
        <div className="flex mb-6 border-b border-gray-700">
          {(['login', 'register'] as const).map((m) => (
            <button
              key={m}
              onClick={() => { setMode(m); setError('') }}
              className={`flex-1 pb-2 text-sm font-medium transition-colors ${
                mode === m
                  ? 'border-b-2 border-indigo-500 text-white'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {m === 'login' ? '로그인' : '회원가입'}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <input
            type="email"
            placeholder="이메일"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
          />
          <input
            type="password"
            placeholder={mode === 'register' ? '비밀번호 (영문+숫자 8자 이상)' : '비밀번호'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
          />

          {error && (
            <p className="text-xs text-red-400">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="mt-1 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors"
          >
            {loading ? '처리 중...' : mode === 'login' ? '로그인' : '가입하기'}
          </button>
        </form>
      </div>
    </div>
  )
}
