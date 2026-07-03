# `data/` — runtime data & model artifacts

These files are **not committed to git** (too large / private) and must be provided
before running the backend. Place them exactly as shown below.

```
data/
├── temp.json                       # keyframe "database": one record per keyframe
│                                   #   { frame, content, ocr, object, color, action, ... }
├── classified_vocab.json           # classified vocabulary (optional; a copy is also
│                                   #   inlined in app/main.py)
├── decode_files/
│   └── image_mapping.json          # FAISS row id -> image path (used by /faiss-search)
└── faiss/
    ├── data.index                  # FAISS index of keyframe text/image embeddings
    └── image.index                 # auxiliary image index
```

The keyframe images referenced by these files live in `../static/images/` and are
served by the API at `GET /static/images/<filename>`.
