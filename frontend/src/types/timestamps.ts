/**
 * Branded timestamp types for compile-time unit safety.
 *
 * All timestamps in the store, IndexedDB, DataSource interfaces, and backend
 * are Unix seconds. Milliseconds only exist at the WASM boundary and are
 * converted to seconds at storage time.
 */

/** Unix timestamp in seconds (branded for type safety). */
export type UnixSeconds = number & { readonly __brand: "UnixSeconds" };

/** Unix timestamp in milliseconds (branded for type safety). */
export type UnixMs = number & { readonly __brand: "UnixMs" };

/** Cast a number known to be seconds to the branded type. */
export function asSeconds(v: number): UnixSeconds {
  return v as UnixSeconds;
}

/** Cast a number known to be milliseconds to the branded type. */
export function asMs(v: number): UnixMs {
  return v as UnixMs;
}

/** Convert a branded milliseconds value to seconds. */
export function msToSeconds(ms: UnixMs): UnixSeconds {
  return ((ms as number) / 1000) as UnixSeconds;
}

/** Convert a branded seconds value to milliseconds. */
export function secondsToMs(sec: UnixSeconds): UnixMs {
  return ((sec as number) * 1000) as UnixMs;
}

/** Convert a branded seconds value to a Date. */
export function secondsToDate(sec: UnixSeconds): Date {
  return new Date((sec as number) * 1000);
}

/** Convert a Date to a branded seconds value. */
export function dateToSeconds(d: Date): UnixSeconds {
  return (d.getTime() / 1000) as UnixSeconds;
}
