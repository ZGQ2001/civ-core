import shutil
from pathlib import Path

src1 = Path(r"G:\我的云端硬盘\工作\工具\03_文档\检测鉴定常见问题汇总.docx")
src2 = Path(r"G:\我的云端硬盘\工作\工具\03_文档\审核提问.docx")
dst = Path(r"D:\CodeProjects\civ-core\data\training_materials")

shutil.copy2(str(src1), str(dst / src1.name))
print(f"Copied: {src1.name}")
shutil.copy2(str(src2), str(dst / src2.name))
print(f"Copied: {src2.name}")
print("Done")
