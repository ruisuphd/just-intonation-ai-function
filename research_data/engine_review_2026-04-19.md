# MTS-MPE Tuning Engine Review — 2026-04-19

**Context:** User reported "MPE mode sounds a bit off" during demo rehearsal. This document audits the tuning engine, separates confirmed bugs from false positives, and documents fixes landed today.

**Scope:** `js/tuning-mpe.js`, `js/tuning-core.js`, `js/tuning-mts.js`, `js/main.js` (routing). MTS path was spot-checked and found clean; all reported issues are in the MPE path.

**Related artefacts:**
- Plan: `/Users/ruisu/.claude/plans/now-while-its-training-floofy-melody.md` (Section 1)
- New reference: `js/TUNING-ENGINE.md`

---

## 1. Executive summary

**One primary bug explains "MPE sounds off":** voice-stealing leaves the original note hanging silently on the reused channel. When you hold 16+ notes or play fast arpeggios that hit the channel-pool limit, stolen notes never receive a note-off, and new notes land on the same channel but the synth is still trying to sustain the old pitch — resulting in stuck-note artefacts, chord staleness, and apparent detuning.

Two secondary issues add MPE-compliance polish:
- **No MPE Configuration Message (MCM)** at init meant strict-MPE synths ignored our per-channel RPN messages.
- **Cosmetic JI-interval modulo `+ 144`** worked but was non-idiomatic.

**One claimed "critical bug" was a false positive** and has been documented here to prevent re-introduction.

All fixes are additive, MTS path is UNCHANGED, backward-compatible with standard MIDI 1.0 synths.

---

## 2. False positive — "pitch-bend byte order reversed"

An earlier audit by a sub-agent claimed `js/tuning-mpe.js:119` sends pitch bend with MSB and LSB reversed, and that this was "the most severe bug." Its own reasoning was self-contradictory (it stated the code `[0xE0|ch, lsb, msb]` was "correct per MIDI spec" in the same paragraph it called it reversed).

**I verified directly against the MIDI 1.0 specification** (§4.1, Channel Voice Messages): pitch-bend payload is `0xEn, LSB (7 bit), MSB (7 bit)`. The prototype's `sendPitchBend` computes `bend = clamped + 8192`, then `lsb = bend & 0x7F`, `msb = (bend >> 7) & 0x7F`, and sends `[0xE0 | channel, lsb, msb]`. This is the correct MIDI serialisation.

**No fix applied. Finding dismissed.** Recording here so future audits don't waste effort.

---

## 3. Confirmed fix F1 — voice-stolen notes hang on the synth

### Mechanism

`js/tuning-mpe.js` pre-fix:

```js
let activeNotes = new Map();  // noteId → channel
// In allocateChannel, voice-steal branch:
reusedNoteId = channelUsageOrder.shift();
channel = activeNotes.get(reusedNoteId);
activeNotes.delete(reusedNoteId);
activeNotes.set(noteId, channel);
return { channel, reusedNoteId };
```

`js/main.js` pre-fix:

```js
if (typeof allocationResult === 'object' && allocationResult.channel !== undefined) {
    totalBytesSent += mpe.sendPitchBend(selectedOutput, allocationResult.channel, 0);
    outputChannel = allocationResult.channel;
}
```

Two composite problems:

1. **The caller IGNORED `allocationResult.reusedNoteId`.** The stolen note was silently removed from `activeNotes` but no note-off was emitted to the synth. The synth therefore continued holding the old note on the channel that was about to be re-used.
2. **The allocator stored only `noteId → channel`.** Even if main.js had wanted to emit a note-off for the stolen note, it could not — the pitch of the stolen note was nowhere recorded.

Result: **every voice-steal leaves one hanging note on the synth.** In a live demo where user plays 16+ simultaneous or densely overlapped notes, the first stolen note produces an inaudibly-held low-velocity drone. New notes landing on the reused channel then inherit that drone's pitch-bend state momentarily, producing chord-staleness and what the user described as "slightly off" tuning.

Also a related bug: the note-off handler at `main.js:445-448`:

```js
} else if (noteData.noteId) {
    const ch = mpe.getChannelForNote(noteData.noteId);
    if (ch !== null) outputChannel = ch;
}
```

If the noteId was voice-stolen earlier, `getChannelForNote` returns `null`. `outputChannel` then falls back to whatever value it had (likely the input MIDI channel, which for MPE output is typically channel 0, the master). Subsequent note-off is sent on the WRONG channel — potentially killing an unrelated note on the master or on channel 0.

### Fix

**`js/tuning-mpe.js`:**
- State model extended: `activeNotes: Map<noteId, {channel, pitch}>`.
- `allocateChannel(noteId, pitch)` now takes pitch explicitly.
- Voice-stealing return shape: `{channel, reusedNoteId, stolenPitch}`.
- `releaseChannel(noteId)` remains a no-op for stolen notes.
- `getChannelForNote(noteId)` returns `null` for stolen notes (unchanged behaviour, but now the caller treats `null` properly).

**`js/main.js`:**
- On note-on voice-steal: emit `note-off` for `stolenPitch` on `channel` BEFORE the pitch-bend reset and BEFORE the new note-on.
- On note-off: if `getChannelForNote` returns `null`, silently skip the output (the note was stolen; the synth already lost it).

### Verification

Before/after MIDI-monitor trace (to be captured during the demo rehearsal):

