// Only completed layouts are retained. The bound prevents a browsing session
// from accumulating every imported repository in memory.
export function createLayoutCache(capacity = 4) {
  const values = new Map();
  return {
    get(key) {
      if (!values.has(key)) return undefined;
      const value = values.get(key);
      values.delete(key);
      values.set(key, value);
      return value;
    },
    set(key, value) {
      values.delete(key);
      values.set(key, value);
      while (values.size > capacity) values.delete(values.keys().next().value);
    },
  };
}
