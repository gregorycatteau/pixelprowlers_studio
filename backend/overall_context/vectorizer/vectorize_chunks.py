import argparse
import json
import time
from pathlib import Path

from overall_context.vectorizer.engines.engine_selector import get_embedder
from overall_context.vectorizer.logger import log_vectorization_run


def vectorize_chunks(chunk_file: Path, output_file: Path, mode: str = "low"):
    start = time.time()

    chunks = json.loads(chunk_file.read_text(encoding="utf-8"))
    embedder = get_embedder(mode=mode)
    texts = [chunk["text"] for chunk in chunks]

    try:
        embeddings = embedder.embed_texts(texts)
        for i, emb in enumerate(embeddings):
            chunks[i]["embedding"] = emb
        output_file.write_text(json.dumps(chunks, indent=2, ensure_ascii=False))
        duration = time.time() - start
        print(f"✅ {len(chunks)} chunks vectorisés en mode `{mode}` → {output_file}")

        # Log du run
        log_vectorization_run(
            zone_id=chunk_file.stem.replace("_chunks", ""),
            mode=mode,
            engine=embedder.__class__.__name__,
            source_file=chunk_file,
            output_file=output_file,
            vector_count=len(chunks),
            duration=duration,
            status="success",
        )

    except Exception as e:
        duration = time.time() - start
        print(f"❌ Erreur de vectorisation : {e}")

        # Log d'échec
        log_vectorization_run(
            zone_id=chunk_file.stem.replace("_chunks", ""),
            mode=mode,
            engine=embedder.__class__.__name__,
            source_file=chunk_file,
            output_file=output_file,
            vector_count=0,
            duration=duration,
            status="error",
            error=str(e),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vectorise les chunks d’une zone du CDN.")
    parser.add_argument(
        "--input",
        type=str,
        required=False,
        default="cdn_zones/Z1_chunks.json",
        help="Chemin vers le fichier de chunks JSON",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=False,
        default="cdn_zones/Z1_vectorized.json",
        help="Chemin de sortie du fichier vectorisé",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["low", "secure", "fortress"],
        default="low",
        help="Mode de vectorisation (low | secure | fortress)",
    )

    args = parser.parse_args()

    base_path = Path(__file__).resolve().parent.parent.parent
    input_file = base_path / args.input
    output_file = base_path / args.output

    vectorize_chunks(input_file, output_file, mode=args.mode)