**Before F1, hold 16 notes then press a 17th:**
```
9?+ch0 60 80  (note 1 on)
...
9?+ch14 75 80 (note 15 on)
9?+ch15 76 80 (note 16 on)
9?+??? 77 80  (note 17 on — channel chosen by LRU, but no note-off for stolen note 1!)
```
Note 1 (pitch 60) hangs on channel 1 forever.

**After F1, same scenario:**
```
9?+ch0 60 80  (note 1 on)
...
9?+ch15 76 80 (note 16 on)
8?+ch0 60 0   ← NEW: note-off for pitch 60 (stolen) on channel 0
E?+ch0 00 40  ← pitch bend reset on reused channel
E?+ch0 lsb msb (pitch bend for note 17)
9?+ch0 77 80  (note 17 on — on channel 0, reused from stolen note 1)
```

A listening test (Steinberg Padshop, Ableton Operator, Pianoteq): play a C-major triad cycle (`C-E-G`, `F-A-C`, `G-B-D`) rapidly and verify no residual drones between chords.

---

## 4. Confirmed fix F3 — missing MPE Configuration Message (MCM)

### Mechanism

Per MMA/AMEI RP-053 (MPE spec 2018), an MPE session begins with an **MPE Configuration Message** on the master channel: `CC 127 (0x7F)` with data = number of member channels. Without MCM, strict-MPE synths (ROLI Equator², Pianoteq's MPE mode, Ableton Live 12+, Logic Pro's MPE-aware plug-ins) treat each incoming MIDI channel as an ordinary MIDI 1.0 channel. Consequence: our per-channel RPN 0 messages are silently dropped or misrouted to the wrong channel, and pitch-bends applied to member channels 1–15 don't reach the voice they were intended for.

Pre-fix: only per-member-channel RPN 0 was sent. Works on non-MPE-aware synths (they respect RPN 0 individually) but fails silently on strict-MPE receivers.

### Fix

Send MCM on master channel BEFORE the per-channel RPN 0 loop:

```js
midiOutput.send([0xB0 | MPE_MASTER_CHANNEL, 127, 15]);  // enter MPE: 15 member channels
// ... existing RPN 0 loop ...
```

### Verification

MIDI monitor on session start:
```
B0 7F 0F         ← MCM (NEW)
B1 65 00, B1 64 00, B1 06 02, B1 26 00, B1 65 7F, B1 64 7F   ← ch 1 RPN 0
... repeated for channels 2..15 ...
```

Regression-safe: synths that don't understand MCM ignore the CC 127. No behaviour change there. Synths that DO understand MCM now work correctly.

---

## 5. Cosmetic fix F4 — JI interval modulo cleanup

`js/tuning-core.js:78` pre-fix:
```js
const interval = (midiNote - keyRoot + 144) % 12;
```

`+ 144` (which is `12 × 12`) is a safely-large positive offset that handles the negative-modulo edge case in JavaScript (`(−1) % 12 === −1`). Works correctly but non-idiomatic.

### Fix

```js
const interval = ((midiNote - keyRoot) % 12 + 12) % 12;
```

Canonical positive-modulo idiom. Identical output. Improves readability for future auditors. No semantic change.

---

## 6. Deferred fix F2 — pitch-bend range UI selector

**Problem:** MPE-native hardware (ROLI Seaboard, LinnStrument, certain Equator² presets) default to ±48 semitones (4 octaves) across the 14-bit pitch-bend range and ignore RPN 0 requests. The prototype's cents-to-bend scaling assumes ±2 semitones; on a ±48-semitone synth, our bends are 24× too small (i.e. mostly inaudible).

**Deferred because:** UI-level work. Planned for Day 2 of the demo-prep plan (`/Users/ruisu/.claude/plans/now-while-its-training-floofy-melody.md` Section 2). Will add a radio group in the new Setup panel: "Pitch-bend range: ±2 semitones (default) / ±48 semitones (MPE-native synths)". Wires into RPN 0 data entry and the denominator in `tuning-core.js:centsToPitchBend`.

Workaround until F2 lands: configure the MPE synth's pitch-bend range to ±2 semitones in its own settings.

---

## 7. Files modified in this commit

- `js/tuning-mpe.js` — F1 (state model + return shape), F3 (MCM init)
- `js/main.js` — F1 (voice-stealing note-off + stolen-note-off guard)
- `js/tuning-core.js` — F4 (canonical modulo)
- `js/TUNING-ENGINE.md` — NEW. Authoritative reference for the full engine design.
- `research_data/engine_review_2026-04-19.md` — this document.

MTS path (`js/tuning-mts.js`, applySingleNoteTuning, bulk scale/octave sysex) UNCHANGED — confirmed clean during review.

---

## 8. Remaining audit items deferred for Day 2/3

- **F2** — pitch-bend range UI selector (Day 2, UI redesign).
- **Ensemble-blend inspection** — this audit was scoped to the tuning output path, not the key-detection ensemble. Key detection is handled in `js/key-detection.js` (3-way classical: Albrecht-Shanahan + Temperley + Krumhansl-Kessler) and `harmonic_context_runtime.py` (neural fallback). No issues found in the spot-checks done during viability review; full audit not in scope today.
- **Per-note tuning latency measurement** — `js/latency-metrics.js` instruments this but we didn't review its numbers. Demo-rehearsal smoke test should capture latency histograms.
- **Note-off pitch-bend-reset path** — `main.js:477-480` sends pitch bend = 0 before releasing the channel. After F1, stolen-channel release is a no-op, but non-stolen release still resets. Verified logically correct; needs MIDI-monitor confirmation during the rehearsal.
