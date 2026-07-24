import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

const SESSION_STATE_EVENT = "buping:session-state-change";

function readSessionValue<T>(key: string, initialValue: T): T {
  if (typeof window === "undefined") return initialValue;
  try {
    const saved = window.sessionStorage.getItem(key);
    return saved === null ? initialValue : JSON.parse(saved) as T;
  } catch {
    return initialValue;
  }
}

/**
 * useState backed by sessionStorage.
 *
 * The setter writes synchronously before updating React, so async work that
 * finishes after a route unmounts can still be restored when the user returns.
 */
export function useSessionState<T>(key: string, initialValue: T): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => readSessionValue(key, initialValue));
  const valueRef = useRef(value);
  valueRef.current = value;

  useEffect(() => {
    const syncValue = (event: Event) => {
      const detail = (event as CustomEvent<{ key: string; value: T }>).detail;
      if (!detail || detail.key !== key) return;
      valueRef.current = detail.value;
      setValue(detail.value);
    };
    window.addEventListener(SESSION_STATE_EVENT, syncValue);
    return () => window.removeEventListener(SESSION_STATE_EVENT, syncValue);
  }, [key]);

  const setSessionValue = useCallback<Dispatch<SetStateAction<T>>>((nextValue) => {
    const resolved = typeof nextValue === "function"
      ? (nextValue as (previous: T) => T)(valueRef.current)
      : nextValue;
    valueRef.current = resolved;
    try {
      window.sessionStorage.setItem(key, JSON.stringify(resolved));
    } catch {
      // Keep the current in-memory state usable when storage is unavailable/full.
    }
    setValue(resolved);
    window.dispatchEvent(new CustomEvent(SESSION_STATE_EVENT, { detail: { key, value: resolved } }));
  }, [key]);

  return [value, setSessionValue];
}
