export type TimeEditField = "onset" | "offset";

interface ResolveEditedTimeParams {
  timeStr: string;
  currentDate: string | null;
  referenceTimestamp: number | null;
  otherBoundaryTimestamp: number | null;
  field: TimeEditField;
}

function parseHHMM(timeStr: string): { hour: number; minute: number } | null {
  const match = timeStr.match(/^(\d{1,2}):(\d{2})$/);
  if (!match) return null;
  const hour = parseInt(match[1], 10);
  const minute = parseInt(match[2], 10);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return { hour, minute };
}

function toUtcTimestampSeconds(baseDate: Date, hour: number, minute: number, dayOffset: number): number {
  return Date.UTC(
    baseDate.getUTCFullYear(),
    baseDate.getUTCMonth(),
    baseDate.getUTCDate() + dayOffset,
    hour,
    minute,
    0,
    0
  ) / 1000;
}

function nearestToReference(candidates: number[], reference: number): number {
  return candidates.reduce((best, candidate) => (
    Math.abs(candidate - reference) < Math.abs(best - reference) ? candidate : best
  ));
}

/**
 * Resolve a typed HH:MM value to a concrete UTC timestamp in seconds.
 *
 * In 48h view the same clock time appears on two dates, so we generate nearby
 * date candidates and choose the one that preserves marker ordering:
 * - onset: latest candidate <= offset
 * - offset: earliest candidate >= onset
 */
export function resolveEditedTimeToTimestamp({
  timeStr,
  currentDate,
  referenceTimestamp,
  otherBoundaryTimestamp,
  field,
}: ResolveEditedTimeParams): number | null {
  const parsed = parseHHMM(timeStr);
  if (!parsed) return null;

  const candidateSet = new Set<number>();

  if (currentDate) {
    const scoringDate = new Date(`${currentDate}T00:00:00Z`);
    for (const dayOffset of [-1, 0, 1]) {
      candidateSet.add(toUtcTimestampSeconds(scoringDate, parsed.hour, parsed.minute, dayOffset));
    }
  }

  if (referenceTimestamp !== null) {
    const referenceDate = new Date(referenceTimestamp * 1000);
    for (const dayOffset of [-1, 0, 1]) {
      candidateSet.add(toUtcTimestampSeconds(referenceDate, parsed.hour, parsed.minute, dayOffset));
    }
  }

  const candidates = Array.from(candidateSet).sort((a, b) => a - b);
  if (candidates.length === 0) return null;

  if (otherBoundaryTimestamp !== null) {
    if (field === "onset") {
      const valid = candidates.filter((ts) => ts <= otherBoundaryTimestamp);
      if (valid.length > 0) return valid[valid.length - 1];
    } else {
      const valid = candidates.filter((ts) => ts >= otherBoundaryTimestamp);
      if (valid.length > 0) return valid[0];
    }
  }

  if (referenceTimestamp !== null) {
    return nearestToReference(candidates, referenceTimestamp);
  }

  return candidates[0];
}
