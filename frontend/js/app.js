// Application State
const state = {
  systemStatus: null,
  readers: [],
  currentReaderId: "nu_1",
  currentReader: null,
  turns: [],
  activeRecordingTurnId: null, // e.g. "D01_02"
  isVerifying: false,
};

// Format seconds into MM:SS
function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

// Initialize Application
document.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadSystemStatus();
    await loadReaders();
    await selectReader("nu_1");
  } catch (err) {
    console.error("Initialization error:", err);
    showToast(err.message, "error");
  }

  // Event Listeners
  document.getElementById("reader-select").addEventListener("change", (e) => {
    selectReader(e.target.value);
  });

  document.getElementById("btn-confirm-all").addEventListener("click", handleConfirmAndVerify);
  document.getElementById("btn-reset-reader").addEventListener("click", handleResetReader);
});

// Load System Status
async function loadSystemStatus() {
  try {
    const data = await API.getSystemStatus();
    state.systemStatus = data;

    // MongoDB Pill
    const mongoPill = document.getElementById("status-mongo");
    if (data.mongodb.connected) {
      mongoPill.className = "badge bg-emerald-100 text-emerald-800 border border-emerald-300";
      mongoPill.innerHTML = `● MongoDB: Đã kết nối (${data.mongodb.scripts_db} / ${data.mongodb.recordings_db})`;
    } else {
      mongoPill.className = "badge bg-amber-100 text-amber-800 border border-amber-300";
      mongoPill.innerHTML = `● MongoDB: Chưa kết nối (Chế độ cục bộ)`;
    }

    // OpenAI Whisper Pill
    const whisperPill = document.getElementById("status-whisper");
    if (data.openai.configured) {
      whisperPill.className = "badge bg-blue-100 text-blue-800 border border-blue-300";
      whisperPill.innerHTML = `● OpenAI Whisper API: Sẵn sàng (${data.openai.model})`;
    } else {
      whisperPill.className = "badge bg-rose-100 text-rose-800 border border-rose-300";
      whisperPill.innerHTML = `● OpenAI API: Chưa có API Key (.env)`;
    }
  } catch (e) {
    console.warn("Could not fetch system status:", e);
  }
}

// Load Readers
async function loadReaders() {
  const readers = await API.getReaders();
  state.readers = readers;

  const select = document.getElementById("reader-select");
  select.innerHTML = "";

  readers.forEach((r) => {
    const opt = document.createElement("option");
    opt.value = r.id;
    opt.textContent = `${r.name} - ${r.role_description} (${r.completed_turns}/${r.total_turns} hoàn thành)`;
    select.appendChild(opt);
  });
}

