<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/logo-dark.svg">
    <img src="brand/logo.svg" width="420" alt="Vulcan">
  </picture>
  <h1>Rivet-A · 对称分组密码与认证加密芯片系列</h1>
  <p><strong>100 MHz+ 可综合 AES-128、AES-256-GCM 认证加密与多上下文 DMA 加速核 · Intel Arria 10 GX 板级在环验证</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Platform-Intel_Arria_10_GX-0f766e?style=flat-square" alt="Platform">
    <img src="https://img.shields.io/badge/Quartus_17.1_STA-100_MHz%2B_Closed-0f766e?style=flat-square" alt="STA">
    <img src="https://img.shields.io/badge/PCIe_Gen3x8_HIL-100%25_Passed-1d4ed8?style=flat-square" alt="HIL">
    <img src="https://img.shields.io/badge/Author-Sufeng_Guo_(MSRA)-334155?style=flat-square" alt="Author">
    <img src="https://img.shields.io/badge/License-MIT-64748b?style=flat-square" alt="License">
  </p>
  <p>
    <a href="https://ahappend.github.io/vulcan/">项目主页</a> ·
    <a href="https://github.com/aHappend/vulcan-showcase">Vulcan 芯片总览</a> ·
    <a href="https://github.com/aHappend/anvil-q">Anvil-Q (大模型)</a> ·
    <a href="https://github.com/aHappend/anvil-e">Anvil-E (多模态向量)</a> ·
    <a href="https://github.com/aHappend/billet-t">Billet-T (频谱变换)</a> ·
    <a href="https://github.com/aHappend/billet-f">Billet-F (数字滤波)</a> ·
    <a href="https://github.com/aHappend/rivet-a">Rivet-A (认证加密)</a> ·
    <a href="https://github.com/aHappend/rivet-h">Rivet-H (杂凑认证)</a> ·
    <a href="https://github.com/aHappend/swage-s">Swage-S (视觉ISP)</a> ·
    <a href="https://github.com/aHappend/bellows-l">Bellows-L (LZ4压缩)</a> ·
    <a href="https://github.com/aHappend/crucible-g">Crucible-G (图形渲染)</a> ·
    <a href="https://github.com/aHappend/furnace-x">Furnace-X (异构SoC)</a> ·
    <a href="README.md"><strong>English</strong></a>
  </p>
</div>

---

**Rivet（铆钉）** 是 Vulcan 七大工坊芯片矩阵中的密码、校验与数据完整性家族。**Rivet-A** 系列严格遵循 FIPS-197 与 NIST SP 800-38D 标准，涵盖 AES-128 加解密核心（`RIVET-A1`）、AES-256-GCM 认证加密引擎（`RIVET-A2`）与 4 密钥槽/4 上下文 DMA 调度加密子系统（`RIVET-A3`）。

## 全系芯片 `100 MHz+` 硬件签核与双轨学术报告总览

| 代际 | 芯片代号 | 架构与数值规格 | Quartus 17.1 STA (`10.0 ns`) | Intel Arria 10 GX 资源占用 | PCIe Gen3x8 板级 HIL | 学术白皮书与开发者工程报告 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Gen-1** | [**RIVET-A1**](rivet-a1/) | FIPS-197 AES-128 加解密核心 · 在线轮密钥扩展与保序流式握手接口 | `458.93 MHz` (`WNS +7.821 ns`) | `2,150 ALMs (0.50%) · 0 DSPs · 4 M20K` | **通过 (3/3)** | [**中文白皮书 PDF**](rivet-a1/SHOWCASE_REPORT.zh-CN.pdf) · [**英文白皮书 PDF**](rivet-a1/SHOWCASE_REPORT.pdf) · [**工程报告 PDF**](rivet-a1/REPORT.pdf) |
| **Gen-2** | [**RIVET-A2**](rivet-a2/) | NIST SP 800-38D AES-128/256-GCM 认证加解密与 `GF(2^128)` GHASH 鉴别标签引擎 | `440.33 MHz` (`WNS +7.729 ns`) | `4,680 ALMs (1.10%) · 0 DSPs · 8 M20K` | **通过 (3/3)** | [**中文白皮书 PDF**](rivet-a2/SHOWCASE_REPORT.zh-CN.pdf) · [**英文白皮书 PDF**](rivet-a2/SHOWCASE_REPORT.pdf) · [**工程报告 PDF**](rivet-a2/REPORT.pdf) |
| **Gen-3** | [**RIVET-A3**](rivet-a3/) | 4 密钥槽、4 上下文优先级调度 AES-GCM 与描述符驱动 Scatter-Gather DMA 子系统 | `185.60 MHz` (`WNS +4.612 ns`) | `8,340 ALMs (1.95%) · 0 DSPs · 24 M20K` | **通过 (3/3)** | [**中文白皮书 PDF**](rivet-a3/SHOWCASE_REPORT.zh-CN.pdf) · [**英文白皮书 PDF**](rivet-a3/SHOWCASE_REPORT.pdf) · [**工程报告 PDF**](rivet-a3/REPORT.pdf) |

## 中文学术产品白皮书图文预览

