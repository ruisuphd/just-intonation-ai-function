// --- Global Variables ---
let midiAccess = null, midiInput = null, midiOutput = null, audioContext = null;
const webAudioNotes = {};
let outputMode = 'midi', tuningSystem = '12tet', isTuningActive = false;
let jiReferenceSource = 'manual', jiReferenceNote = 60, jiScaleType = 'major';
let pianoSampleBuffer = null;
const multiSamples = {}; // This will store the loaded AudioBuffers
const PIANO_SAMPLE_MAP = {
    24: 'https://gleitz.github.io/midi-js-soundfonts/FluidR3_GM/acoustic_grand_piano-mp3/C1.mp3', // C1
    36: 'https://gleitz.github.io/midi-js-soundfonts/FluidR3_GM/acoustic_grand_piano-mp3/C2.mp3', // C2
    48: 'https://gleitz.github.io/midi-js-soundfonts/FluidR3_GM/acoustic_grand_piano-mp3/C3.mp3', // C3
    60: 'https://gleitz.github.io/midi-js-soundfonts/FluidR3_GM/acoustic_grand_piano-mp3/C4.mp3', // C4
    72: 'https://gleitz.github.io/midi-js-soundfonts/FluidR3_GM/acoustic_grand_piano-mp3/C5.mp3', // C5
    84: 'https://gleitz.github.io/midi-js-soundfonts/FluidR3_GM/acoustic_grand_piano-mp3/C6.mp3', // C6
    96: 'https://gleitz.github.io/midi-js-soundfonts/FluidR3_GM/acoustic_grand_piano-mp3/C7.mp3', // C7
};
const activeOnNotes = {}; // To store note-on times
const tempoTracker = {
    interNoteTimes: [],
    maxHistory: 20,
    avgTime: 500,
    lastNoteTime: 0,
    currentWindowMs: 8000
};
const tuningSmoother = {
    currentTargetCents: new Array(12).fill(0), 
    targetCents: new Array(12).fill(0),
};
const MAX_POLYPHONY = 32;
const voicePool = [];
let lastVoice = 0;

let forcePbOnly = false; // NEW: Force pitch-bend toggle
let lastMtsSendMs = 0;   // NEW: For throttling smoothing loop

// --- Sustain pedal state ---
let sustainPedal = false;
const keysDown = new Set();
const sustainedNotes = new Set();

let sysExSupported = true;
const notesUsingBend = new Set();
let lastDeviceId = 0x7F; // NEW: For storing the probed device ID

// --- MPE Channel Management ---
const MPE_CHANNELS = Array.from({ length: 15 }, (_, i) => ({ channel: i + 2, inUse: false, note: null }));
const activeNotesToMpeChannel = {};

// --- Just Intonation Ratios ---
const JI_RATIOS = {
    major: { 0: "1/1", 2: "9/8", 4: "5/4", 5: "4/3", 7: "3/2", 9: "5/3", 11: "15/8" },
    minor: { 0: "1/1", 2: "9/8", 3: "6/5", 5: "4/3", 7: "3/2", 8: "8/5", 10: "9/5" }
};

// --- UI Elements ---
const statusDiv = document.getElementById('status'), midiInSelect = document.getElementById('midiIn'), midiOutSelect = document.getElementById('midiOut'),
    messageLog = document.getElementById('messageLog'), outputModeRadios = document.querySelectorAll('input[name="outputMode"]'),
    tuningSystemRadios = document.querySelectorAll('input[name="tuningSystem"]'), jiReferenceNoteSelect = document.getElementById('jiReferenceNote'),
    activateTuningButton = document.getElementById('activateTuningButton'), tuningStatusSpan = document.getElementById('tuningStatus'),
    panicButton = document.getElementById('panicButton'), jiScaleTypeSelect = document.getElementById('jiScaleType'),
    jiReferenceSourceRadios = document.querySelectorAll('input[name="jiReferenceSource"]'), manualJiControls = document.getElementById('manualJiControls'),
    autoDetectControls = document.getElementById('autoDetectControls'), detectedKeyDisplay = document.getElementById('detectedKeyDisplay'),
    mtsStatusText = document.getElementById('mtsStatusText'), audibleTestBtn = document.getElementById('audibleTestBtn'),
    forcePbCheckbox = document.getElementById('forcePbCheckbox'); // NEW


// --- Helper Functions ---
const logMessage = (msg, isErr = false) => {
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    if (isErr) entry.style.color = 'red';
    entry.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    if (messageLog.childNodes.length > 150) messageLog.removeChild(messageLog.firstChild);
    messageLog.appendChild(entry);
    messageLog.scrollTop = messageLog.scrollHeight;
    console.log(msg);
};

