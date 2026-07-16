// app.js
// ---------------------------------------------------------------
// Handles: login/auth state, forced-camera capture, HTML5 Canvas
// pre-processing (auto-orient + sharpen/contrast), claim submission,
// pipeline step animation, and result rendering.
// ---------------------------------------------------------------

const API_BASE_URL = window.CLAIM_API_BASE_URL || "http://localhost:8000";

// ----- Element refs -----
const loginScreen      = document.getElementById("login-screen");
const dashboardScreen  = document.getElementById("dashboard-screen");
const loginForm        = document.getElementById("login-form");

const displayUserName  = document.getElementById("display-user-name");
const displayVehicleReg= document.getElementById("display-vehicle-reg");
const displayAvatar    = document.getElementById("display-avatar");

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

// Pipeline steps (in order)
const PIPELINE_STEPS = ["step-vision","step-fraud","step-cost","step-policy","step-decision","step-summary"];

// ----- App state -----
let session = null;           // { userName, vehicleReg, insuranceType, policyId }
let processedImageBlob = null;// Blob produced after canvas pre-processing
let pipelineTimer = null;     // interval for step animation

// ===================== LOGIN =====================
loginForm.addEventListener("submit", (event) => {
  event.preventDefault();

  session = {
    userName:      document.getElementById("input-user-name").value.trim(),
    vehicleReg:    document.getElementById("input-vehicle-reg").value.trim(),
    insuranceType: document.getElementById("input-insurance-type").value,
    policyId:      document.getElementById("input-policy-id").value.trim(),
  };

  displayUserName.textContent   = session.userName;
  displayVehicleReg.textContent = session.vehicleReg;
  displayAvatar.textContent     = session.userName.charAt(0).toUpperCase();

  loginScreen.classList.add("hidden");
  dashboardScreen.classList.remove("hidden");
});

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

/**
 * Draws the captured image onto a canvas, auto-orients it, and applies
 * a light contrast/saturation boost before re-exporting as JPEG.
 */
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
  // Reset all steps
  PIPELINE_STEPS.forEach((id) => {
    const el = document.getElementById(id);
    el.classList.remove("active", "done");
  });
  document.getElementById(PIPELINE_STEPS[0]).classList.add("active");

  pipelineTimer = setInterval(() => {
    const currentEl = document.getElementById(PIPELINE_STEPS[current]);
    currentEl.classList.remove("active");
    currentEl.classList.add("done");

    current++;
    if (current < PIPELINE_STEPS.length) {
      document.getElementById(PIPELINE_STEPS[current]).classList.add("active");
    } else {
      clearInterval(pipelineTimer);
    }
  }, 900);
}

function stopPipelineAnimation() {
  if (pipelineTimer) {
    clearInterval(pipelineTimer);
    pipelineTimer = null;
  }
  // Mark all done
  PIPELINE_STEPS.forEach((id) => {
    const el = document.getElementById(id);
    el.classList.remove("active");
    el.classList.add("done");
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
  formData.append("user_name",         session.userName);
  formData.append("vehicle_reg_number",session.vehicleReg);
  formData.append("insurance_type",    session.insuranceType);
  formData.append("policy_id",         session.policyId);
  formData.append("image",             processedImageBlob, "claim_photo.jpg");

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
    await sleep(400); // brief pause so user sees final step
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
    APPROVED:                  { label: "Approved",       cls: "status-approved" },
    REJECTED:                  { label: "Rejected",       cls: "status-rejected" },
    FLAGGED_FOR_MANUAL_REVIEW: { label: "Manual Review",  cls: "status-flagged"  },
  };
  const statusInfo = statusMap[result.decision_result.status] || { label: result.decision_result.status, cls: "status-default" };
  statusBadge.textContent = statusInfo.label;
  statusBadge.className   = `status-badge ${statusInfo.cls}`;

  // Claim ID & timestamp
  document.getElementById("claim-id-line").textContent =
    `${result.claim_id} · ${new Date(result.submitted_at).toLocaleString()}`;

  // Summary
  document.getElementById("summary-text").textContent = result.summary_text;

  // Stats
  document.getElementById("stat-subtotal").textContent = `$${result.cost_result.subtotal}`;
  document.getElementById("stat-payout").textContent   = `$${result.policy_result.final_payout_estimate}`;

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
  const fraudEl  = document.getElementById("fraud-summary");
  const fraud     = result.fraud_result;
  fraudEl.textContent = fraud.fraud_flag
    ? `⚠ Fraud flag raised: ${fraud.exif_check?.reason || ""} ${fraud.duplicate_check?.is_duplicate ? "Duplicate image detected." : ""}`.trim()
    : "✓ No fraud signals detected. EXIF metadata and duplicate-image checks passed.";
  fraudEl.style.color = fraud.fraud_flag ? "var(--amber)" : "var(--text-muted)";
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
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
