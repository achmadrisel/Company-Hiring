from typing import List
import litellm
from app.core.config import get_settings

settings = get_settings()

class EmbeddingService:
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = settings.EMBEDDING_MODEL
        
        # litellm expects the 'openrouter/' prefix for OpenRouter models
        if not self.model.startswith("openrouter/"):
            self.model = f"openrouter/{self.model}"

    def encode(self, text: str) -> List[float]:
        """Encode single text to embedding vector"""
        response = litellm.embedding(
            model=self.model,
            input=[text],
            api_key=self.api_key
        )
        embedding = response.data[0]["embedding"]
        return embedding[:settings.EMBEDDING_DIM]

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """Encode multiple texts to embedding vectors"""
        response = litellm.embedding(
            model=self.model,
            input=texts,
            api_key=self.api_key
        )
        return [item["embedding"][:settings.EMBEDDING_DIM] for item in response.data]

embedding_service = EmbeddingService()
