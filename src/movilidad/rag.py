"""RAG: fragmentación del corpus, embeddings e índice FAISS.

Backend de embeddings (variable RAG_BACKEND):
- "fastembed" (por defecto): modelo multilingüe ONNX en CPU, se descarga una vez.
- "tfidf": TF-IDF de scikit-learn; respaldo sin descargas si fastembed falla.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CORPUS_DIR = Path(__file__).resolve().parents[2] / "corpus"
EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")


@dataclass
class Chunk:
    doc: str  # nombre del archivo, usado como cita
    title: str  # título del documento
    section: str
    text: str

    @property
    def citation(self) -> str:
        return f"[{self.doc} § {self.section}]"


def load_chunks(corpus_dir: Path = CORPUS_DIR) -> list[Chunk]:
    """Un fragmento por sección '## ' de cada markdown; el encabezado (fuentes) es su propio fragmento."""
    chunks = []
    for path in sorted(corpus_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title_m = re.search(r"^# (.+)$", text, re.M)
        title = title_m.group(1).strip() if title_m else path.stem
        parts = re.split(r"^## ", text, flags=re.M)
        head = parts[0].replace(f"# {title}", "").strip()
        if head:
            chunks.append(Chunk(path.name, title, "Fuentes", head))
        for part in parts[1:]:
            section, _, body = part.partition("\n")
            chunks.append(Chunk(path.name, title, section.strip(), body.strip()))
    if not chunks:
        raise RuntimeError(f"El corpus en {corpus_dir} está vacío.")
    return chunks


class _TfidfEmbedder:
    name = "tfidf"

    def __init__(self, texts):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.vec = TfidfVectorizer(strip_accents="unicode", lowercase=True, ngram_range=(1, 2), sublinear_tf=True)
        self.vec.fit(texts)

    def __call__(self, texts):
        return self.vec.transform(texts).toarray().astype("float32")


class _FastEmbedder:
    name = "fastembed"

    def __init__(self):
        from fastembed import TextEmbedding

        cache = Path(__file__).resolve().parents[2] / "cache" / "fastembed"
        self.model = TextEmbedding(EMBED_MODEL, cache_dir=str(cache))

    def __call__(self, texts):
        return np.array(list(self.model.embed(list(texts))), dtype="float32")


class DocIndex:
    def __init__(self, chunks: list[Chunk] | None = None, backend: str | None = None):
        import faiss

        self.chunks = chunks or load_chunks()
        texts = [f"{c.title}. {c.section}. {c.text}" for c in self.chunks]
        backend = (backend or os.getenv("RAG_BACKEND", "fastembed")).lower()
        self.embed = None
        if backend == "fastembed":
            try:
                self.embed = _FastEmbedder()
                vectors = self.embed(texts)
            except Exception as exc:  # sin internet para descargar el modelo, etc.
                print(f"[rag] fastembed no disponible ({exc}); se usa TF-IDF.")
                self.embed = None
        if self.embed is None:
            self.embed = _TfidfEmbedder(texts)
            vectors = self.embed(texts)
        self.backend = self.embed.name
        faiss.normalize_L2(vectors)
        self.index = faiss.IndexFlatIP(vectors.shape[1])  # similitud coseno
        self.index.add(vectors)

    def search(self, query: str, k: int = 4) -> list[dict]:
        import faiss

        if not query or not query.strip():
            raise ValueError("La consulta está vacía.")
        q = self.embed([query])
        faiss.normalize_L2(q)
        scores, ids = self.index.search(q, min(k, len(self.chunks)))
        out = []
        for s, i in zip(scores[0], ids[0]):
            if i < 0:
                continue
            c = self.chunks[i]
            out.append({"cita": c.citation, "documento": c.doc, "titulo": c.title, "seccion": c.section,
                        "score": round(float(s), 3), "texto": c.text})
        return out
