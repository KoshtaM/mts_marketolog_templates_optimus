export interface Bucket {
  segments: number
  count: number
  share: number
}

export interface Bar {
  label: string
  count: number
  share: number
  grouped: boolean
}

const EXACT_LIMIT = 9
const TAIL_RANGES: [number, number | null][] = [
  [10, 19],
  [20, 49],
  [50, 99],
  [100, null],
]

export function groupBuckets(buckets: Bucket[]): Bar[] {
  const present = new Map(
    buckets.filter((bucket) => bucket.count > 0).map((bucket) => [bucket.segments, bucket]),
  )
  const largest = Math.max(0, ...present.keys())
  const bars: Bar[] = []
  for (let segments = 1; segments <= Math.min(EXACT_LIMIT, largest); segments += 1) {
    const bucket = present.get(segments)
    bars.push({
      label: String(segments),
      count: bucket?.count ?? 0,
      share: bucket?.share ?? 0,
      grouped: false,
    })
  }
  for (const [low, high] of TAIL_RANGES) {
    const members = [...present.values()].filter(
      (bucket) => bucket.segments >= low && (high === null || bucket.segments <= high),
    )
    if (!members.length) continue
    bars.push({
      label: high === null ? `${low}+` : `${low}–${high}`,
      count: members.reduce((sum, bucket) => sum + bucket.count, 0),
      share: members.reduce((sum, bucket) => sum + bucket.share, 0),
      grouped: true,
    })
  }
  return bars
}
