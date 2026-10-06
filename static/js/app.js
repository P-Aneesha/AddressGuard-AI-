"use strict";

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];

let currentValidation = null;
let correctionChoices = {};

function escapeHtml(value) {
  const d = document.createElement("div");
  d.textContent = value == null ? "" : String(value);
  return d.innerHTML;
}

async function jsonFetch(url, options = {}) {
  try {
    const response = await fetch(url, options);
    let data = {};
    try { data = await response.json(); } catch (_) {}
    return { response, data };
  } catch (error) {
    console.error(error);
    return {
      response: { ok: false, status: 0 },
      data: { error: "Unable to connect to the server." }
    };
  }
}

function setAuthMessage(message, ok = false) {
  const box = $("#authMsg");
  if (!box) return;
  box.textContent = message || "";
  box.style.color = ok ? "#35d79a" : "#f16b78";
}

/* =========================
   AUTHENTICATION
========================= */
if ($("#loginForm")) {
  const loginTab = $("#tabLogin");
  const registerTab = $("#tabReg");
  const loginForm = $("#loginForm");
  const registerForm = $("#regForm");

  function showLogin() {
    loginTab?.classList.add("active");
    registerTab?.classList.remove("active");
    loginForm?.classList.remove("hidden");
    registerForm?.classList.add("hidden");
    setAuthMessage("");
  }

  function showRegister() {
    registerTab?.classList.add("active");
    loginTab?.classList.remove("active");
    registerForm?.classList.remove("hidden");
    loginForm?.classList.add("hidden");
    setAuthMessage("");
  }

  loginTab?.addEventListener("click", showLogin);
  registerTab?.addEventListener("click", showRegister);

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = loginForm.querySelector("button[type=submit]");
    button.disabled = true;
    button.textContent = "Signing in...";

    const { response, data } = await jsonFetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: $("#loginEmail").value.trim(),
        password: $("#loginPw").value
      })
    });

    if (response.ok) {
      location.href = "/dashboard";
    } else {
      setAuthMessage(data.error || "Invalid email or password.");
      button.disabled = false;
      button.innerHTML = 'Sign in <span>→</span>';
    }
  });

  registerForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = registerForm.querySelector("button[type=submit]");
    button.disabled = true;
    button.textContent = "Creating account...";

    const { response, data } = await jsonFetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: $("#regName").value.trim(),
        email: $("#regEmail").value.trim(),
        password: $("#regPw").value
      })
    });

    if (response.ok) {
      location.href = "/dashboard";
    } else {
      setAuthMessage(data.error || "Could not create account.");
      button.disabled = false;
      button.innerHTML = 'Create account <span>→</span>';
    }
  });
}


/* =========================
   USER PROFILE
========================= */
if ($("#profileBtn")) {
  async function loadCurrentUser() {
    const { response, data } = await jsonFetch("/api/auth/me");
    if (!response.ok || !data.user) {
      location.href = "/login";
      return;
    }
    const user = data.user;
    const name = String(user.name || "User").trim();
    const email = String(user.email || "").trim();
    const first = (name[0] || "U").toUpperCase();

    $("#userNameTop") && ($("#userNameTop").textContent = name);
    $("#welcomeName") && ($("#welcomeName").textContent = name);
    $("#profileName") && ($("#profileName").textContent = name);
    $("#profileEmail") && ($("#profileEmail").textContent = email);
    $("#userAvatar") && ($("#userAvatar").textContent = first);
    $("#profileAvatar") && ($("#profileAvatar").textContent = first);
  }

  const profileBtn = $("#profileBtn");
  const profileMenu = $("#profileMenu");

  profileBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = profileMenu.classList.toggle("hidden") === false;
    profileBtn.setAttribute("aria-expanded", String(open));
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".profile-wrap")) {
      profileMenu.classList.add("hidden");
      profileBtn.setAttribute("aria-expanded", "false");
    }
  });

  $("#profileLogoutBtn")?.addEventListener("click", async () => {
    await jsonFetch("/api/auth/logout", { method: "POST" });
    location.href = "/login";
  });

  loadCurrentUser();
}

