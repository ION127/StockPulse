'use client'

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface PortfolioItem {
  qty: number
  avgPrice: number
}

interface WatchlistState {
  watchlist: string[]
  portfolio: Record<string, PortfolioItem>
  addToWatchlist: (ticker: string) => void
  removeFromWatchlist: (ticker: string) => void
  isWatched: (ticker: string) => boolean
  setPortfolioItem: (ticker: string, qty: number, avgPrice: number) => void
  removePortfolioItem: (ticker: string) => void
}

export const useWatchlistStore = create<WatchlistState>()(
  persist(
    (set, get) => ({
      watchlist: [],
      portfolio: {},

      addToWatchlist: (ticker) =>
        set((s) => ({
          watchlist: s.watchlist.includes(ticker) ? s.watchlist : [...s.watchlist, ticker],
        })),

      removeFromWatchlist: (ticker) =>
        set((s) => ({
          watchlist: s.watchlist.filter((t) => t !== ticker),
        })),

      isWatched: (ticker) => get().watchlist.includes(ticker),

      setPortfolioItem: (ticker, qty, avgPrice) =>
        set((s) => ({ portfolio: { ...s.portfolio, [ticker]: { qty, avgPrice } } })),

      removePortfolioItem: (ticker) =>
        set((s) => {
          const { [ticker]: _, ...rest } = s.portfolio
          return { portfolio: rest }
        }),
    }),
    { name: 'stockpulse-watchlist' }
  )
)
