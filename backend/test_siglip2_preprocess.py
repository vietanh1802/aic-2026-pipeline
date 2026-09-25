# -*- coding: utf-8 -*-
"""Smoke test cho phần SigLIP2 trong preprocess.py — KHÔNG cần GPU, KHÔNG cần
weights 3.5GB, KHÔNG cần index thật 11GB.

Ý tưởng: dựng một bộ index/mapping/metadata GIẢ nhưng ĐÚNG HÌNH DẠNG thật
(cùng số chiều, cùng tên field, cùng quan hệ neighbors_clip), trỏ AIC_INDEX_DIR
vào đó, thay hàm encode_text_* bằng vector ngẫu nhiên, rồi chạy THẬT mọi đường
đi của preprocess: search -> rerank (Alg.2) -> ensemble (Alg.3) -> temporal
(Alg.4) -> TRAKE. Nếu code SigLIP2 có lỗi tích hợp thì nó nổ ở đây, trên máy
bạn, trong 2 giây — thay vì nổ lúc chạy thi.

Cố tình để SigLIP2 chỉ index MỘT PHẦN keyframe (giống thực tế index chưa chạy
xong) để kiểm luôn đường _fid_of() trả -1.

    cd backend
    python test_siglip2_preprocess.py

Yêu cầu: faiss, numpy, torch (torch chỉ cần import được, không dùng GPU).
Exit 0 = mọi kiểm tra qua.
"""
import os

# Windows: faiss-cpu mang theo libomp140, còn numpy/torch (MKL) mang libiomp5md.
# Hai bản OpenMP trong cùng process -> "OMP: Error #15 ... already initialized"
# và tiến trình chết ngay lần faiss.search() đầu tiên. Phải đặt TRƯỚC khi
# import numpy/faiss, nếu không thì runtime đã nạp xong rồi, đặt cũng vô ích.
# Ở đây là smoke test trên vector ngẫu nhiên nên đánh đổi này vô hại.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import json
import shutil
import sys
import tempfile
import traceback

import numpy as np

N_FRAMES = 40           # tổng keyframe trong metadata giả
N_SIGLIP2 = 25          # SigLIP2 chỉ index 25/40 -> 15 frame trả -1
DIMS = {"beit3": 1024, "clip": 1280, "siglip2": 1536}

_fail = []


def check(label, fn):
    """Chạy fn(), in OK/FAIL. Không dừng ở lỗi đầu — chạy hết để thấy toàn cảnh."""
    try:
        detail = fn()
        print(f"  [OK ] {label}" + (f"  — {detail}" if detail else ""))
        return True
    except Exception as e:
        print(f"  [FAIL] {label}")
        print("         " + "\n         ".join(
            traceback.format_exc().strip().splitlines()[-4:]))
        _fail.append(label)
        return False


def build_fake_index_dir(d):
    """Sinh index + mapping + metadata giả, đúng hình dạng thật."""
    import faiss
    rng = np.random.default_rng(0)

    names = [f"L21_V001-{i//10:04d}-{i*7:06d}.jpg" for i in range(N_FRAMES)]

    def unit(n, dim):
        v = rng.standard_normal((n, dim)).astype("float32")
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    # beit3 + clip phủ TOÀN BỘ keyframe
    for model in ("beit3", "clip"):
        idx = faiss.IndexFlatIP(DIMS[model])
        idx.add(unit(N_FRAMES, DIMS[model]))
        faiss.write_index(idx, os.path.join(d, f"{model}.index"))
        json.dump({str(i): f"http://localhost:8000/static/images/{names[i]}"
                   for i in range(N_FRAMES)},
                  open(os.path.join(d, f"{model}_mapping.json"), "w"))

    # SigLIP2 chỉ phủ N_SIGLIP2 keyframe đầu — mô phỏng index CHƯA chạy xong.
    sidx = faiss.IndexFlatIP(DIMS["siglip2"])
    sidx.add(unit(N_SIGLIP2, DIMS["siglip2"]))
    faiss.write_index(sidx, os.path.join(d, "siglip2_giant.index"))
    json.dump({str(i): f"http://localhost:8000/static/images/{names[i]}"
               for i in range(N_SIGLIP2)},
              open(os.path.join(d, "siglip2_giant_mapping.json"), "w"))

    # keyframe_metadata.json — CỐ TÌNH không có field nào của siglip2,
    # đúng thiết kế "SigLIP2 dùng json riêng".
    meta = []
    for i, nm in enumerate(names):
        meta.append({
            "name": nm, "video": "L21_V001", "frame_idx": i * 7,
            "fps": 25.0, "timestamp": f"00:00:{i:02d}",
            "timestamp_str": f"00:00:{i:02d}",
            "faiss_id_beit3": i, "faiss_id_clip": i,
            "neighbors_clip": [j for j in (i - 2, i - 1, i + 1, i + 2)
                               if 0 <= j < N_FRAMES],
        })
    json.dump(meta, open(os.path.join(d, "keyframe_metadata.json"), "w"))
    return names


