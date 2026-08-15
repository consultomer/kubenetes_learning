const byId = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "—")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderTable(targetId, columns, rows) {
  const target = byId(targetId);
  if (!rows.length) {
    target.innerHTML = '<p class="empty">No items returned.</p>';
    return;
  }
  const heading = columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("");
  const body = rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(column.value(row))}</td>`).join("")}</tr>`).join("");
  target.innerHTML = `<div class="table-wrap"><table><thead><tr>${heading}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

async function refreshOverview() {
  const response = await fetch("/api/overview", { cache: "no-store" });
  if (!response.ok) throw new Error(`Dashboard request failed (${response.status})`);
  const data = await response.json();
  const identity = data.identity;
  byId("app-version").textContent = `v${identity.app_version}`;
  byId("cluster-name").textContent = identity.cluster_name;
  byId("pod-name").textContent = identity.pod_name;
  byId("node-name").textContent = identity.node_name;
  byId("pod-ip").textContent = identity.pod_ip;
  byId("node-count").textContent = data.summary.nodes;
  byId("pod-count").textContent = data.summary.pods_in_namespace;
  byId("service-count").textContent = data.summary.services_in_namespace;
  byId("namespace-count").textContent = data.summary.namespaces;
  const status = byId("api-status");
  status.textContent = data.api_access.message;
  status.className = `status ${data.api_access.available ? "good" : "warn"}`;
  byId("rate-limit-description").textContent = `${data.rate_limit.requests} requests per ${data.rate_limit.window_seconds} seconds, ${data.rate_limit.scope.toLowerCase()}.`;

  renderTable("nodes-table", [
    { label: "Name", value: (item) => item.name },
    { label: "Ready", value: (item) => item.ready ? "Ready" : "NotReady" },
    { label: "Architecture", value: (item) => item.architecture },
    { label: "Kubelet", value: (item) => item.kubelet_version },
  ], data.nodes);
  renderTable("pods-table", [
    { label: "Name", value: (item) => item.name },
    { label: "Phase", value: (item) => item.phase },
    { label: "Ready", value: (item) => item.ready ? "Ready" : "NotReady" },
    { label: "Node", value: (item) => item.node },
    { label: "Pod IP", value: (item) => item.pod_ip },
  ], data.pods);
  renderTable("services-table", [
    { label: "Name", value: (item) => item.name },
    { label: "Type", value: (item) => item.type },
    { label: "Cluster IP", value: (item) => item.cluster_ip },
    { label: "Ports", value: (item) => item.ports.join(", ") },
  ], data.services);
  byId("namespaces-list").innerHTML = data.namespaces.length
    ? data.namespaces.map((name) => `<span>${escapeHtml(name)}</span>`).join("")
    : '<p class="empty">No namespaces returned.</p>';
}

async function runLab(url, outputId, button) {
  button.disabled = true;
  try {
    const response = await fetch(url, { cache: "no-store" });
    const payload = await response.json();
    byId(outputId).textContent = pretty(payload);
  } catch (error) {
    byId(outputId).textContent = `Request failed: ${error.message}`;
  } finally {
    button.disabled = false;
  }
}

byId("refresh-button").addEventListener("click", () => refreshOverview().catch((error) => alert(error.message)));
byId("load-balance-button").addEventListener("click", (event) => runLab("/api/lab/load-balance?requests=12", "load-balance-output", event.currentTarget));
byId("rate-limit-button").addEventListener("click", (event) => runLab("/api/lab/rate-limit", "rate-limit-output", event.currentTarget));

refreshOverview().catch((error) => {
  byId("api-status").textContent = error.message;
  byId("api-status").className = "status warn";
});
setInterval(() => refreshOverview().catch(() => {}), 15000);