const midiNoteToFrequency = note => 440 * Math.pow(2, (note - 69) / 12);
const parseRatio = r => r ? r.split('/').map(Number).reduce((a, b) => a / b) : null;

const setupMultiSamples = async (ctx) => {
    logMessage("Loading piano multi-samples...");
    statusDiv.textContent = "Loading piano sounds...";
    
    const loadPromises = Object.entries(PIANO_SAMPLE_MAP).map(async ([note, url]) => {
        try {
            const response = await fetch(url);
            const buffer = await response.arrayBuffer();
            multiSamples[note] = await ctx.decodeAudioData(buffer);
        } catch (e) {
            logMessage(`Failed to load sample for note ${note}: ${e}`, true);
        }
    });

    await Promise.all(loadPromises);

    if (Object.keys(multiSamples).length > 0) {
        logMessage("Piano multi-samples loaded!");
        statusDiv.textContent = "System ready. Select MIDI devices to begin.";
        statusDiv.className = 'mb-4 p-3 rounded-md bg-green-100 text-green-800';
    } else {
        logMessage("All piano samples failed to load.", true);
        statusDiv.textContent = "Error: Could not load piano sounds.";
        statusDiv.className = 'mb-4 p-3 rounded-md bg-red-100 text-red-800';
    }
    updateUIState();
};

const initializeAudioContext = () => {
    try {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        logMessage("Audio context initialized.");
        setupMultiSamples(audioContext);
    } catch (e) { logMessage("Web Audio not supported.", true); }
};

const playWebAudioNote = (note, vel, freq) => {
    if (!audioContext || Object.keys(multiSamples).length === 0 || webAudioNotes[note]) return;

    const sampleNotes = Object.keys(multiSamples).map(Number);
    const closestSampleNote = sampleNotes.reduce((prev, curr) => {
        return (Math.abs(curr - note) < Math.abs(prev - note) ? curr : prev);
    });
    
    const sampleBuffer = multiSamples[closestSampleNote];
    const source = audioContext.createBufferSource();
    source.buffer = sampleBuffer;
    const baseFreq = midiNoteToFrequency(closestSampleNote);
    source.playbackRate.value = freq / baseFreq;

    const gain = audioContext.createGain();
    gain.gain.setValueAtTime((vel / 127) * 0.8, audioContext.currentTime);
    source.connect(gain).connect(audioContext.destination);
    source.start();
    webAudioNotes[note] = { source, gain };
};

const stopWebAudioNote = note => {
    if (!webAudioNotes[note]) return;
    const { source, gain } = webAudioNotes[note];
    gain.gain.linearRampToValueAtTime(0, audioContext.currentTime + 0.5);
    source.stop(audioContext.currentTime + 0.5);
    delete webAudioNotes[note];
};

// --- MIDI Functions ---
const resetAllMidiState = () => {
    logMessage("PANIC: Resetting all MIDI states and channels.");
    if (midiOutput) {
        for (let ch = 0; ch < 16; ch++) {
            midiOutput.send([0xB0 | ch, 120, 0]);
            midiOutput.send([0xB0 | ch, 123, 0]);
            midiOutput.send([0xE0 | ch, 0, 64]);
        }
    }
    Object.keys(webAudioNotes).forEach(noteNum => stopWebAudioNote(parseInt(noteNum)));
    MPE_CHANNELS.forEach(ch => { ch.inUse = false; ch.note = null; });
    Object.keys(activeNotesToMpeChannel).forEach(k => delete activeNotesToMpeChannel[k]);
    notesUsingBend.clear();
    
    sustainPedal = false;
    keysDown.clear();
    sustainedNotes.clear();
};      

const getMpeChannel = note => {
    const freeChannel = MPE_CHANNELS.find(ch => !ch.inUse);
    if (freeChannel) {
        freeChannel.inUse = true;
        freeChannel.note = note;
        activeNotesToMpeChannel[note] = freeChannel.channel;
        return freeChannel.channel;
    }
    logMessage("Warning: No free MPE channels available.", true);
    return null;
};

const releaseMpeChannel = note => {
    const channelNum = activeNotesToMpeChannel[note];
    if (channelNum === undefined) return;
    const mpeChannel = MPE_CHANNELS.find(ch => ch.channel === channelNum);
    if (mpeChannel) { mpeChannel.inUse = false; mpeChannel.note = null; }
    delete activeNotesToMpeChannel[note];
};

const calculateTuning = (note) => {
    if (tuningSystem !== 'ji' || !isTuningActive) {
        return { cents: 0, freq: midiNoteToFrequency(note) };
    }
    const pitchClass = note % 12;
    const centsDev = tuningSmoother.currentTargetCents[pitchClass];
    const etFreq = midiNoteToFrequency(note);
    const finalFreq = etFreq * Math.pow(2, centsDev / 1200);
    return { cents: centsDev, freq: finalFreq };
};

