"""FAISS-based semantic search over keyframe embeddings.

Encodes a text query with a sentence-transformer, searches the pre-built FAISS
index of keyframe embeddings, converts distances to a similarity percentage, and
returns the best-matching keyframe per video. Used by the ``/faiss-search`` endpoint.
"""
import os
import json
import numpy as np
import faiss
import pandas as pd
from sentence_transformers import SentenceTransformer

# Resolve data paths relative to this file so the app works regardless of CWD.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

def search_by_text_from_frames2(
    text,
    faiss_index_path=os.path.join(DATA_DIR, "faiss", "data.index"),
    json_decode_path=os.path.join(DATA_DIR, "decode_files", "image_mapping.json"),
    k_nearest=1000,
    nprobe=None,
    base_url="http://localhost:8000"
):
    """Find the keyframes most similar to a text query.

    The returned ``distance`` field is actually a similarity **percentage** so the
    frontend can display it directly as a percentage. The conversion depends on the
    index's metric (query vectors are L2-normalised beforehand):

    - L2 index:            sim% = (1 - d2 / 4) * 100
    - Inner-product index: sim% = (ip + 1) / 2 * 100

    Args:
        text: The natural-language query.
        faiss_index_path: Path to the FAISS index of keyframe embeddings.
        json_decode_path: Path to the JSON mapping of FAISS row id -> image path.
        k_nearest: Number of nearest neighbours to retrieve.
        nprobe: Optional FAISS ``nprobe`` (search breadth for IVF indexes).
        base_url: Base URL used to build absolute image URLs.

    Returns:
        A list of ``{frame, distance, url, name}`` dicts, one per video, sorted by
        descending similarity.
    """

    # Encode the query (768-D) and L2-normalise it.
    model = SentenceTransformer("all-mpnet-base-v2")
    q = model.encode([text], convert_to_numpy=True, show_progress_bar=False)
    q = q / np.linalg.norm(q, axis=1, keepdims=True)
    q = q.astype("float32")

    # Load FAISS index
    index = faiss.read_index(faiss_index_path)
    if nprobe is not None and hasattr(index, "nprobe"):
        index.nprobe = int(nprobe)

    try:
        metric = index.metric_type
    except Exception:
        metric = faiss.METRIC_L2

    # Load id => path mapping
    with open(json_decode_path, "r", encoding="utf-8") as f:
        id_to_path = json.load(f)

    # Search
    D, I = index.search(q, k_nearest)

    # Convert each distance to a similarity % and build the result rows.
    results = []
    for idx, d in zip(I[0], D[0]):
        path = id_to_path.get(str(idx))
        if not path:
            continue
        # Convert to a percentage based on the index metric.
        if metric == faiss.METRIC_INNER_PRODUCT:
            # Query is normalised, so the inner product is in [-1, 1].
            sim = (float(d) + 1.0) / 2.0 * 100.0
        else:
            # FAISS L2 returns d2 = ||x - y||^2; for unit vectors, d2 is in [0, 4].
            d2 = float(d)

            d2 = max(0.0, min(4.0, d2))
            sim = (1.0 - d2 / 4.0) * 100.0

        filename = os.path.basename(path)
        url = f"{base_url}/static/images/{filename}"
        results.append({
            "frame": filename,
            "distance": float(sim),   # similarity as a percentage
            "url": url,
            "name": filename,
            'video_name' : filename.split('-')[0]
        })

    # Build a DataFrame to aggregate the frame-level hits per video.
    results_df = pd.DataFrame(results)

    # Rank frames within each video by similarity (best first).
    results_df['rank'] = results_df.groupby('video_name')['distance'].rank(method='first', ascending=False)

    # Keep only the top-ranked frame per video.
    results_df = results_df[results_df['rank'] <= 1]

    # Preserve the original ordering.
    results_df = results_df.sort_index()

    # Sum the similarity of the kept frames within each video.
    results_df['distance'] = results_df.groupby('video_name')['distance'].transform('sum')

    # Sort videos by descending total similarity.
    results_df = results_df.sort_values(
    by=["distance", "video_name"],
    ascending=[False, True],
    kind="stable"
)

    # Return one row per video.
    results = results_df.drop(columns=['video_name', 'rank']).to_dict('records')
    return results
