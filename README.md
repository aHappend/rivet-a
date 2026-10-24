<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/logo-dark.svg">
    <img src="brand/logo.svg" width="420" alt="Vulcan">
  </picture>
  <h1>Rivet-A · Authenticated Block Cipher & Crypto DMA Silicon</h1>
  <p><strong>Synthesizable 100 MHz+ AES-128, AES-256-GCM AEAD & Multi-Context DMA Accelerators · Intel Arria 10 GX HIL</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Platform-Intel_Arria_10_GX-0f766e?style=flat-square" alt="Platform">
    <img src="https://img.shields.io/badge/Quartus_17.1_STA-100_MHz%2B_Closed-0f766e?style=flat-square" alt="STA">
    <img src="https://img.shields.io/badge/PCIe_Gen3x8_HIL-100%25_Passed-1d4ed8?style=flat-square" alt="HIL">
    <img src="https://img.shields.io/badge/Author-Sufeng_Guo_(MSRA)-334155?style=flat-square" alt="Author">
    <img src="https://img.shields.io/badge/License-MIT-64748b?style=flat-square" alt="License">
  </p>
  <p>
    <a href="https://ahappend.github.io/vulcan/">Website</a> ·
    <a href="https://github.com/aHappend/vulcan-showcase">Vulcan Showcase</a> ·
    <a href="https://github.com/aHappend/anvil-q">Anvil-Q (LLM)</a> ·
    <a href="https://github.com/aHappend/anvil-e">Anvil-E (Embedding)</a> ·
    <a href="https://github.com/aHappend/billet-t">Billet-T (FFT/DSP)</a> ·
    <a href="https://github.com/aHappend/billet-f">Billet-F (FIR/IIR)</a> ·
    <a href="https://github.com/aHappend/rivet-a">Rivet-A (AES-GCM)</a> ·
    <a href="https://github.com/aHappend/rivet-h">Rivet-H (SHA/HMAC)</a> ·
    <a href="https://github.com/aHappend/swage-s">Swage-S (ISP)</a> ·
    <a href="https://github.com/aHappend/bellows-l">Bellows-L (LZ4)</a> ·
    <a href="https://github.com/aHappend/crucible-g">Crucible-G (3D)</a> ·
    <a href="https://github.com/aHappend/furnace-x">Furnace-X (SoC)</a> ·
    <a href="README.zh-CN.md"><strong>中文文档</strong></a>
  </p>
</div>

---

**Rivet** is the cryptography, checksum, and data-integrity silicon family in Vulcan's seven-family workshop matrix. **Rivet-A** delivers FIPS-197 and NIST SP 800-38D compliant hardware engines spanning AES-128 (`RIVET-A1`), AES-256-GCM AEAD (`RIVET-A2`), and 4-key/4-context priority-scheduled DMA crypto engines (`RIVET-A3`).

## Silicon Signoff Matrix & Dual-Track Publications (`100 MHz+` Baseline)

| Gen | Accelerator | Architecture & Numerical Scope | Quartus 17.1 STA (`10.0 ns`) | Intel Arria 10 GX Utilization | PCIe Gen3x8 HIL | Academic & Developer Reports |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Gen-1** | [**RIVET-A1**](rivet-a1/) | FIPS-197 AES-128 Encryption/Decryption · On-the-Fly Key Schedule & Tag-Preserving Handshake | `458.93 MHz` (`WNS +7.821 ns`) | `2,150 ALMs (0.50%) · 0 DSPs · 4 M20K` | **PASSED (3/3)** | [**Whitepaper PDF**](rivet-a1/SHOWCASE_REPORT.pdf) · [**Engineering PDF**](rivet-a1/REPORT.pdf) |
| **Gen-2** | [**RIVET-A2**](rivet-a2/) | NIST SP 800-38D AES-128/256-GCM Authenticated Encryption & `GF(2^128)` GHASH Tag Engine | `440.33 MHz` (`WNS +7.729 ns`) | `4,680 ALMs (1.10%) · 0 DSPs · 8 M20K` | **PASSED (3/3)** | [**Whitepaper PDF**](rivet-a2/SHOWCASE_REPORT.pdf) · [**Engineering PDF**](rivet-a2/REPORT.pdf) |
| **Gen-3** | [**RIVET-A3**](rivet-a3/) | 4-Key-Slot, 4-Context Priority-Scheduled AES-GCM & Descriptor-Driven Scatter-Gather DMA | `185.60 MHz` (`WNS +4.612 ns`) | `8,340 ALMs (1.95%) · 0 DSPs · 24 M20K` | **PASSED (3/3)** | [**Whitepaper PDF**](rivet-a3/SHOWCASE_REPORT.pdf) · [**Engineering PDF**](rivet-a3/REPORT.pdf) |

## Academic Product Whitepaper Visual Gallery

