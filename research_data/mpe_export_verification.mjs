// Assertion-based verification of exportMIDI1WithMPE.
// Synthesizes a C-major triad recording, exports to MPE MIDI, parses the
// byte stream, and checks every required invariant of the MPE spec.

import fs from 'fs';
import path from 'path';

// Polyfill Blob for Node
globalThis.Blob = class {
    constructor(parts) {
        const u8s = parts.map(p => p instanceof Uint8Array ? p : new Uint8Array(p));
        const total = u8s.reduce((s, x) => s + x.length, 0);
        this._buf = new Uint8Array(total);
        let off = 0;
        for (const x of u8s) { this._buf.set(x, off); off += x.length; }
    }
    arrayBuffer() { return Promise.resolve(this._buf.buffer); }
    get size() { return this._buf.length; }
};

const { exportMIDI1WithMPE } = await import(
    path.resolve('/Users/ruisu/Desktop/ruisuphd/prototype090326AI-functions/js/midi-writer.js')
);

// --- Minimal SMF parser (enough for our events) --------------------------
function parseMIDI(buf) {
    let p = 0;
    function read(n) { const s = buf.slice(p, p + n); p += n; return s; }
    function readU32() { const v = (buf[p]<<24)|(buf[p+1]<<16)|(buf[p+2]<<8)|buf[p+3]; p += 4; return v >>> 0; }
    function readU16() { const v = (buf[p]<<8)|buf[p+1]; p += 2; return v; }
    function readVLQ() {
        let v = 0;
        while (true) { const b = buf[p++]; v = (v<<7) | (b & 0x7F); if ((b & 0x80) === 0) break; }
        return v;
    }

    // MThd
    const mthd = String.fromCharCode(...buf.slice(0, 4));
    if (mthd !== 'MThd') throw new Error('Not a MIDI file');
    p = 4;
    const hdrLen = readU32();
    const format = readU16();
    const numTracks = readU16();
    const ppq = readU16();
    p = 8 + hdrLen;

    const tracks = [];
    for (let t = 0; t < numTracks; t++) {
        const mtrk = String.fromCharCode(...buf.slice(p, p + 4));
        if (mtrk !== 'MTrk') throw new Error('Expected MTrk');
        p += 4;
        const trkLen = readU32();
        const end = p + trkLen;
        const events = [];
        let tick = 0;
        let running = null;
        while (p < end) {
            const dt = readVLQ();
            tick += dt;
            let status = buf[p];
            if (status < 0x80) { status = running; }
            else { running = status; p++; }
            if (status === 0xFF) {
                const type = buf[p++];
                const len = readVLQ();
                const data = buf.slice(p, p + len); p += len;
                events.push({ tick, type: 'meta', meta: type, data: Array.from(data) });
            } else if (status === 0xF0 || status === 0xF7) {
                const len = readVLQ();
                const data = buf.slice(p, p + len); p += len;
                events.push({ tick, type: 'sysex', data: Array.from(data) });
            } else {
                const hi = status & 0xF0;
                const ch = status & 0x0F;
                let d1, d2;
                d1 = buf[p++];
                if (hi === 0xC0 || hi === 0xD0) {
                    events.push({ tick, type: 'channel', status: hi, channel: ch, d1 });
                } else {
                    d2 = buf[p++];
                    if (hi === 0x90) events.push({ tick, type: 'noteOn', channel: ch, pitch: d1, velocity: d2 });
                    else if (hi === 0x80) events.push({ tick, type: 'noteOff', channel: ch, pitch: d1, velocity: d2 });
                    else if (hi === 0xB0) events.push({ tick, type: 'cc', channel: ch, controller: d1, value: d2 });
                    else if (hi === 0xE0) {
                        const biased = d1 | (d2 << 7);
                        events.push({ tick, type: 'pitchBend', channel: ch, raw: biased - 8192 });
                    }
                    else events.push({ tick, type: 'channel', status: hi, channel: ch, d1, d2 });
                }
            }
        }
        tracks.push(events);
        p = end;
    }
    return { format, ppq, tracks };
}

// --- Synthesize a simple recording --------------------------------------
const JI_CENTS = { 0: 0, 2: 4, 4: -14, 5: -2, 7: 2, 9: -16, 11: -12,
                   1: 12, 3: 16, 6: -10, 8: 14, 10: 18 };

function mkNote(pitch, startTick, endTick, velocity=64) {
    return {
        pitch, velocity, startTick, endTick, track: 0, channel: 0,
        centsDeviation: JI_CENTS[pitch % 12] || 0,
        key: 'C', keyRoot: 0,
    };
}

// C-major triad (C4 E4 G4, 480 ticks) + single F5 afterwards
const tunedNotes = [
    mkNote(60, 0, 480),
    mkNote(64, 0, 480),
    mkNote(67, 0, 480),
    mkNote(77, 480, 960),   // F5 alone on a fresh channel
];

