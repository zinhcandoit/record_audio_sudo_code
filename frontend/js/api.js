const API = {
  baseUrl: "",

  async getSystemStatus() {
    const res = await fetch(`${this.baseUrl}/api/system/status`);
    if (!res.ok) throw new Error("Không thể kết nối đến máy chủ");
    return await res.json();
  },

  async getReaders() {
    const res = await fetch(`${this.baseUrl}/api/readers`);
    if (!res.ok) throw new Error("Không thể tải danh sách người đọc");
    return await res.json();
  },

  async getReaderTurns(readerId) {
    const res = await fetch(`${this.baseUrl}/api/readers/${readerId}/turns`);
    if (!res.ok) throw new Error(`Lỗi tải kịch bản cho '${readerId}'`);
    return await res.json();
  },

  async verifyTurn(readerId, dialogueId, turnIdx, audioBlob) {
    const formData = new FormData();
    formData.append("reader_id", readerId);
    formData.append("dialogue_id", dialogueId);
    formData.append("turn_idx", turnIdx);
    formData.append("audio", audioBlob, `${dialogueId}_${turnIdx}.webm`);

    const res = await fetch(`${this.baseUrl}/api/verify/turn`, {
      method: "POST",
      body: formData
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Lỗi khi xử lý kiểm tra lượt thoại");
    }
    return data;
  },

  async finalizeAll(readerId) {
    const res = await fetch(`${this.baseUrl}/api/verify/finalize/${readerId}`, {
      method: "POST"
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Lỗi khi lưu dữ liệu vào MongoDB");
    }
    return data;
  },

  async getReaderStatus(readerId) {
    const res = await fetch(`${this.baseUrl}/api/verify/status/${readerId}`);
    if (!res.ok) throw new Error("Lỗi kiểm tra tiến độ");
    return await res.json();
  },

  async resetReader(readerId) {
    const res = await fetch(`${this.baseUrl}/api/recordings/reset/${readerId}`, {
      method: "POST"
    });
    if (!res.ok) throw new Error("Lỗi khi đặt lại bản thu");
    return await res.json();
  },

  getZipExportUrl(readerId = null) {
    return readerId
      ? `${this.baseUrl}/api/recordings/export/zip?reader_id=${readerId}`
      : `${this.baseUrl}/api/recordings/export/zip`;
  }
};

window.API = API;

