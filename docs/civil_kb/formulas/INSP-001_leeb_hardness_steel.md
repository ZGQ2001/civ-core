---
formula_id: INSP-001
title: 钢结构里氏硬度推算抗拉强度与屈服强度计算逻辑
code_ref: ["GB/T 17394.4-2014", "GB/T 50344-2019"]
business_type: 现场检测与鉴定
inputs:
  - raw_hl_values: List[float]  # 原始里氏硬度测点值（每测区9点）
  - impact_angle: int           # 测量角度
  - thickness: float            # 构件厚度 (mm)
  - material_preset: str        # 材质预设调用标识
outputs:
  # 测区级 (Test Area Level)
  - hl_m: float                 # 里氏硬度平均值
  - hl_t: float                 # 厚度修正量
  - hl_a: float                 # 角度修正量
  - hl_corrected: float         # 修正后的数值
  - fb_min: float               # 测区抗拉强度最小值
  - fb_max: float               # 测区抗拉强度最大值
  # 构件级 (Component Level)
  - comp_fb_min_avg: float      # 构件下限值
  - comp_fb_max_avg: float      # 构件上限值
  - comp_fb_est: float          # 构件推定值
  # 批次/检验批级 (Batch Level)
  - batch_fb_char_avg: float    # 抗拉强度特征值的平均值
---

## 1. 测区级计算逻辑 (对应单个测区)

### 1.1 里氏硬度平均值 $HL_m$

在单测区获取 9 个原始里氏硬度值后，采用截尾平均法（剔除 4/9 的极值）。即去除 2 个最高值和 2 个最低值，对其余 5 个有效值求算术平均，并四舍五入取整（对应 Excel `ROUND(TRIMMEAN(..., 4/9), 0)`）：
$$HL_m = \text{ROUND}\left(\frac{1}{5} \sum_{i=3}^{7} HL_{sorted}[i], 0\right)$$

### 1.2 修正量获取

* **厚度修正量 $HL_t$**：根据构件厚度，直接在系统预设表中进行静态精确匹配（对应 Excel `VLOOKUP`）。
* **角度修正量 $HL_a$**：根据测量角度分类，并基于当前的 $HL_m$ 在预设表中进行线性插值计算（对应 Excel `TREND` 与 `IF` 嵌套）。

### 1.3 修正后的数值

将平均值与两项修正量直接相加：
$$HL_{corr} = HL_m + HL_t + HL_a$$

### 1.4 抗拉强度极值计算

* **抗拉强度最小值 $f_{b,min}$**：基于修正后的数值 $HL_{corr}$，在强度换算预设表中利用 `MATCH` 定位相邻的上下两个硬度节点，截取局部区间进行严密的两点线性插值计算（对应 Excel 局部 `TREND`）。
* **抗拉强度最大值 $f_{b,max}$**：直接由最小值平移推导得出：
$$f_{b,max} = f_{b,min} + 150$$

---

## 2. 构件级计算逻辑 (对应包含多个测区的单个构件)

针对同一构件下的所有测区（如测区1、测区2、测区3），进行聚合计算：

### 2.1 构件下限值与上限值

* **下限值**：该构件下所有测区 $f_{b,min}$ 的算术平均值（对应 Excel `AVERAGE(AW4:AW6)`）。
* **上限值**：该构件下所有测区 $f_{b,max}$ 的算术平均值（对应 Excel `AVERAGE(AX4:AX6)`）。

### 2.2 构件推定值

将该构件下所有测区的最小值与最大值构成一个总体集合，求取综合算术平均（对应 Excel `AVERAGE(AY4:AZ6)`，即下限值和上限值的总平均）：
$$f_{b,est} = \text{AVERAGE}(f_{b,min\_array}, f_{b,max\_array})$$

---

## 3. 检验批/全局计算逻辑 (对应检测单元所有构件)

### 3.1 抗拉强度特征值的平均值

在完成所有构件计算后，提取该计算批次（如本楼层同类构件区域）内所有构件的**下限值**（或所有测区的 $f_{b,min}$ 集合），求取全局算术平均值（对应 Excel `AVERAGE(AY4:AY27)`）：
$$f_{b,char\_avg} = \text{AVERAGE}(\text{全局下限值集合})$$

*(注：此处代码实现时，需注意 `domain` 层的嵌套关系，由 `Project/Batch` 根节点向下遍历收集所有的子节点下限值进行统算。)*
