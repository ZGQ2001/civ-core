/**
 * report_generator 工具的前端类型契约。
 *
 * 这个工具是装配线的「报告填充」环节：
 *   数据处理 → (可选) 绘曲线图 → ★ 报告填充 ★
 *
 * 输入是上游数据处理已选好的原始 Excel + 工程参数（通过 useDataProcessing 拿，
 * 避免用户重复填）；本工具自己 own 的只有 Word 模板路径 + 项目元信息 + 输出目录。
 */

/**
 * 报告级 user_inputs —— 一份报告共享（甲方/施工/仪器/人员等），跟 dotnet/civ-doc
 * AnchorFieldCatalog 的 UserInput 字段对齐。
 *
 * 批次级字段（同一项目不同批次值不同的，目前只有「灌浆日期」）走 ReportBatchUserInputs。
 * 哪些 key 是批次级见 BATCH_DIM_KEYS。
 */
export interface ReportUserInputs {
  // 工程基础信息
  client_name: string;
  project_name: string;
  report_no: string;
  inspection_category: string;
  inspection_item: string;
  inspection_site: string;
  inspection_time: string;
  inspection_engineer: string;
  inspection_conclusion: string;
  // 参建单位
  supervisor_unit: string;
  designer_unit: string;
  constructor_unit: string;
  // 检测依据
  inspection_basis: string;
  /*
   * 备注：之前 catalog 里还有 test_engineer / test_date 两个字段，
   * 已合并到 inspection_engineer / inspection_time（实际报告里基本是同一组人/同一天）。
   * 模板里写 {{试验人员}} / {{试验日期}} 会通过别名命中合并后的字段，向后兼容。
   */
  // 仪器 1
  instrument1_name: string;
  instrument1_no: string;
  instrument1_cert_no: string;
  instrument1_valid_until: string;
  instrument1_precision: string;
  // 仪器 2
  instrument2_name: string;
  instrument2_no: string;
  instrument2_cert_no: string;
  instrument2_valid_until: string;
  instrument2_precision: string;
  // 杆体 / 钻孔 / 注浆（注意：grouting_date 是批次级，见 ReportBatchUserInputs）
  rock_soil_property: string;
  bar_material_spec: string;
  drill_angle: string;
  drill_diameter: string;
  grout_ratio: string;
  grout_strength: string;
}

export const DEFAULT_REPORT_USER_INPUTS: ReportUserInputs = {
  client_name: '',
  project_name: '',
  report_no: '',
  inspection_category: '',
  inspection_item: '锚杆抗拔力（验收）检测',
  inspection_site: '',
  inspection_time: '',
  inspection_engineer: '',
  inspection_conclusion: '',
  supervisor_unit: '',
  designer_unit: '',
  constructor_unit: '',
  inspection_basis: '《岩土锚杆与喷射混凝土支护工程技术规范》GB 50086-2015',
  instrument1_name: '',
  instrument1_no: '',
  instrument1_cert_no: '',
  instrument1_valid_until: '',
  instrument1_precision: '',
  instrument2_name: '',
  instrument2_no: '',
  instrument2_cert_no: '',
  instrument2_valid_until: '',
  instrument2_precision: '',
  rock_soil_property: '',
  bar_material_spec: '',
  drill_angle: '',
  drill_diameter: '',
  grout_ratio: '',
  grout_strength: '',
};

/**
 * 批次级 user_inputs —— 同一项目不同批次值不同的字段。
 *
 * 现在只有「灌浆日期」一个：A 批 5 月初做、B 批 6 月中做属于常见情形。
 * 仪器/人员/检测时间是报告级（一份报告一套），不在此结构。
 */
export interface ReportBatchUserInputs {
  grouting_date: string;
}

export const DEFAULT_REPORT_BATCH_USER_INPUTS: ReportBatchUserInputs = {
  grouting_date: '',
};

/**
 * 哪些 catalog key 是「批次维度」字段 —— 前端白名单，无需 catalog 修改。
 *
 * 在 controller / SettingsForm 决定字段渲染位置（按批次卡片 vs 项目级 input）时用。
 * 后续要把字段从项目级挪到批次级，只需：types.ts 里把字段从 ReportUserInputs 挪到
 * ReportBatchUserInputs + 在这里加 key。
 */
export const BATCH_DIM_KEYS = ['grouting_date'] as const;
export type BatchDimKey = (typeof BATCH_DIM_KEYS)[number];

