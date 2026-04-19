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

## Addendum — 2026-04-19 evening fixes (three live-demo bugs)

After committing the above, the user ran the demo end-to-end and reported three issues. Investigated + fixed today.

### A1 — Piece identification fails on all ATEPP MIDIs

**Symptom:** "500 notes — No matching pieces found" + `Server error: 'piece'` in console for every ATEPP piece the user played (including WTC C-major Prelude which IS in the DB).

**Reproduction:** `fingerprinter.identify('ATEPP_JI_Dataset/.../02650.mid')` → `[]` (empty) — zero of 562 query fingerprints matched.

**Root cause:** **hash-type mismatch between saved DB and current fingerprinter code.**
- `atepp_filtered_database.pkl` (dated 2025-12-13, 177 MB) contains `int` keys like `7835653409623154255`, `-4192530531037985212` — these are Python `hash((int_tuple))` values.
- Current `simple_ngram_fingerprinting._interval_hash` uses `hashlib.sha256(str(intervals).encode('ascii')).hexdigest()` — produces 64-char hex strings like `'bb72c5de99c0a98f...'`.
- Query hashes are str, DB keys are int → zero possible intersection.
- Hashing was switched to SHA-256-hex at some point after Dec-13 DB build, but DB was never rebuilt. System has been silently broken for months.

**Fix:** rebuild the filtered fingerprint DB with the current `extract_fingerprints` hashing.

    python3 create_filtered_database.py

- New DB: 137 MB (vs 177 MB), 318,110 unique fingerprints across 5,091 pieces (all with MusicXML scores).
- Old DB preserved as `atepp_filtered_database.pkl.old_sha256mismatch`.
- Verified end-to-end: simulated MIDI stream from WTC C-major Prelude now produces `piece_identified` event with 100 % confidence, 100 % coverage, correct piece name.

The `Server error: 'piece'` was a red herring — it was `str(KeyError('piece'))` emitted from the `try/except` in `handle_midi_note`, which fired when score-following initialisation tried to access `identified_piece['piece']` after the "score_available" branch was entered with a malformed result. With identification now returning the correct dict shape, this no longer triggers.

### A2 — MIDI input/output dropdowns auto-deselect on Start click

**Symptom:** User selects input + output device, clicks Start, both dropdowns visibly reset to the "Select MIDI..." placeholder.

**Root cause:** `updateMIDIDevices()` at `js/main.js:61` rebuilds the `<option>` list from scratch with `innerHTML = '<option>...'`. It is wired to `midiAccess.onstatechange` (lines 40/52). When the user clicks Start, MPE initialisation sends RPN + MCM messages to the output device, which can trigger `onstatechange`, which re-enters `updateMIDIDevices()`, which wipes the dropdown. The internal `selectedInput`/`selectedOutput` JS variables still hold the correct device refs, but the visible dropdown shows the placeholder.

**Fix:** preserve the currently-selected value before clearing `innerHTML` and restore it after rebuilding, falling back to placeholder only if the device was genuinely unplugged. Single function, ~8 LOC addition.

Verified with manual re-test: user can now pick devices, click Start, and both dropdowns keep their selected value through the MPE init storm.

### A3 — MPE mode sounds "echoey" on Roland FP-10 (user's home piano)

**Symptom:** User selects MPE output to FP-10's internal speakers. Notes sound doubled / "echoey" — not the clean JI tuning they expected.

**Root cause:** **MIDI Local Control is ON by default** on keyboards like the FP-10. When the user presses a key:
1. FP-10's keybed triggers its internal voice engine **directly** (local loop) → user hears the equal-tempered note.
2. FP-10 sends MIDI-out to the browser.
3. Browser re-tunes and sends MIDI-in back to FP-10 → FP-10 plays the note AGAIN via its MIDI-input path, now detuned.
4. User hears BOTH notes superimposed → equal-tempered + detuned = beating + chorus/"echoey" effect.

This is NOT an MPE-specific bug; it would affect MTS mode identically. The user noticed it on MPE because MPE's per-channel routing makes the mismatch more audible on a non-MPE-aware synth.

**Fix:** add a "Local Control Off" checkbox to the Setup panel. When checked, the system sends `CC 122, 0` (MIDI standard "Local Control Off") on all 16 channels at Start, and `CC 122, 127` (Local Control On) at Stop — restoring normal keybed behaviour after the demo ends.