def main():
    tmp = tempfile.mkdtemp(prefix="siglip2_test_")
    print("=" * 74)
    print(f"Index giả: {tmp}")
    print(f"  beit3/clip phủ {N_FRAMES} keyframe · siglip2 chỉ {N_SIGLIP2}"
          f" (mô phỏng index chưa xong)")
    print("=" * 74)
    try:
        names = build_fake_index_dir(tmp)
        os.environ["AIC_INDEX_DIR"] = tmp
        os.environ["AIC_WARMUP"] = "0"

        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        try:
            from app import preprocess as pp
        except ImportError:
            import preprocess as pp          # khi chạy từ trong thư mục app/

        # Thay encode_text_* bằng vector ngẫu nhiên -> KHÔNG tải model thật.
        rng = np.random.default_rng(1)

        def fake(dim):
            def f(_text):
                v = rng.standard_normal((1, dim)).astype("float32")
                return v / np.linalg.norm(v)
            return f

        pp.encode_text_beit3 = fake(DIMS["beit3"])
        pp.encode_text_clip = fake(DIMS["clip"])
        pp.encode_text_siglip2 = fake(DIMS["siglip2"])

        print("\n[1] Hằng số & đăng ký model")
        check("siglip2 có trong MODEL_NAMES",
              lambda: (_assert("siglip2" in pp.MODEL_NAMES), str(pp.MODEL_NAMES))[1])
        check("ENSEMBLE_WEIGHTS có siglip2",
              lambda: (_assert("siglip2" in pp.ENSEMBLE_WEIGHTS),
                       str(pp.ENSEMBLE_WEIGHTS))[1])
        check("SIGLIP2_ID_FIELD KHÔNG phải field metadata",
              lambda: (_assert(not any(pp.SIGLIP2_ID_FIELD in m for m in
                                       json.load(open(os.path.join(tmp, "keyframe_metadata.json")))[0])),
                       pp.SIGLIP2_ID_FIELD)[1])

        print("\n[2] Nạp index + metadata")
        check("_load_indexes() không lỗi", lambda: pp._load_indexes())
        check("_load_meta() không lỗi", lambda: pp._load_meta())
        check("siglip2 index nạp đúng ntotal",
              lambda: (_assert(pp._siglip2_index is not None
                               and pp._siglip2_index.ntotal == N_SIGLIP2),
                       f"{pp._siglip2_index.ntotal} vector")[1])
        check("_siglip2_name2id dựng từ mapping riêng",
              lambda: (_assert(len(pp._siglip2_name2id) == N_SIGLIP2),
                       f"{len(pp._siglip2_name2id)} tên")[1])

        print("\n[3] _fid_of — tra ngược qua tên file")
        _, _, _, sid = pp._model_parts("siglip2")
        m_in = pp._name2meta[names[0]]
        m_out = pp._name2meta[names[N_FRAMES - 1]]
        check("keyframe ĐÃ index -> faiss_id >= 0",
              lambda: (_assert(pp._fid_of(m_in, sid) >= 0),
                       f"id={pp._fid_of(m_in, sid)}")[1])
        check("keyframe CHƯA index -> -1 (không nổ KeyError)",
              lambda: (_assert(pp._fid_of(m_out, sid) == -1), "-1")[1])
        check("beit3 vẫn đọc thẳng field metadata",
              lambda: (_assert(pp._fid_of(m_in, "faiss_id_beit3") == 0), "0")[1])

        print("\n[4] _search_one cho từng model")
        for name in ("beit3", "clip", "siglip2"):
            check(f"_search_one({name})",
                  lambda n=name: (lambda h: (_assert(len(h) > 0), f"{len(h)} hit")[1])(
                      pp._search_one(n, "người đi xe đạp", 10)))

        print("\n[5] rerank_one_model — Alg.2, đi qua _neighbor_faiss_ids")
        for name in ("beit3", "clip", "siglip2"):
            check(f"rerank_one_model({name})",
                  lambda n=name: (lambda h: (_assert(len(h) > 0), f"{len(h)} hit")[1])(
                      pp.rerank_one_model(pp._search_one(n, "q", 10), "q", n)))

        print("\n[6] ensemble_search — mọi tổ hợp checkbox")
        for combo in (["siglip2"], ["beit3", "siglip2"], ["clip", "siglip2"],
                      ["beit3", "clip", "siglip2"], None):
            check(f"ensemble_search(models={combo})",
                  lambda c=combo: (lambda r: (
                      _assert(isinstance(r, list) and len(r) > 0),
                      f"{len(r)} kết quả · routes={sorted((r[0].get('routes') or {}).keys())}")[1])(
                      pp.ensemble_search("q", top_k=5, top_m=10, models=c)))

        print("\n[7] single_model_search")
        check("single_model_search('siglip2')",
              lambda: (lambda r: (_assert(len(r) > 0), f"{len(r)} kết quả")[1])(
                  pp.single_model_search("q", "siglip2", top_k=5, top_m=10)))

        print("\n[8] temporal_search / trake_search với model_name='siglip2'")
        anchor = names[0]
        check("temporal_search(siglip2)",
              lambda: (lambda r: (_assert("error" not in r, r.get("error")),
                                  f"video={r.get('video')}")[1])(
                  pp.temporal_search("bắt đầu", "kết thúc", anchor,
                                     model_name="siglip2")))
        check("trake_search(siglip2)",
              lambda: (lambda r: (_assert("error" not in r, r.get("error")),
                                  f"{len(r.get('events') or [])} event")[1])(
                  pp.trake_search(["e1", "e2", "e3"], anchor, model_name="siglip2")))

        print("\n[9] temporal/trake bản tự khám phá video")
        check("temporal_search_candidates(siglip2)",
              lambda: (lambda r: (_assert(isinstance(r, list)), f"{len(r)} video")[1])(
                  pp.temporal_search_candidates("a", "b", top_videos=2,
                                                model_name="siglip2")))
        check("trake_search_candidates(siglip2)",
              lambda: (lambda r: (_assert(isinstance(r, list)), f"{len(r)} video")[1])(
                  pp.trake_search_candidates(["a", "b"], top_videos=2,
                                             model_name="siglip2")))

        print("\n[10] system_status + preload")
        check("system_status() có vectors.siglip2",
              lambda: (lambda s: (_assert(s["vectors"].get("siglip2") == N_SIGLIP2),
                                  f"{s['vectors']}")[1])(pp.system_status()))
        check("preload() KHÔNG tải weights model thiếu index",
              lambda: _preload_no_download(pp, tmp))

        print("\n[11] Suy biến: index có mà mapping KHÔNG có")
        check("thiếu mapping -> không nổ, chỉ mất rerank",
              lambda: _missing_mapping(pp, tmp))

        print("\n[12] Weights nằm trong INDEX_DIR (như beit3/clip), KHÔNG dùng"
              " cache HF mặc định")
        check("SIGLIP2_LOCAL_DIR trỏ vào INDEX_DIR",
              lambda: (_assert(os.path.abspath(pp.SIGLIP2_LOCAL_DIR)
                               .startswith(os.path.abspath(pp.INDEX_DIR))),
                       pp.SIGLIP2_LOCAL_DIR)[1])
        check("_ensure_siglip2_model() nhận weights PHẲNG trong INDEX_DIR",
              lambda: _finds_flat_model(pp, tmp))
        check("config.json KHÔNG phải siglip -> bỏ qua, không nhận nhầm",
              lambda: _rejects_foreign_config(pp, tmp))
        for layout in ("siglip2_giant_model",
                       "siglip2-giant-opt-patch16-384",
                       "models--google--siglip2-giant-opt-patch16-384"):
            check(f"_ensure_siglip2_model() nhận bố trí '{layout}'",
                  lambda L=layout: _finds_local_model(pp, tmp, L))
        check("KHÔNG có weights -> mới gọi snapshot_download",
              lambda: _downloads_only_when_missing(pp))

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 74)
    if _fail:
        print(f"CÓ {len(_fail)} LỖI: {_fail}")
        return 1
    print("TẤT CẢ ĐỀU QUA — preprocess.py tích hợp SigLIP2 chạy đúng trên mọi nhánh")
    print("=" * 74)
    print("\nLưu ý: test này chứng minh KHÔNG LỖI TÍCH HỢP (không nổ, đúng kiểu,")
    print("đúng luồng). Nó KHÔNG chứng minh embedding text của SigLIP2 khớp")
    print("không gian với index ảnh — cái đó phải chạy verify_siglip2.py với")
    print("index và model THẬT.")
    return 0