export interface UserInputFieldDef {
  key: keyof ReportUserInputs;
  label: string;
  placeholder?: string;
}

export interface UserInputGroup {
  id: string;
  label: string;
  icon: string;
  fields: UserInputFieldDef[];
}

/**
 * SettingsForm 渲染顺序 —— 分 7 组，按报告填写习惯排。
 * 每组在 UI 里是一张可折叠卡片，避免 24+ 字段堆成竖长条。
 */
export const USER_INPUT_GROUPS: UserInputGroup[] = [
  {
    id: 'basic',
    label: '工程基础信息',
    icon: 'briefcase',
    fields: [
      { key: 'client_name', label: '委托单位', placeholder: '例：XX建设集团' },
      {
        key: 'project_name',
        label: '项目名称',
        placeholder: '例：XX环境整治提升项目',
      },
      {
        key: 'report_no',
        label: '报告编号',
        placeholder: '例：J3—G字2026第XXX号',
      },
      {
        key: 'inspection_category',
        label: '检测类别',
        placeholder: '例：一般委托',
      },
      { key: 'inspection_item', label: '检测项目' },
      {
        key: 'inspection_site',
        label: '检测地点',
        placeholder: '例：北京市xx区',
      },
      {
        key: 'inspection_time',
        label: '检测时间/试验日期',
        placeholder: '例：2026-05-25',
      },
      {
        key: 'inspection_engineer',
        label: '检测人员/试验人员',
        placeholder: '例：张三、李四',
      },
      {
        key: 'inspection_conclusion',
        label: '检测结论',
        placeholder: '例：全部合格',
      },
    ],
  },
  {
    id: 'parties',
    label: '参建单位',
    icon: 'organization',
    fields: [
      { key: 'supervisor_unit', label: '监理单位' },
      { key: 'designer_unit', label: '设计单位' },
      { key: 'constructor_unit', label: '施工单位' },
    ],
  },
  {
    id: 'basis',
    label: '检测依据',
    icon: 'book',
    fields: [{ key: 'inspection_basis', label: '检测及判定依据' }],
  },
  {
    id: 'instr1',
    label: '检测仪器 1',
    icon: 'tools',
    fields: [
      {
        key: 'instrument1_name',
        label: '仪器名称',
        placeholder: '例：锚杆拉力计',
      },
      { key: 'instrument1_no', label: '仪器编号' },
      { key: 'instrument1_cert_no', label: '检定证书编号' },
      { key: 'instrument1_valid_until', label: '使用有效期' },
      { key: 'instrument1_precision', label: '检测精度' },
    ],
  },
  {
    id: 'instr2',
    label: '检测仪器 2',
    icon: 'tools',
    fields: [
      { key: 'instrument2_name', label: '仪器名称' },
      { key: 'instrument2_no', label: '仪器编号' },
      { key: 'instrument2_cert_no', label: '检定证书编号' },
      { key: 'instrument2_valid_until', label: '使用有效期' },
      { key: 'instrument2_precision', label: '检测精度' },
    ],
  },
  {
    id: 'anchor_desc',
    label: '锚杆 / 钻孔 / 注浆描述',
    icon: 'symbol-misc',
    fields: [
      {
        key: 'rock_soil_property',
        label: '岩土性状',
        placeholder: '例：山石杂土',
      },
      {
        key: 'bar_material_spec',
        label: '杆体材料规格',
        placeholder: '例：C32（HRB400）钢筋',
      },
      { key: 'drill_angle', label: '钻孔倾角', placeholder: '例：60°' },
      { key: 'drill_diameter', label: '钻孔直径', placeholder: '例：90mm' },
      // 注：grouting_date 已挪到批次级（ReportBatchUserInputs），在 SettingsForm 里单独按批次渲染
      {
        key: 'grout_ratio',
        label: '注浆材料配合比',
        placeholder: '例：1:0.5（重量比）',
      },
      {
        key: 'grout_strength',
        label: '注浆材料强度等级',
        placeholder: '例：M7.5',
      },
    ],
  },
];

/** 报告生成结果（前端渲染用）。 */
export interface ReportRunRes {
  output: string;
  rowsRendered: number;
  unknownKeys: string[];
  /** {{img:xxx}} 图片占位符解析失败的列表（缺路径 / 文件不存在）—— 前端警告用。 */
  missingImages: string[];
}
