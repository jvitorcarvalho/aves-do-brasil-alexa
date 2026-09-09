import json, math

# Read the updated aves.json (with new aliases)
with open('lambda/aves.json', 'r', encoding='utf-8') as f:
    db = json.load(f)

print(f"Total species: {len(db)}")

# Split into 4 files for Alexa editor
chunk = math.ceil(len(db) / 4)
for i in range(4):
    part = db[i*chunk : (i+1)*chunk]
    fn = f'lambda/aves{i+1}.json'
    with open(fn, 'w', encoding='utf-8') as f:
        json.dump(part, f, ensure_ascii=False, separators=(',', ':'))
    print(f"  {fn}: {len(part)} species")

# Verify urutau is in one of the split files
for i in range(4):
    fn = f'lambda/aves{i+1}.json'
    with open(fn, 'r', encoding='utf-8') as f:
        part = json.load(f)
    for sp in part:
        if sp['sci'] == 'Nyctibius griseus':
            print(f"  Nyctibius griseus found in {fn}, alt={sp.get('alt', [])}")