// Select a Reader
async function selectReader(readerId) {
  state.currentReaderId = readerId;
  const select = document.getElementById("reader-select");
  select.value = readerId;

  document.getElementById("turns-container").innerHTML = `
    <div class="p-12 text-center text-slate-500">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mb-4"></div>
      <p>Đang tải danh sách câu thoại...</p>
    </div>
  `;

  try {
    const data = await API.getReaderTurns(readerId);
    state.currentReader = data;
    state.turns = data.turns.map((t) => ({
      ...t,
      id: `${t.dialogue_id}_${t.turn_idx}`,
      localAudioBlob: null,
      localAudioUrl: null,
    }));

    renderReaderInfo();
    renderTurns();
    updateProgressSummary();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// Render Reader Information Banner
function renderReaderInfo() {
  const r = state.currentReader;
  document.getElementById("reader-title").textContent = r.name;
  document.getElementById("reader-desc").textContent = r.role_description;
  document.getElementById("reader-meta-gender").textContent = r.gender === "f" ? "Nữ" : "Nam";
  document.getElementById("reader-meta-region").textContent =
    r.region === "bac" ? "Bắc" : r.region === "nam" ? "Nam" : "Trung";

  // ZIP download button link
  const btnZip = document.getElementById("btn-download-zip");
  btnZip.href = API.getZipExportUrl(state.currentReaderId);
}

// Update Progress Summary
function updateProgressSummary() {
  const total = state.turns.length;
  const passed = state.turns.filter((t) => t.status === "passed").length;
  const recorded = state.turns.filter((t) => t.status === "passed" || t.localAudioBlob).length;

  const percent = total > 0 ? Math.round((passed / total) * 100) : 0;
  document.getElementById("progress-bar").style.width = `${percent}%`;
  document.getElementById("progress-text").textContent = `${passed}/${total} đoạn đạt chuẩn (${percent}%)`;

  const btnConfirm = document.getElementById("btn-confirm-all");
  const bannerSuccess = document.getElementById("all-completed-banner");

  if (passed === total && total > 0) {
    btnConfirm.classList.add("hidden");
    bannerSuccess.classList.remove("hidden");
  } else {
    btnConfirm.classList.remove("hidden");
    bannerSuccess.classList.add("hidden");
    btnConfirm.innerHTML = `
      <i data-lucide="check-circle" class="w-5 h-5 mr-2"></i>
      Xác nhận & Kiểm tra toàn bộ (${recorded}/${total} đã thu)
    `;
    if (window.lucide) lucide.createIcons();
  }
}

// Render Turns Cards
function renderTurns() {
  const container = document.getElementById("turns-container");
  container.innerHTML = "";

  state.turns.forEach((turn, idx) => {
    const card = document.createElement("div");
    card.id = `turn-card-${turn.id}`;
    card.className = `turn-card bg-white rounded-xl border-2 p-5 shadow-sm ${getCardBorderClass(turn)}`;

    card.innerHTML = `
      <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div class="flex items-center space-x-2">
          <span class="badge bg-indigo-100 text-indigo-800 border border-indigo-200">
            [${turn.dialogue_id}] Lượt #${turn.turn_idx.toString().padStart(2, "0")}
          </span>
          <span class="badge ${turn.role === "agent" ? "bg-amber-100 text-amber-800" : "bg-cyan-100 text-cyan-800"}">
            ${turn.role === "agent" ? "Tư vấn viên (Agent)" : "Khách hàng (Customer)"}
          </span>
          <span class="badge bg-slate-100 text-slate-700">
            ${turn.gender === "f" ? "Nữ" : "Nam"} · ${turn.region.toUpperCase()}
          </span>
        </div>
        <div class="flex items-center space-x-2">
          <span class="text-xs font-mono text-slate-500 bg-slate-50 px-2 py-1 rounded border border-slate-200">
            ${turn.filename}
          </span>
          ${getStatusBadgeHtml(turn)}
        </div>
      </div>

      <!-- Transcript Ground Truth -->
      <div class="mb-4 bg-slate-50 rounded-lg p-4 border border-slate-200">
        <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
          Nội dung cần đọc chuẩn xác:
        </div>
        <p class="text-lg font-medium text-slate-900 leading-relaxed select-all">
          "${turn.text}"
        </p>
      </div>

      <!-- Evaluation Result Details (if evaluated) -->
      ${renderEvaluationDetails(turn)}

      <!-- Audio Recording & Playback Section -->
      <div class="mt-4 pt-4 border-t border-slate-100">
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
          
          <!-- Waveform Canvas & Timer Box -->
          <div class="flex-1">
            <canvas id="canvas-${turn.id}" class="waveform-canvas" width="450" height="64"></canvas>
            <div class="flex justify-between items-center text-xs text-slate-500 mt-1.5">
              <span id="rec-status-${turn.id}">
                ${turn.locked ? "✓ Bản thu đã được lưu trữ an toàn" : "Sẵn sàng thu âm"}
              </span>
              <span id="timer-${turn.id}" class="font-mono font-semibold text-slate-700">
                ${turn.duration ? formatTime(turn.duration) : "00:00"}
              </span>
            </div>
          </div>

          <!-- Controls -->
          <div class="flex items-center space-x-3" id="controls-${turn.id}">
            ${renderControlsHtml(turn)}
          </div>

        </div>

        <!-- Audio Player Preview -->
        <div id="player-container-${turn.id}" class="mt-3 ${turn.audio_url || turn.localAudioUrl ? "" : "hidden"}">
          <audio id="audio-${turn.id}" controls class="w-full h-10 rounded">
            <source src="${turn.audio_url || turn.localAudioUrl || ""}" type="audio/mpeg">
          </audio>
        </div>
      </div>
    `;

    container.appendChild(card);

    // Draw initial idle line on canvas
    setTimeout(() => {
      const canvas = document.getElementById(`canvas-${turn.id}`);
      if (canvas && window.audioRecorder) {
        window.audioRecorder._drawIdleWaveform(canvas);
      }
    }, 10);
  });

  if (window.lucide) lucide.createIcons();
}

function getCardBorderClass(turn) {
  if (turn.locked || turn.status === "passed") return "locked";
  if (turn.status === "failed") return "failed";
  if (turn.localAudioBlob) return "has-audio";
  return "border-slate-200";
}

function getStatusBadgeHtml(turn) {
  if (turn.locked || turn.status === "passed") {
    return `<span class="badge bg-emerald-500 text-white"><i data-lucide="check" class="w-3 h-3 mr-1"></i> Đạt chuẩn (Locked)</span>`;
  }
  if (turn.status === "failed") {
    return `<span class="badge bg-rose-500 text-white"><i data-lucide="alert-circle" class="w-3 h-3 mr-1"></i> Chưa đạt - Cần thu lại</span>`;
  }
  if (turn.localAudioBlob) {
    return `<span class="badge bg-blue-500 text-white"><i data-lucide="clock" class="w-3 h-3 mr-1"></i> Đã thu (Chờ xác nhận)</span>`;
  }
  return `<span class="badge bg-slate-200 text-slate-700">Chưa thu âm</span>`;
}

function renderEvaluationDetails(turn) {
  if (turn.status === "passed") {
    const timeStr = turn.recorded_time
      ? new Date(turn.recorded_time).toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit", day: "2-digit", month: "2-digit", year: "numeric" })
      : "";
    return `
      <div class="mb-3 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs space-y-1">
        <div class="flex flex-wrap items-center gap-4 text-emerald-900 font-medium">
          <span>✓ RapidFuzz Score: <strong>${turn.score_percent || (turn.score * 100).toFixed(1)}%</strong> (≥ 85%)</span>
          <span>✓ Tốc độ WPM: <strong>${turn.wpm} WPM</strong> (≥ 4.0)</span>
          <span>⏱ Thời lượng: <strong>${turn.duration}s</strong></span>
          ${timeStr ? `<span>📅 Thời điểm lưu: <strong class="text-slate-800">${timeStr}</strong></span>` : ""}
        </div>
        ${
          turn.asr_transcript
            ? `<div class="text-slate-600 mt-1">ASR Whisper nhận dạng: <span class="italic text-slate-800">"${turn.asr_transcript}"</span></div>`
            : ""
        }
      </div>
    `;
  }

  if (turn.status === "failed") {
    return `
      <div class="mb-3 p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs space-y-1">
        <div class="font-bold text-rose-800 flex items-center">
          <i data-lucide="x-circle" class="w-4 h-4 mr-1 text-rose-600"></i> Các lỗi chưa đạt yêu cầu:
        </div>
        <ul class="list-disc list-inside text-rose-700 pl-2">
          ${(turn.reasons || []).map((r) => `<li>${r}</li>`).join("")}
        </ul>
        <div class="flex gap-4 text-slate-600 mt-1">
          <span>Điểm: <strong>${(turn.score * 100).toFixed(1)}%</strong></span>
          <span>WPM: <strong>${turn.wpm}</strong></span>
          <span>Thời lượng: <strong>${turn.duration}s</strong></span>
        </div>
      </div>
    `;
  }

  return "";
}

function renderControlsHtml(turn) {
  if (turn.locked) {
    return `
      <span class="inline-flex items-center px-4 py-2 rounded-lg bg-emerald-100 text-emerald-800 text-sm font-medium">
        <i data-lucide="lock" class="w-4 h-4 mr-1.5"></i> Đã hoàn tất & Đã khóa
      </span>
    `;
  }

  const isCurrentRecording = state.activeRecordingTurnId === turn.id;

  if (isCurrentRecording) {
    return `
      <button onclick="stopRecordingTurn('${turn.id}')"
        class="inline-flex items-center px-5 py-2.5 rounded-lg bg-rose-600 text-white hover:bg-rose-700 font-medium text-sm shadow-md recording-pulse">
        <i data-lucide="square" class="w-4 h-4 mr-2 fill-current"></i> Dừng thu âm
      </button>
    `;
  }

  if (turn.localAudioBlob || turn.status === "failed") {
    return `
      <button onclick="startRecordingTurn('${turn.id}')"
        class="inline-flex items-center px-4 py-2 rounded-lg bg-amber-500 text-white hover:bg-amber-600 font-medium text-sm shadow-sm">
        <i data-lucide="rotate-ccw" class="w-4 h-4 mr-1.5"></i> Thu âm lại
      </button>
    `;
  }

  return `
    <button onclick="startRecordingTurn('${turn.id}')"
      class="inline-flex items-center px-5 py-2.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 font-medium text-sm shadow-sm transition">
      <i data-lucide="mic" class="w-4 h-4 mr-2"></i> Bắt đầu thu âm
    </button>
  `;
}

// Start Recording Turn
async function startRecordingTurn(turnId) {
  if (state.activeRecordingTurnId) {
    await stopRecordingTurn(state.activeRecordingTurnId);
  }

  const turn = state.turns.find((t) => t.id === turnId);
  if (!turn || turn.locked) return;

  const canvas = document.getElementById(`canvas-${turnId}`);
  const timerElem = document.getElementById(`timer-${turnId}`);
  const statusElem = document.getElementById(`rec-status-${turnId}`);
  const controlsElem = document.getElementById(`controls-${turnId}`);
  const cardElem = document.getElementById(`turn-card-${turnId}`);

  try {
    state.activeRecordingTurnId = turnId;

    if (statusElem) {
      statusElem.innerHTML = `<span class="text-rose-600 font-semibold animate-pulse">● Đang thu âm... Hãy nói vào mic</span>`;
    }
    if (cardElem) {
      cardElem.classList.add("ring-2", "ring-rose-500", "border-rose-400");
    }

    // Update controls button in-place (avoid re-rendering entire list so canvas stays attached!)
    if (controlsElem) {
      controlsElem.innerHTML = `
        <button onclick="stopRecordingTurn('${turn.id}')"
          class="inline-flex items-center px-5 py-2.5 rounded-lg bg-rose-600 text-white hover:bg-rose-700 font-medium text-sm shadow-md recording-pulse">
          <i data-lucide="square" class="w-4 h-4 mr-2 fill-current"></i> Dừng thu âm
        </button>
      `;
      if (window.lucide) lucide.createIcons();
    }

    // Start recording and connect audio analyser to this canvas
    await window.audioRecorder.startRecording(canvas, (elapsed) => {
      if (timerElem) timerElem.textContent = formatTime(elapsed);
    });

  } catch (err) {
    state.activeRecordingTurnId = null;
    showToast(err.message, "error");
    renderTurns();
  }
}

// Stop Recording Turn
async function stopRecordingTurn(turnId) {
  if (state.activeRecordingTurnId !== turnId) return;

  const turn = state.turns.find((t) => t.id === turnId);
  state.activeRecordingTurnId = null;

  try {
    const result = await window.audioRecorder.stopRecording();
    if (result && turn) {
      turn.localAudioBlob = result.blob;
      turn.localAudioUrl = URL.createObjectURL(result.blob);
      turn.duration = result.duration;
      // Reset status to newly recorded
      turn.status = "recorded";
      turn.reasons = [];

      showToast(`Đã thu âm lượt ${turn.dialogue_id} #${turn.turn_idx}!`, "info");
    }
  } catch (e) {
    console.error("Error stopping recorder:", e);
  }

  renderTurns();
  updateProgressSummary();
}

// Handle Confirmation & Verification
async function handleConfirmAndVerify() {
  if (state.isVerifying) return;

  // 1. Check if any turn is missing audio
  const unrecordedTurns = state.turns.filter((t) => !t.locked && !t.localAudioBlob);
  if (unrecordedTurns.length > 0) {
    const missingList = unrecordedTurns
      .map((t) => `[${t.dialogue_id} #${t.turn_idx}]`)
      .join(", ");
    showToast(`Vui lòng thu âm tất cả các đoạn trước khi xác nhận! Còn thiếu ${unrecordedTurns.length} đoạn: ${missingList}`, "warning");

    // Scroll to first missing turn
    const firstMissing = document.getElementById(`turn-card-${unrecordedTurns[0].id}`);
    if (firstMissing) {
      firstMissing.scrollIntoView({ behavior: "smooth", block: "center" });
      firstMissing.classList.add("ring-4", "ring-rose-400");
      setTimeout(() => firstMissing.classList.remove("ring-4", "ring-rose-400"), 2500);
    }
    return;
  }

  // 2. Identify turns needing verification
  const turnsToVerify = state.turns.filter((t) => !t.locked && t.localAudioBlob);
  if (turnsToVerify.length === 0) {
    showToast("Tất cả các đoạn đã được xác nhận đạt chuẩn!", "success");
    return;
  }

  // Show Loading Modal
  openModal("Đang kiểm tra ASR & Đánh giá chất lượng", turnsToVerify.length);
  state.isVerifying = true;

  let passedCount = 0;
  let failedCount = 0;

  for (let i = 0; i < turnsToVerify.length; i++) {
    const turn = turnsToVerify[i];
    updateModalProgress(i + 1, turnsToVerify.length, `Đang xử lý ${turn.dialogue_id} #${turn.turn_idx} qua Whisper ASR...`);

    try {
      const res = await API.verifyTurn(
        state.currentReaderId,
        turn.dialogue_id,
        turn.turn_idx,
        turn.localAudioBlob
      );

      turn.score = res.score;
      turn.score_percent = res.score_percent;
      turn.wpm = res.wpm;
      turn.duration = res.duration;
      turn.asr_transcript = res.asr_transcript;
      turn.reasons = res.reasons || [];

      if (res.passed) {
        turn.status = "passed";
        turn.locked = true;
        turn.audio_url = res.audio_url;
        turn.recorded_time = res.recorded_time;
        passedCount++;
      } else {
        turn.status = "failed";
        turn.locked = false;
        failedCount++;
      }
    } catch (err) {
      turn.status = "failed";
      turn.reasons = [err.message];
      failedCount++;
    }
  }

  const total = state.turns.length;
  const allCompleted = state.turns.every((t) => t.status === "passed");

  // ONLY COMMIT TO MONGODB WHEN ALL N/N TURNS FOR THE ROLE ARE PASSED!
  if (allCompleted && total > 0) {
    updateModalProgress(total, total, "Đang lưu trữ chính thức toàn bộ file MP3 và metadata vào MongoDB...");
    try {
      const finalRes = await API.finalizeAll(state.currentReaderId);
      state.turns.forEach((t) => {
        t.recorded_time = finalRes.recorded_time;
      });
      showToast(`🎉 Chúc mừng! Đã hoàn tất 100% (${total}/${total} đoạn đạt chuẩn). Toàn bộ file MP3 và metadata đã được lưu an toàn vào MongoDB!`, "success");
      setTimeout(() => {
        const banner = document.getElementById("all-completed-banner");
        if (banner) banner.scrollIntoView({ behavior: "smooth" });
      }, 300);
    } catch (err) {
      showToast(err.message, "error");
    }
  } else {
    showToast(`Có ${failedCount} đoạn chưa đạt chuẩn (Score < 85% hoặc WPM < 4). Hệ thống CHƯA LƯU vào Database. Vui lòng thu âm lại các đoạn màu đỏ và ấn Xác nhận lại!`, "warning");
  }

  state.isVerifying = false;
  closeModal();

  renderTurns();
  updateProgressSummary();
}

// Handle Reset Reader Recordings
async function handleResetReader() {
  if (!confirm(`Bạn có chắc muốn xóa toàn bộ bản thu của ${state.currentReader?.name || state.currentReaderId} để thu lại từ đầu?`)) {
    return;
  }

  try {
    await API.resetReader(state.currentReaderId);
    showToast("Đã đặt lại dữ liệu bản thu thành công!", "info");
    await selectReader(state.currentReaderId);
  } catch (err) {
    showToast(err.message, "error");
  }
}

// Modal Helpers
function openModal(title, totalItems) {
  const modal = document.getElementById("progress-modal");
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-total").textContent = totalItems;
  document.getElementById("modal-current").textContent = "0";
  document.getElementById("modal-status").textContent = "Bắt đầu xử lý...";
  document.getElementById("modal-bar").style.width = "0%";
  modal.classList.remove("hidden");
}

function updateModalProgress(current, total, statusText) {
  document.getElementById("modal-current").textContent = current;
  document.getElementById("modal-status").textContent = statusText;
  const pct = Math.round((current / total) * 100);
  document.getElementById("modal-bar").style.width = `${pct}%`;
}

function closeModal() {
  const modal = document.getElementById("progress-modal");
  modal.classList.add("hidden");
}

// Toast Notification Helper
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");

  const colors = {
    info: "bg-indigo-600 text-white",
    success: "bg-emerald-600 text-white",
    warning: "bg-amber-600 text-white",
    error: "bg-rose-600 text-white"
  };

  toast.className = `${colors[type]} px-4 py-3 rounded-lg shadow-lg text-sm font-medium flex items-center space-x-2 transition transform duration-300 translate-y-2 opacity-0`;
  toast.innerHTML = `<span>${message}</span>`;

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.remove("translate-y-2", "opacity-0");
  }, 10);

  setTimeout(() => {
    toast.classList.add("translate-y-2", "opacity-0");
    setTimeout(() => toast.remove(), 300);
  }, 4500);
}

