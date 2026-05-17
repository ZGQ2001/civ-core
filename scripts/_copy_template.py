import shutil
from pathlib import Path

src = Path(r"D:\3JS\工具\通用表格模版（复制使用）.docx")
dst = Path(r"D:\CodeProjects\civ-core\data\training_materials")
shutil.copy2(str(src), str(dst / src.name))
print(f"Copied: {src.name}")