### RIVET-A1 · 中文学术白皮书预览 ([`rivet-a1/SHOWCASE_REPORT.zh-CN.pdf`](rivet-a1/SHOWCASE_REPORT.zh-CN.pdf))
<table>
  <tr>
    <td align="center" width="33%"><a href="rivet-a1/SHOWCASE_REPORT.zh-CN.pdf"><img src="rivet-a1/showcase_figures_zh/page-1.png" width="100%" alt="RIVET-A1 第 1 页"></a><br><sub><strong>第 1 页 · 核心指标与微架构拓扑</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-a1/SHOWCASE_REPORT.zh-CN.pdf"><img src="rivet-a1/showcase_figures_zh/page-2.png" width="100%" alt="RIVET-A1 第 2 页"></a><br><sub><strong>第 2 页 · 实测基准对比与误差剖析</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-a1/SHOWCASE_REPORT.zh-CN.pdf"><img src="rivet-a1/showcase_figures_zh/page-3.png" width="100%" alt="RIVET-A1 第 3 页"></a><br><sub><strong>第 3 页 · Arria 10 时序签核、HIL 与演进路线</strong></sub></td>
  </tr>
</table>

### RIVET-A2 · 中文学术白皮书预览 ([`rivet-a2/SHOWCASE_REPORT.zh-CN.pdf`](rivet-a2/SHOWCASE_REPORT.zh-CN.pdf))
<table>
  <tr>
    <td align="center" width="33%"><a href="rivet-a2/SHOWCASE_REPORT.zh-CN.pdf"><img src="rivet-a2/showcase_figures_zh/page-1.png" width="100%" alt="RIVET-A2 第 1 页"></a><br><sub><strong>第 1 页 · 核心指标与微架构拓扑</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-a2/SHOWCASE_REPORT.zh-CN.pdf"><img src="rivet-a2/showcase_figures_zh/page-2.png" width="100%" alt="RIVET-A2 第 2 页"></a><br><sub><strong>第 2 页 · 实测基准对比与误差剖析</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-a2/SHOWCASE_REPORT.zh-CN.pdf"><img src="rivet-a2/showcase_figures_zh/page-3.png" width="100%" alt="RIVET-A2 第 3 页"></a><br><sub><strong>第 3 页 · Arria 10 时序签核、HIL 与演进路线</strong></sub></td>
  </tr>
</table>

### RIVET-A3 · 中文学术白皮书预览 ([`rivet-a3/SHOWCASE_REPORT.zh-CN.pdf`](rivet-a3/SHOWCASE_REPORT.zh-CN.pdf))
<table>
  <tr>
    <td align="center" width="33%"><a href="rivet-a3/SHOWCASE_REPORT.zh-CN.pdf"><img src="rivet-a3/showcase_figures_zh/page-1.png" width="100%" alt="RIVET-A3 第 1 页"></a><br><sub><strong>第 1 页 · 核心指标与微架构拓扑</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-a3/SHOWCASE_REPORT.zh-CN.pdf"><img src="rivet-a3/showcase_figures_zh/page-2.png" width="100%" alt="RIVET-A3 第 2 页"></a><br><sub><strong>第 2 页 · 实测基准对比与误差剖析</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-a3/SHOWCASE_REPORT.zh-CN.pdf"><img src="rivet-a3/showcase_figures_zh/page-3.png" width="100%" alt="RIVET-A3 第 3 页"></a><br><sub><strong>第 3 页 · Arria 10 时序签核、HIL 与演进路线</strong></sub></td>
  </tr>
</table>

## Vulcan 七大工坊芯片家族矩阵

| 芯片家族 | 工坊意象 | 领域定位与开源仓库 |
| :--- | :--- | :--- |
| **Anvil（铁砧）** *(当前核心重心)* | 承担核心计算任务的工坊重器 | AI 与大模型计算系列 — [**Anvil-Q**（开源量化大模型推理）](https://github.com/aHappend/anvil-q) · [**Anvil-E**（多模态向量表征）](https://github.com/aHappend/anvil-e) |
| **Billet（金属坯料）** | 基础材料经加工组合构建计算系统 | 数字信号处理系列 — [**Billet-T**（FFT/IFFT 与功率谱）](https://github.com/aHappend/billet-t) · [**Billet-F**（FIR 与级联 SOS-IIR 滤波）](https://github.com/aHappend/billet-f) |
| **Rivet（铆钉）** | 小而关键、牢固可靠的安全基石 | 密码、校验与数据完整性系列 — [**Rivet-A**（AES-GCM 与多上下文 DMA）](https://github.com/aHappend/rivet-a) · [**Rivet-H**（SHA-256/512 与 HMAC）](https://github.com/aHappend/rivet-h) |
| **Swage（型锻模）** | 将输入加工成形的精密模具 | 图像处理与 ISP 系列 — [**Swage-S**（双线性图像缩放、3×3 空间卷积滤波、Bayer 去马赛克、色彩空间转换）](https://github.com/aHappend/swage-s) |
| **Bellows（风箱）** | 收缩展开、连续高吞吐的数据流 | 压缩、解压与流式数据处理系列 — [**Bellows-L**（流式 LZ4 解压/哈希压缩、多通道 XXH32/CRC32 DMA）](https://github.com/aHappend/bellows-l) |
| **Crucible（坩埚）** | 多种材料融合成形的渲染容器 | 图形处理与渲染系列 — [**Crucible-G**（三角形建立、分块光栅化、Z-Buffer 与纹理光照着色）](https://github.com/aHappend/crucible-g) |
| **Furnace（工业炉）** | 整合多计算环节的系统级设备 | 大型异构 SoC 系列 — [**Furnace-X**（多引擎 AI + DSP + 密码 + ISP + 压缩异构计算 SoC）](https://github.com/aHappend/furnace-x) |

---
<p align="center"><sub>作者：<strong>Sufeng Guo</strong> · 微软亚洲研究院 (Microsoft Research Asia) · <a href="mailto:sufeng_guo@smail.nju.edu.cn">sufeng_guo@smail.nju.edu.cn</a> · <a href="LICENSE">MIT License</a></sub></p>
