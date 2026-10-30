type Command = Record<string, unknown>;
type Pending = Record<string, Command>;
function read(key: string): Pending {
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) || 'null');
    if (saved?.requests && typeof saved.requests === 'object') return saved.requests;
    // Preserve the previous single-operation cache on upgrade.
    if (typeof saved?.intent === 'string' && saved.command) return {[saved.intent]: saved.command};
  } catch { /* A corrupt UI cache must not leave the request lock held. */ }
  return {};
}
/** Pending request identities only; canonical messages still belong to the server. */
export function phoneOperation(key: string, command: Command) {
  const intent = JSON.stringify(command);
  const requests = read(key);
  const payload = requests[intent] || {operation_id: crypto.randomUUID(), ...command};
  requests[intent] = payload;
  sessionStorage.setItem(key, JSON.stringify({requests}));
  return {payload, complete() {
    const remaining = read(key);
    delete remaining[intent];
    if (Object.keys(remaining).length) sessionStorage.setItem(key, JSON.stringify({requests: remaining}));
    else sessionStorage.removeItem(key);
  }};
}