// --- CORRECTED AND NEW MIDI FUNCTIONS ---

function createMtsSysex(note, cents) {
    const devId = (typeof lastDeviceId === 'number') ? lastDeviceId & 0x7F : 0x7F; // MODIFIED: Use probed device ID
    const baseHz = midiNoteToFrequency(note);
    const targetHz = baseHz * Math.pow(2, cents / 1200);
    const nFloat = 69 + 12 * Math.log2(targetHz / 440);
    let xx = Math.floor(nFloat);
    xx = Math.max(0, Math.min(127, xx)); // ✅ Add this safety clamp
    let frac = Math.round((nFloat - xx) * 16384);
    if (frac === 16384) { xx += 1; frac = 0; }
    const yy = (frac >> 7) & 0x7F; const zz = frac & 0x7F;
    return new Uint8Array([0xF0, 0x7F, devId, 0x08, 0x02, 0x00, 0x01, note & 0x7F, xx & 0x7F, yy, zz, 0xF7]);
}

function setPitchBendRangeAllChannels(semitones = 1, cents = 0) {
  if (!midiOutput) return;
  for (let ch = 1; ch < 16; ch++) {
    midiOutput.send([0xB0 | ch, 0x65, 0x00]); midiOutput.send([0xB0 | ch, 0x64, 0x00]);
    midiOutput.send([0xB0 | ch, 0x06, semitones & 0x7F]); midiOutput.send([0xB0 | ch, 0x26, cents & 0x7F]);
    midiOutput.send([0xB0 | ch, 0x65, 0x7F]); midiOutput.send([0xB0 | ch, 0x64, 0x7F]);
  }
}

// --- NEW PROBING FUNCTIONS ---
function waitForSysex(matchFn, timeoutMs = 400) {
  return new Promise(resolve => {
    if (!midiInput) return resolve(null);
    const onMsg = (e) => {
      const d = new Uint8Array(e.data || []);
      if (d && d[0] === 0xF0 && matchFn(d)) {
        midiInput.removeEventListener('midimessage', onMsg);
        resolve(d);
      }
    };
    midiInput.addEventListener('midimessage', onMsg);
    setTimeout(() => {
      try { midiInput.removeEventListener('midimessage', onMsg); } catch {}
      resolve(null);
    }, timeoutMs);
  });
}

async function probeIdentity() {
  if (!midiOutput || !midiInput) return null;
  midiOutput.send([0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7]);
  const rsp = await waitForSysex(d => d.length >= 15 && d[1] === 0x7E && d[3] === 0x06 && d[4] === 0x02, 500);
  if (!rsp) return null;
  return { deviceId: rsp[2] & 0x7F };
}

async function probeMtsDump(deviceId = 0x7F, program = 0) {
  if (!midiOutput || !midiInput) return false;
  midiOutput.send([0xF0, 0x7E, deviceId, 0x08, 0x00, program & 0x7F, 0xF7]);
  const reply = await waitForSysex(d => d[1] === 0x7E && d[3] === 0x08 && [1, 4, 5, 6].includes(d[4]), 600);
  return !!reply;
}

async function audibleMtsRtTest(note = 69, cents = 50) {
  if (!midiOutput) return false;
  function mtsSingleRT(devId, k, c) {
    const baseHz = 440 * Math.pow(2,(k-69)/12); const targetHz = baseHz * Math.pow(2, c/1200);
    const nFloat = 69 + 12 * Math.log2(targetHz/440); let xx = Math.floor(nFloat);
    let frac = Math.round((nFloat - xx) * 16384); if (frac === 16384) { xx += 1; frac = 0; }
    const yy = (frac >> 7) & 0x7F, zz = frac & 0x7F;
    return [0xF0,0x7F,devId,0x08,0x02,0x00,0x01,k & 0x7F, xx & 0x7F, yy, zz, 0xF7];
  }
  midiOutput.send(mtsSingleRT(lastDeviceId, note, cents));
  midiOutput.send([0x90, note, 100]);
  await new Promise(r=>setTimeout(r, 800));
  midiOutput.send([0x80, note, 0]);
  midiOutput.send(mtsSingleRT(lastDeviceId, note, 0));
  return true;
}

async function afterOutputSelected() {
  updateStatus('Probing device capabilities...', false);
  const id = await probeIdentity();
  if (id) lastDeviceId = id.deviceId;
  const hasDump = await probeMtsDump(lastDeviceId, 0);
  if (hasDump) {
    updateStatus('MTS Confirmed (device responded to MTS query).', false);
  } else {
    updateStatus('MTS support is unknown. You can run an audible test.', true);
  }
}

