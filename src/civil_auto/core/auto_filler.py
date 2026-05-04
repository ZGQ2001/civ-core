import threading

# 引入我们刚才改好的引擎
from civil_auto.core.auto_filler_core import run_generator

# 把需要的 UI 组件全部引入进来
from civil_auto.ui.components import (
    ModernHandwriteDialog,
    ModernInfoDialog,
    ModernMappingDialog,
    ModernProgressConsole,
)


def main():
    print(">>> 启动阶段 1：基础配置")
    stage1_dialog = ModernHandwriteDialog()
    stage1_data = stage1_dialog.show()

    if not stage1_data:
        print("已取消操作。")
        return

    json_path = stage1_data.get("json_path")
    if not json_path:
        print("❌ 未选择 JSON 文件！")
        return

    print(">>> 启动阶段 2：数据映射")
    stage2_dialog = ModernMappingDialog(json_path)
    stage2_data = stage2_dialog.show()

    # =========== 核心改动：多线程与进度条接入 ===========
    if stage2_data:
        print(">>> 启动阶段 3：多线程引擎点火")

        progress_ui = ModernProgressConsole("仿生手写引擎运行中", max_val=100)

        # 准备一个安全的“战报小本本”，记录后台的干活结果
        work_result = {"success": False, "error": None}

        # 2. 定义后台干活的“右手”（子线程任务）
        def engine_worker():
            try:
                # 引擎呼叫 update_progress（现在已经是安全的丢纸条操作了）
                success = run_generator(stage1_data, stage2_data, progress_console=progress_ui)

                if success and not progress_ui.is_cancelled:
                    progress_ui.update_progress(progress_ui.max_val, "🎉 全部任务生成完毕！")
                    work_result["success"] = True  # 在小本本上记一笔“成功”
            except Exception as e:
                work_result["error"] = str(e)
                progress_ui.update_progress(0, f"❌ 发生致命错误: {e}")
                print(f"详细报错: {e}")
            finally:
                import time

                time.sleep(0.5)  # 给用户留半秒钟看一眼 100% 的进度
                progress_ui.close()  # 安全发送关窗纸条

        # 3. 启动后台线程开始干活
        t = threading.Thread(target=engine_worker, daemon=True)
        t.start()

        # 4. 主线程（左手）在这里原地发呆，全心全意维护进度条，直到进度条窗口被销毁
        progress_ui.root.grab_set()
        progress_ui.root.master.wait_window(progress_ui.root)

        # 💡 5. 【极其关键】：进度条关掉后，主线程代码继续往下走！
        # 此时已经回到了主线程的安全区，想怎么弹窗就怎么弹窗！
        if work_result["success"]:
            ModernInfoDialog("生成成功", "所有手写记录表已完美生成并保存为 PDF！").show()
        elif work_result["error"]:
            ModernInfoDialog("发生错误", f"引擎异常中断：\n{work_result['error']}").show()


if __name__ == "__main__":
    main()
