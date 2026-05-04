// WPS JSA 文档自动化处理脚本：国标半全角括号专项纠偏
// 核心架构：单一闭包主入口，规避作用域污染
function 全半角括号一键处理() {
    // 强制声明底层常数，禁止使用 Enum 枚举以防 WPS JSA 解析崩溃
    var wdFindContinue = 1; // 查找到文档末尾时继续从头开始查找
    var wdReplaceAll = 2; // 执行全部替换操作
    var wdDoNotSaveChanges = 0; // 关闭文档时不保存更改
    
    // 最外层包裹 try...catch 结构，确保发生意外错误时程序不会导致 WPS 假死
    try {
        // 关闭屏幕实时刷新，提升宏执行速度并防止画面闪烁
        Application.ScreenUpdating = false; 
        // 接管底部状态栏，向用户输出当前程序运行状态
        Application.StatusBar = "正在初始化括号专项处理引擎...";

        // 唤起原生对话框收集用户意图。36 代表包含“是/否”按钮及问号图标
        var runFlag = MsgBox(
            "是否执行【检测报告：括号半全角专项纠偏】处理？\r\n\r\n处理逻辑：\r\n1. 全局小括号建立基准（统一转全角）\r\n2. 纯技术参数转半角\r\n3. 书名号标准代号恢复全角\r\n4. 纯数字层级序号恢复全角\r\n5. 锚定排除：包含“第”字的编号保留半角", 
            36, 
            "括号专项引擎启动"
        );
        
        // 校验返回值，6 代表用户点击了“是(Y)”
        if (runFlag !== 6) { 
            // 若用户取消，则弹窗提示并阻断程序继续执行
            MsgBox("已取消操作，文档未作任何更改。", 64, "操作终止");
            return;
        }

        Application.StatusBar = "正在执行源文件强制保存与静默克隆备份...";
        // 在进行破坏性替换前，强制保存当前处于激活状态的源文件
        Application.ActiveDocument.Save(); 
        
        // 获取当前文档的完整绝对路径
        var docPath = Application.ActiveDocument.FullName;
        // 利用正则表达式在文件扩展名前插入 _backup 标识，生成备份路径
        var backupPath = docPath.replace(/(\.[a-zA-Z0-9]+)$/, "_backup$1");
        // 正则替换失效的极低概率兜底方案，直接在末尾追加
        if (docPath === backupPath) backupPath = docPath + "_backup.docx"; 
        
        // 核心静默备份逻辑：以克隆方式在后台隐式加载源文档
        var backupDoc = Application.Documents.Add(docPath); 
        // 将克隆的文档对象另存为备份路径
        backupDoc.SaveAs2(backupPath);
        // 立即销毁该副本实例，确保用户的光标和视图焦点仍然停留在原文档
        backupDoc.Close(wdDoNotSaveChanges); 

        // 构建正则通配符替换规则集。f: 查找文本, r: 替换文本, wc: 是否开启通配符
        var rules = [
            // 步骤1：清洗环境基准，将所有现存的半角括号强制抹平为全角括号
            { f: "(", r: "（", wc: false },
            { f: ")", r: "）", wc: false },
            
            // 步骤2：前置数据清洗，修正输入法易错打出的全角波浪号，保障后续正则能够精准命中
            { f: "～", r: "~", wc: false },

            // 步骤3：提取技术参数转为半角
            // 通配符解析：括号内包含任意大小写字母、数字，以及预设的标点白名单（如度°、±、四则运算等）
            // @ 符号在 Word 通配符中代表匹配前一字符的一个或多个连续实例
            // 命中后通过 \1 反向引用保留内部文本，外部替换为半角 ()
            { f: "（([a-zA-Z0-9 .,/\\\\_~—–:%°+=±×÷·　-]@)）", r: "(\\1)", wc: true },

            // 步骤4：特例纠偏 - 书名号标准代号锁定全角
            // 查找右书名号》后紧跟的半角括号，括号内部不包含右括号（[!\\)]），将其强行拉回全角
            { f: "》\\(([!\\)]@)\\)", r: "》（\\1）", wc: true },

            // 步骤5：特例纠偏 - 中文纯数字层级序号锁定全角
            // 若步骤3误将 (1)、(2) 等转为半角，此规则用于捕获纯数字序列并恢复全角
            { f: "\\(([0-9]@)\\)", r: "（\\1）", wc: true },

            // 步骤6：锚定排除 - 编号“第(xxx)”保留半角
            // 应对步骤5的误伤，只要纯数字括号左侧存在“第”字，则触发豁免，再次转回半角
            // 依次穷举匹配“紧贴”、“半角空格”、“全角空格”三种情况
            { f: "第（([0-9]@)）", r: "第(\\1)", wc: true },
            { f: "第 （([0-9]@)）", r: "第 (\\1)", wc: true },
            { f: "第　（([0-9]@)）", r: "第　(\\1)", wc: true }
        ];

        // 获取文档主体的文本操作范围对象
        var rng = Application.ActiveDocument.Content;
        // 实例化查找替换引擎
        var fnd = rng.Find;
        var totalSteps = rules.length;

        // 遍历所有清洗规则，执行流线型全局替换
        for (var j = 0; j < totalSteps; j++) {
            // 刷新底部状态栏进度条
            Application.StatusBar = "正在处理括号规范，进度: (" + (j + 1) + "/" + totalSteps + ") ...";
            
            // 每次执行前必须清空格式限制，防止继承上一次搜索的幽灵条件
            fnd.ClearFormatting();
            fnd.Replacement.ClearFormatting();
            
            // 将规则集参数映射到原生的 Execute 方法中
            fnd.Execute(
                rules[j].f,      // FindText: 要查找的字符串表达式
                false,           // MatchCase: 区分大小写（关闭）
                false,           // MatchWholeWord: 全字匹配（关闭）
                rules[j].wc,     // MatchWildcards: 动态开关正则通配符支持
                false,           // MatchSoundsLike: 同音词（关闭）
                false,           // MatchAllWordForms: 所有词形（关闭）
                true,            // Forward: 向下查找（开启）
                wdFindContinue,  // Wrap: 到达文档末尾后继续（1）
                false,           // Format: 包含格式（关闭）
                rules[j].r,      // ReplaceWith: 用于替换的字符串格式
                wdReplaceAll     // Replace: 全部替换（2）
            );
        }

        // 流程跑通，向用户反馈执行成果
        MsgBox("文档括号专项纠偏完成！\n\n- 参数范围括号：已转半角\n- 编号锚定排除：第()已保留半角\n- 层级序号：已锁定全角\n- 源文件备份：已生成至当前目录", 64, "执行成功");

    } catch (err) {
        // 捕获到运行时异常，向用户抛出原生错误堆栈信息以便调试排错
        MsgBox("架构运行遭遇异常抛出：\n" + err.message + "\n\n请检查文档格式或联系开发人员。", 16, "运行期错误拦截");
    } finally {
        // 绝对兜底动作：无论上方执行成功还是中途崩溃，都必须交还屏幕控制权并重置状态栏
        Application.ScreenUpdating = true;
        Application.StatusBar = "就绪";
    }
}