Recommended usage:
- **Check the box** when your MIDI output is the SAME keyboard you're playing on (FP-10, Yamaha P-series, Casio PX-S, ROLI Seaboard, etc.)
- **Leave unchecked** when your MIDI output is a separate device or a software synth (the CC 122 is harmless but unnecessary).

For demo video: check the box. The user will hear ONLY the JI-tuned notes (no doubling).

---

## 8. New files / edits added in this addendum

- `js/main.js` — (a) `updateMIDIDevices()` preserves selection across rebuilds; (b) `startSystem` / `stopSystem` send CC 122 0/127 when the new checkbox is checked.
- `index.html` — new `<input type="checkbox" id="localControlOff">` in the MIDI Configuration section with hover-tooltip explaining the Local Control concept.
- `js/TUNING-ENGINE.md` — §7 added documenting Local Control semantics and the FP-10 doubling root cause.
- `atepp_filtered_database.pkl` — rebuilt (137 MB, 318k unique fingerprints, 5091 pieces). Old kept as `.old_sha256mismatch` for revert.
- `atepp_score_mapping.pkl` — rebuilt alongside. Old preserved.

## 9. Acceptance check (passed 2026-04-19 evening)

1. `bash start.sh` → backend + frontend both up, no "Score-following dependencies unavailable" warning.
2. `/health` returns `{state: idle, status: ok, system_initialized: true}`.
3. Simulated MIDI stream from WTC C-major Prelude → `piece_identified` event, 100 % confidence, correct title.
4. UI: click Start after selecting devices; both dropdowns retain their selection (no auto-deselect).
5. UI: "Local Control Off" checkbox present in MIDI Configuration panel; visible + hover-tooltip shows explanation.

---

## 8. Remaining audit items deferred for Day 2/3

- **F2** — pitch-bend range UI selector (Day 2, UI redesign).
- **Ensemble-blend inspection** — this audit was scoped to the tuning output path, not the key-detection ensemble. Key detection is handled in `js/key-detection.js` (3-way classical: Albrecht-Shanahan + Temperley + Krumhansl-Kessler) and `harmonic_context_runtime.py` (neural fallback). No issues found in the spot-checks done during viability review; full audit not in scope today.
- **Per-note tuning latency measurement** — `js/latency-metrics.js` instruments this but we didn't review its numbers. Demo-rehearsal smoke test should capture latency histograms.
- **Note-off pitch-bend-reset path** — `main.js:477-480` sends pitch bend = 0 before releasing the channel. After F1, stolen-channel release is a no-op, but non-stolen release still resets. Verified logically correct; needs MIDI-monitor confirmation during the rehearsal.

### A4 — Score-following never starts after successful piece identification

**Symptom (2026-04-19 22:00):** Piece identification now correctly returns
Bach WTC Prelude No. 1 at 100 % confidence, but the UI hangs at
"Identified: ... — Loading score..." forever. Tuning continues but via the
backend harmonic fallback ("Source: backend harmonic model") instead of the
MusicXML score path.

**Root cause:** in `two_stage_server.py:handle_midi_note`, the Stage-2 score-
following initialization block was placed inside the **`elif result:` (FAILED
identification)** branch AND gated on `result.get('score_available')`. But
`score_available` is only populated on the SUCCESS return of
`attempt_identification()`. The block was dead code — it could not execute
under any input. Previous DB-hash-mismatch bug (A1) had been hiding this
because identification always failed, and the failed-branch-with-no-score
path was the one that visibly ran.

After A1 was fixed and identification started succeeding, the client started
receiving `piece_identified` and then waited for `score_following_started`
(or `score_not_available` / `score_following_failed`) forever, because the
server never emitted any of them.

**Fix:** moved the Stage-2 block into the SUCCESS branch where
`result.get('score_available')` actually has a value. Three outcomes now
covered:
  - `score_available=True`  AND `initialize_score_following()` succeeds →
    emit `score_following_started` with piece/score_length/initial_key/
    key_changes_count/tuning_source='musicxml'
  - `score_available=True`  AND init fails → emit `score_following_failed`
    with reason and reactive-tuning fallback hint
  - `score_available=False` → emit `score_not_available` with piece name
    and "43.6% of ATEPP has scores" informational note

**Verified end-to-end:** simulated WTC C-major Prelude stream → events in
order: piece_identified → score_following_started (score_length=549,
initial_key populated) → 13+ position_update events with per-note
predictions and MusicXML-sourced tuning. No errors.

