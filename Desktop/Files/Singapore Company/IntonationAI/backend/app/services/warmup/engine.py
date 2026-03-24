import uuid

from app.services.llm.gemini import gemini_client
from app.services.llm.prompts import WARMUP_COMMENTARY_PROMPT
from app.services.warmup.exercises import WARMUP_EXERCISES, score_exercise


class WarmupEngine:
    def create_session(self, user_level: int = 1, full_library: bool = True) -> dict:
        max_difficulty = min(user_level + 1, 5)
        candidate = [
            {
                "id": e.id,
                "name": e.name,
                "description": e.description,
                "target_pitch_range": e.target_pitch_range,
                "duration_sec": e.duration_sec,
                "tempo": e.tempo,
                "difficulty": e.difficulty,
            }
            for e in WARMUP_EXERCISES
            if e.difficulty <= max_difficulty
        ]
        exercises = candidate[:3] if not full_library and len(candidate) > 3 else candidate
        if not exercises:
            take = 3 if not full_library else len(WARMUP_EXERCISES)
            exercises = [
                {
                    "id": e.id,
                    "name": e.name,
                    "description": e.description,
                    "target_pitch_range": e.target_pitch_range,
                    "duration_sec": e.duration_sec,
                    "tempo": e.tempo,
                    "difficulty": e.difficulty,
                }
                for e in WARMUP_EXERCISES[:take]
            ]
        return {
            "id": str(uuid.uuid4()),
            "exercises": exercises,
            "scores": [],
            "user_level": user_level,
            "started_at": None,
            "completed_at": None,
        }

    async def score_and_advance(
        self,
        session: dict,
        exercise_id: str,
        audio_analysis: dict,
    ) -> dict:
        exercise = next((e for e in session["exercises"] if e["id"] == exercise_id), None)
        if not exercise:
            raise ValueError(f"Exercise {exercise_id} not found in session")

        score = score_exercise(audio_analysis, exercise)
        scores = session.get("scores", []) + [score]
        session["scores"] = scores

        user_level = session.get("user_level", 1)
        overall = score["overall_score"]
        if overall > 0.8:
            user_level = min(user_level + 1, 5)
        elif overall < 0.5:
            user_level = max(user_level - 1, 1)
        session["user_level"] = user_level

        completed_idx = next(
            (i for i, e in enumerate(session["exercises"]) if e["id"] == exercise_id),
            -1,
        )
        next_exercise = None
        if completed_idx >= 0 and completed_idx + 1 < len(session["exercises"]):
            next_exercise = session["exercises"][completed_idx + 1]

        return {
            "score": score,
            "next_exercise": next_exercise,
            "session": session,
        }

    async def get_commentary(
        self,
        exercise_name: str,
        score: dict,
        next_exercise_name: str | None,
    ) -> str:
        prompt = WARMUP_COMMENTARY_PROMPT.format(
            exercise_name=exercise_name,
            pitch_accuracy=score.get("pitch_accuracy", 0),
            rhythm_accuracy=score.get("rhythm_accuracy", 0.8),
            overall_score=score.get("overall_score", 0.5),
            next_exercise=next_exercise_name or "none (session complete)",
        )
        messages = [{"role": "user", "content": prompt}]
        return await gemini_client.invoke(
            system_prompt="You are an encouraging vocal warm-up coach.",
            messages=messages,
            max_tokens=150,
        )


warmup_engine = WarmupEngine()
