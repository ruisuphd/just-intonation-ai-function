// MIDI Writer - exports files with JI tuning embedded
// Supports MIDI 1.0 with MTS SysEx and MIDI 2.0 Clip File with Pitch 7.25

import { calculateMTSScaleTuning } from './midi-file-tuner.js';
import { centsToPitch725, encodePerNotePitch725UMP } from './tuning-midi2.js';

export function exportMIDI1WithMTS(tuningResult) {
    const { tunedNotes, keySegments, originalMidiData } = tuningResult;
    
    const trackNumbers = new Set();
    for (const note of tunedNotes) {
        trackNumbers.add(note.track || 0);
    }
    const noteTracks = Array.from(trackNumbers).sort((a, b) => a - b);
    const numNoteTracks = Math.max(noteTracks.length, 1);
    
    const chunks = [];
    
    chunks.push(createHeaderChunk(1, 1 + numNoteTracks, originalMidiData.ticksPerQuarterNote));
    
    let lastTick = 0;
    for (const n of tunedNotes) {
        if (n.endTick > lastTick) lastTick = n.endTick;
    }
    
    // Track 0: tempo, time signatures, MTS tuning changes
    const track0Events = [];
    
    for (const tempoChange of originalMidiData.tempoChanges) {
        track0Events.push({ tick: tempoChange.tick, type: 'tempo', tempo: tempoChange.tempo });
    }
    
    for (const timeSig of originalMidiData.timeSignatures) {
        track0Events.push({
            tick: timeSig.tick, type: 'timeSignature',
            numerator: timeSig.numerator, denominator: timeSig.denominator
        });
    }
    
    for (const segment of keySegments) {
        const mtsData = calculateMTSScaleTuning(segment.key);
        track0Events.push({
            tick: segment.startTick || 0, type: 'mtsScaleOctave',
            centsArray: mtsData, key: segment.key
        });
    }
    
    track0Events.sort((a, b) => a.tick - b.tick);
    track0Events.push({ tick: lastTick, type: 'endOfTrack' });
    
    chunks.push(createTrack0WithMTS(track0Events));
    
    // Note tracks
    for (let i = 0; i < numNoteTracks; i++) {
        const originalTrackNum = noteTracks[i];
        const trackEvents = [];
        
        for (const note of tunedNotes) {
            if ((note.track || 0) !== originalTrackNum) continue;
            
            trackEvents.push({
                tick: note.startTick, type: 'noteOn',
                channel: note.channel || 0, pitch: note.pitch, velocity: note.velocity
            });
            
            trackEvents.push({
                tick: note.endTick, type: 'noteOff',
                channel: note.channel || 0, pitch: note.pitch, velocity: 0
            });
        }
        
        if (originalMidiData.ccEvents) {
            for (const cc of originalMidiData.ccEvents) {
                trackEvents.push({
                    tick: cc.tick, type: 'controlChange',
                    channel: cc.channel || 0, controller: cc.controller, value: cc.value
                });
            }
        }
        
        trackEvents.sort((a, b) => a.tick - b.tick || (a.type === 'noteOff' ? -1 : 1));
        
        const trackLastTick = trackEvents.length > 0 
            ? Math.max(...trackEvents.map(e => e.tick)) : lastTick;
        trackEvents.push({ tick: trackLastTick, type: 'endOfTrack' });
        
        chunks.push(createNoteTrack(trackEvents));
    }
    
    const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const output = new Uint8Array(totalLength);
    let offset = 0;
    for (const chunk of chunks) {
        output.set(chunk, offset);
        offset += chunk.length;
    }
    
    return new Blob([output], { type: 'audio/midi' });
}

function createHeaderChunk(format, numTracks, ticksPerQuarter) {
    const chunk = new Uint8Array(14);
    const view = new DataView(chunk.buffer);
    
    chunk[0] = 0x4D; chunk[1] = 0x54; chunk[2] = 0x68; chunk[3] = 0x64; // MThd
    view.setUint32(4, 6, false);
    view.setUint16(8, format, false);
    view.setUint16(10, numTracks, false);
    view.setUint16(12, ticksPerQuarter, false);
    
    return chunk;
}

function createTrack0WithMTS(events) {
    const eventBytes = [];
    let prevTick = 0;
    
    for (const event of events) {
        const deltaTime = event.tick - prevTick;
        eventBytes.push(...encodeVariableLength(deltaTime));
        prevTick = event.tick;
        
        switch (event.type) {
            case 'tempo':
                eventBytes.push(0xFF, 0x51, 0x03);
                eventBytes.push((event.tempo >> 16) & 0xFF);
                eventBytes.push((event.tempo >> 8) & 0xFF);
                eventBytes.push(event.tempo & 0xFF);
                break;
            case 'timeSignature':
                eventBytes.push(0xFF, 0x58, 0x04);
                eventBytes.push(event.numerator);
                eventBytes.push(Math.log2(event.denominator));
                eventBytes.push(24, 8);
                break;
            case 'mtsScaleOctave':
                const sysexData = createMTSScaleOctaveSysExData(event.centsArray);
                eventBytes.push(0xF0);
                eventBytes.push(...encodeVariableLength(sysexData.length));
                eventBytes.push(...sysexData);
                break;
            case 'endOfTrack':
                eventBytes.push(0xFF, 0x2F, 0x00);
                break;
        }
    }
    
    return createTrackChunk(eventBytes);
}