/* =========================
   DASHBOARD
========================= */
if ($("#runBtn")) {
  function show(selector) {
    const el = $(selector);
    if (el) el.classList.remove("hidden");
  }

  function hide(selector) {
    const el = $(selector);
    if (el) el.classList.add("hidden");
  }

  function badgeClass(type, value) {
    const v = String(value || "").toUpperCase();
    if (type === "risk") {
      if (v === "LOW") return "good";
      if (v === "MEDIUM") return "warning";
      if (v === "HIGH" || v === "CRITICAL") return "danger";
    }
    if (type === "decision") {
      if (v === "VERIFIED") return "good";
      if (v.includes("CONFIRMATION")) return "warning";
      if (v.includes("SUSPICIOUS") || v.includes("FAKE")) return "danger";
    }
    return "neutral";
  }

  function statusClass(value) {
    const v = String(value || "").toUpperCase();
    if (["CONSISTENT", "VERIFIED", "COMPLETED", "VALID", "VALID / CHECKED", "CHECKED"].includes(v)) return "check-good";
    if (["LIKELY_MATCH", "INCOMPLETE", "WARNING", "FALLBACK", "MISSING"].includes(v)) return "check-warn";
    return "check-bad";
  }

  async function loadStats() {
    const { response, data } = await jsonFetch("/api/dashboard-stats");
    if (!response.ok) return;

    const decisions = data.decisions || {};
    const boxes = [
      ["Total validations", data.total_validations ?? 0, "▦", ""],
      ["Average confidence", `${data.average_confidence ?? 0}%`, "◉", "blue"],
      ["Verified", decisions["VERIFIED"] ?? 0, "✓", "green"],
      ["Needs confirmation", decisions["NEEDS CUSTOMER CONFIRMATION"] ?? 0, "!", "yellow"]
    ];

    $("#statsSection").innerHTML = boxes.map(([label, value, icon, cls]) => `
      <div class="stat-box">
        <div><span class="num">${escapeHtml(value)}</span><span class="lbl">${escapeHtml(label)}</span></div>
        <span class="stat-icon ${cls}">${icon}</span>
      </div>
    `).join("");
  }

  function percent(value) {
    const n = Number(value);
    return Number.isFinite(n) ? `${(n * 100).toFixed(2)}%` : "—";
  }

  async function loadEvaluation() {
    const box = $("#evaluationBox");
    if (!box) return;

    const { response, data } = await jsonFetch("/api/evaluation/latest");
    if (!response.ok || data.status === "NOT_YET_MEASURED") {
      box.innerHTML = `
        <div class="eval-empty">
          <strong>Evaluation not available yet</strong>
          <span>${escapeHtml(data.message || "Run the evaluation dataset to generate measured results.")}</span>
        </div>`;
      return;
    }

    if (data.status === "ERROR") {
      box.innerHTML = `<div class="eval-empty"><strong>Evaluation error</strong><span>${escapeHtml(data.message)}</span></div>`;
      return;
    }

    const m = data.metrics || {};
    const c = data.correction_metrics || {};
    const cards = [
      ["Dataset", data.dataset_size ?? 0],
      ["Accuracy", percent(m.accuracy)],
      ["Precision", percent(m.precision_macro)],
      ["Recall", percent(m.recall_macro)],
      ["F1", percent(m.f1_macro)],
      ["Correction", percent(c.correction_accuracy)],
      ["Avg time", `${data.average_validation_time_ms ?? "—"} ms`]
    ];

    const labels = ["VERIFIED", "NEEDS CUSTOMER CONFIRMATION", "SUSPICIOUS", "FAKE ADDRESS"];
    const matrix = m.confusion_matrix || {};

    box.innerHTML = `
      <div class="eval-metrics">
        ${cards.map(([label, value]) => `
          <div class="eval-metric"><strong>${escapeHtml(value)}</strong><small>${escapeHtml(label)}</small></div>
        `).join("")}
      </div>
      <div class="eval-grid">
        <div class="eval-panel">
          <h3>Confusion matrix</h3>
          <div style="overflow:auto">
            <table class="data-table">
              <thead><tr><th>Expected / Predicted</th>${labels.map(x => `<th>${escapeHtml(x)}</th>`).join("")}</tr></thead>
              <tbody>
                ${Object.entries(matrix).map(([expected, row]) => `
                  <tr><td>${escapeHtml(expected)}</td>${labels.map(pred => `<td>${row?.[pred] ?? 0}</td>`).join("")}</tr>
                `).join("")}
              </tbody>
            </table>
          </div>
        </div>
        <div class="eval-panel">
          <h3>Measured comparison</h3>
          <div class="baseline-row"><span>Basic baseline</span><strong>${percent(data.baseline?.accuracy)}</strong></div>
          <div class="baseline-row"><span>AddressGuard</span><strong>${percent(m.accuracy)}</strong></div>
          <div class="baseline-row"><span>Before correction</span><strong>${percent(data.before_correction_accuracy ?? m.accuracy)}</strong></div>
          <div class="baseline-row"><span>After labelled corrections</span><strong>${percent(data.after_expected_correction_accuracy)}</strong></div>
          <span class="eval-note">Values are measured from the labelled evaluation dataset; after-correction uses the expected post-correction status.</span>
        </div>
      </div>`;
  }

  function renderParsedAddress(parsed = {}) {
    const fields = [
      ["Name", "name"], ["Phone", "phone"], ["House number", "house_number"],
      ["Flat / unit", "flat_unit"], ["Building", "building"], ["Street / road", "street"],
      ["Landmark", "landmark"], ["Locality", "locality"], ["City", "city"],
      ["District", "district"], ["State", "state"], ["PIN code", "pin_code"]
    ];

    const html = fields.map(([label, key]) => {
      const raw = parsed[key];
      const value = Array.isArray(raw) ? raw.join(", ") : raw;
      if (!value) return "";
      const full = ["building", "landmark"].includes(key) ? " full" : "";
      return `<div class="field-card${full}"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`;
    }).join("");

    $("#parsedAddressGrid").innerHTML = html || `<div class="empty-state">No parsed address data available.</div>`;
  }

  function renderValidationDetails(v) {
    const ex = v.explainability || {};
    const geo = ex.geo_checks || {};
    const parsed = v.parsed_data || {};

    const checks = [
      ["Phone number", parsed.phone ? "VALID" : "MISSING"],
      ["PIN code", parsed.pin_code ? "VALID / CHECKED" : "MISSING"],
      ["City ↔ State", geo.city_state || "INCOMPLETE"],
      ["Locality ↔ City", geo.locality_city || "INCOMPLETE"],
      ["PIN ↔ State", geo.pin_state || "INCOMPLETE"],
      ["PIN ↔ City", geo.pin_city || "INCOMPLETE"]
    ];

    $("#validationDetails").innerHTML = checks.map(([name, value]) => `
      <div class="detail-row">
        <span class="detail-name">${escapeHtml(name)}</span>
        <span class="detail-value ${statusClass(value)}">${escapeHtml(value)}</span>
      </div>
    `).join("");

    const box = $("#geocodingContainer");
    const g = v.geocoding || v.geocoding_result;
    if (box) {
      box.innerHTML = g
        ? `<div class="geo-box"><strong>${escapeHtml(g.status || "Geocoding")}</strong> · ${escapeHtml(g.source || "reference check")}<br>${escapeHtml(g.reason || "")}</div>`
        : "";
    }
  }

  function renderQuickChecks(v) {
    const ex = v.explainability || {};
    const geo = ex.geo_checks || {};
    const checks = [
      ["Phone", v.parsed_data?.phone ? "Valid" : "Missing"],
      ["PIN", v.parsed_data?.pin_code ? "Checked" : "Missing"],
      ["City / State", geo.city_state || "Incomplete"],
      ["Locality / City", geo.locality_city || "Incomplete"],
      ["Geography", ex.geo_issues?.length ? "Conflict" : "Consistent"]
    ];

    $("#quickChecks").innerHTML = checks.map(([label, value]) => {
      const cls = statusClass(value);
      return `
        <div class="quick-check">
          <div class="q-top"><i class="q-dot ${cls === "check-bad" ? "bad" : cls === "check-warn" ? "warn" : ""}"></i>${escapeHtml(label)}</div>
          <small class="${cls}">${escapeHtml(value)}</small>
        </div>`;
    }).join("");
  }

  function renderPipeline(pipeline) {
    const box = $("#pipelineContainer");
    if (!Array.isArray(pipeline) || !pipeline.length) {
      box.innerHTML = `<div class="eval-empty">Pipeline information unavailable.</div>`;
      return;
    }

    box.innerHTML = pipeline.map(stage => {
      const status = String(stage.status || "");
      const lower = status.toLowerCase();
      const cls = lower === "completed" ? "stage-completed" : lower === "failed" ? "stage-failed" : "stage-warning";
      return `
        <div class="pipeline-stage">
          <div class="pipeline-top">
            <strong>${escapeHtml(stage.stage || "Stage")}</strong>
            <span class="stage-status ${cls}">${escapeHtml(status)}</span>
          </div>
          <p>${escapeHtml(stage.details || "")}</p>
        </div>`;
    }).join("");
  }

  function renderExplainability(ex = {}) {
    const box = $("#explainabilityContainer");
    if (!box) return;

    const clean = (text) => String(text || "").replace(/^[✓✗ℹ]\s*/, "");
    const confidence = Array.isArray(ex.confidence_explanation) ? ex.confidence_explanation : [];
    const risk = Array.isArray(ex.risk_explanation) ? ex.risk_explanation : [];
    const decision = Array.isArray(ex.decision_explanation) ? ex.decision_explanation : [];
    const issues = Array.isArray(ex.geo_issues) ? ex.geo_issues : [];
    const geo = ex.geo_checks || {};

    const list = (items, cls) => items.length
      ? `<div class="explain-list">${items.map(x => `<div class="explain-line ${cls}">${escapeHtml(clean(x))}</div>`).join("")}</div>`
      : `<span class="eval-note">None reported.</span>`;

    const pills = Object.entries(geo).map(([key, value]) => {
      const cls = statusClass(value) === "check-good" ? "good" : statusClass(value) === "check-bad" ? "bad" : "";
      return `<span class="geo-pill ${cls}">${escapeHtml(key.replaceAll("_", " "))}: ${escapeHtml(value)}</span>`;
    }).join("");

    box.innerHTML = `
      <div class="explain-card"><div class="explain-title"><span class="explain-icon">◉</span>Confidence evidence</div>${list(confidence, "good")}</div>
      <div class="explain-card"><div class="explain-title"><span class="explain-icon">◆</span>Risk signals</div>${list(risk, risk.length ? "bad" : "info")}</div>
      <div class="explain-card"><div class="explain-title"><span class="explain-icon">✓</span>Decision reasoning</div>${list(decision, decision.length ? "info" : "good")}</div>
      <div class="explain-card">
        <div class="explain-title"><span class="explain-icon">⌖</span>Geographic checks</div>
        <div class="geo-pill-row">${pills || `<span class="eval-note">No geographic checks available.</span>`}</div>
        ${issues.length ? `<div class="explain-list" style="margin-top:9px">${issues.map(x => `<div class="explain-line bad">${escapeHtml(x)}</div>`).join("")}</div>` : ""}
      </div>`;
  }

  function renderCorrections(corrections) {
    const card = $("#correctionsCard");
    const list = $("#correctionsContainer");
    if (!card || !list) return;

    if (!Array.isArray(corrections) || corrections.length === 0) {
      card.classList.add("hidden");
      $("#correctionSummary").innerHTML = "";
      return;
    }

    card.classList.remove("hidden");

    const accepted = Object.values(correctionChoices).filter(x => x === "accept").length;
    const rejected = Object.values(correctionChoices).filter(x => x === "reject").length;

    $("#correctionSummary").innerHTML = `
      <span class="summary-chip">${corrections.length} suggestion${corrections.length === 1 ? "" : "s"}</span>
      <span class="summary-chip">${accepted} accepted</span>
      <span class="summary-chip">${rejected} rejected</span>`;

    list.innerHTML = corrections.map((c, index) => {
      const choice = correctionChoices[index] || "";
      return `
        <div class="correction-card ${choice ? `selected-${choice}` : ""}" data-index="${index}">
          <div class="correction-top">
            <strong class="correction-field">${escapeHtml(c.field || "Address field")}</strong>
            <span class="correction-confidence">${escapeHtml(c.confidence ?? "—")}% confidence</span>
          </div>
          <div class="correction-values">
            <div class="correction-value"><span>Original</span><strong>${escapeHtml(c.original || "")}</strong></div>
            <div class="arrow">→</div>
            <div class="correction-value suggested"><span>Suggested</span><strong>${escapeHtml(c.suggested || "")}</strong></div>
          </div>
          <div class="correction-reason">${escapeHtml(c.reason || "Context-aware address correction")}</div>
          <div class="correction-actions">
            <button class="secondary-btn" data-action="accept">✓ Accept</button>
            <button class="secondary-btn" data-action="reject">× Reject</button>
            <button class="secondary-btn" data-action="edit">Edit</button>
          </div>
        </div>`;
    }).join("");

    $$(".correction-card", list).forEach(cardEl => {
      const index = Number(cardEl.dataset.index);
      $("[data-action=accept]", cardEl).onclick = () => {
        correctionChoices[index] = "accept";
        renderCorrections(corrections);
      };
      $("[data-action=reject]", cardEl).onclick = () => {
        correctionChoices[index] = "reject";
        renderCorrections(corrections);
      };
      $("[data-action=edit]", cardEl).onclick = () => {
        const value = prompt(`Edit the suggested value for ${corrections[index].field}:`, corrections[index].suggested || "");
        if (value == null || !value.trim()) return;
        corrections[index].suggested = value.trim();
        correctionChoices[index] = "accept";
        renderCorrections(corrections);
      };
    });
  }

  function renderReports(validationId) {
    const box = $("#reportLinks");
    if (!box || !validationId) return;
    const base = `/api/report/${encodeURIComponent(validationId)}`;
    box.innerHTML = [
      ["▤", "PDF report", `${base}/pdf`],
      ["▦", "CSV export", `${base}/csv`],
      ["⌗", "QR code", `${base}/qr`],
      ["▥", "Barcode", `${base}/barcode`]
    ].map(([icon, label, url]) =>
      `<a class="report-link" href="${url}" target="_blank" rel="noopener"><span>${icon}</span>${label}</a>`
    ).join("");
  }

  async function loadDeliveryLocation(validationId) {
    const card = $("#deliveryLocationCard");
    const qr = $("#deliveryQr");
    const placeholder = $("#deliveryQrPlaceholder");
    const mapsBtn = $("#googleMapsBtn");
    const status = $("#deliveryLocationStatus");
    if (!card || !validationId) return;

    card.classList.remove("hidden");
    qr?.classList.add("hidden");
    placeholder?.classList.remove("hidden");
    if (status) status.textContent = "Preparing verified navigation location…";
    mapsBtn?.classList.add("hidden");

    const { response, data } = await jsonFetch(`/api/delivery/${encodeURIComponent(validationId)}`);
    if (!response.ok) {
      if (status) status.textContent = data.error || "Delivery location is not available.";
      return;
    }

    if (mapsBtn && data.maps_url) {
      mapsBtn.href = data.maps_url;
      mapsBtn.classList.remove("hidden");
    }
    if (status) {
      status.textContent = data.message || "Verified Google Maps destination ready.";
    }
    if (qr && data.qr_url) {
      qr.src = `${data.qr_url}?t=${Date.now()}`;
      qr.onload = () => {
        qr.classList.remove("hidden");
        placeholder?.classList.add("hidden");
      };
      qr.onerror = () => {
        placeholder.textContent = "QR code could not be loaded.";
      };
    }
  }

  function showFinalAddress(v) {
    const card = $("#finalAddressCard");
    if (!card) return;

    const ready = v.final_address_ready === true;
    const hasAddress = Boolean(String(v.corrected_address || "").trim());
    if (!ready || !hasAddress) {
      card.classList.add("hidden");
      $("#deliveryLocationCard")?.classList.add("hidden");
      return;
    }

    card.classList.remove("hidden");
    $("#originalAddressValue").textContent = v.original_address || v.raw_address || "";
    $("#correctedAddressValue").textContent = v.corrected_address || "";

    const verified = String(v.decision || "").toUpperCase() === "VERIFIED";
    $("#finalAddressTitle").textContent = verified ? "Final verified address" : "Final re-validated address";
    $("#finalAddressStatus").className = `final-status ${verified ? "" : "review"}`;
    $("#finalAddressStatus").textContent =
      `${v.decision || "RE-VALIDATED"} · ${v.confidence ?? "—"}% confidence · ${v.risk_level || "UNKNOWN"} risk`;

    if (verified && v.validation_id) loadDeliveryLocation(v.validation_id);
  }

  function renderResult(v, options = {}) {
    currentValidation = v;

    show("#resultSection");
    if (options.initial) hide("#finalAddressCard");

    $("#confVal").textContent = `${v.confidence ?? "—"}%`;
    $("#riskVal").textContent = v.risk_level || "UNKNOWN";
    $("#riskVal").className = `badge ${badgeClass("risk", v.risk_level)}`;
    $("#decisionVal").textContent = v.decision || "UNKNOWN";
    $("#decisionVal").className = `badge ${badgeClass("decision", v.decision)}`;
    $("#resultId").textContent = v.validation_id ? `Validation ID: ${v.validation_id}` : "";

    renderQuickChecks(v);
    renderParsedAddress(v.parsed_data || {});
    renderValidationDetails(v);
    renderCorrections(v.corrections || []);
    renderExplainability(v.explainability || {});
    renderPipeline(v.pipeline || []);
    renderReports(v.validation_id);

    if (v.final_address_ready === true) showFinalAddress(v);
    else hide("#finalAddressCard");
  }

  async function revalidate() {
    if (!currentValidation) {
      alert("Please run validation first.");
      return;
    }

    const corrections = currentValidation.corrections || [];
    const accepted = [];
    const rejected = [];

    corrections.forEach((c, index) => {
      const item = {
        field: c.field,
        original: c.original,
        suggested: c.suggested
      };
      if (correctionChoices[index] === "accept") accepted.push(item);
      if (correctionChoices[index] === "reject") rejected.push(item);
    });

    if (!accepted.length && !rejected.length) {
      alert("Please Accept, Reject, or Edit at least one correction.");
      return;
    }

    const button = $("#applyBtn");
    button.disabled = true;
    button.textContent = "Re-validating...";

    try {
      const { response, data } = await jsonFetch(
        `/api/revalidate/${encodeURIComponent(currentValidation.validation_id)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ accepted, rejected })
        }
      );

      if (!response.ok) {
        alert(data.error || "Re-validation failed.");
        return;
      }

      correctionChoices = {};
      renderResult(data, { revalidated: true });
      await loadStats();
      await loadEvaluation();

      setTimeout(() => {
        $("#finalAddressCard")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 150);
    } finally {
      button.disabled = false;
      button.textContent = "↻ Apply decisions & re-validate";
    }
  }

  $("#acceptAllBtn")?.addEventListener("click", () => {
    (currentValidation?.corrections || []).forEach((_, index) => {
      correctionChoices[index] = "accept";
    });
    renderCorrections(currentValidation?.corrections || []);
  });

  $("#rejectAllBtn")?.addEventListener("click", () => {
    (currentValidation?.corrections || []).forEach((_, index) => {
      correctionChoices[index] = "reject";
    });
    renderCorrections(currentValidation?.corrections || []);
  });

  $("#applyBtn")?.addEventListener("click", revalidate);

  $("#sampleBtn")?.addEventListener("click", async () => {
    const { response, data } = await jsonFetch("/api/samples");
    if (response.ok && data.samples?.length) {
      $("#addressInput").value = data.samples[Math.floor(Math.random() * data.samples.length)];
    }
  });

  $("#runBtn")?.addEventListener("click", async () => {
    const raw = $("#addressInput").value.trim();
    if (!raw) {
      alert("Please enter an address first.");
      return;
    }

    const button = $("#runBtn");
    button.disabled = true;
    button.textContent = "Validating...";
    currentValidation = null;
    correctionChoices = {};
    hide("#finalAddressCard");
    hide("#deliveryLocationCard");

    try {
      const { response, data } = await jsonFetch("/api/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_address: raw })
      });

      if (!response.ok) {
        alert(data.error || "Validation failed.");
        return;
      }

      renderResult(data, { initial: true });
      setTimeout(() => {
        $("#resultSection")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 100);
      await loadStats();
    } finally {
      button.disabled = false;
      button.textContent = "▶ Run validation";
    }
  });

  async function loadHistory() {
    const { response, data } = await jsonFetch("/api/history");
    if (!response.ok) return;

    const rows = data.history || [];
    $("#historyList").innerHTML = rows.length
      ? rows.map(v => `
        <div class="history-item">
          <div>
            <strong>${escapeHtml(v.validation_id || "")}</strong>
            <span class="h-addr">${escapeHtml(v.raw_address || "")}</span>
          </div>
          <div class="history-right">
            ${escapeHtml(v.confidence ?? "—")}%<br>
            <span class="badge ${badgeClass("decision", v.decision)}">${escapeHtml(v.decision || "")}</span>
          </div>
        </div>`).join("")
      : `<div class="eval-empty">No validations yet.</div>`;
  }

  function switchView(history) {
    $("#navDashboard")?.classList.toggle("active", !history);
    $("#navHistory")?.classList.toggle("active", history);
    $("#historySection")?.classList.toggle("hidden", !history);
    $("#resultSection")?.classList.toggle("hidden", history);
    if (history) loadHistory();
  }

  $("#navDashboard")?.addEventListener("click", (event) => {
    event.preventDefault();
    switchView(false);
  });

  $("#navHistory")?.addEventListener("click", (event) => {
    event.preventDefault();
    switchView(true);
  });

  $("#logoutBtn")?.addEventListener("click", async (event) => {
    event.preventDefault();
    await fetch("/api/auth/logout", { method: "POST" });
    location.href = "/";
  });

  loadStats();
  loadEvaluation();
}
