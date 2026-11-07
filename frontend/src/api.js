function errorMessage(data, statusText) {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => String(item.msg || "").replace(/^Value error,\s*/i, ""))
      .filter(Boolean)
      .join(" ");
  }
  return statusText || "Request failed";
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
  } catch {
    throw new Error("The trust engine is not responding. Start the API on port 8000.");
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(errorMessage(data, response.statusText));
  }
  return data;
}

export const api = {
  search: (query) => request(`/api/v1/search?query=${encodeURIComponent(query)}`),
  vendor: (id) => request(`/api/v1/vendor/${id}`),
  reading: (id) => request(`/api/v1/vendor/${id}/reading`),
  register: (body) => request("/api/v1/vendors", { method: "POST", body: JSON.stringify(body) }),
  classify: (body) => request("/api/v1/classify", { method: "POST", body: JSON.stringify(body) }),
  report: (body) => request("/api/v1/reports", { method: "POST", body: JSON.stringify(body) }),
  reply: (reportId, body) => request(`/api/v1/reports/${reportId}/replies`, { method: "POST", body: JSON.stringify(body) }),
  resolve: (reportId, body) => request(`/api/v1/reports/${reportId}/resolve`, { method: "POST", body: JSON.stringify(body) }),
  verifyLegal: (body) => request("/api/v1/verify-legal", { method: "POST", body: JSON.stringify(body) }),
  sms: (body) => request("/api/v1/sms/webhook", { method: "POST", body: JSON.stringify(body) }),
  importSocial: (body) => request("/api/v1/social/import", { method: "POST", body: JSON.stringify(body) }),
  syncSocial: () => request("/api/v1/social/sync", { method: "POST", body: JSON.stringify({}) }),
};
