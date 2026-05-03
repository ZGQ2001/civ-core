function 交叉引用固定格式JSA() {
    // 关闭屏幕更新以提升速度
    Application.ScreenUpdating = false;

    try {
        let doc = ActiveDocument;
        let fields = doc.Fields;
        let count = 0;

        // 遍历文档中的所有域代码
        for (let i = 1; i <= fields.Count; i++) {
            let f = fields.Item(i);
            
            // 3 代表 wdFieldRef，即交叉引用/引用域
            if (f.Type === 3) {
                let code_text = f.Code.Text;
                
                // 检查是否已经存在 \* MERGEFORMAT，防止重复添加
                if (code_text.toUpperCase().indexOf("\\* MERGEFORMAT") === -1) {
                    // 在原有的域代码末尾追加保留格式的开关
                    f.Code.Text = code_text + " \\* MERGEFORMAT";
                    count++;
                }
            }
        }
        
        MsgBox("处理完毕！共为 " + count + " 个交叉引用追加了保留格式开关。");

    } catch (e) {
        MsgBox("执行异常: " + e.message);
    } finally {
        Application.ScreenUpdating = true;
    }
}