export const pct = (v, digits = 2) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(digits)}%`)

const et = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
})
export const etTime = (iso) => `${et.format(new Date(iso))} ET`

const etDay = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', weekday: 'short', month: 'short', day: 'numeric' })
export const etDate = (iso) => etDay.format(new Date(iso))

export const longDate = (isoDate) =>
  new Date(`${isoDate}T12:00:00Z`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })

export const monthYear = (isoDate) =>
  new Date(`${isoDate}T12:00:00Z`).toLocaleDateString('en-US', { month: 'short', year: '2-digit' })

const dayMonth = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric' })
export const dayMonthLabel = (iso) => dayMonth.format(new Date(iso))
