// app.js
// ---------------------------------------------------------------
// Handles navigation, database-validated customer login,
// insurer vehicle registration with color and auto-tier classification,
// camera capture/preprocessing, and claim submission.
// ---------------------------------------------------------------

const API_BASE_URL = window.CLAIM_API_BASE_URL || "http://localhost:8000";

// ----- Navigation -----
function showScreen(screenId) {
  const screens = ["home-screen", "customer-login-screen", "insurer-screen", "dashboard-screen"];
  screens.forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      if (id === screenId) {
        el.classList.remove("hidden");
      } else {
        el.classList.add("hidden");
      }
    }
  });

  // If entering insurer screen, reload the vehicle list
  if (screenId === "insurer-screen") {
    loadVehicles();
  }
}

// ----- Element refs -----
const loginForm        = document.getElementById("login-form");
const insurerForm      = document.getElementById("insurer-form");

const displayUserName  = document.getElementById("display-user-name");
const displayVehicleReg= document.getElementById("display-vehicle-reg");
const displayAvatar    = document.getElementById("display-avatar");
const displayTierBadge = document.getElementById("display-tier-badge");

const captureZone      = document.getElementById("capture-zone");
const cameraInput      = document.getElementById("camera-input");
const preprocessCanvas = document.getElementById("preprocess-canvas");
const previewWrap      = document.getElementById("preview-wrap");
const previewImage     = document.getElementById("preview-image");
const btnRetake        = document.getElementById("btn-retake");
const btnSubmitClaim   = document.getElementById("btn-submit-claim");
const uploadCard       = document.getElementById("upload-card");

const processingCard   = document.getElementById("processing-card");
const errorCard        = document.getElementById("error-card");
const errorMessage     = document.getElementById("error-message");
const resultCard       = document.getElementById("result-card");
const btnNewClaim      = document.getElementById("btn-new-claim");

const PIPELINE_STEPS = ["step-vision","step-fraud","step-cost","step-policy","step-decision","step-summary"];

// ----- App state -----
let session = null;           // full session object from API
let processedImageBlob = null;
let pipelineTimer = null;

// ===================== CUSTOMER LOGIN =====================
loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const vehicleReg     = document.getElementById("input-vehicle-reg").value.trim();
  const customerNumber = document.getElementById("input-customer-number").value.trim();
  const loginError     = document.getElementById("login-error");
  const btnLoginText   = document.getElementById("btn-login-text");

  if (!vehicleReg || !customerNumber) {
    showFormError(loginError, "Please fill in both fields.");
    return;
  }

  btnLoginText.textContent = "Verifying...";
  document.getElementById("btn-login").disabled = true;
  loginError.classList.add("hidden");

  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vehicle_reg_number: vehicleReg, customer_number: customerNumber }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || "Authentication failed.");
    }

    const data = await response.json();
    session = {
      customerName:  data.customer_name || vehicleReg,
      vehicleReg:    data.vehicle_reg_number,
      insuranceType: data.insurance_type,
      policyId:      data.policy_id,
      make:          data.make,
      model:         data.model,
      year:          data.year,
      color:         data.color,
      priceTier:     data.price_tier,
    };

    populateDashboard();
    showScreen("dashboard-screen");

  } catch (err) {
    showFormError(loginError, err.message || "Login failed. Please try again.");
  } finally {
    btnLoginText.textContent = "Continue to Dashboard";
    document.getElementById("btn-login").disabled = false;
  }
});

function populateDashboard() {
  displayUserName.textContent   = session.customerName;
  displayVehicleReg.textContent = `${session.make} ${session.model} ${session.year} · ${session.vehicleReg} (${session.color || "No color specified"})`;
  displayAvatar.textContent     = session.customerName.charAt(0).toUpperCase();

  // Tier badge
  const tierColors = { Low: "tier-low", Mid: "tier-mid", High: "tier-high" };
  displayTierBadge.textContent  = `${session.priceTier} Tier`;
  displayTierBadge.className    = `tier-badge ${tierColors[session.priceTier] || "tier-mid"}`;
  displayTierBadge.classList.remove("hidden");
}