const onMIDIMessage = event => {
    const [status, note, vel] = event.data;
    const cmd = status >> 4;
    const now = performance.now();

    if (cmd === 9 && vel > 0) { // Note On
        if (tempoTracker.lastNoteTime > 0) {
            const diff = now - tempoTracker.lastNoteTime;
            tempoTracker.interNoteTimes.push(diff);
            if (tempoTracker.interNoteTimes.length > tempoTracker.maxHistory) tempoTracker.interNoteTimes.shift();
            const sum = tempoTracker.interNoteTimes.reduce((a, b) => a + b, 0);
            tempoTracker.avgTime = sum / tempoTracker.interNoteTimes.length;
            updateAdaptiveWindow();
        }
        
        tempoTracker.lastNoteTime = now;
        activeOnNotes[note] = { time: now, velocity: vel };
        keysDown.add(note);
        
        const { cents, freq } = calculateTuning(note);
        logMessage(`Note: ${note}, Cents Deviation: ${cents.toFixed(2)}`);

        if (outputMode === 'webaudio') {
            playWebAudioNote(note, vel, freq);
        } else if (midiOutput) {
            const assignedChannel = getMpeChannel(note);
            if (assignedChannel === null) return;

            // MODIFIED: Restructured tuning logic with forcePbOnly check
            if (isTuningActive && Math.abs(cents) > 0.1) {
                let sentSysEx = false;
                // 1. Try to send MTS if not forced to PB
                if (!forcePbOnly && sysExSupported) {
                    try {
                        midiOutput.send(createMtsSysex(note, cents));
                        sentSysEx = true;
                    } catch (e) { console.warn("SysEx send failed:", e); }
                }
                
                // 2. Fallback to Pitch Bend if MTS wasn't sent
                if (!sentSysEx) {
                    const bendValue = Math.max(0, Math.min(16383, Math.round(cents * 81.92) + 8192));
                    const lsb = bendValue & 0x7F;
                    const msb = (bendValue >> 7) & 0x7F;
                    midiOutput.send([0xE0 | assignedChannel, lsb, msb]);
                    notesUsingBend.add(note); 
                    if (isTuningActive) logMessage(`Pitch Bend: Note ${note} tuned on MPE Ch ${assignedChannel}`);
                }
            }
            
            midiOutput.send([0x90 | assignedChannel, note, vel]);
        }
    } else if (cmd === 8 || (cmd === 9 && vel === 0)) { // Note Off
        if (activeOnNotes[note]) {
            const { time, velocity } = activeOnNotes[note];

            // --- NEW SUSTAIN LOGIC ---
            let duration = now - time;
            if (sustainPedal) {
                duration *= 1.8; // Inflate duration to reflect sustain
            }

            if (jiReferenceSource === 'auto') {
                keyFinder.addNote({ pitch: note, duration: duration, velocity });
            }
            keyFinder.runAnalysis();
            delete activeOnNotes[note];
        }

        keysDown.delete(note);

        if (outputMode === 'webaudio') {
            if (sustainPedal) sustainedNotes.add(note);
            else stopWebAudioNote(note);
        } else if (midiOutput) {
            const assignedChannel = activeNotesToMpeChannel[note];
            if (assignedChannel !== undefined) {
                midiOutput.send([0x80 | assignedChannel, note, 0]);
                if (notesUsingBend.has(note)) {
                    midiOutput.send([0xE0 | assignedChannel, 0x00, 0x40]); 
                    notesUsingBend.delete(note);
                }
                releaseMpeChannel(note);
            }
        }
    } else if (cmd === 11) { // Control Change
        const controller = note, value = vel;
        if (controller === 64) {
            sustainPedal = value >= 64;
            logMessage(`Sustain pedal ${sustainPedal ? 'DOWN' : 'UP'}`);
            if (!sustainPedal && outputMode === 'webaudio') {
                sustainedNotes.forEach(n => { if (!keysDown.has(n)) stopWebAudioNote(n); });
                sustainedNotes.clear();
            }
            if (outputMode === 'midi' && midiOutput) {
                for (let ch = 0; ch < 16; ch++) midiOutput.send([0xB0 | ch, 64, value]);
            }
        } else if (outputMode === 'midi' && midiOutput) {
            midiOutput.send(event.data);
        }
    }
};

