/*
===============================================================================
脚本名称：报告全量排版综合引擎 (JSA 最终可用版)
功能概述：
    基于 V8 引擎将原 Python 跨进程调用的正文与表格排版逻辑本地化。
    包含：内存克隆无感备份机制，彻底修复表格段落防穿透与 0.85cm 缩进污染。
===============================================================================
*/

function main() {
    // ==================== 板块 1：配置与规则大脑 (内嵌 JSON) ====================
    var styleConfig = {
        "检测报告": {
            "一级标题": { chinese_font: "宋体", english_font: "Times New Roman", font_size: 15.0, bold: true, alignment: 1, space_before: 0.5, space_after: 0.0, line_spacing_rule: 1, outline_level: 1, first_line_indent: 0.0, right_indent: 1.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "二级标题": { chinese_font: "宋体", english_font: "Times New Roman", font_size: 14.0, bold: true, alignment: 0, space_before: 0.2, space_after: 0.2, line_spacing_rule: 0, outline_level: 2, first_line_indent: 0.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "三级标题": { chinese_font: "宋体", english_font: "Times New Roman", font_size: 12.0, bold: true, alignment: 0, space_before: 0.2, space_after: 0.2, line_spacing_rule: 0, outline_level: 3, first_line_indent: 0.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "标准正文": { chinese_font: "宋体", english_font: "Times New Roman", font_size: 12.0, bold: false, alignment: 3, space_before: 0.0, space_after: 0.0, line_spacing_rule: 1, outline_level: 10, first_line_indent: 2.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "无缩进正文": { chinese_font: "宋体", english_font: "Times New Roman", font_size: 12.0, bold: false, alignment: 3, space_before: 0.0, space_after: 0.0, line_spacing_rule: 1, outline_level: 10, first_line_indent: 0.0, right_indent: 0.0, left_indent_pt: 30.05, first_line_indent_pt: -20.98 },
            "空白提示": { chinese_font: "宋体", english_font: "Times New Roman", font_size: 12.0, bold: true, alignment: 0, space_before: 0.5, space_after: 0.0, line_spacing_rule: 1, outline_level: 10, first_line_indent: 2.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "图片": { chinese_font: "宋体", english_font: "Times New Roman", font_size: 10.5, bold: false, alignment: 1, space_before: 0.5, space_after: 0.5, line_spacing_rule: 0, outline_level: 10, first_line_indent: 0.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "图表名称": { chinese_font: "宋体", english_font: "Times New Roman", font_size: 10.5, bold: false, alignment: 1, space_before: 0.5, space_after: 0.0, line_spacing_rule: 0, outline_level: 10, first_line_indent: 0.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "表格正文": { chinese_font: "宋体", english_font: "Times New Roman", font_size: 10.5, bold: false, alignment: 1, space_before: 0.0, space_after: 0.0, line_spacing_rule: 0, outline_level: 10, first_line_indent: 0.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "表注说明_起点": { chinese_font: "宋体", english_font: "Times New Roman", font_size: 10.5, bold: false, alignment: 3, space_before: 0.0, space_after: 0.0, line_spacing_rule: 0, outline_level: 10, first_line_indent: 2.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "表注说明_延续": { chinese_font: "宋体", english_font: "Times New Roman", font_size: 10.5, bold: false, alignment: 3, space_before: 0.0, space_after: 0.0, line_spacing_rule: 0, outline_level: 10, first_line_indent: 4.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 }
        },
        "鉴定报告": {
            "结论一级标题": { chinese_font: "仿宋", english_font: "Times New Roman", font_size: 15.0, bold: true, alignment: 1, space_before: 1.0, space_after: 1.0, line_spacing_rule: 0, outline_level: 1, first_line_indent: 0.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "结论二级标题": { chinese_font: "仿宋", english_font: "Times New Roman", font_size: 14.0, bold: true, alignment: 3, space_before: 0.0, space_after: 0.0, line_spacing_rule: 1, outline_level: 2, first_line_indent: 0.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "一级标题": { chinese_font: "仿宋", english_font: "Times New Roman", font_size: 15.0, bold: true, alignment: 0, space_before: 1.0, space_after: 1.0, line_spacing_rule: 0, outline_level: 1, first_line_indent: 0.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "二级标题": { chinese_font: "仿宋", english_font: "Times New Roman", font_size: 14.0, bold: true, alignment: 0, space_before: 1.0, space_after: 1.0, line_spacing_rule: 1, outline_level: 2, first_line_indent: 0.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "三级标题": { chinese_font: "仿宋", english_font: "Times New Roman", font_size: 12.0, bold: true, alignment: 0, space_before: 1.0, space_after: 0.5, line_spacing_rule: 0, outline_level: 3, first_line_indent: 0.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "标准正文": { chinese_font: "仿宋", english_font: "Times New Roman", font_size: 12.0, bold: false, alignment: 3, space_before: 0.0, space_after: 0.0, line_spacing_rule: 1, outline_level: 10, first_line_indent: 2.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "无缩进正文": { chinese_font: "仿宋", english_font: "Times New Roman", font_size: 12.0, bold: false, alignment: 3, space_before: 0.0, space_after: 0.0, line_spacing_rule: 1, outline_level: 10, first_line_indent: 0.0, right_indent: 0.0, left_indent_pt: 30.05, first_line_indent_pt: -20.98 },
            "空白提示": { chinese_font: "仿宋", english_font: "Times New Roman", font_size: 12.0, bold: true, alignment: 0, space_before: 0.5, space_after: 0.0, line_spacing_rule: 1, outline_level: 10, first_line_indent: 2.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "图片": { chinese_font: "仿宋", english_font: "Times New Roman", font_size: 10.5, bold: false, alignment: 1, space_before: 0.5, space_after: 0.5, line_spacing_rule: 0, outline_level: 10, first_line_indent: 0.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "图表名称": { chinese_font: "仿宋", english_font: "Times New Roman", font_size: 10.5, bold: false, alignment: 1, space_before: 0.5, space_after: 0.0, line_spacing_rule: 0, outline_level: 10, first_line_indent: 0.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "表格正文": { chinese_font: "仿宋", english_font: "Times New Roman", font_size: 10.5, bold: false, alignment: 1, space_before: 0.0, space_after: 0.0, line_spacing_rule: 0, outline_level: 10, first_line_indent: 0.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "表注说明_起点": { chinese_font: "仿宋", english_font: "Times New Roman", font_size: 10.5, bold: false, alignment: 3, space_before: 0.0, space_after: 0.0, line_spacing_rule: 0, outline_level: 10, first_line_indent: 2.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 },
            "表注说明_延续": { chinese_font: "仿宋", english_font: "Times New Roman", font_size: 10.5, bold: false, alignment: 3, space_before: 0.0, space_after: 0.0, line_spacing_rule: 0, outline_level: 10, first_line_indent: 4.0, right_indent: 0.0, left_indent_pt: 0.0, first_line_indent_pt: 0.0 }
        }
    };

    // ==================== 板块 2：正则引擎与分类器 ====================
    var ReRules = {
        fig_tbl: /^\s*(图|表)\s*(\d+(\.\d+)*)/,
        note: /^\s*(注|说明)\s*[：:]/,
        list_item: /^(\d+[.、）\)]|[①②③④⑤⑥⑦⑧⑨⑩])/,
        blank: /.*[（(]?(本页)?以下空白[）)].*/,
        no_indent: /^\s*[《\(\[（]/,
        h1: /^(\d+[\.\s\u3000\t]+|[一二三四五六七八九十]+[、\.\s\u3000\t]+)/,
        h2: /^\d+[\.．]\d+[\s\u3000\t]*/,
        h3: /^\d+[\.．]\d+[\.．]\d+[\s\u3000\t]*/,
        appr_c_h1: /^[检\s·]*测[\s·]*结[\s·]*论[\s·]*与[\s·]*建[\s·]*议$/,
        appr_c_h2: /^\d+[\.．\s\u3000\t]+[\u4e00-\u9fa5]+/,
        basis_title: /^[\d\.．\s\u3000\t]*(检测|鉴定)依据.*/,
        suggest_title: /^[处\s]*理[\s]*建[\s]*议$/
    };

    function classifyParagraph(text, listString, flags, reportType) {
        var rawText = listString + text;
        var cleanText = rawText.replace(/\x13.*?\x14/g, '').replace(/[\x13\x14\x15\x07\x01\x02]/g, '').replace(/\xa0/g, ' ').trim();
        
        if (!cleanText) return "空行";
        if (ReRules.blank.test(cleanText)) return "空白提示";
        if (ReRules.fig_tbl.test(cleanText)) return "图表名称";
        
        if (ReRules.note.test(cleanText)) return "表注说明_起点";
        if (flags.is_in_note_mode && ReRules.list_item.test(cleanText)) return "表注说明_延续";

        if (reportType === "鉴定报告") {
            var condensed = cleanText.replace(/ /g, "").replace(/·/g, "").replace(/\u3000/g, "");
            if (condensed === "检测结论与建议" || ReRules.suggest_title.test(condensed)) return "结论一级标题";
            if (flags.is_in_conclusion_mode && ReRules.appr_c_h2.test(cleanText)) return "结论二级标题";
            
            if (ReRules.h3.test(cleanText)) return "三级标题";
            if (ReRules.h2.test(cleanText)) return "二级标题";
            if (ReRules.h1.test(cleanText)) return "一级标题";
            if (flags.is_in_basis_mode) return "无缩进正文";
            if (ReRules.no_indent.test(cleanText)) return "无缩进正文";
            return "标准正文";
        } else {
            if (ReRules.h3.test(cleanText)) return "三级标题";
            if (ReRules.h2.test(cleanText)) return "二级标题";
            if (ReRules.h1.test(cleanText)) return "一级标题";
            if (flags.is_in_basis_mode) return "无缩进正文";
            if (ReRules.no_indent.test(cleanText)) return "无缩进正文";
            return "标准正文";
        }
    }

    // ==================== 板块 3：格式化核心函数 ====================
    function applyFormat(para, cfg, typeName) {
        try {
            var f = para.Range.Font;
            f.Name = cfg.english_font;
            f.NameAscii = cfg.english_font;
            f.NameFarEast = cfg.chinese_font;
            f.Size = cfg.font_size;
            f.Bold = cfg.bold;

            var pf = para.Format;
            pf.Alignment = cfg.alignment;
            pf.OutlineLevel = cfg.outline_level;
            pf.SpaceBefore = cfg.space_before * 12;
            pf.SpaceAfter = cfg.space_after * 12;

            var lsRule = cfg.line_spacing_rule;
            if (lsRule === 1) pf.LineSpacingRule = 1;      
            else if (lsRule === 0) pf.LineSpacingRule = 0; 
            else {
                pf.LineSpacingRule = 5; 
                pf.LineSpacing = (cfg.line_spacing || 1.5) * 12;
            }
            pf.DisableLineHeightGrid = false;
            
            pf.CharacterUnitRightIndent = cfg.right_indent || 0;
            var charFirst = cfg.first_line_indent || 0;
            pf.CharacterUnitFirstLineIndent = charFirst;
            if (charFirst === 0) pf.FirstLineIndent = 0;
            pf.CharacterUnitLeftIndent = 0;
            pf.LeftIndent = 0;
            
            if ((cfg.left_indent_pt || 0) !== 0) pf.LeftIndent = cfg.left_indent_pt;
            if ((cfg.first_line_indent_pt || 0) !== 0) pf.FirstLineIndent = cfg.first_line_indent_pt;
        } catch (e) {
        }
    }

    // ==================== 板块 4：内存克隆无感备份机制 ====================
    function silentBackup(doc) {
        var path = doc.FullName;
        if (!path || path === doc.Name) {
            MsgBox("当前文档未在磁盘中持久化，无法构建数据备份沙箱，程序终止。请先将文档保存至本地。", 16, "环境异常");
            return false;
        }
        
        doc.Save(); 
        var timestamp = new Date().getTime(); 
        var dotIndex = path.lastIndexOf("."); 
        var newPath = path.substring(0, dotIndex) + "_backup_" + timestamp + path.substring(dotIndex);
        
        try {
            var backupDoc = Application.Documents.Add(path);
            backupDoc.SaveAs2(newPath); 
            backupDoc.Close(0); 
            return true;
        } catch (e) {
            return false;
        }
    }

    // ==================== 板块 5：主执行逻辑 ====================
    if (!ActiveDocument) {
        MsgBox("运行阻断：未检测到打开的文档。", 0 + 48, "提示");
        return;
    }

    var reportType = InputBox("请输入报告类型（检测报告/鉴定报告）：", "参数设置 [1/3]", "检测报告");
    if (!reportType) return; 
    if (!styleConfig[reportType]) {
        MsgBox("错误：未知的报告类型。", 0 + 16, "错误");
        return;
    }

    var widthInput = InputBox("请输入表格首选宽度（%）：", "参数设置 [2/3]", "100");
    if (!widthInput) return;
    var tableWidthPercent = parseInt(widthInput) || 100;

    var skipInput = InputBox("请输入跳过页码（逗号分隔，例如: 1,2,3，留空全排）：", "参数设置 [3/3]", "1,2,3,4");
    if (skipInput === undefined) return; 
    
    var skipPages = [];
    if (skipInput.trim() !== "") {
        var parts = skipInput.replace(/，/g, ",").split(",");
        for (var i = 0; i < parts.length; i++) {
            var num = parseInt(parts[i].trim());
            if (!isNaN(num)) skipPages.push(num);
        }
    }

    var summary = "配置清单核对：\n\n" +
                  "报告类型: " + reportType + "\n" +
                  "表格宽度: " + tableWidthPercent + "%\n" +
                  "跳过页码: " + (skipPages.length > 0 ? skipPages.join(", ") : "无") + "\n\n" +
                  "确认执行后，将自动生成底层物理备份，并开始全量排版。";
    var confirm = MsgBox(summary, 1 + 64, "请最终确认排版清单");
    if (confirm !== 1) return; 

    Application.ScreenUpdating = false;
    Application.DisplayAlerts = 0; 
    var oldPagination = false;
    try { oldPagination = Application.Options.Pagination; Application.Options.Pagination = false; } catch(e){}
    
    var stats = { bodySuccess: 0, bodySkip: 0, bodyManual: 0, tblTotal: 0, tblSuccess: 0, tblSkip: 0, tblErr: 0, emptyCells: [] };

    try {
        if (!silentBackup(ActiveDocument)) {
            var backupConfirm = MsgBox("⚠️ 警告：无感物理备份失败！\n\n文档可能未保存或存在底层权限冲突。继续执行可能会直接修改原文件且无法撤销。是否强制继续？", 4 + 48, "安全防呆");
            if (backupConfirm !== 6) return; 
        }

        var doc = ActiveDocument;
        var config = styleConfig[reportType];
        
        // ================= 阶段A：正文排版 =================
        var paras = doc.Paragraphs;
        var totalParas = paras.Count;
        var maxSkip = skipPages.length > 0 ? Math.max.apply(null, skipPages) : 0;
        var flags = { is_in_note_mode: false, is_in_basis_mode: false, is_in_conclusion_mode: false };
        
        for (var i = 1; i <= totalParas; i++) {
            if (i % 20 === 0 || i === totalParas) {
                Application.StatusBar = "【引擎运行中】正在排版正文: " + i + " / " + totalParas + " 段";
            }
            
            var para = paras.Item(i);
            
            // 核心修复1：使用更底层的 Tables.Count 确保表格段落绝对被跳过，防止正文排版将其强刷为2字符缩进
            var isSkipPara = false;
            try {
                if (para.Range.Tables.Count > 0) { 
                    isSkipPara = true;
                } else if (para.Style.NameLocal.indexOf("目录") !== -1 || para.Style.NameLocal.indexOf("TOC") !== -1) {
                    isSkipPara = true;
                } else if (skipPages.length > 0 && i <= (maxSkip * 40 + 50)) {
                    var pageNum = para.Range.Information(3); 
                    if (skipPages.indexOf(pageNum) !== -1) {
                        isSkipPara = true;
                    }
                }
            } catch(e) {}
            
            if (isSkipPara) {
                stats.bodySkip++;
                continue;
            }
            
            var text = para.Range.Text;
            var listStr = "";
            try { listStr = para.Range.ListFormat.ListString; } catch(e) {}
            var cleanT = text.trim();
            
            var isBasisHeader = ReRules.basis_title.test(cleanT);
            var isSuggestHeader = ReRules.suggest_title.test(cleanT.replace(/ /g, ""));
            
            var hasImage = false;
            try { if (para.Range.InlineShapes.Count > 0) hasImage = true; } catch(e) {}
            
            var paraType = hasImage ? "图片" : classifyParagraph(text, listStr, flags, reportType);
            
            if (paraType === "结论一级标题") flags.is_in_conclusion_mode = true;
            else if (paraType === "一级标题") flags.is_in_conclusion_mode = false;
            
            if (isBasisHeader) flags.is_in_basis_mode = true;
            else if (["一级标题", "二级标题", "三级标题", "结论一级标题", "结论二级标题"].indexOf(paraType) !== -1) flags.is_in_basis_mode = false;
            
            if (paraType === "表注说明_起点") flags.is_in_note_mode = true;
            else if (paraType !== "表注说明_延续" && paraType !== "空行") flags.is_in_note_mode = false;
            
            if (paraType === "标准正文" && /^(\d+[.、）\)]|[①②③④⑤⑥⑦⑧⑨⑩])/.test(cleanT)) {
                stats.bodyManual++;
                try { para.Range.Font.Color = 255; } catch(e){} 
                continue;
            }
            if (paraType === "标准正文" && /^[\s]*[•\-*]\s+/.test(cleanT)) {
                paraType = "无缩进正文";
            }
            
            if (config[paraType]) {
                applyFormat(para, config[paraType], paraType);
                stats.bodySuccess++;
            }
        }
        
        // ================= 阶段B：表格排版 =================
        var tbls = doc.Tables;
        var tblCount = tbls.Count;
        stats.tblTotal = tblCount;
        var passedSkipZone = false;
        
        var titleCfg = config["图表名称"] || {chinese_font: "宋体", english_font: "Times New Roman", font_size: 10.5, alignment: 1, space_before: 0.5, space_after: 0};
        var cellCfg = config["表格正文"] || {chinese_font: "宋体", english_font: "Times New Roman", font_size: 10.5};

        for (var idx = 1; idx <= tblCount; idx++) {
            Application.StatusBar = "【引擎运行中】正在排版表格: " + idx + " / " + tblCount + " 表";
            var tbl = tbls.Item(idx);
            
            try {
                var pageNumTbl = 999;
                if (skipPages.length > 0 && !passedSkipZone) {
                    try {
                        pageNumTbl = tbl.Range.Information(3);
                        if (pageNumTbl > maxSkip) passedSkipZone = true;
                    } catch(e) {}
                }
                if (pageNumTbl !== 999 && skipPages.indexOf(pageNumTbl) !== -1) {
                    stats.tblSkip++;
                    continue;
                }
                
                try {
                    var titleRange = tbl.Range.Previous(4, 1); 
                    if (titleRange && titleRange.Text.replace(/[\s\x07]/g, '').indexOf("表") === 0) {
                        var tf = titleRange.Font;
                        tf.Name = titleCfg.english_font;
                        tf.NameAscii = titleCfg.english_font;
                        tf.NameFarEast = titleCfg.chinese_font;
                        tf.Size = titleCfg.font_size;
                        tf.Bold = titleCfg.bold || false;
                        
                        var pf = titleRange.ParagraphFormat;
                        pf.Alignment = titleCfg.alignment !== undefined ? titleCfg.alignment : 1;
                        pf.LineUnitBefore = titleCfg.space_before !== undefined ? titleCfg.space_before : 0.5;
                        pf.LineUnitAfter = titleCfg.space_after || 0.0;
                        pf.CharacterUnitFirstLineIndent = 0;
                        pf.FirstLineIndent = 0;
                        pf.CharacterUnitLeftIndent = 0;
                        pf.LeftIndent = 0;
                    }
                } catch(e) {}
                
                tbl.PreferredWidthType = 2; 
                tbl.PreferredWidth = tableWidthPercent;
                tbl.Rows.Alignment = 1; 
                
                var cells = tbl.Range.Cells;
                var cellCount = cells.Count;
                for (var j = 1; j <= cellCount; j++) {
                    var cell = cells.Item(j);
                    var cellText = cell.Range.Text.replace(/[\r\n\x07\s]/g, '');
                    
                    if (!cellText) {
                        cell.Shading.BackgroundPatternColor = 255;
                        stats.emptyCells.push("P" + pageNumTbl + "-T" + idx + "-C" + j);
                    } else {
                        var f2 = cell.Range.Font;
                        f2.Name = cellCfg.english_font;
                        f2.NameAscii = cellCfg.english_font;
                        f2.NameFarEast = cellCfg.chinese_font;
                        f2.Size = cellCfg.font_size; 
                        f2.Bold = cellCfg.bold || false;
                        
                        cell.VerticalAlignment = 1; 
                        
                        // 核心修复2：强制覆盖并双重清零单元格内的所有缩进记录，强制单倍行距
                        var cpf = cell.Range.ParagraphFormat;
                        cpf.Alignment = cellCfg.alignment !== undefined ? cellCfg.alignment : 1; 
                        cpf.SpaceBefore = 0;
                        cpf.SpaceAfter = 0;
                        cpf.LineUnitBefore = 0;
                        cpf.LineUnitAfter = 0;
                        cpf.LineSpacingRule = 0; // 单倍行距
                        
                        cpf.CharacterUnitFirstLineIndent = 0; 
                        cpf.FirstLineIndent = 0; 
                        cpf.CharacterUnitLeftIndent = 0;
                        cpf.LeftIndent = 0;
                        cpf.CharacterUnitRightIndent = 0;
                        cpf.RightIndent = 0;
                        cpf.DisableLineHeightGrid = false;
                    }
                }
                stats.tblSuccess++;
            } catch (e) {
                stats.tblErr++;
            }
        }
        
        var emptyInfo = stats.emptyCells.slice(0, 15).join("\n");
        if (stats.emptyCells.length > 15) emptyInfo += "\n... (余下 " + (stats.emptyCells.length - 15) + " 处省略)";
        
        var finalMsg = "✅ 排版任务执行完毕！\n\n" +
                       "【正文执行】\n" +
                       "成功排版段落：" + stats.bodySuccess + " 段\n" +
                       "标红待核段落：" + stats.bodyManual + " 段\n" +
                       "规则跳过段落：" + stats.bodySkip + " 段\n\n" +
                       "【表格执行】\n" +
                       "成功排版表格：" + stats.tblSuccess + " / " + stats.tblTotal + " 表\n" +
                       "标红空值单元格：" + stats.emptyCells.length + " 处\n\n" +
                       "📍 空值坐标参考：\n" + (emptyInfo ? emptyInfo : "无");
                       
        MsgBox(finalMsg, 0 + 64, "执行完毕");
        
    } catch(e) {
        MsgBox("排版引擎发生异常中断：\n" + e.message, 0 + 16, "运行期错误");
    } finally {
        Application.ScreenUpdating = true;
        Application.DisplayAlerts = -1; 
        try { Application.Options.Pagination = oldPagination; } catch(e){}
        Application.StatusBar = false; 
    }
}