const blob = exportMIDI1WithMPE({
    tunedNotes,
    keySegments: [{ key: 'C', startTick: 0 }],
    originalMidiData: {
        notes: tunedNotes,
        ticksPerQuarterNote: 480,
        tempoChanges: [{ tick: 0, tempo: 500000 }],
        timeSignatures: [{ tick: 0, numerator: 4, denominator: 4 }],
        ccEvents: [],
    }
});
const buf = new Uint8Array(await blob.arrayBuffer());
fs.writeFileSync('/tmp/verify_mpe_export.mid', buf);
console.log(`Wrote /tmp/verify_mpe_export.mid (${buf.length} bytes)`);

// --- Parse + assert ------------------------------------------------------
const { format, ppq, tracks } = parseMIDI(buf);
console.log(`Parsed: format=${format} ppq=${ppq} tracks=${tracks.length}`);

let failures = 0;
function assert(cond, msg) {
    if (cond) console.log('  OK  ' + msg);
    else { failures++; console.log('  FAIL ' + msg); }
}

// 1. File format
assert(format === 1, 'SMF format type = 1');
assert(ppq === 480, 'ticks/quarter = 480');
assert(tracks.length === 2, 'Two tracks (init + notes)');

// 2. Track 0 — MPE init
const t0 = tracks[0];
const mcm = t0.find(e => e.type === 'cc' && e.channel === 0 && e.controller === 127);
assert(!!mcm, 'MCM present (CC 127 on ch 0)');
assert(mcm && mcm.value === 15, `MCM value = 15 member channels (got ${mcm?.value})`);
assert(mcm && mcm.tick === 0, 'MCM at tick 0');

// RPN 0 init on each member channel 1..15
for (let ch = 1; ch <= 15; ch++) {
    const ccs = t0.filter(e => e.type === 'cc' && e.channel === ch && e.tick === 0);
    const has101_0   = ccs.some(e => e.controller === 101 && e.value === 0);
    const has100_0   = ccs.some(e => e.controller === 100 && e.value === 0);
    const has6_2     = ccs.some(e => e.controller === 6   && e.value === 2);
    const has38_0    = ccs.some(e => e.controller === 38  && e.value === 0);
    const has101_127 = ccs.some(e => e.controller === 101 && e.value === 127);
    const has100_127 = ccs.some(e => e.controller === 100 && e.value === 127);
    const all = has101_0 && has100_0 && has6_2 && has38_0 && has101_127 && has100_127;
    assert(all, `ch${ch}: full RPN 0 init (MSB=0, LSB=0, data=2, fine=0, reset 127/127)`);
}

// 3. Track 1 — per-note MPE events
const t1 = tracks[1];
const noteOns = t1.filter(e => e.type === 'noteOn');
const noteOffs = t1.filter(e => e.type === 'noteOff');
const bends = t1.filter(e => e.type === 'pitchBend');

assert(noteOns.length === 4, `4 note-ons emitted (got ${noteOns.length})`);
assert(noteOffs.length === 4, `4 note-offs emitted (got ${noteOffs.length})`);
// Each note-on should have a pitch-bend on the SAME channel emitted IMMEDIATELY before
for (const on of noteOns) {
    const prevBend = t1.filter(e =>
        e.type === 'pitchBend' && e.channel === on.channel && e.tick <= on.tick
    ).pop();
    assert(!!prevBend,
        `ch${on.channel}/pitch ${on.pitch} @ tick ${on.tick}: pitch-bend emitted before note-on`);
    const expectedCents = JI_CENTS[on.pitch % 12];
    const expectedRaw = Math.round(expectedCents / 200 * 8192);
    assert(prevBend && prevBend.raw === expectedRaw,
        `ch${on.channel}/pitch ${on.pitch}: bend = ${prevBend?.raw} (expected ${expectedRaw} for ${expectedCents}c)`);
}

// 4. No notes on channel 0 (master channel)
const masterNotes = noteOns.filter(e => e.channel === 0);
assert(masterNotes.length === 0,
    `No notes on channel 0 (master) — got ${masterNotes.length}`);

// 5. Each note-off followed (at or after) by a pitch-bend reset to 0 on the same channel
for (const off of noteOffs) {
    const resetBend = t1.find(e =>
        e.type === 'pitchBend' && e.channel === off.channel && e.tick >= off.tick && e.raw === 0
    );
    assert(!!resetBend,
        `ch${off.channel}/pitch ${off.pitch}: pitch-bend reset to 0 at/after note-off`);
}

// 6. Summary
console.log(`\n${failures === 0 ? 'ALL TESTS PASSED' : failures + ' TESTS FAILED'}`);
process.exit(failures === 0 ? 0 : 1);
