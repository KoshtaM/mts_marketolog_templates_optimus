const moneyFormatter = new Intl.NumberFormat('ru-RU', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const moneyShortFormatter = new Intl.NumberFormat('ru-RU', {
  maximumFractionDigits: 0,
})

const integerFormatter = new Intl.NumberFormat('ru-RU', {
  maximumFractionDigits: 0,
})

export function money(value: string | number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || value === '') return '—'
  const number = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(number)) return '—'
  const formatted = decimals === 0 ? moneyShortFormatter.format(number) : moneyFormatter.format(number)
  return `${formatted} ₽`
}

export function moneyValue(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === '') return 0
  const number = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(number) ? number : 0
}

export function integer(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return integerFormatter.format(value)
}

export function percent(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value * 100)} %`
}

export function share(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value * 100)} %`
}

export function date(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

export function dayLabel(value: string): string {
  const [, month, dayPart] = value.split('-')
  return `${dayPart}.${month}`
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function period(from: string | null | undefined, to: string | null | undefined): string {
  if (!from && !to) return 'период не определён'
  return `${date(from)} — ${date(to)}`
}

export function plural(value: number, one: string, few: string, many: string): string {
  const mod10 = value % 10
  const mod100 = value % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few
  return many
}

export function statusTone(status: string): string {
  const normalized = status.toLowerCase()
  if (normalized.includes('достав')) return 'positive'
  if (normalized.includes('ошиб') || normalized.includes('недост')) return 'negative'
  return 'muted'
}
