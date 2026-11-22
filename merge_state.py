"""把並行分片各自的 state/seen.json 合併回 repo 的 state/seen.json（每個節目的已處理 guid 取聯集）。

用法：python3 merge_state.py state/seen.json 分片狀態資料夾
分片狀態資料夾底下每個子資料夾放一份 seen.json（artifact 下載後的結構：<資料夾>/state-0/seen.json ...）。
順序：先保留原有順序，再附加新出現的 guid；每個節目最多留最後 50 筆（與 digest.py 一致）。
"""
import json
import sys
from pathlib import Path


def merge(base, fragments, keep=50):
    out = {k: {"guids": list(v.get("guids", []))} for k, v in base.items()}
    for frag in fragments:
        for show, v in frag.items():
            cur = out.setdefault(show, {"guids": []})
            seen = set(cur["guids"])
            for g in v.get("guids", []):
                if g not in seen:
                    cur["guids"].append(g)
                    seen.add(g)
    for v in out.values():
        v["guids"] = v["guids"][-keep:]
    return out


def main():
    base_path = Path(sys.argv[1])
    frag_dir = Path(sys.argv[2])
    base = json.loads(base_path.read_text(encoding="utf-8")) if base_path.exists() else {}
    files = sorted(frag_dir.glob("**/seen.json"))
    frags = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    print(f"合併 {len(frags)} 份分片狀態：{[str(f) for f in files]}")
    merged = merge(base, frags)
    base_path.parent.mkdir(exist_ok=True)
    base_path.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    added = sum(len(merged.get(k, {}).get("guids", [])) - len(base.get(k, {}).get("guids", [])) for k in merged)
    print(f"合併完成，共 {len(merged)} 個節目，新增 guid {added} 筆")


if __name__ == "__main__":
    main()
