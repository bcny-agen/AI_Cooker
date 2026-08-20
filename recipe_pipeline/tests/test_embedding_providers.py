"""Model-specific local embedding adapter contracts."""

from recipe_pipeline.evaluation.embedding_providers import (
    SentenceTransformerEmbeddingProvider,
)


class _FakeArray:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return self._values


class _CapturingModel:
    def __init__(self):
        self.calls = []

    def encode(self, texts, **kwargs):
        self.calls.append((list(texts), kwargs))
        return [_FakeArray([1.0, 0.0]) for _ in texts]


def test_e5_uses_query_and_passage_prefixes():
    provider = SentenceTransformerEmbeddingProvider(
        "intfloat/multilingual-e5-small", dimensions=2
    )
    model = _CapturingModel()
    provider._model_instance = model

    provider.embed_queries(["番茄食谱"])
    provider.embed_documents(["番茄炒蛋"])

    assert model.calls[0][0] == ["query: 番茄食谱"]
    assert model.calls[1][0] == ["passage: 番茄炒蛋"]


def test_bge_zh_uses_retrieval_instruction_only_for_queries():
    provider = SentenceTransformerEmbeddingProvider(
        "BAAI/bge-small-zh-v1.5", dimensions=2
    )
    model = _CapturingModel()
    provider._model_instance = model

    provider.embed_queries(["番茄食谱"])
    provider.embed_documents(["番茄炒蛋"])

    assert model.calls[0][0] == [
        "为这个句子生成表示以用于检索相关文章：番茄食谱"
    ]
    assert model.calls[1][0] == ["番茄炒蛋"]
