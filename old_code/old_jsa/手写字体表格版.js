function 高逼真手写_表格专版() {
    let sel = Application.ActiveDocument.ActiveWindow.Selection;
    
    if (sel.Type == 1) {
        alert("请先用鼠标框选需要处理的数据！");
        return;
    }

    if (sel.Cells.Count > 0) {
        let cells = sel.Cells;
        for (let i = 1; i <= cells.Count; i++) {
            let cellRange = cells.Item(i).Range;
            let charCount = cellRange.Characters.Count;
            
            // 抛弃单元格末尾隐藏符，防止格式溢出
            for (let j = 1; j < charCount; j++) {
                let charItem = cellRange.Characters.Item(j);
                let charText = charItem.Text;
                
                if (charText == " " || charText == "\r" || charText == "\n" || charText == "\x07") {
                    continue;
                }

                let f = charItem.Font;
                let currentSize = f.Size;
                if (currentSize == 9999999 || !currentSize) {
                    currentSize = 10.5; // 默认五号字打底
                }

                // 1. 大小扰动 (-0.5 到 +0.5)
                f.Size = currentSize + (Math.random() * 1) - 0.5;
                // 2. 高低扰动 (-1.5 到 +1.5)
                f.Position = (Math.random() * 3) - 1.5;
                // 3. 间距扰动 (-0.5 到 +1.5)
                f.Spacing = (Math.random() * 2) - 0.5;
                
                // 4. 墨迹颜色扰动 (生成深色系的RGB值)
                let r = Math.floor(Math.random() * 35); // 红
                let g = Math.floor(Math.random() * 35); // 绿
                let b = Math.floor(Math.random() * 55); // 蓝，略微偏蓝黑
                f.Color = r + g * 256 + b * 65536; // 转换为WPS可识别的颜色值
            }
        }
    } else {
        // 非表格区域处理逻辑
        let chars = sel.Characters;
        for (let i = 1; i <= chars.Count; i++) {
            let charItem = chars.Item(i);
            let charText = charItem.Text;
            
            if (charText == " " || charText == "\r" || charText == "\n" || charText == "\x07") {
                continue;
            }

            let f = charItem.Font;
            let currentSize = f.Size;
            if (currentSize == 9999999 || !currentSize) {
                currentSize = 10.5;
            }

            f.Size = currentSize + (Math.random() * 1) - 0.5;
            f.Position = (Math.random() * 3) - 1.5;
            f.Spacing = (Math.random() * 2) - 0.5;

            let r = Math.floor(Math.random() * 35);
            let g = Math.floor(Math.random() * 35);
            let b = Math.floor(Math.random() * 55);
            f.Color = r + g * 256 + b * 65536;
        }
    }
    alert("高逼真手写处理完毕");
}
