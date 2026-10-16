<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="brand/logo-dark.svg"><img src="brand/logo.svg" width="480" alt="Vulcan"></picture></p>

<h1 align="center">RIVET-A · Cryptographic silicon, forged with Vulcan.</h1>

[Vulcan](https://ahappend.github.io/vulcan/) · [Showcase](https://github.com/aHappend/vulcan-showcase) · [Anvil-E](https://github.com/aHappend/anvil-e) · [RIVET-A](https://github.com/aHappend/rivet-a) · [BILLET-T](https://github.com/aHappend/billet-t)

[中文](README.zh-CN.md)

**RIVET** is an independent silicon family. **RIVET-A** is its current series.
This repository publishes selected open engineering deliverables produced with Vulcan.

## Series roadmap

| Generation | Design | Scope | Engineering status | Product report |
|---|---|---|---|---|
| 1 | [RIVET-A1](rivet-a1/) | AES-128 encryption/decryption, iterative rounds and transaction interfaces | Engineering accepted | [PDF](rivet-a1/REPORT.pdf) |
| 2 | [RIVET-A2](rivet-a2/) | AES-256 and GCM authenticated encryption/decryption | Engineering accepted | [PDF](rivet-a2/REPORT.pdf) |
| 3 | [RIVET-A3](rivet-a3/) | Multiple keys and contexts, scheduling and DMA | Not accepted (checks) | Pending |

Accepted sources are published separately from in-progress status. Each generation keeps its own specification, RTL, executable verification and report. Planned generations are not completed products.

An admitted product README is preserved byte-for-byte; when present, generated publication details and reproduction commands are in that generation's `DELIVERY.md`.

## Publication and scope

Only selected product files, available predecessor reference RTL needed by regression tests, and a compact check-status record are exported. Accounts, model sessions, private experience, framework state and raw internal logs are excluded. Reports are published only after rendered-artifact approval. Internal relative evidence references in reports are provenance, not links to files included in this public package; regenerate public test evidence with the command above.

No tapeout, measured PPA, side-channel certification or board-level performance is claimed.

## License

[MIT](LICENSE), consistent with the Anvil results repositories.
