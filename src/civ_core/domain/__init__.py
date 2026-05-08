"""domain：核心业务域数据契约（与 IO / UI 解耦）。

约定（v2.3 总纲）：
  • 业务热路径（每次任务都会构造的对象）用 @dataclass(slots=True) + __post_init__ 校验
  • 路径字段统一用 pathlib.Path；构造时若传入 str 由 __post_init__ 自动转换
  • 模块间严禁裸传 dict —— 任何返回多字段的函数都要返回这里定义的某个 dataclass
  • 旧路径 civ_core.models.* 仍保留只读，新代码一律从 civ_core.domain.* 引用
"""

from __future__ import annotations
