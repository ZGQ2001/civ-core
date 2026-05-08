function 表格排版处理JSA() {
    var GlobalConfig = { 
        // 全局核心参数配置字典，用于统一管理排版格式
        chineseFont: "宋体", // 默认中文字体，可修改为 "黑体"、"仿宋" 等
        englishFont: "Times New Roman", // 默认英文/数字字体，可修改为 "Arial" 等
        fontSize: 12, // 默认字号大小（12代表小四号，10.5代表五号字，16代表三号字）
        tableWidthPercent: 100, // 默认表格宽度基于页面边距的百分比（10-100）
        skipPages: [], // 存储需要跳过的物理页码数组（运行时由用户输入动态推入）
        emptyCellColor: 255, // 检测到空单元格时的填充底色（255 代表 WPS 颜色值中的红色）
        maxTableThreshold: 100, // 触发防卡顿警告弹窗的表格数量上限
        backupSuffix: "_备份_", // 静默生成备份文件时添加到原文件名后的文本标识
        titleFormat: { 
            // 针对表名（表格正上方相邻的一个段落）的独立排版参数
            align: 1, // 表名水平对齐方式（0：左对齐，1：居中对齐，2：右对齐）
            spaceBefore: 0.5, // 表名的段前间距（单位：行），可修改为 0、1 等
            spaceAfter: 0, // 表名的段后间距（单位：行），为0表示表名紧贴下方表格
            lineSpacingRule: 0 // 表名的行距规则（0：单倍行距，1：1.5倍行距，2：双倍行距）
        }
    };

    var AuditLog = { 
        // 审计追踪日志对象，用于在脚本执行完毕后生成结果报告
        total: 0, // 记录提取到的文档总表格数
        success: 0, // 记录成功完成格式化排版的表格数
        skipped: 0, // 记录因在跳过页码列表内而未处理的表格数
        errors: 0, // 记录处理过程中遇到底层 API 崩溃的表格数
        errorDetails: [], // 收集具体的错误原因字符串数组
        emptyCells: [] // 收集所有空单元格的具体坐标信息字符串数组
    };

    function showUIAndGetParams() {
        // 1/5：选择模板，收集字体和默认字号
        var fontMenu = "请选择排版模板（输入数字）：\n1 - 公文模板 (中文仿宋_GB2312)\n2 - 标准模板 (中文宋体)";
        var tplInput = InputBox(fontMenu, "引导式参数配置 - 1/5", "1");
        if (!tplInput || tplInput === "False") return false; // 用户点击取消或关闭窗口，中断执行

        if (tplInput === "1") {
            GlobalConfig.chineseFont = "仿宋_GB2312"; // 覆盖默认中文字体为仿宋
            GlobalConfig.fontSize = 10.5; // 覆盖默认字号为10.5（五号）
        } else {
            GlobalConfig.chineseFont = "宋体"; // 覆盖默认中文字体为宋体
            GlobalConfig.fontSize = 10.5; // 覆盖默认字号为10.5（五号）
        }

        // 2/5：允许用户手动干预全局字号
        var sizeInput = InputBox("请输入全局字号（默认已根据模板设定）：", "引导式参数配置 - 2/5", GlobalConfig.fontSize.toString());
        if (!sizeInput || sizeInput === "False") return false;
        var sizeVal = parseFloat(sizeInput); // 将输入的字符串转为浮点数
        if (!isNaN(sizeVal)) GlobalConfig.fontSize = sizeVal; // 若输入合法，覆盖字号配置

        // 3/5：收集表格缩放百分比
        var widthInput = InputBox("请输入表格宽度基于页面的百分比(10-100)：", "引导式参数配置 - 3/5", "95");
        if (!widthInput || widthInput === "False") return false;
        var widthVal = parseInt(widthInput); // 将输入的字符串转为整数
        if (isNaN(widthVal) || widthVal < 10 || widthVal > 100) {
            MsgBox("宽度百分比输入非法，程序终止。", 16, "参数校验失败"); // 16代表错误图标弹窗
            return false;
        }
        GlobalConfig.tableWidthPercent = widthVal; // 覆盖表格宽度配置

        // 4/5：收集需跳过的页码，使用逗号分隔
        var skipPagesInput = InputBox("请输入需跳过的页码（英文逗号分隔），无则留空：", "引导式参数配置 - 4/5", "4");
        if (skipPagesInput && skipPagesInput !== "False") {
            var pages = skipPagesInput.split(","); // 将字符串按逗号切割成数组
            for (var i = 0; i < pages.length; i++) {
                var p = parseInt(pages[i]);
                if (!isNaN(p)) GlobalConfig.skipPages.push(p); // 将合法的页码压入跳过数组
            }
        }

        // 5/5：收集表名的段前间距
        var titleSpaceInput = InputBox("请输入表名（表格上方相邻段落）的段前间距行数：\n（其余默认：居中对齐、单倍行距、对齐网格）", "引导式参数配置 - 5/5", "0.5");
        if (!titleSpaceInput || titleSpaceInput === "False") return false;
        var spaceVal = parseFloat(titleSpaceInput);
        if (!isNaN(spaceVal)) GlobalConfig.titleFormat.spaceBefore = spaceVal; // 覆盖表名段前间距

        // 二次执行确认，防止误触
        var finalConfirm = MsgBox("参数配置完成。\n即将自动生成备份文件并在【源文档】执行全量排版格式化，是否确认开始？", 4, "二次执行确认"); // 4代表包含“是/否”按钮的弹窗
        if (finalConfirm !== 6) return false; // 6代表用户点击了“是”

        return true;
    }

    function backupDocument() {
        var doc = Application.ActiveDocument; // 获取当前激活的文档对象（源文件）
        var path = doc.FullName; // 获取文档在系统中的绝对物理路径
        
        // 校验文档是否已经在硬盘中保存过，防止针对新建未保存文档执行操作
        if (!path || path === doc.Name) {
            MsgBox("当前文档未在磁盘中持久化，无法构建数据备份沙箱，程序终止。请先将文档保存至本地。", 16, "环境异常");
            return false;
        }
        
        doc.Save(); // 强制覆盖保存当前源文件状态，确保数据最新
        var timestamp = new Date().getTime(); // 获取当前毫秒级时间戳，用于拼接唯一文件名
        var dotIndex = path.lastIndexOf("."); // 找到扩展名（如 .docx）的起始索引
        // 拼接备份文件的完整物理路径：原路径 + 备份后缀 + 时间戳 + 原扩展名
        var newPath = path.substring(0, dotIndex) + GlobalConfig.backupSuffix + timestamp + path.substring(dotIndex);
        
        try {
            Application.ScreenUpdating = false; // 锁定屏幕刷新，防止处理过程中界面闪烁
            // 使用底层模板方法，在后台以源文件为模板静默创建一个内容完全相同的副本对象
            var backupDoc = Application.Documents.Add(path);
            backupDoc.SaveAs2(newPath); // 将这个副本对象另存为刚才拼接好的备份路径
            backupDoc.Close(0); // 立刻关闭副本对象，释放内存。0代表关闭时不提示保存更改
            Application.ScreenUpdating = true; // 恢复屏幕刷新
            return true;
        } catch (e) {
            Application.ScreenUpdating = true;
            MsgBox("调用WPS对象模型备份失败，请检查文档是否被独占锁定。\n错误信息：" + e.message, 16, "I/O阻断");
            return false;
        }
    }

    function updateProgress(current, total, phase) {
        var percent = Math.round((current / total) * 100); // 计算当前进度的整数百分比
        // 写入 WPS 左下角状态栏，实现白盒进度监控
        Application.StatusBar = "进度白盒监控 | 阶段: " + phase + " | 处理量: " + current + "/" + total + " (" + percent + "%)";
    }

    function processAllTables() {
        var doc = Application.ActiveDocument; // 确保执行指针仍然锁定在源文件上
        var tables = doc.Tables; // 获取文档内所有的表格集合
        var tableCount = tables.Count; // 获取表格总数
        AuditLog.total = tableCount; // 写入审计日志

        if (tableCount === 0) return true; // 如果没有表格，直接返回成功跳过

        if (tableCount > GlobalConfig.maxTableThreshold) {
            // 超过最大阈值，弹出性能警告，交由用户决策是否强行执行
            var confirmObj = MsgBox("触发阈值保护：检测到表格数量（" + tableCount + "）过大。强制在内存中运算可能引发卡顿，是否继续？", 4, "性能干预");
            if (confirmObj !== 6) return false;
        }

        Application.ScreenUpdating = false; // 全局锁定屏幕渲染，极大提升循环执行速度并防止闪烁

        // 核心排版循环，遍历每一个表格
        for (var i = 1; i <= tableCount; i++) {
            updateProgress(i, tableCount, "格式化与空值排查"); // 实时刷新状态栏进度
            try {
                var tbl = tables.Item(i); // 获取第 i 个表格对象
                // 获取当前表格所在的物理绝对页码（3 代表 wdActiveEndPageNumber 常量）
                var pageNum = tbl.Range.Information(3); 

                // ---------------- 步骤 A：表名特征判定与格式化 ----------------
                try {
                    // 特征 1：在表格上一行（获取表格上方的第一个段落）
                    var titleRange = tbl.Range.Previous(4, 1); 
                    if (titleRange) {
                        // 剔除底层的回车符、换行符及首尾空格，提取干净的纯文本
                        var rawText = titleRange.Text.replace(/[\r\n\x07]/g, "").replace(/(^\s*)|(\s*$)/g, "");
                        
                        // 特征 2：以“表”开头（索引位置为 0）
                        if (rawText.indexOf("表") === 0) {
                            var pFormat = titleRange.ParagraphFormat; 
                            pFormat.Alignment = GlobalConfig.titleFormat.align; 
                            pFormat.SpaceBefore = 0; 
                            pFormat.SpaceAfter = 0;  
                            pFormat.LineUnitBefore = GlobalConfig.titleFormat.spaceBefore; 
                            pFormat.LineUnitAfter = GlobalConfig.titleFormat.spaceAfter;   
                            pFormat.LineSpacingRule = GlobalConfig.titleFormat.lineSpacingRule; 
                            pFormat.DisableLineHeightGrid = false; 
                        }
                    }
                } catch (titleErr) {
                    // 获取或判定失败时静默跳过，不影响后续表格处理
                }
                
                // ---------------- 步骤 B：页码跳过判定 ----------------
                // 检查当前表格所在的页码是否在用户输入的跳过数组内
                if (GlobalConfig.skipPages.indexOf(pageNum) !== -1) {
                    AuditLog.skipped++; // 记录跳过次数
                    continue; // 直接跳入下一个循环，中止当前表格处理
                }

                // ---------------- 步骤 C：表格整体格式化 ----------------
                tbl.PreferredWidthType = 2; // 设置表格宽度模式为基于页面百分比（2 代表 wdPreferredWidthPercent）
                tbl.PreferredWidth = GlobalConfig.tableWidthPercent; // 写入百分比数值
                tbl.Rows.Alignment = 1;     // 设置表格在页面中整体水平居中（1 代表 wdAlignRowCenter）

                // ---------------- 步骤 D：单元格遍历与标红/排版 ----------------
                var cells = tbl.Range.Cells; // 将表格解构为一维线性的单元格集合（规避合并单元格导致的行列索引越界崩溃）
                var cellsCount = cells.Count; // 获取当前表格的单元格总数

                for (var j = 1; j <= cellsCount; j++) {
                    var cell = cells.Item(j); // 获取第 j 个单元格
                    // 核心容错处理：利用正则将底层可能含有的 回车符(\r)、换行符(\n)、单元格结束符(\x07)、空格(\s) 统统删掉后判定纯文本
                    var cleanText = cell.Range.Text.replace(/[\r\n\x07\s]/g, "");

                    if (cleanText === "") {
                        // 触发空值预警逻辑
                        cell.Shading.BackgroundPatternColor = GlobalConfig.emptyCellColor; // 修改单元格底纹颜色标红
                        // 将该空单元格的具体坐标结构化后压入审计日志数组
                        AuditLog.emptyCells.push("页码:" + pageNum + " 表格序号:" + i + " 单元格一维索引:" + j);
                    } else {
                        // 1. 先将单元格的基础主字体强刷为英文字体
                        // 迫使乘号(×)、上下角标、标点符号、数字及字母全部采用英文排版
                        cell.Range.Font.Name = GlobalConfig.englishFont;
                        
                        // 2. 再将严格的东亚字符（纯中文汉字）强刷回中文字体
                        cell.Range.Font.NameFarEast = GlobalConfig.chineseFont;
                        
                        // 3. 补充安全网：确保常规英文和数字绝对锚定
                        cell.Range.Font.NameAscii = GlobalConfig.englishFont;
                        cell.Range.Font.NameOther = GlobalConfig.englishFont;
                        
                        // 设置全局字号及居中对齐方式
                        cell.Range.Font.Size = GlobalConfig.fontSize; 
                        cell.VerticalAlignment = 1; 
                        cell.Range.ParagraphFormat.Alignment = 1; 
                        
                        // 清理段前段后间距
                        cell.Range.ParagraphFormat.SpaceBefore = 0;
                        cell.Range.ParagraphFormat.SpaceAfter = 0;
                        cell.Range.ParagraphFormat.LineUnitBefore = 0;
                        cell.Range.ParagraphFormat.LineUnitAfter = 0;
                    }
                }
                
                AuditLog.success++; // 单个表格排版全流程无异常，成功计数加1
            } catch (err) {
                AuditLog.errors++; // 捕获到底层崩溃（如极其特殊的嵌套结构无法解析），异常计数加1
                // 将引发崩溃的表格基础信息及系统报错文本压入日志，防止阻断剩余表格排版
                AuditLog.errorDetails.push("表格序号:" + i + " | 物理页码:" + pageNum + " | 崩溃捕获:" + err.message);
            }
        }
        
        doc.Save(); // 所有排版结束后，立刻强制保存一次源文件，将内存计算结果落盘
        
        Application.ScreenUpdating = true; // 恢复屏幕渲染，用户能瞬间看到排版结果
        Application.StatusBar = "执行管道已清空"; // 重置底部状态栏
        return true;
    }

    function generateAuditReport() {
        var reportDoc = Application.Documents.Add(); // 在内存中新建一个纯净的空白 Word 文档作为报告载体
        var sel = Application.Selection; // 获取当前报告文档的输入光标
        
        // ---------------- 拼接并输出审计摘要 ----------------
        sel.TypeText("办公自动化脚本审计追踪报告\n\n");
        sel.TypeText("总表格数: " + AuditLog.total + "\n");
        sel.TypeText("成功处理数: " + AuditLog.success + "\n");
        sel.TypeText("跳过数: " + AuditLog.skipped + "\n");
        sel.TypeText("异常数: " + AuditLog.errors + "\n\n");

        // ---------------- 拼接并输出空值明细 ----------------
        sel.TypeText("空值标记单元格明细:\n");
        if (AuditLog.emptyCells.length === 0) {
            sel.TypeText("未检测到空值单元格。\n\n");
        } else {
            for (var i = 0; i < AuditLog.emptyCells.length; i++) {
                sel.TypeText(AuditLog.emptyCells[i] + "\n");
            }
            sel.TypeText("\n");
        }

        // ---------------- 拼接并输出异常明细 ----------------
        sel.TypeText("异常报错明细:\n");
        if (AuditLog.errorDetails.length === 0) {
            sel.TypeText("无系统捕获异常。\n");
        } else {
            for (var j = 0; j < AuditLog.errorDetails.length; j++) {
                sel.TypeText(AuditLog.errorDetails[j] + "\n");
            }
        }
        
        // ---------------- 保存日志文件 ----------------
        var basePath = Application.ActiveDocument.Path; // 获取源文件存放的系统路径
        if (basePath) {
            // 兼容性探测：通过判断路径中的斜杠方向确认当前系统的路径分隔符
            var separator = basePath.indexOf("/") > -1 ? "/" : "\\"; 
            // 拼接日志文件的绝对物理路径
            var logPath = basePath + separator + "执行日志_" + new Date().getTime() + ".docx";
            try {
                reportDoc.SaveAs2(logPath); // 将报告文档保存到源文件同级目录
            } catch(e) {
                // 若日志自动保存因权限等原因失败，弹窗告知用户目前文档已生成，需手动按Ctrl+S保存
                MsgBox("日志文件自动保存失败，请手动保存当前新建的审计文档。", 48, "I/O提示"); // 48代表警告图标
            }
        }
    }

    // ---------------- 主程序统一入口控制流 ----------------
    try {
        if (!showUIAndGetParams()) {
            Application.StatusBar = "用户取消交互或参数校验阻断，执行终止"; // 若前置校验失败或取消，退出流转
            return;
        }
        
        if (!backupDocument()) {
            Application.StatusBar = "沙箱构建失败，执行终止"; // 若备份阶段受阻，退出流转保护源文件
            return;
        }
        
        var processResult = processAllTables(); // 进入核心计算排版逻辑
        
        if (processResult) {
            generateAuditReport(); // 排版完成，生成并保存日志
            // 弹出最终成功提示，64 代表包含信息图标的弹窗
            MsgBox("全量排版与空值排查执行完毕。\n\n1. 源文件已经更新格式并自动保存。\n2. 未格式化的原版数据备份已生成至同级目录。\n3. 执行日志也已同步生成。\n\n(若出现兼容性保存提示，点击“继续保存”即可)", 64, "执行流转完成");
        }
    } catch (globalError) {
        // 最高级别的异常兜底：若前序所有的 try 结构都没防住引发底层崩溃，最后在这里接管
        Application.ScreenUpdating = true; // 强制解锁屏幕，防止 WPS 彻底卡死白屏
        MsgBox("发生全局未捕获异常: " + globalError.message + "\n系统已强制恢复渲染锁释放内存资源。", 16, "最高级阻断");
    } finally {
        // 无论执行成功或崩溃，终结前无条件执行的清理操作
        Application.ScreenUpdating = true; // 确保屏幕更新锁必须释放
        Application.StatusBar = "就绪"; // 重置 WPS 底部状态栏
    }
}