### RIVET-A1 · Academic Whitepaper Preview ([`rivet-a1/SHOWCASE_REPORT.pdf`](rivet-a1/SHOWCASE_REPORT.pdf))
<table>
  <tr>
    <td align="center" width="33%"><a href="rivet-a1/SHOWCASE_REPORT.pdf"><img src="rivet-a1/showcase_figures/page-1.png" width="100%" alt="RIVET-A1 Page 1"></a><br><sub><strong>Page 1 · Architecture & KPI Summary</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-a1/SHOWCASE_REPORT.pdf"><img src="rivet-a1/showcase_figures/page-2.png" width="100%" alt="RIVET-A1 Page 2"></a><br><sub><strong>Page 2 · Experimental Benchmarks & Parity</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-a1/SHOWCASE_REPORT.pdf"><img src="rivet-a1/showcase_figures/page-3.png" width="100%" alt="RIVET-A1 Page 3"></a><br><sub><strong>Page 3 · Arria 10 STA, HIL & Scaling</strong></sub></td>
  </tr>
</table>

### RIVET-A2 · Academic Whitepaper Preview ([`rivet-a2/SHOWCASE_REPORT.pdf`](rivet-a2/SHOWCASE_REPORT.pdf))
<table>
  <tr>
    <td align="center" width="33%"><a href="rivet-a2/SHOWCASE_REPORT.pdf"><img src="rivet-a2/showcase_figures/page-1.png" width="100%" alt="RIVET-A2 Page 1"></a><br><sub><strong>Page 1 · Architecture & KPI Summary</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-a2/SHOWCASE_REPORT.pdf"><img src="rivet-a2/showcase_figures/page-2.png" width="100%" alt="RIVET-A2 Page 2"></a><br><sub><strong>Page 2 · Experimental Benchmarks & Parity</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-a2/SHOWCASE_REPORT.pdf"><img src="rivet-a2/showcase_figures/page-3.png" width="100%" alt="RIVET-A2 Page 3"></a><br><sub><strong>Page 3 · Arria 10 STA, HIL & Scaling</strong></sub></td>
  </tr>
</table>

### RIVET-A3 · Academic Whitepaper Preview ([`rivet-a3/SHOWCASE_REPORT.pdf`](rivet-a3/SHOWCASE_REPORT.pdf))
<table>
  <tr>
    <td align="center" width="33%"><a href="rivet-a3/SHOWCASE_REPORT.pdf"><img src="rivet-a3/showcase_figures/page-1.png" width="100%" alt="RIVET-A3 Page 1"></a><br><sub><strong>Page 1 · Architecture & KPI Summary</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-a3/SHOWCASE_REPORT.pdf"><img src="rivet-a3/showcase_figures/page-2.png" width="100%" alt="RIVET-A3 Page 2"></a><br><sub><strong>Page 2 · Experimental Benchmarks & Parity</strong></sub></td>
    <td align="center" width="33%"><a href="rivet-a3/SHOWCASE_REPORT.pdf"><img src="rivet-a3/showcase_figures/page-3.png" width="100%" alt="RIVET-A3 Page 3"></a><br><sub><strong>Page 3 · Arria 10 STA, HIL & Scaling</strong></sub></td>
  </tr>
</table>

## Vulcan Seven-Family Workshop Silicon Matrix

| Silicon Family | Workshop Metaphor | Domain & Series Repositories |
| :--- | :--- | :--- |
| **Anvil** *(Primary Focus)* | Heavy forge anvil bearing core compute loads | AI & Large-Model Compute — [**Anvil-Q** (Quantized LLMs)](https://github.com/aHappend/anvil-q) · [**Anvil-E** (Multimodal Embeddings)](https://github.com/aHappend/anvil-e) |
| **Billet** | Raw metal stock shaped and combined into systems | Digital Signal Processing — [**Billet-T** (FFT/Spectral)](https://github.com/aHappend/billet-t) · [**Billet-F** (FIR/SOS-IIR Filters)](https://github.com/aHappend/billet-f) |
| **Rivet** | Small, critical, rock-solid fasteners | Cryptography & Data Integrity — [**Rivet-A** (AES/GCM/DMA)](https://github.com/aHappend/rivet-a) · [**Rivet-H** (SHA-256/512/HMAC)](https://github.com/aHappend/rivet-h) |
| **Swage** | Die-forming tool shaping inputs into target forms | Image Processing & ISP — [**Swage-S** (2D Scaler, 3×3 Spatial Filter, Bayer Demosaic, CSC)](https://github.com/aHappend/swage-s) |
| **Bellows** | Expanding/contracting continuous airflow | Streaming Data Compression — [**Bellows-L** (LZ4 Decompressor, Hash-Table Compressor, XXH32 DMA)](https://github.com/aHappend/bellows-l) |
| **Crucible** | Vessel fusing diverse materials into form | Graphics Processing & Rendering — [**Crucible-G** (Triangle Setup, Tile Rasterizer, Z-Buffer & Texture Shader)](https://github.com/aHappend/crucible-g) |
| **Furnace** | Industrial furnace integrating multiple stages | Heterogeneous SoCs — [**Furnace-X** (Multi-Engine AI + DSP + Crypto + ISP + Compression SoC)](https://github.com/aHappend/furnace-x) |

---
<p align="center"><sub>Author: <strong>Sufeng Guo</strong> · Microsoft Research Asia · <a href="mailto:sufeng_guo@smail.nju.edu.cn">sufeng_guo@smail.nju.edu.cn</a> · <a href="LICENSE">MIT License</a></sub></p>
