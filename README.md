# Rivet-A — AES and authenticated-encryption RTL

[English](README.md) · [简体中文](README.zh-CN.md) · [Repository guide / 文件导航](REPOSITORY_GUIDE.md)

Documentation updated: 2026-11-17. This page describes a repository snapshot, not a live job dashboard.

## Overview

**Rivet-A** publishes chip RTL, technical reports and verification artifacts. AES-128/256, GCM/GHASH and descriptor-driven multicontext cryptographic datapaths. References to standards describe engineering targets, not certification by a standards body.

The chip project is public; Vulcan itself remains private and closed-source. Future public releases must be limited to chip technology and public reproducibility materials, excluding Vulcan internal architecture and operating materials. This refresh organizes documentation only; it is not a comprehensive disclosure audit of historical material and does not claim that the existing repository tree has undergone such clearance.

## Scope and evidence

Use the [exact-directory result index](REPOSITORY_GUIDE.md). Functional simulation, synthesis, standalone/virtual-pin timing, board-bridge probing, workload readback and system-software execution are different evidence scopes. A pass at one scope does not establish another. Existing historical results are retained; this documentation refresh neither upgrades nor invalidates them.

Read timing, utilization and performance values from their specific records and applicability conditions; results from differently located copies are not merged. This page makes no fleet-wide claim of physical-board completion, full-model inference, physical Linux boot or measured power/energy efficiency.

## Repository guide

The [repository guide](REPOSITORY_GUIDE.md) lists existing source, constraints, tests, reports and result paths. Hyphenated, underscored and `chips/` directories can be different publication copies; none is silently designated authoritative, moved or deleted.

Start reproduction from the selected chip’s public specification, test instructions and scripts. Tool, input and board requirements belong to that directory. Chip experiments were not rerun as part of this documentation update.

## Existing chip directories

| Chip / variant | Existing root paths | Public artifacts |
| --- | --- | --- |
| RIVET-A1 | [`rivet-a1/`](rivet-a1/) | [REPORT.md](rivet-a1/REPORT.md) · [REPORT.pdf](rivet-a1/REPORT.pdf) · [SHOWCASE_REPORT.pdf](rivet-a1/SHOWCASE_REPORT.pdf) · [SHOWCASE_REPORT.zh-CN.pdf](rivet-a1/SHOWCASE_REPORT.zh-CN.pdf) |
| RIVET-A2 | [`rivet-a2/`](rivet-a2/) | [REPORT.md](rivet-a2/REPORT.md) · [REPORT.pdf](rivet-a2/REPORT.pdf) · [SHOWCASE_REPORT.pdf](rivet-a2/SHOWCASE_REPORT.pdf) · [SHOWCASE_REPORT.zh-CN.pdf](rivet-a2/SHOWCASE_REPORT.zh-CN.pdf) |
| RIVET-A3 | [`rivet-a3/`](rivet-a3/) | [REPORT.md](rivet-a3/REPORT.md) · [REPORT.pdf](rivet-a3/REPORT.pdf) · [SHOWCASE_REPORT.pdf](rivet-a3/SHOWCASE_REPORT.pdf) · [SHOWCASE_REPORT.zh-CN.pdf](rivet-a3/SHOWCASE_REPORT.zh-CN.pdf) |

## Architecture catalog and publications

| Generation | Chip | Architecture / research scope | Record navigation | Reports |
| --- | --- | --- | --- | --- |
| **Gen-1** | [**RIVET-A1**](rivet-a1/) | FIPS-197 AES-128 Encryption/Decryption · On-the-Fly Key Schedule & Tag-Preserving Handshake | [Exact-directory records](REPOSITORY_GUIDE.md) | [**Whitepaper PDF**](rivet-a1/SHOWCASE_REPORT.pdf) · [**Engineering PDF**](rivet-a1/REPORT.pdf) |
| **Gen-2** | [**RIVET-A2**](rivet-a2/) | NIST SP 800-38D AES-128/256-GCM Authenticated Encryption & `GF(2^128)` GHASH Tag Engine | [Exact-directory records](REPOSITORY_GUIDE.md) | [**Whitepaper PDF**](rivet-a2/SHOWCASE_REPORT.pdf) · [**Engineering PDF**](rivet-a2/REPORT.pdf) |
| **Gen-3** | [**RIVET-A3**](rivet-a3/) | 4-Key-Slot, 4-Context Priority-Scheduled AES-GCM & Descriptor-Driven Scatter-Gather DMA | [Exact-directory records](REPOSITORY_GUIDE.md) | [**Whitepaper PDF**](rivet-a3/SHOWCASE_REPORT.pdf) · [**Engineering PDF**](rivet-a3/REPORT.pdf) |

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

## Related projects

- AI / embeddings: [Anvil-Q](https://github.com/aHappend/anvil-q), [Anvil-E](https://github.com/aHappend/anvil-e), [Anvil-QN](https://github.com/aHappend/anvil-qn), [Anvil-EN](https://github.com/aHappend/anvil-en), [Anvil-D](https://github.com/aHappend/anvil-d).
- Systems: [Hammer-V](https://github.com/aHappend/hammer-v), [Furnace-X](https://github.com/aHappend/furnace-x).
- DSP / vision: [Billet-F](https://github.com/aHappend/billet-f), [Billet-T](https://github.com/aHappend/billet-t), [Swage-S](https://github.com/aHappend/swage-s).
- Data / security / graphics: [Bellows-L](https://github.com/aHappend/bellows-l), [Bellows-N](https://github.com/aHappend/bellows-n), [Rivet-A](https://github.com/aHappend/rivet-a), [Rivet-H](https://github.com/aHappend/rivet-h), [Crucible-G](https://github.com/aHappend/crucible-g), [SABLE](https://github.com/aHappend/sable).
- [Public fleet catalog](https://github.com/aHappend/vulcan-showcase). Related independent research: [ACE-2](https://github.com/aHappend/ace-2), [ACE-3](https://github.com/aHappend/ace-3); these retain their own provenance and acceptance boundaries.
- DSpark is a research direction, not a published chip delivery in this repository; no implementation or repository link is asserted here.