function createMTSScaleOctaveSysExData(centsArray) {
    const data = [0x7F, 0x7F, 0x08, 0x09, 0x7F, 0x7F, 0x03];
    
    for (let i = 0; i < 12; i++) {
        const cents = centsArray[i];
        const clampedCents = Math.max(-100, Math.min(100, cents));
        const value14bit = Math.round(((clampedCents + 100) / 200) * 16383);
        const valueClamped = Math.max(0, Math.min(16383, value14bit));
        
        const msb = (valueClamped >> 7) & 0x7F;
        const lsb = valueClamped & 0x7F;
        data.push(msb, lsb);
    }
    
    data.push(0xF7);
    return data;
}

function createNoteTrack(events) {
    const eventBytes = [];
    let prevTick = 0;
    
    for (const event of events) {
        const deltaTime = event.tick - prevTick;
        eventBytes.push(...encodeVariableLength(deltaTime));
        prevTick = event.tick;
        
        switch (event.type) {
            case 'noteOn':
                eventBytes.push(0x90 | (event.channel & 0x0F));
                eventBytes.push(event.pitch & 0x7F);
                eventBytes.push(event.velocity & 0x7F);
                break;
            case 'noteOff':
                eventBytes.push(0x80 | (event.channel & 0x0F));
                eventBytes.push(event.pitch & 0x7F);
                eventBytes.push(0);
                break;
            case 'controlChange':
                eventBytes.push(0xB0 | (event.channel & 0x0F));
                eventBytes.push(event.controller & 0x7F);
                eventBytes.push(event.value & 0x7F);
                break;
            case 'endOfTrack':
                eventBytes.push(0xFF, 0x2F, 0x00);
                break;
        }
    }
    
    return createTrackChunk(eventBytes);
}

function createTrackChunk(eventBytes) {
    const chunkLength = eventBytes.length;
    const chunk = new Uint8Array(8 + chunkLength);
    const view = new DataView(chunk.buffer);
    
    chunk[0] = 0x4D; chunk[1] = 0x54; chunk[2] = 0x72; chunk[3] = 0x6B; // MTrk
    view.setUint32(4, chunkLength, false);
    chunk.set(new Uint8Array(eventBytes), 8);
    
    return chunk;
}

function encodeVariableLength(value) {
    if (value < 0) value = 0;
    
    const bytes = [];
    bytes.push(value & 0x7F);
    
    while (value > 0x7F) {
        value >>= 7;
        bytes.push((value & 0x7F) | 0x80);
    }
    
    return bytes.reverse();
}

export function exportMIDI2WithPitch725(tuningResult) {
    const { tunedNotes, keySegments, originalMidiData } = tuningResult;
    
    const packets = [];
    const ticksPerQuarter = originalMidiData.ticksPerQuarterNote;
    
    for (const note of tunedNotes) {
        const pitch725Value = centsToPitch725(note.pitch, note.centsDeviation);
        const pitch725UMP = encodePerNotePitch725UMP(note.channel || 0, note.pitch, pitch725Value);
        
        packets.push({ tick: note.startTick, order: 0, ump: pitch725UMP });
        
        const noteOnUMP = encodeMIDI2NoteOn(note.channel || 0, note.pitch, note.velocity);
        packets.push({ tick: note.startTick, order: 1, ump: noteOnUMP });
        
        const noteOffUMP = encodeMIDI2NoteOff(note.channel || 0, note.pitch);
        packets.push({ tick: note.endTick, order: 0, ump: noteOffUMP });
    }
    
    packets.sort((a, b) => a.tick - b.tick || a.order - b.order);
    
    const clipFile = buildMIDIClipFile(packets, ticksPerQuarter);
    return new Blob([clipFile], { type: 'audio/midi2' });
}

function encodeMIDI2NoteOn(channel, pitch, velocity) {
    const velocity16 = velocity << 9;
    
    const word1 = (0x4 << 28) | (0 << 24) | ((0x90 | (channel & 0x0F)) << 16) |
                  ((pitch & 0x7F) << 8) | 0x00;
    const word2 = (velocity16 << 16) | 0x0000;
    
    return new Uint32Array([word1, word2]);
}

function encodeMIDI2NoteOff(channel, pitch) {
    const word1 = (0x4 << 28) | (0 << 24) | ((0x80 | (channel & 0x0F)) << 16) |
                  ((pitch & 0x7F) << 8) | 0x00;
    const word2 = 0x00000000;
    
    return new Uint32Array([word1, word2]);
}

function buildMIDIClipFile(packets, ticksPerQuarter) {
    const headerSize = 16;
    const packetSize = 12;
    const totalSize = headerSize + (packets.length * packetSize);
    
    const buffer = new ArrayBuffer(totalSize);
    const view = new DataView(buffer);
    const bytes = new Uint8Array(buffer);
    
    const magic = "SMF2CLIP";
    for (let i = 0; i < 8; i++) {
        bytes[i] = magic.charCodeAt(i);
    }
    
    view.setUint32(8, 0x00010000, false);
    view.setUint16(12, ticksPerQuarter, false);
    view.setUint16(14, 0, false);
    
    let offset = headerSize;
    let prevTick = 0;
    
    for (const packet of packets) {
        const deltaTime = packet.tick - prevTick;
        prevTick = packet.tick;
        
        view.setUint32(offset, deltaTime, false);
        offset += 4;
        view.setUint32(offset, packet.ump[0], false);
        offset += 4;
        view.setUint32(offset, packet.ump[1], false);
        offset += 4;
    }
    
    return buffer;
}

export function downloadFile(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

export function generateOutputFilename(originalName, format) {
    const baseName = originalName.replace(/\.(mid|midi|midi2)$/i, '');
    return format === 'midi2' ? `${baseName}_JI.midi2` : `${baseName}_JI.mid`;
}
