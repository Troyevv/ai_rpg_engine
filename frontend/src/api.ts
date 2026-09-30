export async function api<T>(
  path: string,
  body?: unknown,
  method = body === undefined ? "GET" : "POST",
  signal?: AbortSignal,
): Promise<T> {
  // The settings field holds a DeepSeek key. Never forward it to another service.
  if (body && typeof body === "object") {
    const value = body as {
      config?: { provider?: string };
      provider?: string;
      api_key?: string;
    };
    if ((value.config?.provider || value.provider) === "compatible") {
      const { api_key: _key, ...withoutKey } = value;
      body = withoutKey;
    }
  }
  const response = await fetch("/api" + path, {
    method,
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Сервер недоступен" }));
    throw new Error(
      typeof error.detail === "string" ? error.detail : "Некорректный запрос",
    );
  }
  return response.json();
}
export function download(text: string, name: string) {
  const url = URL.createObjectURL(
    new Blob([text], { type: "text/markdown;charset=utf-8" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
