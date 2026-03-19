from app.services.rag.knowledge_base import KnowledgeBase, knowledge_base


class Retriever:
    def __init__(self, kb: KnowledgeBase) -> None:
        self._kb = kb

    async def retrieve_context(self, query: str, top_k: int = 3) -> str:
        if len(self._kb) == 0:
            return ""
        results = await self._kb.search(query, top_k=top_k)
        parts = []
        for i, r in enumerate(results, 1):
            parts.append(f"[Reference {i}]:\n{r['text']}")
        return "\n---\n".join(parts)


retriever = Retriever(knowledge_base)
