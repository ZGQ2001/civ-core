// 锚杆抗拔判定核心公式（GB 50086-2015 附录 C 蠕变试验 / 抗拔试验）。
//
//   弹性位移量 M = 1.2Nt 持荷 5min 时位移 − 卸载到 0.1Nt 时位移
//   下限 Q = 0.9·P·Lf / (E·A)             自由段弹性变形的 90%
//   上限 R = (Lf + La/3)·P / (E·A)        自由段 + 1/3 锚固段的弹性变形
//   合格 ⇔ Q < M < R（开区间，沿用 xlsx 的 IF(AND(M>Q, M<R)) 语义）

namespace CivCore.Doc.Calc.Anchor;

public static class AnchorMath
{
    public static AnchorRowResult ComputeRow(AnchorDisplacements d, AnchorParams p)
    {
        double ea = p.ElasticModulus * p.SteelArea;
        double m = d.D12Nt5Min - d.U01Nt;
        double q = 0.9 * p.AxialDesignLoad * p.FreeLength / ea;
        double r = (p.FreeLength + p.AnchorLength / 3.0) * p.AxialDesignLoad / ea;
        bool qualified = m > q && m < r;
        return new AnchorRowResult(m, q, r, qualified);
    }
}
