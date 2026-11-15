class AudioRecorderManager {
  constructor() {
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.stream = null;
    this.audioContext = null;
    this.analyser = null;
    this.source = null;
    this.animationId = null;
    this.startTime = 0;
    this.timerInterval = null;
    this.currentCanvas = null;
    this.isRecording = false;
  }

  async startRecording(canvasElement, onTickCallback) {
    if (this.isRecording) {
      await this.stopRecording();
    }

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        }
      });
    } catch (err) {
      console.error("Microphone access denied or error:", err);
      throw new Error("Không thể truy cập microphone. Vui lòng cấp quyền micro cho trình duyệt!");
    }

    this.currentCanvas = canvasElement;
    this.audioChunks = [];

    // Choose supported MIME type
    const mimeTypes = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/wav",
      ""
    ];
    let selectedMime = "";
    for (const m of mimeTypes) {
      if (!m || MediaRecorder.isTypeSupported(m)) {
        selectedMime = m;
        break;
      }
    }

    const options = selectedMime ? { mimeType: selectedMime } : {};
    this.mediaRecorder = new MediaRecorder(this.stream, options);

    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        this.audioChunks.push(event.data);
      }
    };

    // Set up Web Audio API Analyser for Waveform
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.audioContext = new AudioCtx();
      if (this.audioContext.state === "suspended") {
        await this.audioContext.resume();
      }
      this.source = this.audioContext.createMediaStreamSource(this.stream);
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 256;
      this.analyser.smoothingTimeConstant = 0.65; // Smooth audio transitions
      this.source.connect(this.analyser);
      
      this.isRecording = true;
      this._drawWaveform();
    } catch (e) {
      console.warn("Could not start AudioContext for waveform:", e);
      this.isRecording = true;
    }

    this.mediaRecorder.start(100);
    this.startTime = Date.now();

    // Start timer callback
    if (onTickCallback) {
      onTickCallback(0);
      this.timerInterval = setInterval(() => {
        const elapsed = (Date.now() - this.startTime) / 1000;
        onTickCallback(elapsed);
      }, 100);
    }
  }

  stopRecording() {
    return new Promise((resolve) => {
      if (!this.mediaRecorder || !this.isRecording) {
        this.isRecording = false;
        resolve(null);
        return;
      }

      const elapsedDuration = (Date.now() - this.startTime) / 1000;

      if (this.timerInterval) {
        clearInterval(this.timerInterval);
        this.timerInterval = null;
      }

      if (this.animationId) {
        cancelAnimationFrame(this.animationId);
        this.animationId = null;
      }

      this.isRecording = false;

      this.mediaRecorder.onstop = () => {
        const mimeType = this.mediaRecorder.mimeType || "audio/webm";
        const audioBlob = new Blob(this.audioChunks, { type: mimeType });

        // Clean up audio tracks
        if (this.stream) {
          this.stream.getTracks().forEach((track) => track.stop());
          this.stream = null;
        }

        if (this.audioContext && this.audioContext.state !== "closed") {
          try {
            this.audioContext.close();
          } catch (e) {}
          this.audioContext = null;
        }

        if (this.currentCanvas) {
          this._drawIdleWaveform(this.currentCanvas);
        }

        resolve({
          blob: audioBlob,
          duration: Math.max(0.2, elapsedDuration),
          mimeType: mimeType
        });
      };

      this.mediaRecorder.stop();
    });
  }

  _drawWaveform() {
    if (!this.analyser || !this.currentCanvas || !this.isRecording) return;

    const canvas = this.currentCanvas;
    const ctx = canvas.getContext("2d");

    // Adjust canvas resolution to match display size (High DPI)
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(200, Math.floor((rect.width || 400) * dpr));
    const height = Math.max(50, Math.floor((rect.height || 64) * dpr));
    
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    const centerY = height / 2;
    const bufferLength = this.analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    // Number of vertical bars across canvas (approx 45-55 bars like reference image)
    const numBars = Math.min(50, Math.max(24, Math.floor(width / (9 * dpr))));
    const barWidth = Math.max(3 * dpr, (width / numBars) * 0.45);
    const gap = (width - numBars * barWidth) / (numBars + 1);

    const draw = () => {
      if (!this.isRecording) return;
      this.animationId = requestAnimationFrame(draw);

      this.analyser.getByteFrequencyData(dataArray);

      // Pitch black background matching user reference image
      ctx.fillStyle = "#000000";
      ctx.fillRect(0, 0, width, height);

      // Symmetrical vertical bars oscillating around centerY
      for (let i = 0; i < numBars; i++) {
        // Sample frequencies focusing on speech range (speech is usually in bins 1 to 45)
        const freqIndex = Math.min(
          bufferLength - 1,
          Math.floor(Math.pow(i / numBars, 1.15) * (bufferLength * 0.7)) + 1
        );
        const val = dataArray[freqIndex] || 0;

        // Normalized amplitude (0.0 to 1.0) with voice amplification
        const amp = Math.min(1.0, (val / 255.0) * 1.6);

        // Minimum baseline bar height when quiet (4px)
        const minH = 4 * dpr;
        // Maximum expansion when speaking (up to 85% of canvas height)
        const maxH = height * 0.85;
        const barHeight = Math.max(minH, amp * maxH);

        const x = gap + i * (barWidth + gap);
        const y = centerY - barHeight / 2;

        // Draw crisp white pill-shaped bar matching the reference image
        ctx.fillStyle = "#ffffff";
        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(x, y, barWidth, barHeight, barWidth / 2);
        } else {
          ctx.rect(x, y, barWidth, barHeight);
        }
        ctx.fill();
      }
    };

    draw();
  }

  _drawIdleWaveform(canvas) {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(200, Math.floor((rect.width || 400) * dpr));
    const height = Math.max(50, Math.floor((rect.height || 64) * dpr));

    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    const centerY = height / 2;

    // Pitch black background
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, width, height);

    const numBars = Math.min(50, Math.max(24, Math.floor(width / (9 * dpr))));
    const barWidth = Math.max(3 * dpr, (width / numBars) * 0.45);
    const gap = (width - numBars * barWidth) / (numBars + 1);

    // Subtle dark-gray baseline bars when idle
    ctx.fillStyle = "#27272a";
    for (let i = 0; i < numBars; i++) {
      const x = gap + i * (barWidth + gap);
      const barHeight = 4 * dpr;
      const y = centerY - barHeight / 2;
      ctx.beginPath();
      if (ctx.roundRect) {
        ctx.roundRect(x, y, barWidth, barHeight, barWidth / 2);
      } else {
        ctx.rect(x, y, barWidth, barHeight);
      }
      ctx.fill();
    }
  }
}

// Global recorder instance
window.audioRecorder = new AudioRecorderManager();