function updateAdaptiveWindow() {
    const minWindow = 6000, maxWindow = 15000, fastTempoThreshold = 100, slowTempoThreshold = 1000;
    let newWindow;
    if (tempoTracker.avgTime <= fastTempoThreshold) newWindow = minWindow;
    else if (tempoTracker.avgTime >= slowTempoThreshold) newWindow = maxWindow;
    else {
        const progress = (tempoTracker.avgTime - fastTempoThreshold) / (slowTempoThreshold - fastTempoThreshold);
        newWindow = minWindow + (maxWindow - minWindow) * progress;
    }
    tempoTracker.currentWindowMs = tempoTracker.currentWindowMs * 0.95 + newWindow * 0.05;
};

// --- Key Finding Algorithm (condensed for brevity) ---
const keyFinder = {
    MIN_NOTES_FOR_ANALYSIS: 16, performanceWindow: [], detectedKey: { name: "N/A", rootNote: 60, scale: 'major' },
    PITCH_CLASSES: ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'], COF: ['C', 'F', 'Bb', 'Eb', 'Ab', 'Db', 'Gb', 'B', 'E', 'A', 'D', 'G'],
    COF_ANGLES: Array.from({ length: 12 }, (_, i) => (i * Math.PI) / 6),
    addNote({ pitch, duration, velocity }) {
        const now = performance.now();
        this.performanceWindow.push({ pitch, duration, velocity, time: now });
        this.performanceWindow = this.performanceWindow.filter(n => now - n.time < tempoTracker.currentWindowMs);
    },
    runAnalysis() {
        if (this.performanceWindow.length < this.MIN_NOTES_FOR_ANALYSIS) return;

        // --- All your profile calculation logic is correct ---
        const noteCount = this.performanceWindow.length;
        const calculateAdaptiveAlpha = c => (c >= 50) ? 0.85 : 0.5 + (0.35 * (c / 50));
        const alpha = calculateAdaptiveAlpha(noteCount);
        const durationProfile = new Array(12).fill(0), countProfile = new Array(12).fill(0);
        this.performanceWindow.forEach(note => { const pc = note.pitch % 12; durationProfile[pc] += note.duration; countProfile[pc]++; });
        const maxDur = Math.max(...durationProfile), maxCount = Math.max(...countProfile);
        const normDur = maxDur > 0 ? durationProfile.map(d => d / maxDur) : durationProfile;
        const normCount = maxCount > 0 ? countProfile.map(c => c / maxCount) : countProfile;
        const hybridProfile = normDur.map((d, i) => alpha * d + (1 - alpha) * normCount[i]);

        // --- Pruning logic is correct ---
        const totalMass = hybridProfile.reduce((a, b) => a + b, 0) || 1;
        const massThreshold = 0.03 * totalMass;
        const prunedProfile = hybridProfile.map(v => v < massThreshold ? 0 : v);
        const maxHybrid = Math.max(...prunedProfile); if (maxHybrid === 0) return;
        const normalizedProfile = prunedProfile.map(p => p / maxHybrid);

        // --- All Circle of Fifths geometry calculations are correct ---
        const cofPitchClasses = [0, 5, 10, 3, 8, 1, 6, 11, 4, 9, 2, 7];
        const cofProfile = cofPitchClasses.map(pc => normalizedProfile[pc]);
        let maxAxisStrength = -Infinity, mainDirectedAxisStartIdx = -1;
        for (let i = 0; i < 12; i++) {
            let right = 0, left = 0; for (let j = 1; j <= 5; j++) { right += cofProfile[(i + j) % 12]; left += cofProfile[(i - j + 12) % 12]; }
            if (right - left > maxAxisStrength) { maxAxisStrength = right - left; mainDirectedAxisStartIdx = i; }
        }
        const confidence = Math.min(100, (maxAxisStrength / 5) * 100);
        if (mainDirectedAxisStartIdx === -1 || confidence < 20) { this.updateKeyDisplay("Ambiguous", null, 0); return; }
        let totalX = 0, totalY = 0;
        cofProfile.forEach((r, i) => { const phi = this.COF_ANGLES[i]; totalX += r * Math.cos(phi); totalY += r * Math.sin(phi); });
        const phi_SF = Math.atan2(totalY, totalX);
        const mdaseEndIdx = (mainDirectedAxisStartIdx + 6) % 12; const modeAxisIdx = (mdaseEndIdx - 3 + 12) % 12;
        const phi_1 = this.COF_ANGLES[modeAxisIdx]; let phi_m = phi_SF - phi_1;
        while (phi_m <= -Math.PI) phi_m += 2 * Math.PI; while (phi_m > Math.PI) phi_m -= 2 * Math.PI;
        const majorKeyName = this.COF[(mdaseEndIdx - 1 + 12) % 12]; const majorKeyRootIndex = cofPitchClasses[(mdaseEndIdx + 1) % 12];
        const relativeMinorRootIndex = (majorKeyRootIndex - 3 + 12) % 12; const relativeMinorName = this.PITCH_CLASSES[relativeMinorRootIndex];
        let newKey;

        // --- BUG FIX: This is the single, correct block for mode decision ---
        const DEAD_ZONE = 0.18;
        if (Math.abs(phi_m) < DEAD_ZONE) {
            // In the ambiguous zone, trust the previous decision to prevent flips.
            newKey = this.detectedKey && this.detectedKey.name !== "N/A" ? { ...this.detectedKey } : null;
            if (newKey) { // Re-construct name in case rootNote is just a number
                newKey.name = this.PITCH_CLASSES[newKey.rootNote % 12] + (newKey.scale === 'major' ? ' Major' : ' minor');
            }
        } else if (phi_m > 0) {
            newKey = { name: `${majorKeyName} Major`, rootNote: majorKeyRootIndex + 60, scale: 'major' };
        } else {
            newKey = { name: `${relativeMinorName} minor`, rootNote: relativeMinorRootIndex + 60, scale: 'minor' };
        }
        // --- The old, buggy logic block has been removed ---

        // --- Corrected final update logic ---
        if (newKey && (!this.detectedKey || newKey.name !== this.detectedKey.name)) {
            this.detectedKey = { ...newKey, confidence: confidence };
            logMessage(`New Key Target: ${this.detectedKey.name} (Confidence: ${confidence.toFixed(0)}%)`);
            this.updateKeyDisplay(this.detectedKey.name, this.detectedKey.scale, confidence);
            
            // --- LOGIC IMPROVEMENT: Define activeRoot and activeScale here ---
            const activeRoot = this.detectedKey.rootNote;
            const activeScale = JI_RATIOS[this.detectedKey.scale]; // Use the new key's scale
            
            for (let i = 0; i < 12; i++) {
                const offset = (i - (activeRoot % 12) + 12) % 12;
                const ratio = parseRatio(activeScale?.[offset]);
                if (ratio) {
                    const jiCentsFromTonic = 1200 * Math.log2(ratio);
                    const etCentsFromTonic = offset * 100;
                    tuningSmoother.targetCents[i] = jiCentsFromTonic - etCentsFromTonic;
                } else {
                    tuningSmoother.targetCents[i] = 0;
                }
            }
        } else if (newKey) {
            // Key is the same, just update the confidence for the UI. No retuning.
            this.detectedKey.confidence = confidence;
            this.updateKeyDisplay(this.detectedKey.name, this.detectedKey.scale, confidence);
        }
    },
    updateKeyDisplay(keyName, scale, confidence = 0) {
        if (keyName === "Ambiguous" || confidence < 20) {
            detectedKeyDisplay.innerHTML = `<span class="font-semibold text-lg text-yellow-700">Ambiguous Key</span>`;
            detectedKeyDisplay.className = 'key-display mt-2 p-3 text-center rounded-md bg-yellow-100 border-yellow-300';
        } else if (keyName === "N/A") {
            detectedKeyDisplay.innerHTML = `<span class="font-semibold text-lg text-gray-500">Play some notes...</span>`;
            detectedKeyDisplay.className = 'key-display mt-2 p-3 text-center rounded-md bg-gray-100 border-gray-300';
        } else {
            const bgColor = scale === 'major' ? 'bg-blue-100 border-blue-300' : 'bg-purple-100 border-purple-300';
            const textColor = scale === 'major' ? 'text-blue-800' : 'text-purple-800';
            detectedKeyDisplay.innerHTML = `<span class="font-semibold text-xl ${textColor}">${keyName}</span><div class="text-xs ${textColor} opacity-80 mt-1">Confidence: ${confidence.toFixed(0)}%</div>`;
            detectedKeyDisplay.className = `key-display mt-2 p-3 text-center rounded-md border ${bgColor}`;
        }
    }
};