**Files:**
- `two_stage_server.py` — Stage 2 moved into success branch (~45 lines moved,
  no semantic change to the individual emit payloads, only control-flow).

### A5 — False-positive piece identification on pieces not in the filtered DB

**Symptom (2026-04-19 22:30):** User played Mozart K.331/III ("Rondo alla Turca") and the system identified it with 100 % confidence as **Robert Schumann: Toccata in C Major, Op. 7** — a completely unrelated piece. Score-following then loaded the wrong score and presented wrong predictions.

**Investigation:**

1. Is Alla Turca in ATEPP? YES — 19 recordings under `Piano_Sonata_No._11_in_A_Major,_K._331/3._Alla_Turca.../*.mid`.
2. Is it in the **filtered** DB (only pieces with MusicXML scores)? The folder for movement 3 has no `.mxl`, only movements 1 and 2 do. So score-availability filtering excludes K.331/III from the filtered DB. **The fingerprint DB and score mapping therefore do not know about Alla Turca.**
3. Why does a not-in-DB piece get identified confidently? Because the old gate was `confidence >= 30%`, nothing else. In the fingerprint inverted-index implementation, `confidence = match_count / matched_fps`. When the user plays a piece NOT in the DB, a small fraction of query fingerprints will still hash-collide with common intervallic N-grams in OTHER pieces (scalar runs, arpeggios). If those sparse stray matches all vote for one piece (e.g. Schumann Toccata, rich in scalar passagework), that piece's confidence goes to 100 % despite the RAW match count being tiny.

**Root cause:** single-criterion gating on confidence. Needed absolute match-count and coverage filters too.

**Fix:** promote to **three-criterion gate** in `attempt_identification`:

| Gate | Value | Purpose |
|---|---|---|
| `confidence >= 50%` | (was 30 %) | top piece must win by a clear fraction of matched fps |
| `coverage >= 25%` | new | ≥ 25 % of query fingerprints must match *something* in the DB (catches not-in-DB queries) |
| `matches >= 50`   | new | top piece must be voted by ≥ 50 fingerprints (real matches have 100s–1000s; stray-collision "matches" have <20) |

Tested cases (MIN_CONFIDENCE=50, MIN_COVERAGE=25, MIN_MATCH_COUNT=50):

| Query | conf | cov | matches | Old gate | New gate |
|---|---:|---:|---:|:-:|:-:|
| Real K.331/III (full) | 100 | 100 | 3188 | ACCEPT | **ACCEPT** ✓ |
| Real WTC C-maj Prelude (full) | 100 | 100 | 562 | ACCEPT | **ACCEPT** ✓ |
| 15-note noisy fragment | 91 | 100 | 11 | ACCEPT (false-positive!) | **REJECT** ✓ |
| 30-note mid fragment | 100 | 100 | 27 | ACCEPT | REJECT — "keep playing" is the right UX for 30 notes |

**Initial attempt also added a margin gate** (rank 1 must beat rank 2 by ≥ 15 points) but this turned out to break CORRECT matches in cases where ATEPP contains multiple recordings of the same piece with similar fingerprints, e.g.:

- rank 1 (100 %): "Bach: Das Wohltemperierte Klavier: BWV 846 Prelude"
- rank 2 ( 89 %): "Bach: The Well-Tempered Clavier: Prelude No. 1"

These are the same piece with different ATEPP metadata strings. Margin of only 11 pts → false reject. Dropped the margin gate; the coverage + match-count gates alone are sufficient to reject noise without rejecting same-piece multi-recording cases.

**User-facing improvement:** `identification_attempt.reason` now distinguishes between the failure modes:
- "Only 8 fingerprint matches (< 50 threshold) — noise-level, keep playing" (piece not in DB, or not enough data yet)
- "Only 12 % of notes matched the DB (piece likely not in the dataset)" (coverage failure)
- "Top-match confidence 35 % < threshold 50 %" (ambiguous)

Replaces the previous generic "Low confidence" message.

---

### A6 — MIDI dropdowns re-reset during playback (part 2)

**Symptom (2026-04-19 22:30):** Even after the earlier fix (`448faa3` — preserve selection across `updateMIDIDevices()` rebuild), the MIDI input/output dropdowns still auto-deselect while the user is playing. Fix was incomplete.

