from dataclasses import dataclass


@dataclass
class WarmupExercise:
    id: str
    name: str
    description: str
    target_pitch_range: list[float]
    duration_sec: int
    tempo: int
    difficulty: int


WARMUP_EXERCISES: list[WarmupExercise] = [
    WarmupExercise(
        id="straw_breathing",
        name="Straw Breathing",
        description="Blow or sing gently through a straw to coordinate breath and reduce throat tension. Builds support.",
        target_pitch_range=[150.0, 400.0],
        duration_sec=45,
        tempo=60,
        difficulty=1,
    ),
    WarmupExercise(
        id="lip_trills",
        name="Lip Trills",
        description="Relax the lips and trill on a comfortable pitch to warm up the vocal mechanism.",
        target_pitch_range=[200.0, 400.0],
        duration_sec=30,
        tempo=120,
        difficulty=1,
    ),
    WarmupExercise(
        id="ya_ya_ya_sirens",
        name="Raise Your Ya Ya Ya",
        description="Slide 'ya ya ya' smoothly from low to high and back. Opens the voice and connects registers without strain.",
        target_pitch_range=[200.0, 600.0],
        duration_sec=50,
        tempo=72,
        difficulty=1,
    ),
    WarmupExercise(
        id="humming_scales",
        name="Humming Scales",
        description="Hum ascending and descending scales to build resonance and pitch awareness.",
        target_pitch_range=[261.63, 523.25],
        duration_sec=45,
        tempo=80,
        difficulty=2,
    ),
    WarmupExercise(
        id="vowel_slides",
        name="Vowel Slides",
        description="Slide between vowels (ee-ah-oh) on a sustained pitch to develop vowel clarity.",
        target_pitch_range=[220.0, 440.0],
        duration_sec=40,
        tempo=60,
        difficulty=2,
    ),
    WarmupExercise(
        id="belt_mix_head",
        name="Belt, Mix & Head",
        description="Practice sustained notes in chest, then mix, then head voice. Smooth transitions, no flipping.",
        target_pitch_range=[200.0, 700.0],
        duration_sec=55,
        tempo=65,
        difficulty=3,
    ),
    WarmupExercise(
        id="octave_jumps",
        name="Octave Jumps",
        description="Jump an octave and sustain the upper note to develop register transitions.",
        target_pitch_range=[130.81, 523.25],
        duration_sec=35,
        tempo=72,
        difficulty=3,
    ),
    WarmupExercise(
        id="staccato_patterns",
        name="Staccato Patterns",
        description="Short, detached notes in patterns to sharpen articulation and rhythm.",
        target_pitch_range=[261.63, 523.25],
        duration_sec=40,
        tempo=100,
        difficulty=4,
    ),
    WarmupExercise(
        id="simple_riffs",
        name="Simple Riffs",
        description="Light melodic runs: 1-2-3-2-1 patterns. Build agility for riffs and runs.",
        target_pitch_range=[261.63, 659.25],
        duration_sec=45,
        tempo=90,
        difficulty=5,
    ),
]


def score_exercise(analysis: dict, exercise: WarmupExercise | dict) -> dict:
    if isinstance(exercise, dict):
        target_low = exercise.get("target_pitch_range", [0, 1000])[0]
        target_high = exercise.get("target_pitch_range", [0, 1000])[1]
        ex_id = exercise.get("id", "unknown")
    else:
        target_low, target_high = exercise.target_pitch_range
        ex_id = exercise.id

    pitch_hz = analysis.get("pitch_hz")
    cents = analysis.get("cents_deviation", 0.0)

    if pitch_hz and target_low and target_high:
        in_range = target_low <= pitch_hz <= target_high
        cent_penalty = min(abs(cents) / 50, 1.0)
        pitch_accuracy = (0.9 if in_range else 0.4) * (1 - cent_penalty * 0.3)
        pitch_accuracy = max(0, min(1, pitch_accuracy))
    else:
        pitch_accuracy = 0.5

    rhythm_score = analysis.get("rhythm_score")
    if rhythm_score is not None:
        rhythm_accuracy = float(rhythm_score)
    else:
        onset_detected = analysis.get("onset_detected", False)
        tempo = analysis.get("tempo")
        rhythm_accuracy = 0.6
        if onset_detected:
            rhythm_accuracy += 0.2
        if tempo is not None and 60 <= tempo <= 180:
            rhythm_accuracy += 0.2
        rhythm_accuracy = min(1.0, rhythm_accuracy)

    overall_score = 0.6 * pitch_accuracy + 0.4 * rhythm_accuracy

    return {
        "exercise_id": ex_id,
        "pitch_accuracy": pitch_accuracy,
        "rhythm_accuracy": rhythm_accuracy,
        "overall_score": overall_score,
    }
