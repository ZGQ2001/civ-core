/**
 * WPS JSA 工业极速版 - 专用于处理数万行数据
 * 核心原理：内存数组批量写入 + 延迟合并
 */
function 生成防火表格_工业级() {
    var app = Application;
    var wb = app.ActiveWorkbook;
    var shtName = "桁架防火截面数量表"; // 你的源数据表名
    
    // 1. 提速开关：关掉所有屏幕刷新和计算
    app.ScreenUpdating = false;
    app.Calculation = -4135; // 手动计算
    app.DisplayAlerts = false; // 关掉警告

    // 2. 读取源数据 (一次性读入内存)
    var wsData;
    try {
        wsData = wb.Sheets.Item(shtName);
    } catch (e) {
        alert("找不到表：" + shtName);
        app.ScreenUpdating = true;
        return;
    }
    
    var lastRow = wsData.Range("A1048576").End(-4162).Row;
    if (lastRow < 2) { alert("数据表没数据？"); return; }
    
    // 直接把源数据全部读入一个大数组 sourceArr
    // 格式：[[构件名, 数量], [构件名, 数量], ...]
    var sourceArr = wsData.Range("A2:B" + lastRow).Value2; 

    // 3. 在内存中构建结果数组
    // 这是一个巨大的二维数组，用来存放最终要写入 Excel 的值
    var resultArr = []; 
    var mergeTasks = []; // 记录需要合并的区域坐标，稍后统一处理
    
    var serialNum = 1; // 序号
    var currentOutputRow = 0; // 记录当前在结果数组里的行号
    
    // 遍历源数据
    for (var i = 0; i < sourceArr.length; i++) {
        var compName = sourceArr[i][0];
        var count = sourceArr[i][1];
        
        if (count == null || typeof(count) != "number" || count <= 0) continue;
        
        // 记录这一组数据的起始和结束行号（相对于结果表，从0开始算）
        var startRow = currentOutputRow;
        var endRow = currentOutputRow + count - 1;
        
        // 记录合并任务：[起始行(Excel行号), 结束行(Excel行号)]
        // Excel行号 = 数组索引 + 3 (因为有2行表头)
        mergeTasks.push({
            start: startRow + 3,
            end: endRow + 3,
            name: compName,
            sn: serialNum
        });

        // 填充每一行的数据
        for (var j = 1; j <= count; j++) {
            // 构建一行数据：[序号, 构件名, 截面X, 占位, 占位, 占位, 平均值]
            // 注意：因为要合并，序号和构件名其实只需要填第一个，但为了防止出错我们全填上也无妨，合并后只显示左上角
            var rowData = new Array(7); 
            rowData[0] = serialNum;     // A列
            rowData[1] = compName;      // B列
            rowData[2] = "截面" + j;    // C列
            rowData[6] = "";            // G列 (公式之后填)
            
            resultArr.push(rowData);
        }
        
        serialNum++;
        currentOutputRow += count;
    }
    
    // 4. 新建表并批量写入数据
    var wsReport = wb.Sheets.Add(null, wb.Sheets.Item(wb.Sheets.Count));
    wsReport.Name = "大数据结果_" + parseInt(Math.random()*100);
    
    // 写入表头
    wsReport.Range("A2:G2").Value2 = ["序号", "构件位置", "测点位置", "D", "E", "F", "平均值"];
    
    if (resultArr.length > 0) {
        // 【关键一步】一次性把几万行数据“拍”进表格
        // Resize(行数, 列数)
        var targetRange = wsReport.Range("A3").Resize(resultArr.length, 7);
        targetRange.Value2 = resultArr;
        
        // 5. 批量处理合并和公式 (这是目前唯一耗时的步骤，但比之前快多了)
        // 我们遍历 mergeTasks 而不是遍历每一行
        for (var k = 0; k < mergeTasks.length; k++) {
            var task = mergeTasks[k];
            var s = task.start;
            var e = task.end;
            
            // 合并A列 (序号)
            wsReport.Range("A" + s + ":A" + e).Merge();
            // 合并B列 (构件名)
            wsReport.Range("B" + s + ":B" + e).Merge();
            // 合并G列 (平均值) 并写入公式
            var rngG = wsReport.Range("G" + s + ":G" + e);
            rngG.Merge();
            rngG.Formula = "=ROUND(AVERAGE(D" + s + ":F" + e + "), 0)";
        }
        
        // 6. 统一设置格式 (最后一次性设置，不要在循环里搞)
        var allRange = wsReport.Range("A3:G" + (resultArr.length + 2));
        allRange.HorizontalAlignment = -4108; // 居中
        allRange.VerticalAlignment = -4108;   // 居中
        allRange.Borders.LineStyle = 1;       // 边框
        
        // 调整列宽
        wsReport.Columns.Item("A").ColumnWidth = 6;
        wsReport.Columns.Item("B").ColumnWidth = 20;
    }

    // 7. 恢复环境
    app.Calculation = -4105; // 自动计算
    app.ScreenUpdating = true;
    
    alert("生成完毕！总共生成了 " + resultArr.length + " 行数据。");
}