def _assert(cond, msg=""):
    if not cond:
        raise AssertionError(msg or "assert thất bại")


def _preload_no_download(pp, tmp):
    """preload() phải BỎ QUA model chưa có index thay vì tải 3.5GB weights.

    Phải GIẤU CHÍNH FILE index đi, không chỉ gán global = None: preload() gọi
    _load_indexes() trước tiên, mà hàm đó nạp lại từ đĩa nếu file vẫn còn —
    gán global = None sẽ bị ghi đè ngay và test không kiểm được gì.
    """
    called = []
    orig = (pp._load_beit3, pp._load_clip, pp._load_siglip2)
    pp._load_beit3 = lambda: called.append("beit3")
    pp._load_clip = lambda: called.append("clip")
    pp._load_siglip2 = lambda: called.append("siglip2")
    idx_p = os.path.join(tmp, "siglip2_giant.index")
    hidden = idx_p + ".hidden"
    saved = pp._siglip2_index
    try:
        os.rename(idx_p, hidden)          # giả lập index CHƯA build xong
        pp._siglip2_index = None
        pp.preload()
        _assert("siglip2" not in called,
                f"preload() vẫn gọi _load_siglip2() dù không có index: {called}")
        return f"đã gọi {called} — siglip2 bị bỏ qua đúng như mong đợi"
    finally:
        os.rename(hidden, idx_p)
        pp._siglip2_index = saved
        pp._load_beit3, pp._load_clip, pp._load_siglip2 = orig


