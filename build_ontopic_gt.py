import json

KEEP_IDS = {1, 2, 3, 4, 5}  # G6 Bullet, GGUF/ComfyUI, kernel 6.19.11 (x2), Ace-Step 1.5 XL

data = json.load(open("validation_gt.json"))
kept = [r for r in data if r.get("id") in KEEP_IDS]

missing = KEEP_IDS - {r["id"] for r in kept}
if missing:
    print("WARNING: expected ids not found in validation_gt.json:", missing)

json.dump(kept, open("validation_gt_ontopic.json", "w"), indent=2)
print(f"wrote validation_gt_ontopic.json with {len(kept)} on-topic questions")
for r in kept:
    print(" -", r["id"], ":", r["title"][:70])
