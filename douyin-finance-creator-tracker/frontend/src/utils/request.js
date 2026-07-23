const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://123.207.36.204:8000";

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

function endpoint(path) {
  return path.startsWith("http") ? path : `${API_BASE_URL}${path}`;
}

export async function request(path, options = {}) {
  const response = await fetch(endpoint(path), {
    ...options,
    headers: { Accept: "application/json", ...options.headers },
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => ({}))
    : await response.text().catch(() => "");

  if (!response.ok) {
    const message = payload?.detail || payload?.message || `请求失败（${response.status}）`;
    throw new ApiError(message, response.status, payload);
  }
  return payload;
}