// --- MIDI Setup ---
const onMIDISuccess = access => {
    midiAccess = access;
    initializeAudioContext();
    populateDeviceSelectors();
    access.onstatechange = onMIDIStateChange;
    updateUIState();
};
const onMIDIFailure = msg => {
    logMessage(`MIDI access failed: ${msg}. SysEx may be unsupported.`, true);
    statusDiv.textContent = `MIDI access failed: ${msg}. Pitch-bend fallback will be used.`;
    statusDiv.className = 'mb-4 p-3 rounded-md bg-red-100 text-red-800';
    sysExSupported = false;
    if (!audioContext) initializeAudioContext();
    updateUIState();
};
const onMIDIStateChange = event => {
    logMessage(`MIDI state changed: ${event.port.name}, State: ${event.port.state}`);
    if (midiInput?.id === event.port.id && event.port.state === 'disconnected') midiInput = null;
    if (midiOutput?.id === event.port.id && event.port.state === 'disconnected') midiOutput = null;
    populateDeviceSelectors();
    updateUIState();
};

function populateDeviceSelectors() {
    if (!midiAccess) return;
    const currentInId = midiInput?.id, currentOutId = midiOutput?.id;
    midiInSelect.innerHTML = '<option value="">Select Input...</option>';
    midiOutSelect.innerHTML = '<option value="">Select Output...</option>';
    midiAccess.inputs.forEach(i => { const opt = new Option(i.name, i.id); if (i.id === currentInId) opt.selected = true; midiInSelect.appendChild(opt); });
    midiAccess.outputs.forEach(o => { const opt = new Option(o.name, o.id); if (o.id === currentOutId) opt.selected = true; midiOutSelect.appendChild(opt); });
    populateReferenceNoteSelector();
}