// ===================== INSURER REGISTRATION =====================
insurerForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const insurerError   = document.getElementById("insurer-error");
  const insurerSuccess = document.getElementById("insurer-success");
  const btnText        = document.getElementById("btn-insurer-text");

  insurerError.classList.add("hidden");
  insurerSuccess.classList.add("hidden");
  btnText.textContent = "Classifying vehicle...";
  document.getElementById("btn-insurer-register").disabled = true;

  const payload = {
    customer_name:       document.getElementById("ins-customer-name").value.trim(),
    customer_number:     document.getElementById("ins-customer-number").value.trim().toUpperCase(),
    vehicle_reg_number:  document.getElementById("ins-vehicle-reg").value.trim(),
    color:               document.getElementById("ins-color").value.trim(),
    make:                document.getElementById("ins-make").value.trim(),
    model:               document.getElementById("ins-model").value.trim(),
    year:                parseInt(document.getElementById("ins-year").value, 10),
    policy_id:           document.getElementById("ins-policy-id").value.trim(),
    insurance_type:      document.getElementById("ins-insurance-type").value,
  };

  try {
    const response = await fetch(`${API_BASE_URL}/api/insurer/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || "Registration failed.");
    }

    const data = await response.json();
    const tierEmoji = { Low: "🟢", Mid: "🟡", High: "🔴" }[data.price_tier] || "⚪";

    showFormSuccess(
      insurerSuccess,
      `✓ Registered! Classified as ${tierEmoji} ${data.price_tier} Tier. Reg: ${data.vehicle_reg_number}`
    );

    insurerForm.reset();
    loadVehicles(); // refresh vehicle list
  } catch (err) {
    showFormError(insurerError, err.message);
  } finally {
    btnText.textContent = "Register & Classify Vehicle";
    document.getElementById("btn-insurer-register").disabled = false;
  }
});

// ===================== VEHICLE LIST FOR INSURER =====================
async function loadVehicles() {
  const container = document.getElementById("vehicle-list");
  if (!container) return;

  try {
    const response = await fetch(`${API_BASE_URL}/api/insurer/vehicles`);
    if (!response.ok) throw new Error("Failed to fetch vehicles.");
    const data = await response.json();

    container.innerHTML = "";
    if (data.vehicles.length === 0) {
      container.innerHTML = `<p class="vehicle-list-empty">No vehicles registered yet.</p>`;
      return;
    }

    data.vehicles.forEach((v) => {
      const item = document.createElement("div");
      item.className = "vehicle-list-item";
      
      const tierClass = { Low: "tier-low", Mid: "tier-mid", High: "tier-high" }[v.price_tier] || "tier-mid";

      item.innerHTML = `
        <div class="vehicle-list-info">
          <div class="vehicle-list-main">${v.year} ${v.make} ${v.model} <span class="vehicle-list-color">${v.color || 'No Color'}</span></div>
          <div class="vehicle-list-sub">Reg: <strong>${v.vehicle_reg_number}</strong> &bull; Cust: ${v.customer_name} (${v.customer_number})</div>
        </div>
        <div style="display:flex; flex-direction:column; align-items:flex-end; gap:4px;">
          <span class="tier-badge ${tierClass}">${v.price_tier}</span>
          <span class="vehicle-list-policy">${v.policy_id}</span>
        </div>
      `;
      container.appendChild(item);
    });
  } catch (err) {
    container.innerHTML = `<p class="vehicle-list-error">Error loading vehicles: ${err.message}</p>`;
  }
}

// ===================== CAMERA CAPTURE =====================
captureZone.addEventListener("click", () => cameraInput.click());
captureZone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") cameraInput.click(); });

cameraInput.addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;

  try {
    const blob = await preprocessImage(file);
    processedImageBlob = blob;
    previewImage.src = URL.createObjectURL(blob);
    captureZone.classList.add("hidden");
    previewWrap.classList.remove("hidden");
  } catch (err) {
    console.error("Pre-processing failed:", err);
    showError("Could not process the captured photo. Please try again.");
  }
});

btnRetake.addEventListener("click", () => {
  processedImageBlob = null;
  cameraInput.value  = "";
  previewWrap.classList.add("hidden");
  captureZone.classList.remove("hidden");
});

async function preprocessImage(file) {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const canvas = preprocessCanvas;
  const ctx    = canvas.getContext("2d");

  canvas.width  = bitmap.width;
  canvas.height = bitmap.height;

  ctx.filter = "contrast(1.12) saturate(1.08) brightness(1.02)";
  ctx.drawImage(bitmap, 0, 0);
  ctx.filter = "none";

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("Canvas export failed"))),
      "image/jpeg",
      0.92
    );
  });
}

// ===================== PIPELINE STEP ANIMATION =====================
function startPipelineAnimation() {
  let current = 0;
  PIPELINE_STEPS.forEach((id) => {
    const el = document.getElementById(id);
    el.classList.remove("active", "done");
  });
  document.getElementById(PIPELINE_STEPS[0]).classList.add("active");

  pipelineTimer = setInterval(() => {
    const currentEl = document.getElementById(PIPELINE_STEPS[current]);
    if (currentEl) {
      currentEl.classList.remove("active");
      currentEl.classList.add("done");
    }

    current++;
    if (current < PIPELINE_STEPS.length) {
      const nextEl = document.getElementById(PIPELINE_STEPS[current]);
      if (nextEl) nextEl.classList.add("active");
    } else {
      clearInterval(pipelineTimer);
    }
  }, 900);
}

function stopPipelineAnimation() {
  if (pipelineTimer) { clearInterval(pipelineTimer); pipelineTimer = null; }
  PIPELINE_STEPS.forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.classList.remove("active");
      el.classList.add("done");
    }
  });
}

// ===================== SUBMIT CLAIM =====================
btnSubmitClaim.addEventListener("click", async () => {
  if (!processedImageBlob || !session) return;

  uploadCard.classList.add("hidden");
  errorCard.classList.add("hidden");
  resultCard.classList.add("hidden");
  processingCard.classList.remove("hidden");
  startPipelineAnimation();

  const formData = new FormData();
  formData.append("user_name",          session.customerName);
  formData.append("vehicle_reg_number", session.vehicleReg);
  formData.append("insurance_type",     session.insuranceType);
  formData.append("policy_id",          session.policyId);
  formData.append("image",              processedImageBlob, "claim_photo.jpg");

  try {
    const response = await fetch(`${API_BASE_URL}/api/claims`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errBody = await response.json().catch(() => ({}));
      throw new Error(errBody.detail || `Server returned ${response.status}`);
    }

    const result = await response.json();
    stopPipelineAnimation();
    await sleep(400);
    renderResult(result);
  } catch (err) {
    console.error("Claim submission failed:", err);
    stopPipelineAnimation();
    processingCard.classList.add("hidden");
    showError(`Submission failed: ${err.message}. Please try again.`);
    uploadCard.classList.remove("hidden");
  }
});

// ===================== RENDER RESULT =====================
function renderResult(result) {
  processingCard.classList.add("hidden");
  resultCard.classList.remove("hidden");

  // Status badge
  const statusBadge = document.getElementById("status-badge");
  const statusMap = {
    APPROVED:                  { label: "Approved",      cls: "status-approved" },
    REJECTED:                  { label: "Rejected",      cls: "status-rejected" },
    FLAGGED_FOR_MANUAL_REVIEW: { label: "Manual Review", cls: "status-flagged"  },
  };
  const statusInfo = statusMap[result.decision_result.status] || { label: result.decision_result.status, cls: "status-default" };
  statusBadge.textContent = statusInfo.label;
  statusBadge.className   = `status-badge ${statusInfo.cls}`;

  // Claim ID & timestamp
  document.getElementById("claim-id-line").textContent =
    `${result.claim_id} · ${new Date(result.submitted_at).toLocaleString()}`;

  // Summary
  document.getElementById("summary-text").textContent = result.summary_text;

  // Stats — show tier info too
  const tier = result.cost_result?.price_tier || session?.priceTier || "";
  const multiplier = result.cost_result?.tier_multiplier || 1;
  const tierLabel = tier ? ` (${tier} Tier ×${multiplier})` : "";
  document.getElementById("stat-subtotal").textContent = `$${result.cost_result.subtotal}${tierLabel}`;
  document.getElementById("stat-payout").textContent   = `$${result.policy_result.final_payout_estimate}`;

  // Color verification box display
  const colorBox = document.getElementById("color-result-box");
  const colRes = result.color_result;
  if (colorBox) {
    if (colRes) {
      colorBox.classList.remove("hidden");
      const matchText = colRes.match 
        ? `<span style="color:var(--green)">✓ MATCHED</span>` 
        : `<span style="color:var(--red); font-weight:700;">✗ MISMATCH</span>`;
      
      const badgeClass = colRes.match ? "alert-success" : (colRes.confidence === "high" ? "alert-error" : "alert-warning");
      
      colorBox.className = `color-result-box ${badgeClass}`;
      colorBox.innerHTML = `
        <div style="font-weight:600; margin-bottom: 4px;">Car Color Verification: ${matchText}</div>
        <div style="font-size:12.5px; color:var(--text-muted);">
          Registered: <strong>${colRes.registered_color}</strong> &bull; 
          AI Detected: <strong>${colRes.detected_color}</strong> (Confidence: ${colRes.confidence})
        </div>
        ${colRes.notes ? `<div style="font-size:11.5px; margin-top:4px; opacity:0.85;">${colRes.notes}</div>` : ''}
      `;
    } else {
      colorBox.classList.add("hidden");
    }
  }

  // Damage list
  const damageList = document.getElementById("damage-list");
  damageList.innerHTML = "";
  result.cost_result.line_items.forEach((item, i) => {
    const row = document.createElement("div");
    row.className = "damage-row";
    row.style.animationDelay = `${i * 60}ms`;
    row.innerHTML = `
      <div class="damage-row-left">
        <div>${item.part_name} &mdash; ${item.damage_type}</div>
        <div class="damage-row-sev">Severity ${item.severity_score}/5</div>
      </div>
      <div class="damage-row-cost">$${item.estimated_cost}</div>
    `;
    damageList.appendChild(row);
  });

  // Fraud summary
  const fraudEl = document.getElementById("fraud-summary");
  const fraud   = result.fraud_result;
  let fraudMessage = "";
  if (fraud.fraud_flag) {
    fraudMessage = `⚠ Fraud flag raised: ${fraud.exif_check?.reason || ""} ${fraud.duplicate_check?.is_duplicate ? "Duplicate image detected." : ""}`.trim();
  } else {
    fraudMessage = "✓ No fraud signals detected. EXIF metadata and duplicate-image checks passed.";
  }
  
  if (colRes && !colRes.match) {
    fraudMessage += `\n⚠ Vehicle Color Mismatch: registered color is '${colRes.registered_color}', but the image shows '${colRes.detected_color}'.`;
  }

  fraudEl.textContent = fraudMessage;
  fraudEl.style.color = (fraud.fraud_flag || (colRes && !colRes.match)) ? "var(--amber)" : "var(--text-muted)";
}

// ===================== RESET =====================
btnNewClaim.addEventListener("click", () => {
  processedImageBlob = null;
  cameraInput.value  = "";
  resultCard.classList.add("hidden");
  previewWrap.classList.add("hidden");
  captureZone.classList.remove("hidden");
  uploadCard.classList.remove("hidden");
});

// ===================== HELPERS =====================
function showError(message) {
  errorMessage.textContent = message;
  errorCard.classList.remove("hidden");
}

function showFormError(el, message) {
  el.textContent = message;
  el.classList.remove("hidden");
}

function showFormSuccess(el, message) {
  el.textContent = message;
  el.classList.remove("hidden");
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
