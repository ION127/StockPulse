'use client'

import { useEffect, useState, useCallback } from 'react'
import { useStore } from '@/lib/store'
import { api } from '@/lib/api'
import type { Prediction, ModelPerformance } from '@/types'
import clsx from 'clsx'

export default function PredictionPanel() {
  const selectedTicker = useStore((s) => s.selectedTicker)

  const [prediction, setPrediction] = useState<Prediction | null>(null)
  const [performance, setPerformance] = useState<ModelPerformance[]>([])
  const [loading, setLoading] = useState(false)
  const [training, setTraining] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchPrediction = useCallback(async (ticker: string) => {
    setLoading(true)
    setError(null)
    try {
      const [pred, perf] = await Promise.all([
        api.getLatestPrediction(ticker).catch(() => null),
        api.getModelPerformance(ticker, 14).catch(() => []),
      ])
      setPrediction(pred)
      setPerformance(perf)
    } catch {
      setError('예측 데이터를 불러올 수 없습니다')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!selectedTicker) return
    fetchPrediction(selectedTicker)
  }, [selectedTicker, fetchPrediction])

  const handleTrain = async () => {
    if (!selectedTicker || training) return
    setTraining(true)
    try {
      await api.triggerTrain(selectedTicker)
      // 학습은 백그라운드에서 진행 — 5초 후 새로고침
      setTimeout(() => {
        fetchPrediction(selectedTicker)
        setTraining(false)
      }, 5000)
    } catch {
      setTraining(false)
    }
  }

  // 종목 미선택
  if (!selectedTicker) {
    return (
      <div className="rounded-lg bg-gray-900 p-4 flex flex-col h-full">
        <h2 className="text-sm font-semibold text-gray-300 mb-3">ML 주가 예측</h2>
        <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
          종목을 선택하세요
        </div>
      </div>
    )
  }

  const acc30 = performance.find(p => p.accuracy_30d != null)?.accuracy_30d
  const acc7  = performance.find(p => p.accuracy_7d != null)?.accuracy_7d

  return (
    <div className="rounded-lg bg-gray-900 p-4 flex flex-col h-full gap-3">
      {/* 헤더 */}
      <div className="flex items-center justify-between shrink-0">
        <h2 className="text-sm font-semibold text-gray-300">
          ML 주가 예측
          <span className="ml-2 text-xs text-gray-500 font-normal">{selectedTicker}</span>
        </h2>
        <button
          onClick={handleTrain}
          disabled={training}
          className={clsx(
            'text-xs px-2 py-1 rounded transition-colors',
            training
              ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
              : 'bg-blue-800 hover:bg-blue-700 text-blue-200'
          )}
        >
          {training ? '학습 중...' : '재학습'}
        </button>
      </div>

      {loading && (
        <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
          로딩 중...
        </div>
      )}

      {error && !loading && (
        <div className="flex-1 flex items-center justify-center text-red-500 text-sm">
          {error}
        </div>
      )}

      {!loading && !error && !prediction && (
        <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
          예측 데이터 없음 — 재학습 버튼을 눌러 시작하세요
        </div>
      )}

      {!loading && prediction && (
        <>
          {/* 예측 결과 메인 카드 */}
          <div className={clsx(
            'rounded-lg p-3 flex items-center justify-between',
            prediction.direction === '상승' ? 'bg-emerald-900/40 border border-emerald-700/50' : 'bg-red-900/40 border border-red-700/50'
          )}>
            <div>
              <div className={clsx(
                'text-2xl font-bold',
                prediction.direction === '상승' ? 'text-emerald-400' : 'text-red-400'
              )}>
                {prediction.direction === '상승' ? '▲ 상승' : '▼ 하락'}
              </div>
              <div className="text-xs text-gray-400 mt-0.5">
                {prediction.prediction_date} 예측
              </div>
            </div>
            <div className="text-right">
              <div className="text-lg font-semibold text-white">
                {prediction.up_prob.toFixed(1)}%
              </div>
              <div className="text-xs text-gray-400">상승 확률</div>
            </div>
          </div>

          {/* 지표 행 */}
          <div className="grid grid-cols-3 gap-2 shrink-0">
            <MetricBox
              label="신뢰도"
              value={`${prediction.confidence.toFixed(0)}%`}
              sub={prediction.confidence >= 70 ? '높음' : prediction.confidence >= 50 ? '보통' : '낮음'}
              color={prediction.confidence >= 70 ? 'text-emerald-400' : prediction.confidence >= 50 ? 'text-yellow-400' : 'text-red-400'}
            />
            <MetricBox
              label="CV 정확도"
              value={prediction.cv_accuracy != null ? `${(prediction.cv_accuracy * 100).toFixed(1)}%` : '-'}
              sub="교차검증"
              color="text-blue-400"
            />
            <MetricBox
              label="30일 정확도"
              value={acc30 != null ? `${(acc30 * 100).toFixed(1)}%` : '-'}
              sub={acc30 != null && acc30 < 0.52 ? '재학습 권장' : '실제 검증'}
              color={acc30 != null && acc30 < 0.52 ? 'text-red-400' : 'text-gray-300'}
            />
          </div>

          {/* 전일 결과 (검증된 경우) */}
          {prediction.was_correct !== null && (
            <div className={clsx(
              'text-xs px-2 py-1.5 rounded flex items-center gap-2',
              prediction.was_correct ? 'bg-emerald-900/30 text-emerald-400' : 'bg-red-900/30 text-red-400'
            )}>
              <span>{prediction.was_correct ? '✓' : '✗'}</span>
              <span>
                전일 예측: {prediction.direction} →
                실제: {prediction.actual_direction ?? '-'}
                {prediction.actual_return != null && ` (${prediction.actual_return > 0 ? '+' : ''}${prediction.actual_return.toFixed(2)}%)`}
              </span>
            </div>
          )}

          {/* SHAP 주요 피처 */}
          {prediction.shap_top5 && Object.keys(prediction.shap_top5).length > 0 && (
            <div className="shrink-0">
              <div className="text-xs text-gray-500 mb-1.5">주요 영향 피처 (SHAP)</div>
              <div className="space-y-1">
                {Object.entries(prediction.shap_top5)
                  .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))
                  .slice(0, 4)
                  .map(([feat, val]) => (
                    <ShapBar key={feat} name={feat} value={val} />
                  ))}
              </div>
            </div>
          )}

          {/* 정확도 추이 (최근 7일) */}
          {performance.length > 0 && (
            <div className="text-xs text-gray-600 shrink-0">
              모델 버전: {prediction.model_version ?? '-'} ·
              7일 정확도: {acc7 != null ? `${(acc7 * 100).toFixed(1)}%` : '-'}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function MetricBox({ label, value, sub, color }: {
  label: string; value: string; sub: string; color: string
}) {
  return (
    <div className="bg-gray-800 rounded p-2 text-center">
      <div className={clsx('text-base font-semibold', color)}>{value}</div>
      <div className="text-xs text-gray-400">{label}</div>
      <div className="text-xs text-gray-600">{sub}</div>
    </div>
  )
}

function ShapBar({ name, value }: { name: string; value: number }) {
  const isPositive = value >= 0
  const pct = Math.min(Math.abs(value) * 10, 100)  // 시각화용 스케일링
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-gray-500 w-28 truncate shrink-0" title={name}>
        {name.replace(/_/g, ' ')}
      </span>
      <div className="flex-1 bg-gray-800 rounded-full h-1.5 overflow-hidden">
        <div
          className={clsx(
            'h-full rounded-full transition-all',
            isPositive ? 'bg-emerald-500' : 'bg-red-500'
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={clsx('w-10 text-right shrink-0', isPositive ? 'text-emerald-400' : 'text-red-400')}>
        {value > 0 ? '+' : ''}{value.toFixed(2)}
      </span>
    </div>
  )
}