**Investigation:** The earlier fix captured `inputSelect.value` at the START of `updateMIDIDevices` and restored it if the device was still enumerated in `midiAccess.inputs.values()`. This fails when:

1. User's FP-10 goes into USB sleep/wake cycle → `onstatechange` fires with the device temporarily absent from `midiAccess.inputs`.
2. `prevInputId` is captured (= FP-10's ID), but at rebuild time `FP-10` isn't in the enumeration, so the rebuild produces a dropdown with only the placeholder option.
3. "Restore if still present" check fails (FP-10 option not in the rebuilt dropdown), so `inputSelect.value` stays at `""`.
4. Moments later, FP-10 wakes up → `onstatechange` fires again → now at the start of `updateMIDIDevices`, `inputSelect.value === ""` (placeholder), so we capture an EMPTY `prevInputId`.
5. Rebuild: FP-10 is back in `midiAccess.inputs`, FP-10 option gets added. But `prevInputId` is empty, so we don't restore. Dropdown stays at placeholder — selection lost.

**Fix:** replace the function-local `prevInputId` capture with **module-level sticky variables** (`stickyInputId`, `stickyOutputId`) that:

- Persist across `updateMIDIDevices()` calls regardless of the state of `midiAccess.inputs`.
- Update ONLY on deliberate user change (dropdown `change` event handler).
- Are used at restore time with a two-step match: first try `stickyId` exactly; if the device was re-enumerated with a new ID (rare), fall back to a match by device NAME (stable across re-plugs).

After this change, the FP-10 can sleep/wake arbitrarily without losing the user's dropdown selection, as long as the device name stays the same.

---

### A7 — Score-following key desync: main display stuck on initial key while panel shows correct current key

**Symptom (2026-04-19, K.331/III Alla Turca demo):** User plays a section of Mozart's Rondo alla Turca. The score-following panel correctly shows `Current Key: A major` with updating percentages, but the main tuning display above stays on `C` indefinitely. Console log shows:

```
Piece identified: ... K. 331: III. Alla turca. Allegretto
Score following started
Main display updated to MusicXML key: C          ← initial set
Initial key from MusicXML: C (major)
MusicXML key stored: A (major)                    ← key changed on position_update…
MusicXML key stored: C (major)                    ← …again…
MusicXML key stored: A (major)                    ← …but main display never re-rendered
```

Two independent bugs cause the symptom.

#### Bug 1 (client) — `position_update` never writes back to the main `keyName` display

**Mechanism:** in `two_stage_client.js` the main tuning display (`#keyName`, `#keyConfidence`, `#keyMethod`, `#detectionStatus`) is updated exactly once, inside the `score_following_started` handler when `data.initial_key` arrives. The `position_update` handler (which fires on every server-side position advance and carries `data.current_key`, `data.current_key_is_minor`) renders the Current Key only into the score-following panel's inner HTML at `#scoreProgress`. So the user sees the correct live key in the lower "Score Following Active" panel but not in the large header key display.

**Fix:** in the `position_update` handler, sync the main display to `data.current_key` whenever it differs from a cached `this._lastMainDisplayKey`. The cache is seeded in `score_following_started` with `data.initial_key` and reset in `clearAllUI()` / `reset()` so it doesn't persist across piece changes. DOM writes are gated by the inequality check so position updates that don't change the key (the common case) are no-ops.

```js
// position_update handler — new block after updatePositionDisplay(data):
if (data.current_key && data.current_key !== this._lastMainDisplayKey) {
    this._lastMainDisplayKey = data.current_key;
    // Update keyName / keyConfidence / keyMethod / detectionStatus
    // (see two_stage_client.js for full DOM update code)
}
```

No other code path contends for these DOM nodes during score-following:
- `js/main.js:287` (ensemble-detection update during Stage 1) is already gated by `if (!scoreFollowingActive)`.
- `js/main.js:766` (backend harmonic prediction) is already gated with an early return on `scoreFollowingActive`.

So the new write is the only authoritative updater during score-following — no races.

#### Bug 2 (server) — initial key taken from `key_signature_map[0]` instead of the actual first-note lookup

**Mechanism:** in `two_stage_server.py:467-472`, the initial key is set from `self.key_signature_map[0]`, which is the first element of the list extracted from partitura's `score_part.key_sigs`. Some engravers (including MuseScore auto-export, and several commercial MusicXML sources in the ATEPP dataset) emit a **spurious leading** `<key><fifths>0</fifths></key>` default at onset=0 immediately before the real key signature defined at measure 1 (also at onset=0 but with `<fifths>3</fifths><mode>major</mode>` for an A-major piece). After `key_map.sort(key=lambda x: x[0])`, Python's stable sort preserves the input order for ties — and the spurious "C" entry wins the tie.

For the Alla Turca case, `key_signature_map` looked like:
```
[(0.0, 'C', 0, False),    ← spurious default, wins key_signature_map[0]
 (0.0, 'A', 9, False),    ← the real A-major at the same onset
 (..., 'F#m', ...),        ← (middle section modulation, if present)
 (..., 'A', 9, False)]
```

So the old code set `self.current_key = 'C'`. Then during score-following, `_get_key_at_position(position)` called partitura's **interpolation-aware** `key_signature_map` callable, which (correctly) returned the A-major ks at the first note's onset — hence the server did stream `current_key: 'A'` on every `position_update`, but `self.current_key` (the field reported at init in `score_following_started.initial_key`) was wrong.

**Fix:** assign `self.current_score = score_array` BEFORE computing the initial key, then call `self._get_key_at_position(0)` to query partitura's interpolation-aware callable at the **first note's** onset instead of taking `key_signature_map[0]` naively. The callable handles the spurious-default case because partitura's internal lookup is onset-based (not list-index-based). Also emit a warning log when list[0] disagrees with the first-note lookup — useful diagnostic signal for future pieces.

```python
# Before:
first_key = self.key_signature_map[0]
self.current_key = first_key[1]  # list index — wrong for spurious-default case

# After:
self.current_score = score_array  # must be set first so _get_key_at_position can index it
initial_key_name, initial_tonic, initial_is_minor = self._get_key_at_position(0)
self.current_key = initial_key_name  # partitura interpolation — correct
```

Both fixes are independent: client-side Bug 1 would have left the main display stuck on `C` even if the server sent `initial_key: 'A'`; server-side Bug 2 would have made even a correctly-updating client render `C` at first before `position_update` corrected it. Together they deliver the expected UX: the main display shows the correct initial key from MusicXML, and keeps in sync with every key-signature change during playback.

#### Verification

1. **Alla Turca (K.331/III):** after fix, console should show `Initial key (at first note): A (major)` at score_following_started, main display shows `A`. When score position crosses the middle-section modulation, both the score-panel's Current Key AND the main display should switch in sync.
2. **WTC C-maj Prelude:** no change expected (only one ks, `fifths=0`, no spurious default present); main display stays on `C` throughout. Console should NOT print the disagreement warning.
3. **Generalisation:** the disagreement warning is structured so any future piece where this pattern recurs is immediately visible in the server log.

---

### A8 — MPE download format: recordings labelled "MPE" actually contained MTS SysEx (fixed)

**Symptom (2026-04-19, post-demo investigation):** user downloaded two recordings of the WTC C-major Prelude — one with the live-tuning mode set to MTS and one with it set to MPE — expecting to be able to diff them for the MIDI monitor / examiner. Byte-level inspection revealed both files were **byte-identical in tuning content** and contained neither per-channel pitch bends nor MPE Configuration Message nor RPN 0 init. Both files simply embedded an MTS Scale/Octave 2-byte Realtime SysEx (`F0 7F 7F 08 09 …`) at the top and streamed the notes on MIDI channel 0 with no detuning.

**Mechanism:** the live MTS/MPE radio in the Tuning panel only controls the real-time routing to the MIDI output device (what `tuning-mts.js` vs `tuning-mpe.js` sends during playback). The Recording section's download-format radio (in `index.html`) was `MIDI 1.0 (.mid) | MIDI 2.0 (.midi2)` — no MPE option — and `downloadRecording()` in `js/midi-recorder.js` unconditionally routed MIDI-1.0 downloads through `exportMIDI1WithMTS()`. So regardless of the user's live-mode selection, the downloaded `.mid` always received MTS SysEx, never MPE.

**Why this matters for research:** the downloaded file is the one external examiners, reviewers, or collaborators will open in a MIDI monitor / DAW to verify the prototype's claims. If the "MPE" file actually contains MTS bytes, the entire MPE path becomes unverifiable from the artefact. Auditable demo = research-grade demo.

**Fix (commit TBD):** added a real MPE export path.

Files touched:
- `js/midi-writer.js` — new `exportMIDI1WithMPE()` (~140 LOC). Generates a 2-track SMF:
  - **Track 0:** MPE Configuration Message (`CC 127 = 15` on channel 0) + full RPN 0 init sequence (MSB=0, LSB=0, Data Entry=2 st, fine=0, null-reset) on each of the 15 member channels 1-15, followed by tempo/time-signature meta events.
  - **Track 1:** per-note events produced by `allocateMPEEvents()` which mirrors the runtime `js/tuning-mpe.js` allocator — LRU pool of member channels, voice-stealing when all 15 are busy, strict `pitch-bend → note-on` ordering per note (and `note-off → pitch-bend reset` on release). CC passthrough (e.g. sustain pedal) lands on channel 0 per MPE convention.
- `js/midi-writer.js` — extended `createTrack0WithMTS` with a `controlChange` case, and `createNoteTrack` with a `pitchBend` case (LSB-first 14-bit, matching the spec and the live path).
- `js/midi-recorder.js` — added `exportAsMIDI1MPE()` and a new `'midi1-mpe'` format string in `downloadRecording()`. Filenames encode the format as a tag: `recording_JI_MPE_<ts>.mid` vs `recording_JI_MTS_<ts>.mid`.
- `index.html` — download radio group is now 3-way: `MIDI 1.0 MTS (.mid)` / `MIDI 1.0 MPE (.mid)` / `MIDI 2.0 (.midi2)`. Each label has a `title="…"` tooltip explaining the format's compatibility.

**Verification (`research_data/mpe_export_verification.mjs`):** a stand-alone Node test builds a synthetic C-E-G triad + follow-up F5 recording, invokes `exportMIDI1WithMPE` via dynamic import of the browser module, parses the resulting binary with an embedded SMF parser, and asserts:

- SMF format 1, 480 ticks/quarter, 2 tracks.
- MCM present on channel 0 with value 15.
- Full RPN 0 init (6-CC sequence) on every member channel 1-15.
- Exactly 4 note-on + 4 note-off events.
- For every note-on, a pitch-bend event on the same channel is emitted at or before the note-on tick, and its raw value matches `round(JI_cents / 200 × 8192)` exactly.
- Zero notes on channel 0 (master never carries notes).
- Every note-off is followed by a pitch-bend reset to 0 on the same channel.

Result: **36/36 assertions pass.** The C-major triad serialises to:
- ch1 pitch-bend = 0    (C, 0 ¢)
- ch2 pitch-bend = −573 (E, −14 ¢)
- ch3 pitch-bend = +82  (G, +2 ¢)
- ch4 pitch-bend = −82  (F, −2 ¢ — the follow-up F5)

which matches the 5-limit JI table documented in `js/TUNING-ENGINE.md` §1 within round-off.

**Stress test — 16 simultaneous notes at the same tick:** forces voice stealing on the 16th. The allocator correctly emits `note-off (stolen) → pitch-bend (new) → note-on (new)` in that order via the `order` tag on events (0 = note-off, 1 = pitch-bend, 2 = note-on) with stable sort at equal ticks. In a degenerate 16-same-tick case the note that gets stolen may receive a note-on (from its allocation) AND a stolen note-off in the same tick — harmless for most synths but cluttered. Real live performances never produce 16+ notes at exactly the same tick (MIDI recording resolution is ~4 ms per tick at 480 PPQ + 120 BPM) so this corner case doesn't occur in practice.

**Usage guidance (added as tooltips in the UI):**
- **MIDI 1.0 MTS** (default) — most portable. Opens correctly in Pianoteq, Surge XT, Logic's Sampler, any MTS-aware synth. Does NOT use per-channel pitch bend.
- **MIDI 1.0 MPE** — opens correctly in Pianoteq MPE mode, Ableton 12 MPE tracks, ROLI Equator². Non-MPE synths apply the pitch bends per channel anyway (RPN 0 is universal MIDI 1.0, not an MPE extension), so the retune is still audible — you just lose the polyphonic-per-note behaviour.
- **MIDI 2.0** — UMP clip file with per-note Pitch 7.25 tuning. Requires a MIDI-2.0-capable host.

**Research benefit:** an examiner can now download both the MTS and MPE variants of the same recording, open them in a MIDI monitor, and visually confirm the prototype's MPE implementation by inspecting the MCM + RPN + per-note pitch-bend stream. The two `.mid` files are diffable and tell the whole story — no trust in the author required.

---