def _missing_mapping(pp, tmp):
    """Có index nhưng thiếu siglip2_giant_mapping.json: _search_one phải trả []
    (không có tên file để tra), và KHÔNG được ném exception."""
    saved_map, saved_n2i = pp._siglip2_map, pp._siglip2_name2id
    try:
        pp._siglip2_map, pp._siglip2_name2id = None, {}
        hits = pp._search_one("siglip2", "q", 5)
        _assert(hits == [], f"phải trả [] khi thiếu mapping, nhận {len(hits)} hit")
        res = pp.ensemble_search("q", top_k=5, top_m=10,
                                 models=["beit3", "siglip2"])
        _assert(len(res) > 0, "beit3 vẫn phải chạy được")
        return "trả [] cho siglip2, beit3 vẫn chạy bình thường"
    finally:
        pp._siglip2_map, pp._siglip2_name2id = saved_map, saved_n2i


def _finds_flat_model(pp, tmp):
    """Bố trí (0): config.json + weights nằm PHẲNG ngay trong INDEX_DIR, chung
    với beit3.index/clip.index. Đây là kết quả của "copy toàn bộ vào indexes/"."""
    cfg = os.path.join(tmp, "config.json")
    json.dump({"model_type": "siglip2", "architectures": ["Siglip2Model"]},
              open(cfg, "w"))
    try:
        got = pp._ensure_siglip2_model()
        _assert(os.path.abspath(got) == os.path.abspath(tmp),
                f"trả {got}, mong đợi chính INDEX_DIR {tmp}")
        return "-> chính INDEX_DIR"
    finally:
        os.remove(cfg)


