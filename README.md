# Instant Harmonies - Just Intonation Tuner

A real-time just intonation tuning system for MIDI keyboards. It listens to what you play, figures out the key, and applies pure interval tuning on the fly.

The interesting part: if you're playing a known piece (from the ATEPP dataset), it can identify the piece from the first few notes and use the actual key signatures from the score for more accurate tuning.

## What it does

- **Live tuning** - Plug in a MIDI keyboard, hit play, and hear just intonation instead of equal temperament
- **Key detection** - Uses an ensemble of three algorithms (Albrecht-Shanahan, Temperley, Krumhansl-Kessler) to figure out what key you're in
- **Optional AI harmonic tracking** - If a harmonic-model checkpoint is present, the Python backend can provide confidence-gated local-key predictions for the unknown-piece path
- **Piece identification** - If you're playing something from ATEPP, it'll recognize it and pull the real key signatures from the MusicXML score
- **Score following** - Once it knows the piece, it tracks where you are and predicts upcoming notes
- **File tuning** - Drop in a MIDI file, and it'll export a tuned version (MIDI 1.0 with MTS or MIDI 2.0)
- **Recording** - Record your performance with JI tuning baked in

## How it works

```
┌────────────────────────────────────────────────────────────────┐
│                        Web Frontend                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐│
│  │   MIDI   │  │   Key    │  │  Tuning  │  │    Recording     ││
│  │  Input   │  │Detection │  │  Engine  │  │    & Export      ││
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────────┬─────────┘│
└───────┼─────────────┼─────────────┼─────────────────┼──────────┘
        │             │             │                 │
        └─────────────┴──────┬──────┴─────────────────┘
                             │ WebSocket
        ┌────────────────────┴────────────────────┐
        │         Two-Stage Python Server         │
        │  ┌──────────────┐  ┌──────────────────┐ │
        │  │  Fingerprint │  │  Score Following │ │
        │  │ Identification│  │   (Parangonar)  │ │
        │  └──────────────┘  └──────────────────┘ │
        └─────────────────────────────────────────┘
```

The frontend handles MIDI I/O and basic key detection. When the Python server is running, it adds piece identification (via n-gram fingerprinting) and score following (via Parangonar).

## Getting started

You'll need Python 3.9+ and a browser that supports Web MIDI (Chrome or Edge work best).

```bash
git clone https://github.com/rsu0/Instant_Harmonies.git
cd Instant_Harmonies
pip install -r requirements.txt
```

### Running it

**Simplest way** - Just open `index.html` in your browser. You get live tuning and key detection, but no piece identification.

**Full system** - Run the backend too:
```bash
./start_all.sh
```
This starts both the Python server and a local web server. Open http://localhost:8000.

**Manual startup** (if the script doesn't work):
```bash
python two_stage_server.py --port 5005
# Then open index.html in your browser
```

Optional harmonic-model runtime:

```bash
python two_stage_server.py --port 5005 --harmonic-checkpoint research_data/harmonic_context_model.pt
```

If the checkpoint is missing, the backend keeps running and falls back to the classical score-free path.

### Setting up piece identification (optional)

If you want the system to recognize pieces and use their actual key signatures:

1. Get the ATEPP dataset and put it in `ATEPP_JI_Dataset/ATEPP-1.2/`
2. Build the fingerprint database:
   ```bash
   python build_atepp_fingerprint_db.py
   ```
   This takes 10-15 minutes and creates a ~100MB database.

## Using it

### Live tuning
1. Connect your MIDI keyboard
2. Select input/output in the web UI
3. Hit "Start"
4. Play something - the key display updates as you go

### Tuning a MIDI file
1. Click "Select MIDI File"
2. Choose auto-detect or pick a key manually
3. Click "Apply Tuning"
4. Download the result

### Recording
1. Click "Record" and play
2. Click "Stop" when done
3. Download as MIDI 1.0 (with MTS tuning) or MIDI 2.0

## Tuning modes

The system supports two ways of sending microtuning data:

- **MTS** (MIDI Tuning Standard) - Uses SysEx messages. High precision but not all synths support it.
- **MPE** (MIDI Polyphonic Expression) - Uses per-channel pitch bend. Works with more synths but slightly less precise.

It tries MTS first and falls back to MPE if needed. You can also switch manually.

## Project layout

```
index.html                     - Main UI
js/
  main.js                      - App orchestration
  key-detection.js             - Ensemble key detection
  tuning-core.js               - JI ratio math
  tuning-mts.js, tuning-mpe.js - Tuning output modes
  midi-*.js                    - MIDI parsing/writing/recording
  audio-engine.js              - Built-in synth (Salamander samples)

two_stage_server.py            - Python backend for piece ID + score following
simple_ngram_fingerprinting.py - Fingerprint algorithm
```

## Dependencies

Python side: Flask, Flask-SocketIO, Parangonar, Partitura, pretty_midi, PyTorch

JavaScript: Vanilla ES6, no build step needed

## Credits

- [Parangonar](https://github.com/sildater/parangonar) for score following
- [Partitura](https://github.com/CPJKU/partitura) for MusicXML parsing
- ATEPP dataset for the piano performance data

## License

MIT