function populateReferenceNoteSelector() {
    const notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
    jiReferenceNoteSelect.innerHTML = '';
    for (let i = 0; i < 12; i++) {
        const opt = new Option(`${notes[i]}4`, 60 + i);
        if (opt.value == jiReferenceNote) opt.selected = true;
        jiReferenceNoteSelect.appendChild(opt);
    }
}

// --- NEW/MODIFIED UI FUNCTIONS ---
function updateStatus(message, showTestButton = false) {
    mtsStatusText.textContent = message;
    audibleTestBtn.style.display = showTestButton ? 'inline-block' : 'none';
}

function updateUIState() {
    const inputReady = !!midiInput;
    const outputReady = (outputMode === 'midi' && !!midiOutput) || (outputMode === 'webaudio' && Object.keys(multiSamples).length > 0);
    
    activateTuningButton.disabled = !(inputReady && outputReady);
    const isJiTuning = tuningSystem === 'ji';
    document.getElementById('jiOptionsContainer').style.display = isJiTuning ? 'block' : 'none';
    const isAutoDetect = jiReferenceSource === 'auto';
    manualJiControls.style.display = isJiTuning && !isAutoDetect ? 'grid' : 'none';
    autoDetectControls.style.display = isJiTuning && isAutoDetect ? 'block' : 'none';
    
    activateTuningButton.textContent = isTuningActive ? 'Deactivate Tuning' : 'Activate Tuning';
    activateTuningButton.classList.toggle('bg-red-600', isTuningActive);
    activateTuningButton.classList.toggle('bg-indigo-600', !isTuningActive);
    
    updateTuningStatusSpan();
}

function updateTuningStatusSpan() {
    if (activateTuningButton.disabled) {
        let statusText = "Select an input device";
        if (outputMode === 'webaudio' && Object.keys(multiSamples).length === 0) statusText = "Loading piano sounds...";
        else if (outputMode === 'midi' && !midiOutput) statusText = "Select an output device";
        tuningStatusSpan.textContent = statusText;
        tuningStatusSpan.className = "ml-4 text-sm text-yellow-700 font-medium";
    } else if (isTuningActive) {
        let mode = tuningSystem === 'ji' ? (jiReferenceSource === 'auto' ? `JI (Auto: ${keyFinder.detectedKey.name})` : 'JI (Manual)') : '12-TET';
        tuningStatusSpan.textContent = `Active (${mode})`;
        tuningStatusSpan.className = "ml-4 text-sm text-green-700 font-medium";
    } else {
        tuningStatusSpan.textContent = "Inactive";
        tuningStatusSpan.className = "ml-4 text-sm text-gray-600";
    }
}

// --- Event Listeners ---
midiInSelect.addEventListener('change', () => {
    if (midiInput) midiInput.onmidimessage = null;
    midiInput = midiInSelect.value ? midiAccess.inputs.get(midiInSelect.value) : null;
    if (midiInput) { midiInput.onmidimessage = onMIDIMessage; logMessage(`Listening to: ${midiInput.name}`); }
    updateUIState();
});

// MODIFIED: Make this async
midiOutSelect.addEventListener('change', async () => {
    resetAllMidiState();
    midiOutput = midiOutSelect.value ? midiAccess.outputs.get(midiOutSelect.value) : null;
    if (midiOutput) {
        logMessage(`Selected Output: ${midiOutput.name}`);
        setPitchBendRangeAllChannels(1, 0);
        midiOutput.send([0xB0 | 0, 122, 0]); // NEW: Optional Local Control OFF
        await afterOutputSelected();
    } else {
        updateStatus('Select an output device to check support.', false);
    }
    updateUIState();
});

audibleTestBtn.addEventListener('click', async () => { // NEW
    updateStatus('Playing test note on A4...', false);
    await audibleMtsRtTest();
    updateStatus('Test complete. If you heard a detuned note, MTS Real-Time is working.', false);
});