def _rejects_foreign_config(pp, tmp):
    """config.json của model KHÁC nằm trong INDEX_DIR thì không được nhận nhầm
    là SigLIP2 — nếu không, from_pretrained() sẽ nạp sai model mà không báo."""
    cfg = os.path.join(tmp, "config.json")
    json.dump({"model_type": "bert", "architectures": ["BertModel"]},
              open(cfg, "w"))
    called = []
    import huggingface_hub
    orig = huggingface_hub.snapshot_download

    def spy(**kw):
        called.append(kw)
        os.makedirs(kw["local_dir"], exist_ok=True)
        open(os.path.join(kw["local_dir"], "config.json"), "w").write("{}")
        return kw["local_dir"]

    huggingface_hub.snapshot_download = spy
    try:
        got = pp._ensure_siglip2_model()
        _assert(os.path.abspath(got) != os.path.abspath(tmp),
                "nhận nhầm config.json của bert làm SigLIP2")
        return "đã bỏ qua config.json lạ, chuyển sang tải"
    finally:
        huggingface_hub.snapshot_download = orig
        os.remove(cfg)
        shutil.rmtree(pp.SIGLIP2_LOCAL_DIR, ignore_errors=True)


def _finds_local_model(pp, tmp, layout):
    """_ensure_siglip2_model() phải TÌM THẤY weights đã có trong INDEX_DIR và
    trả về đường dẫn đó — tuyệt đối KHÔNG được gọi snapshot_download.

    Dựng lần lượt 3 kiểu bố trí thư mục có thể gặp tuỳ cách tải/copy.
    """
    if layout.startswith("models--"):
        d = os.path.join(tmp, layout, "snapshots", "abc123")
    else:
        d = os.path.join(tmp, layout)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "config.json"), "w").write("{}")
    try:
        got = pp._ensure_siglip2_model()
        _assert(os.path.abspath(got) == os.path.abspath(d),
                f"trả {got}, mong đợi {d}")
        return f"-> {os.path.relpath(got, tmp)}"
    finally:
        shutil.rmtree(os.path.join(tmp, layout.split(os.sep)[0]),
                      ignore_errors=True)


def _downloads_only_when_missing(pp):
    """Không có weights ở đâu cả thì mới được tải — và tải vào INDEX_DIR,
    không phải cache mặc định."""
    import huggingface_hub
    calls = []
    orig = huggingface_hub.snapshot_download

    def spy(**kw):
        calls.append(kw)
        os.makedirs(kw["local_dir"], exist_ok=True)
        open(os.path.join(kw["local_dir"], "config.json"), "w").write("{}")
        return kw["local_dir"]

    huggingface_hub.snapshot_download = spy
    try:
        got = pp._ensure_siglip2_model()
        _assert(len(calls) == 1, f"gọi snapshot_download {len(calls)} lần")
        _assert(calls[0].get("local_dir") == pp.SIGLIP2_LOCAL_DIR,
                f"tải vào {calls[0].get('local_dir')}, phải là {pp.SIGLIP2_LOCAL_DIR}")
        _assert(os.path.abspath(got) == os.path.abspath(pp.SIGLIP2_LOCAL_DIR))
        return f"local_dir={os.path.basename(pp.SIGLIP2_LOCAL_DIR)}"
    finally:
        huggingface_hub.snapshot_download = orig
        shutil.rmtree(pp.SIGLIP2_LOCAL_DIR, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())