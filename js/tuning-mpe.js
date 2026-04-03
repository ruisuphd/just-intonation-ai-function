// MPE Microtuning - per-note pitch bend via channel rotation
// Fallback when MTS SysEx is not available

export const MPE_MASTER_CHANNEL = 0;
export const MPE_MEMBER_CHANNELS = Array.from({ length: 15 }, (_, i) => i + 1);

let channelPool = [...MPE_MEMBER_CHANNELS];
let activeNotes = new Map();
let channelUsageOrder = [];
let pitchBendRangeInitialized = false;

export function resetMPEState() {
    channelPool = [...MPE_MEMBER_CHANNELS];
    activeNotes = new Map();
    channelUsageOrder = [];
    pitchBendRangeInitialized = false;
}

export function isPitchBendRangeInitialized() {
    return pitchBendRangeInitialized;
}

// Set pitch bend range to ±2 semitones on all MPE channels using RPN 0
export function initializePitchBendRange(midiOutput) {
    if (!midiOutput) {
        console.warn('Cannot initialize MPE pitch bend range: no MIDI output');
        return false;
    }
    
    if (pitchBendRangeInitialized) {
        console.log('MPE pitch bend range already initialized');
        return true;
    }
    
    console.log('Initializing MPE pitch bend range (±2 semitones)...');
    
    try {
        for (const channel of MPE_MEMBER_CHANNELS) {
            midiOutput.send([0xB0 | channel, 101, 0]);    // RPN MSB = 0
            midiOutput.send([0xB0 | channel, 100, 0]);    // RPN LSB = 0
            midiOutput.send([0xB0 | channel, 6, 2]);      // Data Entry MSB = 2 semitones
            midiOutput.send([0xB0 | channel, 38, 0]);     // Data Entry LSB = 0
            midiOutput.send([0xB0 | channel, 101, 127]);  // Reset RPN to null
            midiOutput.send([0xB0 | channel, 100, 127]);
        }
        
        pitchBendRangeInitialized = true;
        console.log('MPE pitch bend range set to ±2 semitones');
        return true;
    } catch (error) {
        console.error('Failed to initialize MPE pitch bend range:', error);
        return false;
    }
}

// LRU channel allocation
export function allocateChannel(noteId) {
    if (!noteId) return null;
    
    if (activeNotes.has(noteId)) {
        const index = channelUsageOrder.indexOf(noteId);
        if (index > -1) channelUsageOrder.splice(index, 1);
        channelUsageOrder.push(noteId);
        return activeNotes.get(noteId);
    }
    
    let channel = channelPool.length > 0 ? channelPool.shift() : null;
    let reusedNoteId = null;
    
    // All channels busy - steal the oldest one
    if (channel === null && channelUsageOrder.length > 0) {
        reusedNoteId = channelUsageOrder.shift();
        channel = activeNotes.get(reusedNoteId);
        activeNotes.delete(reusedNoteId);
        activeNotes.set(noteId, channel);
        channelUsageOrder.push(noteId);
        
        console.warn(`Channel pool exhausted. Reusing channel ${channel}`);
        return { channel, reusedNoteId };
    }
    
    if (channel !== null) {
        activeNotes.set(noteId, channel);
        channelUsageOrder.push(noteId);
    }
    
    return channel;
}

export function releaseChannel(noteId) {
    if (!noteId) return;
    if (!activeNotes.has(noteId)) return;
    
    const channel = activeNotes.get(noteId);
    activeNotes.delete(noteId);
    
    const index = channelUsageOrder.indexOf(noteId);
    if (index > -1) channelUsageOrder.splice(index, 1);
    
    if (channel !== null && !channelPool.includes(channel) && channel !== MPE_MASTER_CHANNEL) {
        channelPool.push(channel);
        channelPool.sort((a, b) => a - b);
    }
}

export function getChannelForNote(noteId) {
    return activeNotes.has(noteId) ? activeNotes.get(noteId) : null;
}

// Returns number of bytes sent (3 for pitch bend)
export function sendPitchBend(midiOutput, channel, bendValue) {
    if (!midiOutput || channel === null || typeof channel === 'undefined') return 0;
    
    const clamped = Math.max(-8192, Math.min(8191, bendValue));
    const bend = clamped + 8192;
    const lsb = bend & 0x7F;
    const msb = (bend >> 7) & 0x7F;
    
    midiOutput.send([0xE0 | channel, lsb, msb]);
    return 3;
}

export function sendNoteOn(midiOutput, channel, note, velocity) {
    if (!midiOutput) return 0;
    midiOutput.send([0x90 | channel, note, velocity]);
    return 3;
}

export function sendNoteOff(midiOutput, channel, note) {
    if (!midiOutput) return 0;
    midiOutput.send([0x80 | channel, note, 0]);
    return 3;
}

export function getMPEState() {
    return {
        availableChannels: channelPool.length,
        activeNoteCount: activeNotes.size,
        pitchBendRangeInitialized,
        channelPool: [...channelPool],
        activeNotes: Object.fromEntries(activeNotes)
    };
}
