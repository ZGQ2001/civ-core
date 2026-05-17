"""使用 zipfile 提取 PPTX 文本（不需要 python-pptx）"""
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

src = Path(r"D:\CodeProjects\civ-core\data\training_materials")
ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}

for f in sorted(src.glob("*.pptx")):
    print(f"Processing: {f.name}")
    text = ""
    with zipfile.ZipFile(str(f), 'r') as z:
        slide_files = sorted([n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")])
        for i, sf in enumerate(slide_files):
            slide_text = ""
            xml_data = z.read(sf)
            root = ET.fromstring(xml_data)
            for elem in root.iter():
                if elem.tag.endswith("}t"):
                    if elem.text:
                        slide_text += elem.text
            if slide_text.strip():
                text += f"\n---SLIDE {i+1}---\n{slide_text}"
    out = src / f"{f.stem}.txt"
    out.write_text(text, encoding="utf-8")
    print(f"  -> {out.name} ({len(text)} chars)")
print("Done")
