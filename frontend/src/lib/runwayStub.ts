// TODO(phase4): replace this whole module with a real GET /runway call once the
// Monte Carlo twin exists. Nothing here is computed from data — it's a fixed,
// internally-consistent placeholder so Today's ForecastChart and risk pill have
// something plausible to render before the model is built.
import { addDays, daysBetween, firstOfNextMonth } from '@/lib/date'

export interface ForecastPoint {
  date: string
  p10: number
  median: number
  p90: number
}

export type RunOutRisk = 'low' | 'watch' | 'risk'

export interface RunwayStub {
  nextInflowDate: string
  nextInflowAmountPaise: number
  pRunOutPercent: number
  pRunOutRisk: RunOutRisk
  forecast: ForecastPoint[]
}

export function getRunwayStub(asOfDate: string, currentBalancePaise: number): RunwayStub {
  const nextInflowDate = firstOfNextMonth(asOfDate)
  const totalDays = Math.max(daysBetween(asOfDate, nextInflowDate), 1)
  const dailyMedianSpend = currentBalancePaise / totalDays

  const forecast: ForecastPoint[] = []
  for (let day = 0; day <= totalDays; day++) {
    const spread = day / totalDays
    const median = Math.max(0, Math.round(currentBalancePaise - dailyMedianSpend * day))
    const bandHalfWidth = Math.round(currentBalancePaise * 0.22 * spread)
    forecast.push({
      date: addDays(asOfDate, day),
      median,
      p10: Math.max(0, median - bandHalfWidth),
      p90: median + bandHalfWidth,
    })
  }

  const floorP10 = forecast[forecast.length - 1].p10
  const pRunOutRisk: RunOutRisk = floorP10 === 0 ? 'watch' : 'low'
  const pRunOutPercent = floorP10 === 0 ? 22 : 8

  return {
    nextInflowDate,
    nextInflowAmountPaise: 900_000,
    pRunOutPercent,
    pRunOutRisk,
    forecast,
  }
}