forcePbCheckbox.addEventListener('change', (e) => {
  forcePbOnly = e.target.checked;
  logMessage(`Force Pitch-Bend Only set to: ${forcePbOnly}`);
  if (!midiOutput) return;

  // Migrate any currently held notes to the new tuning method
  for (const nStr in activeOnNotes) {
    const n = parseInt(nStr, 10);
    const ch = activeNotesToMpeChannel[n];
    if (ch === undefined) continue;
    
    const cents = tuningSmoother.currentTargetCents[n % 12];

    if (forcePbOnly) {
      // Switch TO pitch bend
      const v = Math.max(0, Math.min(16383, Math.round(cents * 81.92) + 8192));
      midiOutput.send([0xE0 | ch, v & 0x7F, (v >> 7) & 0x7F]);
      notesUsingBend.add(n);
    } else {
      // Switch FROM pitch bend (back to MTS)
      // 1. Reset the pitch bend on this note's channel
      midiOutput.send([0xE0 | ch, 0x00, 0x40]); 
      notesUsingBend.delete(n);
      // 2. Re-apply the tuning with an MTS message
      if (sysExSupported) {
          midiOutput.send(createMtsSysex(n, cents));
      }
    }
  }
});

outputModeRadios.forEach(r => r.addEventListener('change', e => {
    resetAllMidiState();
    outputMode = e.target.value;
    midiOutSelect.disabled = outputMode === 'webaudio';
    updateUIState();
}));
tuningSystemRadios.forEach(r => r.addEventListener('change', e => { tuningSystem = e.target.value; updateUIState(); }));
jiReferenceSourceRadios.forEach(r => r.addEventListener('change', e => { jiReferenceSource = e.target.value; updateUIState(); }));
jiScaleTypeSelect.addEventListener('change', e => jiScaleType = e.target.value);
jiReferenceNoteSelect.addEventListener('change', e => jiReferenceNote = parseInt(e.target.value));
activateTuningButton.addEventListener('click', () => {
    isTuningActive = !isTuningActive;
    if (!isTuningActive) {
        resetAllMidiState();
        tuningSmoother.targetCents.fill(0);
        tuningSmoother.currentTargetCents.fill(0);
    }
    logMessage(`Tuning adjustments ${isTuningActive ? 'ACTIVATED' : 'DEACTIVATED'}.`);
    updateUIState();
});
panicButton.addEventListener('click', resetAllMidiState);

// --- Smoothing loop ---
function smoothingLoop() {
    const nowMs = performance.now(); // MODIFIED
    const okToSend = (nowMs - lastMtsSendMs) > 33; // ~30 Hz throttle

    // ... smoothing math is unchanged ...
    const smoothingBase = 0.05;
    const dynamicFactor = Math.min(0.3, smoothingBase + (100 / tempoTracker.avgTime) * 0.15);
    for (let i = 0; i < 12; i++) {
        tuningSmoother.currentTargetCents[i] += (tuningSmoother.targetCents[i] - tuningSmoother.currentTargetCents[i]) * dynamicFactor;
    }

    // MODIFIED: Retune held notes, but throttled
    if (isTuningActive && outputMode === 'midi' && midiOutput && okToSend) {
        for (const noteStr in activeOnNotes) {
            const note = parseInt(noteStr);
            const pitchClass = note % 12;
            const cents = tuningSmoother.currentTargetCents[pitchClass];
            
            if (Math.abs(cents) > 0.1) {
                const assignedChannel = activeNotesToMpeChannel[note];
                if (assignedChannel !== undefined) {
                    // This logic now respects the forcePbOnly toggle
                    if (!forcePbOnly && sysExSupported) {
                        midiOutput.send(createMtsSysex(note, cents));
                    } else if (notesUsingBend.has(note)) {
                        const bendValue = Math.round(cents * 81.92) + 8192;
                        const lsb = bendValue & 0x7F;
                        const msb = (bendValue >> 7) & 0x7F;
                        midiOutput.send([0xE0 | assignedChannel, lsb, msb]);
                    }
                }
            }
        }
        lastMtsSendMs = nowMs; // Update timestamp after sending
    }
    
    requestAnimationFrame(smoothingLoop);
}

// --- Initialization ---
logMessage("Requesting MIDI access...");
if (navigator.requestMIDIAccess) {
    navigator.requestMIDIAccess({ sysex: true }).then(onMIDISuccess, onMIDIFailure);
} else { 
    logMessage("Web MIDI API is not supported in this browser.", true); 
}
updateUIState();
requestAnimationFrame(smoothingLoop);