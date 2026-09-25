# -*- coding: utf-8 -*-
"""Kiểm tra SigLIP2 TRƯỚC KHI push / bật cho cả nhóm dùng.

Chạy từ thư mục backend:
    python verify_siglip2.py
    python verify_siglip2.py --compare     # so thêm với CLIP (nạp thêm ~5GB)

KHÔNG nạp app, KHÔNG nạp beit3 — chỉ đụng đúng siglip2 (+ clip nếu --compare),
nên chạy nhanh và cô lập được lỗi.

Trả exit code 0 nếu mọi kiểm tra BẮT BUỘC đều qua, 1 nếu có cái hỏng.
"""
import os, sys, json, argparse

INDEX_DIR = os.environ.get("AIC_INDEX_DIR",
                           os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "app", "indexes"))
SIGLIP2_MODEL_ID = "google/siglip2-giant-opt-patch16-384"
SIGLIP2_DIM = 1536

QUERIES = [
    "a cyclist riding on a road",
    "a man speaking at a podium",
    "a crowd of people waving flags",
    "traffic on a city street at night",
]

ok_all = True
def check(label, ok, detail="", fatal=True):
    global ok_all
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}" + (f"  — {detail}" if detail else ""))
    if not ok and fatal:
        ok_all = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", action="store_true",
                    help="so top-K với CLIP để phát hiện lệch không gian vector")
    args = ap.parse_args()

    print("=" * 74)
    print(f"INDEX_DIR = {INDEX_DIR}")
    print("=" * 74)

    # ── 1. File có đúng chỗ không ────────────────────────────────────────────
    print("\n[1/6] File trong INDEX_DIR")
    if not os.path.isdir(INDEX_DIR):
        check("thư mục tồn tại", False, INDEX_DIR)
        return 1
    entries = sorted(os.listdir(INDEX_DIR))
    for e in entries:
        p = os.path.join(INDEX_DIR, e)
        sz = os.path.getsize(p) if os.path.isfile(p) else -1
        tag = "DIR " if os.path.isdir(p) else f"{sz/1e6:9.1f} MB"
        print(f"      {tag}  {e}")

    # Weights SigLIP2 PHẢI nằm trong INDEX_DIR, đúng quy ước repo: beit3 để
    # beit3_large_patch16_384_coco_retrieval.pth + beit3.spm ở đây, CLIP để
    # open_clip_model.safetensors ở đây. Lý do trong docstring
    # _ensure_clip_checkpoint(): cache mặc định của huggingface_hub không ổn
    # định (đổi ổ đĩa, venv mới, nhiều máy) -> tải lại 10GB và ăn rate-limit.
    model_src = None
    # (0) PHẲNG ngay trong INDEX_DIR — kiểu hay gặp nhất khi copy tay.
    #     Kiểm model_type để chắc config.json này là của SigLIP2.
    cfg0 = os.path.join(INDEX_DIR, "config.json")
    if os.path.exists(cfg0):
        try:
            with open(cfg0, encoding="utf-8") as f:
                c = json.load(f)
            blob = (str(c.get("model_type", "")) + " "
                    + " ".join(c.get("architectures") or [])).lower()
            if "siglip" in blob:
                model_src = INDEX_DIR
        except Exception:
            pass
    for cand in ("siglip2_giant_model", "siglip2-giant-opt-patch16-384"):
        if model_src:
            break
        p = os.path.join(INDEX_DIR, cand)
        if os.path.exists(os.path.join(p, "config.json")):
            model_src = p
            break
    if model_src is None:
        snap = os.path.join(INDEX_DIR,
                            "models--google--siglip2-giant-opt-patch16-384",
                            "snapshots")
        if os.path.isdir(snap):
            for sdir in sorted(os.listdir(snap)):
                p = os.path.join(snap, sdir)
                if os.path.exists(os.path.join(p, "config.json")):
                    model_src = p
                    break
    print()
    check("weights SigLIP2 có sẵn trong INDEX_DIR", model_src is not None,
          model_src if model_src else
          "chưa thấy -> lần chạy đầu preprocess sẽ tự tải ~3.5GB vào "
          "INDEX_DIR/siglip2_giant_model (không phải lỗi, chỉ là chậm 1 lần)",
          fatal=False)

    idx_p = os.path.join(INDEX_DIR, "siglip2_giant.index")
    map_p = os.path.join(INDEX_DIR, "siglip2_giant_mapping.json")
    check("siglip2_giant.index", os.path.isfile(idx_p))
    check("siglip2_giant_mapping.json", os.path.isfile(map_p))
    if not (os.path.isfile(idx_p) and os.path.isfile(map_p)):
        return 1

    # ── 2. transformers có hỗ trợ SigLIP2 không ─────────────────────────────
    print("\n[2/6] transformers")
    try:
        import transformers
    except ImportError as ex:
        # Hay gặp: huggingface_hub bị nâng lên 2.x trong khi transformers đang
        # cài pin <2.0 -> import transformers chết ngay, chưa đụng gì tới SigLIP2.
        print(f"  [FAIL] import transformers — {ex}")
        print("         CHỮA (chọn 1):")
        print('           pip install "huggingface_hub>=0.30,<2.0"   # giữ transformers hiện tại')
        print("           pip install -U transformers                # hoặc nâng transformers")
        return 1
    v = transformers.__version__
    parts = [int(x) for x in v.split(".")[:2] if x.isdigit()]
    check(f"transformers {v} >= 4.49", tuple(parts) >= (4, 49),
          "SigLIP2 được thêm từ 4.49" if tuple(parts) < (4, 49) else "")

    # ── 3. Index đọc được, đúng số chiều ────────────────────────────────────
    print("\n[3/6] FAISS index")
    import faiss, numpy as np
    index = faiss.read_index(idx_p)
    check(f"số chiều = {SIGLIP2_DIM}", index.d == SIGLIP2_DIM, f"đang là {index.d}")
    print(f"       ntotal = {index.ntotal:,} vector")

    with open(map_p, encoding="utf-8") as f:
        mapping = json.load(f)
    check("mapping khớp ntotal", len(mapping) == index.ntotal,
          f"mapping {len(mapping):,} vs index {index.ntotal:,}"
          if len(mapping) != index.ntotal else "")

    # Vector trong index phải đã L2-normalize (IndexFlatIP + cosine)
    v0 = index.reconstruct(0)
    n0 = float(np.linalg.norm(v0))
    check("vector ảnh đã L2-normalize", abs(n0 - 1.0) < 1e-3, f"|v0| = {n0:.6f}")

    # ── 4. Text encoder chạy được không ─────────────────────────────────────
    print("\n[4/6] Text encoder (nhánh CHƯA từng được chạy lúc index)")
    import torch
    from transformers import AutoProcessor, AutoModel
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if dev == "cuda" else torch.float32
    # Nạp từ thư mục local trong INDEX_DIR nếu có — đúng đường đi mà
    # preprocess._ensure_siglip2_model() dùng lúc chạy thật.
    src_model = model_src or SIGLIP2_MODEL_ID
    print(f"       nguồn model: {src_model}")
    proc = AutoProcessor.from_pretrained(src_model)
    try:
        model = AutoModel.from_pretrained(src_model, dtype=dtype)
    except TypeError:
        model = AutoModel.from_pretrained(src_model, torch_dtype=dtype)
    model = model.to(dev).eval()
    print(f"       device={dev} dtype={dtype}")

    @torch.no_grad()
    def enc(t):
        i = proc(text=[t], padding="max_length", truncation=True, return_tensors="pt")
        i = {k: x.to(dev) for k, x in i.items()}
        f = model.get_text_features(**i).float()
        return (f / f.norm(dim=-1, keepdim=True).clamp_min(1e-12)).cpu().numpy().astype("float32")

    q = enc(QUERIES[0])
    check("get_text_features chạy được", True)
    check(f"shape = (1, {SIGLIP2_DIM})", q.shape == (1, SIGLIP2_DIM), f"đang là {q.shape}")
    check("vector text đã L2-normalize", abs(float(np.linalg.norm(q)) - 1.0) < 1e-3)

    # ── 5. Search ra kết quả có hình dạng hợp lý ────────────────────────────
    print("\n[5/6] Search thử")
    ok_scores = True
    top_by_q = {}
    for text in QUERIES:
        D, I = index.search(enc(text), 5)
        names = [os.path.basename(mapping.get(str(int(i)), "")) for i in I[0]]
        top_by_q[text] = names
        s = D[0]
        print(f'       "{text}"')
        print(f"         score: {s[0]:.4f} .. {s[-1]:.4f}")
        for nm, sc in zip(names[:3], s[:3]):
            print(f"           {sc:.4f}  {nm}")
        # cosine hợp lệ phải nằm trong [-1, 1]; và top1 phải > top5 (có phân biệt)
        if not (-1.01 <= float(s[0]) <= 1.01) or float(s[0]) <= float(s[-1]):
            ok_scores = False
    check("score nằm trong [-1,1] và có phân biệt thứ hạng", ok_scores)

    # Query khác nhau phải ra kết quả khác nhau. Giống hệt nhau = text encoder
    # không thực sự ảnh hưởng -> gần như chắc chắn hỏng.
    firsts = [v[0] for v in top_by_q.values() if v]
    check("các query khác nhau cho top-1 khác nhau",
          len(set(firsts)) > 1,
          f"mọi query đều ra {firsts[0]!r} -> text encoder KHÔNG ăn vào kết quả")

    # ── 6. (tuỳ chọn) So với CLIP để bắt lệch không gian vector ─────────────
    if args.compare:
        print("\n[6/6] So chồng lấn video với CLIP")
        cidx_p = os.path.join(INDEX_DIR, "clip.index")
        cmap_p = os.path.join(INDEX_DIR, "clip_mapping.json")
        if not (os.path.isfile(cidx_p) and os.path.isfile(cmap_p)):
            print("       bỏ qua: thiếu clip.index / clip_mapping.json")
        else:
            import open_clip
            cidx = faiss.read_index(cidx_p)
            cmap = json.load(open(cmap_p, encoding="utf-8"))
            cm, _, _ = open_clip.create_model_and_transforms(
                "ViT-bigG-14", pretrained="laion2b_s39b_b160k")
            ctok = open_clip.get_tokenizer("ViT-bigG-14")
            cm = cm.to(dev).eval()

            @torch.no_grad()
            def cenc(t):
                f = cm.encode_text(ctok([t]).to(dev))
                return (f / f.norm(dim=-1, keepdim=True)).cpu().numpy().astype("float32")

            tot = 0.0
            for text in QUERIES:
                _, I = index.search(enc(text), 50)
                sv = {os.path.basename(mapping.get(str(int(i)), "")).split("-")[0]
                      for i in I[0]}
                _, J = cidx.search(cenc(text), 50)
                cv = {os.path.basename(cmap.get(str(int(j)), "")).split("-")[0]
                      for j in J[0]}
                ov = len(sv & cv) / max(1, len(sv | cv))
                tot += ov
                print(f'       "{text[:38]:38s}"  overlap video = {ov*100:5.1f}%')
            avg = tot / len(QUERIES)
            # Hai model tốt, cùng corpus, cùng query -> phải trùng ÍT NHẤT vài video.
            # 0% xuyên suốt = SigLIP2 đang tìm trong một không gian khác hẳn.
            check(f"chồng lấn TB {avg*100:.1f}% > 0", avg > 0.0,
                  "0% -> text embedding nhiều khả năng LỆCH không gian so với "
                  "image embedding đã index")
    else:
        print("\n[6/6] bỏ qua so sánh CLIP (thêm --compare để bật)")

    print("\n" + "=" * 74)
    print("KẾT LUẬN:", "ĐẠT — push được" if ok_all else "CÓ LỖI — xem dòng FAIL ở trên")
    print("=" * 74)
    print("\nLưu ý: script này KHÔNG khẳng định caption/kết quả ĐÚNG về ngữ nghĩa.")
    print("Nó chỉ chứng minh text encoder chạy, đúng chiều, có phân biệt query.")
    print("Bạn vẫn nên nhìn top-5 ở mục [5/6] xem có hợp lý bằng mắt không.")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())