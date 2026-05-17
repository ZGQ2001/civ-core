import shutil
from pathlib import Path

src = Path(r"G:\我的云端硬盘\工作\培训")
dst = Path(r"D:\CodeProjects\civ-core\data\training_materials")
dst.mkdir(parents=True, exist_ok=True)

for f in src.iterdir():
    if f.is_file():
        shutil.copy2(str(f), str(dst / f.name))
        print(f"Copied: {f.name}")

print("\nDestination contents:")
for f in sorted(dst.iterdir()):
    print(f"  {f.name}")
