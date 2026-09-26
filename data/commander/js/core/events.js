// Synchronous topics between the transport (net/*) and the views. The
// transport never touches the DOM: it updates the store and emits a topic;
// view modules subscribe in their initializer. Handlers run inside emit() in
// registration order, so a topic keeps the exact ordering of a direct call.
const handlers = new Map();

export function on(topic, handler) {
  if (!handlers.has(topic)) handlers.set(topic, []);
  handlers.get(topic).push(handler);
}

export function emit(topic, ...args) {
  for (const handler of handlers.get(topic) ?? []) handler(...args);
}
