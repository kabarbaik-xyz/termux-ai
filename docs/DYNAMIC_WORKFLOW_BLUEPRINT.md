# ManuOS — Dynamic Workflow Engine Blueprint

**Dokumen**: Comprehensive design untuk dynamic workflow per Order Type
**Status**: Master blueprint (menggantikan `DYNAMIC_WORKFLOW_DESIGN.md`)
**Sumber**: Hasil interview proses manufaktur 10 divisi (Marketing → Delivered)

---

## Daftar Isi

1. [Ringkasan Eksekutif](#1-ringkasan-eksekutif)
2. [Proses Bisnis As-Is (Hasil Interview)](#2-proses-bisnis-as-is-hasil-interview)
3. [Pemilihan Pendekatan](#3-pemilihan-pendekatan)
4. [Arsitektur Keseluruhan](#4-arsitektur-keseluruhan)
5. [Metamodel & Konsep Inti](#5-metamodel--konsep-inti)
6. [Reference Workflow (DAG)](#6-reference-workflow-dag)
7. [Hierarki Artefak (Fan-out)](#7-hierarki-artefak-fan-out)
8. [State Machine](#8-state-machine)
9. [Katalog Node Components](#9-katalog-node-components)
10. [Action Components & Trigger](#10-action-components--trigger)
11. [Semantik Eksekusi Aksi](#11-semantik-eksekusi-aksi)
12. [Pemetaan Interview → Komponen](#12-pemetaan-interview--komponen)
13. [Skenario Kunci](#13-skenario-kunci)
14. [Data Model](#14-data-model)
15. [Pengalaman Builder untuk End User](#15-pengalaman-builder-untuk-end-user)
16. [Katalog Event](#16-katalog-event)
17. [Contoh Konfigurasi](#17-contoh-konfigurasi)
18. [Strategi Migrasi dari Sistem Saat Ini](#18-strategi-migrasi-dari-sistem-saat-ini)
19. [Roadmap Implementasi](#19-roadmap-implementasi)
20. [Risiko & Keputusan Desain Terbuka](#20-risiko--keputusan-desain-terbuka)

---

## 1. Ringkasan Eksekutif

ManuOS saat ini memakai pipeline hardcoded (enum `OrderStatus` tetap: DRAFT → … → DELIVERED). Interview 10 divisi menunjukkan proses nyata **bukan pipeline linear**:

- **Percabangan per part**: assy / machining / standard part punya jalur berbeda.
- **Penggandaan**: 1 project → 1 MO; 1 drawing → ≥2 operation; 1 operation → 2 jobsheet (produksi + QC pair).
- **Paralelisme**: Warehouse & Purchasing, Production & Assembly berjalan bersamaan.
- **Loop-back**: retur → tiket revisi Urgent ke Engineering Design; hasil subcon masuk kembali ke QC.
- **Integrasi eksternal**: sync Odoo, PR ke Procurement Odoo — jaringan tak selalu andal.
- **Rule numerik yang bisa berubah**: kapasitas mesin 22 jam/hari, margin material, MoQ.
- **Perbedaan per order type**: Regular vs Final Part (dan tipe yang akan dibuat user sendiri).

**Keputusan**: bangun **config-driven DAG workflow engine + registry komponen** (node components + action components), dengan **transactional outbox** untuk aksi eksternal. End user menyusun workflow per Order Type lewat builder visual — tanpa menyentuh kode.

> **Node itu wadah, bukan modul.** End user mengustomisasi 3 hal: (1) struktur DAG, (2) komponen di tiap node, (3) aksi di tiap routing/trigger.

---

## 2. Proses Bisnis As-Is (Hasil Interview)

### 2.1 Value stream overview

```mermaid
flowchart LR
    A["1. Marketing<br/>Incoming Order + Odoo"] --> B["2. Eng Design<br/>Breakdown + Drawing"]
    B --> C["3. Eng Process<br/>Operations + CAM"]
    C --> D["4. PPIC<br/>MO + Jobsheet + Approval"]
    D --> E["5. Warehouse Material<br/>Stok + Receiving"]
    E --> F["6. Purchasing<br/>PR + PO + Subcon"]
    F -.->|material datang| E
    D --> G["7. Production<br/>Machining + QC"]
    D --> H["8. Assembly<br/>Ping-pong QC"]
    G --> I["9. Packing & Shipment"]
    H --> I
    I --> J["10. Delivered<br/>Tracking + Retur"]
    J -.->|tiket revisi Urgent| B
```

Perhatikan dua **loop** yang membuktikan ini bukan pipeline: `Purchasing → Warehouse` (material kembali) dan `Delivered → Eng Design` (retur).

### 2.2 Detail tiap tahap (ringkasan interview)

| # | Divisi | Input | Aktivitas kunci | Output |
|---|---|---|---|---|
| 1 | Marketing | PO customer | Incoming Order (project no auto, tipe Regular/Final Part) → sync Odoo; PO release → SO; Drawing Request | Drawing Request |
| 2 | Eng Design | Drawing Request | Breakdown Final Part List; klasifikasi assy / machining / standard part | Drawing release 2D + riwayat revisi |
| 3 | Eng Process | Detail drawing | Sequence, jenis mesin, durasi, operation type; margin material (20×150×5 → 25×175×8); CAM (machining only) | ≥2 operation per drawing |
| 4 | PPIC | Operations + material | 1 project = 1 MO; cek material; jobsheet = op × 2 (QC pair); routing assy/machining; assign mesin (≤22 jam/hari, pindah = approval); approval 4 tahap (boleh mulai sejak PREPARED/CHECKED) | Jobsheet siap + PR material |
| 5 | Warehouse Material | Kebutuhan material | Cek stok (ada → kurangi request; habis → PR); receiving → cek → Warehouse Done → *ready to machining*; partial incoming; cacat → ttd 4 divisi; standard part masuk stok, raw tidak | Material ready |
| 6 | Purchasing | PR | PO vendor (+MoQ), monitor vendor; subcon `SC-` (Preprocess dari Marketing / Process dari PPIC) | PO + material datang |
| 7 | Production | Jobsheet + material | Start/stop per operation; QC pair inspeksi (termasuk hasil subcon); breakdown → PAUSE atau alih subcon (flag + riwayat posisi) | Part selesai |
| 8 | Assembly | Jobsheet assy | Ping-pong operator ⇄ QC sampai selesai; durasi total dicatat, operator vs QC terpisah | Assy selesai |
| 9 | Packing & Shipment | Produk jadi | Packing; tunggu instruksi/approval Marketing; upload bukti (surat jalan/foto/resi) | Bukti kirim |
| 10 | Delivered | Bukti kirim | Status akhir; public order tracking; retur → replacement; salah gambar/produksi → tiket Urgent ke Eng Design | Order closed |

---

## 3. Pemilihan Pendekatan

### 3.1 Kriteria dari interview

| # | Temuan interview | Implikasi teknis |
|---|---|---|
| K1 | Klasifikasi part menentukan jalur | Conditional routing di edge |
| K2 | Jobsheet = operation × 2 (QC pair) | Fan-out dengan multiplier + pairing |
| K3 | Warehouse & Purchasing, Production & Assembly paralel | DAG, bukan state list linear |
| K4 | Retur & subcon kembali ke alur | Loop-back edge (graph bersiklus) |
| K5 | Regular vs Final Part berbeda; user bisa buat tipe baru | Template per Order Type, versioned |
| K6 | Odoo bisa down | Aksi eksternal async + retry + idempotent |
| K7 | 22 jam/hari, margin, MoQ berubah-ubah | Rule numerik = config, bukan kode |
| K8 | End user (bukan developer) menyusun workflow | Builder visual sederhana, bukan XML/BPMN |

### 3.2 Perbandingan opsi

| Aspek | A. Pipeline hardcoded | B. BPMN engine (Camunda/Flowable) | C. Embed n8n/Zapier | **D. Config-driven DAG + component registry** ✅ |
|---|---|---|---|---|
| Percabangan K1 | ❌ hardcode if-else | ✅ | ⚠️ lemah untuk struktur order | ✅ kondisi di edge |
| Fan-out artefak K2 | ❌ | ⚠️ perlu kustom juga | ❌ tidak kenal artefak manufaktur | ✅ `ARTIFACT_CREATE` + pairing |
| Paralel K3 | ⚠️ susah | ✅ | ⚠️ | ✅ DAG native |
| Loop-back K4 | ❌ | ✅ | ⚠️ | ✅ edge type LOOP_BACK |
| Per order type K5 | ❌ kode baru tiap tipe | ✅ | ⚠️ | ✅ template versioned |
| Integrasi K6 | manual | ✅ job worker | ✅ | ✅ outbox + retry + idempotency |
| Rule numerik K7 | ❌ recompile | ⚠️ | ⚠️ | ✅ semua di config JSON |
| End-user builder K8 | — | ❌ BPMN XML, developer-oriented | ⚠️ terlalu generik | ✅ palet komponen domain (form, approval, jobsheet…) |
| Infra | ringan | ❌ Zeebe/engine terpisah | ❌ service terpisah | ✅ in-app (Next.js + Prisma + worker) |
| Artefak domain (MO, Jobsheet, QC pair) | ✅ native | ❌ harus dipetakan | ❌ | ✅ tetap native manuos |

**Kesimpulan**: Opsi D — hybrid. Kita adopsi *ide bagus* dari BPMN engine (definisi berversi, token/token-per-instance, job worker + retry ala Zeebe/outbox) dan dari n8n/Zapier (trigger → actions berurutan dengan shared context), tapi **tanpa** infrastruktur eksternal dan **tanpa** memaksa user belajar notasi BPMN. Domain artefak manufaktur (MO, Jobsheet, QC pair, Drawing) tetap first-class.

---

## 4. Arsitektur Keseluruhan

```mermaid
flowchart TB
    subgraph L3["Layer 3 — CONFIGURABLE (dibuat end user per Order Type)"]
        direction LR
        WT["Workflow Template<br/>(DAG: nodes + edges + conditions)"]
        NC["Node Components<br/>(Form, Approval, QC Pattern, ...)"]
        AC["Action Components<br/>(Odoo, PR, Ledger, Notify, ...)"]
    end

    subgraph L2["Layer 2 — GLOBAL COMPONENTS (shared services)"]
        direction LR
        INV["Inventory Core<br/>(stok, ledger, reservasi)"]
        SCH["Machine Scheduler<br/>(kapasitas, assign, breakdown)"]
        PUR["Purchasing Core<br/>(PR, PO, vendor, subcon)"]
        NUM["Numbering Service<br/>(project no, MO, SC-)"]
        DOCV["Document Versioning<br/>(revisi drawing)"]
        ODOO["Odoo Connector"]
        NT["Notification"]
        PUB["Public Tracking Portal"]
        MD["Master Data<br/>(customer, vendor, part, op type)"]
    end

    subgraph L1["Layer 1 — ENGINE (fixed, di-code sekali)"]
        direction LR
        DAG["DAG Executor"]
        SM["State Machine Runtime"]
        EVT["Event Bus"]
        AX["Action Executor<br/>+ Outbox/Worker"]
        FRM["Form Renderer"]
        APR["Approval Engine"]
        RB["RBAC + Tenancy"]
        AUD["Audit Trail"]
    end

    WT --> DAG
    NC --> FRM
    NC --> APR
    AC --> AX
    AX --> ODOO
    AX --> INV
    AX --> NT
    DAG --> EVT
    EVT --> AX
    DAG --> SM
    SM --> AUD
```

**Aturan praktis**: perilaku yang dibutuhkan ≥ 2 node → global component. Perilaku khas satu jenis tahap → node/action component.

---

## 5. Metamodel & Konsep Inti

```mermaid
classDiagram
    class OrderType {
        +String code
        +String name
        +Boolean isActive
    }
    class WorkflowTemplate {
        +Int version
        +Boolean isActive
        +publish()
        +validate()
    }
    class WorkflowNodeDef {
        +String nodeKey
        +String name
        +String businessUnitId
        +Json config
    }
    class WorkflowEdgeDef {
        +String fromNodeId
        +String toNodeId
        +Json condition
        +String edgeType
    }
    class NodeComponent {
        <<palette: FORM, DOCUMENT, APPROVAL, ROUTING, ...>>
        +String kind
        +Json config
        +Int order
    }
    class ActionDef {
        +String triggerType
        +String kind
        +Json config
        +Boolean blocking
        +Json retry
    }
    class Order
    class WorkflowRun {
        +String status
    }
    class WorkflowNodeRun {
        +String status
    }
    class ComponentRun
    class ActionRun {
        +String status
        +String idempotencyKey
        +Int attempts
    }

    OrderType "1" --> "*" WorkflowTemplate : versi
    WorkflowTemplate "1" --> "*" WorkflowNodeDef : berisi
    WorkflowTemplate "1" --> "*" WorkflowEdgeDef : berisi
    WorkflowNodeDef "1" --> "*" NodeComponent : ditempeli
    WorkflowEdgeDef "1" --> "*" ActionDef : on routing
    Order "1" --> "1" WorkflowRun : instantiate template aktif
    WorkflowRun "1" --> "*" WorkflowNodeRun : eksekusi
    WorkflowNodeRun "1" --> "*" ComponentRun : hasil
    WorkflowRun "1" --> "*" ActionRun : trigger
    ActionDef "1" --> "*" ActionRun : dieksekusi sebagai
```

Konsep kunci:

- **Definisi vs Eksekusi** terpisah total. Template di-edit bebas; run yang sedang jalan **terkunci pada versi template** saat order dibuat.
- **Node bisa di-instantiate berulang** dalam satu workflow dengan konfigurasi berbeda (terbukti dari interview: "Warehouse" muncul 2× — Material dan Packing/Shipment).
- **Artifak domain tetap first-class**: MO, Jobsheet, Drawing, PR, PO dibuat *oleh* komponen workflow (FANOUT / DOC_GENERATE), bukan digantikan JSON.

---

## 6. Reference Workflow (DAG)

DAG lengkap hasil interview — inilah "workflow default" untuk Order Type pertama:

```mermaid
flowchart TD
    CUST([Customer]) -->|"PO / permintaan"| MKT

    subgraph S1["1 · Marketing"]
        MKT["Incoming Order<br/>project no auto · customer · produk · qty<br/>tipe Regular / Final Part · req date"]
        SYNC["Sync ke Odoo (SO)"]
        REL["PO release<br/>Sales Order resmi"]
        DR["Drawing Request<br/>part name · part no · qty/batch · target finish"]
    end
    MKT --> SYNC
    MKT --> REL
    REL --> DR
    DR --> ENG

    subgraph S2["2 · Engineering Design"]
        ENG["Breakdown Final Part List"]
        KLAS{"Klasifikasi part"}
        DWG["Drawing release 2D<br/>part list (assy) atau material &amp; size (machining)<br/>riwayat revisi"]
    end
    ENG --> KLAS
    KLAS -->|"machining"| DWG
    KLAS -->|"assy"| DWG
    KLAS -->|"standard part"| STD["Kebutuhan standard part<br/>(beli jadi: mur, baut)"]

    subgraph S3["3 · Engineering Process"]
        EPR["Operation per drawing<br/>sequence · jenis mesin · durasi · op type"]
        MARG["Margin material<br/>20×150×5 → 25×175×8"]
        CAM["CAM program<br/>(hanya machining)"]
    end
    DWG --> EPR
    EPR --> MARG
    MARG --> OPS
    EPR -->|"machining"| CAM
    CAM -.-> OPS
    OPS["Operations + kebutuhan material"]
    EPR -->|"1 drawing → ≥2 operations"| OPS

    subgraph S4["4 · PPIC"]
        MO["MO · 1 project = 1 MO"]
        MAT["Cek kebutuhan material<br/>raw + margin · standard part"]
        JS["Jobsheet = operation × 2<br/>pasangan QC"]
        ROUT{"Routing jobsheet"}
        ASG["Assign mesin · durasi · tanggal<br/>kapasitas ≤ 22 jam/hari<br/>pindah mesin → approval + alasan"]
        APP["Approval 4 tahap<br/>PREPARED → CHECKED → APPROVED → FINAL JUDGE<br/>kerja boleh mulai sejak PREPARED/CHECKED"]
    end
    OPS --> MO
    MO --> MAT
    MO --> JS
    JS --> ASG --> APP --> ROUT
    STD --> MAT

    subgraph S5["5 · Warehouse Material"]
        STK{"Cek stok aktual"}
        RECV["Material datang → diterima → dicek<br/>→ Warehouse Done"]
        PART["Partial incoming<br/>produksi tetap jalan"]
        DEF["Cacat / kurang →<br/>ttd 4 divisi<br/>PPIC · WH · Purchasing · QC"]
    end
    MAT --> STK
    STK -->|"tersedia"| RESV["Kurangi qty request / reservasi"]
    STK -->|"habis"| PR

    subgraph S6["6 · Purchasing"]
        PR["Terima PR"]
        PO["PO ke vendor<br/>qty + MoQ · monitor vendor"]
        SPO["PO subcon SC-<br/>Preprocess (dari Marketing) ·<br/>Process (dari PPIC)"]
    end
    PR --> PO
    PO --> VND[[Vendor]]
    VND --> RECV
    RECV -.->|"sebagian datang"| PART
    RECV -.->|"cacat / kurang"| DEF
    RECV -->|"ready to machining"| GATE["Gate material ready"]
    RESV --> GATE

    subgraph S7["7 · Production"]
        RUN["Kerjakan jobsheet machining<br/>catat start / stop"]
        QCP["Jobsheet QC inspeksi tiap operation<br/>termasuk hasil subcon"]
        BRK{"Mesin breakdown?"}
    end
    GATE --> RUN
    ROUT -->|"machining"| RUN
    RUN --> QCP
    RUN -.->|"saat kerja"| BRK
    BRK -->|"bisa diperbaiki"| PAU["PAUSE + notif maintenance"]
    PAU -.->|"diperbaiki → resume"| RUN
    BRK -->|"tidak bisa"| SUB["Alihkan ke subcon<br/>flag + riwayat posisi terakhir"]
    SUB --> SPO
    SPO --> QCP

    subgraph S8["8 · Assembly"]
        PPNG["Ping-pong operator ⇄ QC<br/>kerja → pause → inspeksi → ulang"]
        TAT["Total durasi start–end<br/>operator vs QC terpisah"]
    end
    ROUT -->|"assy"| PPNG
    PPNG --> TAT

    subgraph S9["9 · Warehouse Packing &amp; Shipment"]
        PCK["Packing"]
        WAI["Menunggu instruksi /<br/>approval Marketing"]
        UPL["Upload bukti kirim<br/>surat jalan · foto · resi"]
    end
    QCP --> PCK
    TAT --> PCK
    PCK --> WAI --> UPL

    subgraph S10["10 · Delivered"]
        DEL["Delivered<br/>public order tracking"]
        RT{"Retur / komplain"}
    end
    UPL --> DEL
    DEL --> RT
    RT -->|"penyebab lain"| RPLC["Replacement"]
    RT -->|"salah gambar / produksi"| URG["Tiket revisi URGENT"]
    URG -.->|"LOOP-BACK edge"| ENG
```

Elemen DAG yang **wajib** didukung engine (semua muncul di interview):

| Kemampuan | Contoh di diagram |
|---|---|
| Edge bersyarat | `KLAS → machining/assy/standard` |
| Edge paralel (fan-in) | `QCP + TAT → PCK` |
| Fan-out multiplier | `JS = operation × 2` |
| Gate (tunggu event) | `GATE material ready`, `WAI approval Marketing` |
| Loop-back | `URG -.-> ENG` |
| Sub-proses per node berulang | S1 vs S9 (Warehouse ×2) |

---

## 7. Hierarki Artefak (Fan-out)

```mermaid
flowchart TD
    O["Order / Project (1)"] -->|"1 : 1"| MO["MO"]
    O --> PL["Final Part List"]
    PL --> P1["Part: machining"]
    PL --> P2["Part: assy"]
    PL --> P3["Part: standard (beli)"]
    P1 --> D1["Drawing rev 1..n"]
    D1 -->|"1 : ≥2"| OP1["Op-10 Sawing"]
    D1 --> OP2["Op-20 Milling"]
    OP1 -->|"× 2"| JSP["Jobsheet Produksi Op-10"]
    OP1 --> JQC["Jobsheet QC Op-10 (pair)"]
    OP2 --> JSP2["Jobsheet Produksi Op-20"]
    OP2 --> JQC2["Jobsheet QC Op-20 (pair)"]
    MO --> JSP
    MO --> JQC
    MO --> JSP2
    MO --> JQC2
    JSP --> T1["MachiningTask · start/stop per mesin"]
    P3 --> PRQ["PR standard part"]
```

Poin desain: fan-out menghasilkan **artefak nyata di tabel domain** (MO, Jobsheet, Task), bukan hanya JSON. `WorkflowNodeRun`/`ComponentRun` merekam *siapa membuat apa*, artefak tetap bisa di-query dengan performa tinggi untuk kanban/gantt/report yang sudah ada.

---

## 8. State Machine

### 8.1 Siklus hidup WorkflowNodeRun (generik, untuk semua node)

```mermaid
stateDiagram-v2
    [*] --> PENDING : edge masuk terpenuhi
    PENDING --> ACTIVE : prasyarat OK dan blocking actions sukses
    PENDING --> SKIPPED : kondisi routing tidak cocok
    ACTIVE --> WAITING : gate tertutup - material atau approval atau event
    WAITING --> ACTIVE : gate terbuka
    ACTIVE --> ON_HOLD : eskalasi atau pause manual
    ON_HOLD --> ACTIVE : resume
    ACTIVE --> DONE : exit criteria terpenuhi
    DONE --> [*]
    SKIPPED --> [*]
```

### 8.2 Rantai approval jobsheet (dari interview PPIC)

```mermaid
stateDiagram-v2
    [*] --> PREPARED : PPIC membuat jobsheet
    PREPARED --> CHECKED
    CHECKED --> APPROVED
    APPROVED --> FINAL_JUDGE
    FINAL_JUDGE --> [*] : disetujui penuh
    PREPARED --> REJECTED : ditolak di tahap mana pun
    CHECKED --> REJECTED
    APPROVED --> REJECTED
    REJECTED --> PREPARED : revisi dan submit ulang
```

> Pembeda penting: **status approval** dan **status pekerjaan** dua sumbu berbeda. Interview menyebut kerja boleh mulai sejak PREPARED/CHECKED — artinya `WORK_STARTED` tidak menunggu approval selesai.

### 8.3 Siklus kerja jobsheet produksi

```mermaid
stateDiagram-v2
    [*] --> NOT_READY : menunggu material
    NOT_READY --> READY : Warehouse Done
    READY --> IN_PROGRESS : operator start - sah sejak PREPARED/CHECKED
    IN_PROGRESS --> PAUSED : breakdown bisa diperbaiki atau ping-pong QC
    PAUSED --> IN_PROGRESS : perbaikan selesai atau QC lanjut
    PAUSED --> SUBCON : tidak bisa diperbaiki - dialihkan
    SUBCON --> QC_IN : hasil subcon kembali
    QC_IN --> IN_PROGRESS : lolos inspeksi
    IN_PROGRESS --> COMPLETED : QC pass semua operation
    COMPLETED --> [*]
```

---

## 9. Katalog Node Components

Komponen yang ditempel ke node — "apa yang dikerjakan DI DALAM node". Setiap kind punya config schema tervalidasi.

| Kind | Deskripsi | Contoh dari interview |
|---|---|---|
| `FORM` | Form dinamis (lanjutan form-templates) | Incoming Order: customer, produk, qty, tipe Regular/Final Part, req date |
| `DOCUMENT` | Template dokumen + field | Drawing Request; Drawing 2D; surat jalan |
| `APPROVAL` | Rantai tahap + role + aturan mulai kerja + kebijakan reject | PREPARED → CHECKED → APPROVED → FINAL JUDGE; mulai sejak PREPARED |
| `ROUTING` | Taksonomi klasifikasi + routing table | assy → Assembly; machining → Production; standard → Purchasing |
| `CALC` | Formula pada data context | Margin material 20×150×5 → 25×175×8 |
| `FANOUT` | Multiplier / agregasi / pairing artefak | 1 project = 1 MO; jobsheet = op × 2 QC pair |
| `QC_PATTERN` | Checklist per operation · ping-pong loop · multi-party signature | Inspeksi tiap op + hasil subcon; ttd 4 divisi |
| `TIMER` | Mode pencatatan waktu + atribusi | Start/stop machining; operator vs QC terpisah |
| `EVIDENCE` | Upload wajib (foto, ttd, dokumen) | Surat jalan, foto, resi saat shipment |
| `INVENTORY_POLICY` | Kebijakan stok & receiving | Standard part masuk stok, raw tidak; partial incoming |
| `SCHEDULING` | Constraint penjadwalan | Kapasitas ≤ 22 jam/hari; pindah mesin = approval + alasan |
| `GATE` | Kondisi node boleh dieksekusi | *Ready to machining*; tunggu approval Marketing |
| `ESCALATION` | Penanganan kejadian luar biasa | Breakdown → PAUSE / subcon; retur → tiket Urgent |

---

## 10. Action Components & Trigger

Aksi = efek samping **saat routing/transisi** — pola *when trigger fires → do a₁, a₂, … → lanjut*.

### 10.1 Empat titik pemicu

```mermaid
flowchart LR
    subgraph T["TRIGGER"]
        T1["EDGE<br/>transisi node A → B<br/>(+ condition)"]
        T2["NODE_STATE<br/>node capai status<br/>ACTIVE / DONE / SKIPPED"]
        T3["EVENT<br/>event bus domain"]
        T4["SCHEDULE<br/>cron / delay<br/>(SLA, reminder)"]
    end
    subgraph C["CONTEXT (shared, dot-path)"]
        CTX["workflowRun state<br/>+ hasil aksi sebelumnya<br/>mis. stockCheck.shortfall"]
    end
    subgraph A["ACTIONS (berurutan)"]
        A1["ODOO_RPC"]
        A2["PR_CREATE"]
        A3["LEDGER_POST"]
        A4["NOTIFY"]
        A5["DOC_GENERATE"]
        A6["dll."]
    end
    T --> CTX --> A
```

### 10.2 Katalog action

| Kind | Blocking default | Contoh pemakaian |
|---|---|---|
| `ODOO_RPC` | ❌ | Upsert Sales Order saat Incoming Order; update status delivered |
| `HTTP_REQUEST` | ❌ | Webhook pihak ketiga |
| `STOCK_CHECK` | ✅ | Warehouse cek kebutuhan → hasil `shortfall` di context |
| `LEDGER_POST` | ✅ | Material diterima → `IN`; issue → `OUT`; reservasi |
| `STOCK_RESERVE` | ✅ | Standard part tersedia → reserved |
| `PR_CREATE` | ✅ | Stok habis → PR ke Purchasing / Odoo Procurement |
| `PO_CREATE` | ❌ | PO vendor; subcon `SC-` Process/Preprocess |
| `DOC_GENERATE` | ✅ | Drawing Request, jobsheet, surat jalan |
| `NUMBER_ALLOCATE` | ✅ | Project number auto; MO-01; prefix `SC-` |
| `ARTIFACT_CREATE` | ✅ | MO, jobsheet pair, task |
| `MACHINE_ASSIGN` | ✅ | Assign + validasi kapasitas 22 jam/hari |
| `APPROVAL_START` | ✅ | Mulai rantai approval jobsheet |
| `NOTIFY` | ❌ | Material ready → operator; breakdown → maintenance |
| `CALC_APPLY` | ✅ | Terapkan margin material |
| `FIELD_SET` | ✅ | Set `readyToMachining = true` |
| `GATE_OPEN` / `GATE_WAIT` | ✅ | Buka/pasang gate shipment approval |
| `TRACKING_UPDATE` | ❌ | Update progres public tracking |
| `AUDIT_LOG` | ❌ | Audit eksplisit (semua aksi sudah otomatis ter-audit) |

> Menambah action baru = daftarkan executor (kontrak: config schema + context in/out). Engine tidak berubah.

---

## 11. Semantik Eksekusi Aksi

### 11.1 Transisi edge: aksi sync (in-transaction) + async (outbox)

```mermaid
sequenceDiagram
    autonumber
    participant E as DAG Executor
    participant TX as DB Transaksi
    participant OB as Outbox / ActionRun
    participant W as Action Worker
    participant O as Odoo

    E->>TX: BEGIN
    E->>TX: NodeRun Marketing = DONE
    E->>TX: Aksi sync DOC_GENERATE (blocking) → row Drawing Request
    E->>TX: Insert ActionRun ODOO_RPC status PENDING (idempotencyKey K1)
    E->>TX: COMMIT (perubahan state + outbox dalam SATU transaksi)
    E->>TX: NodeRun EngDesign = ACTIVE (blocking actions sudah sukses)
    OB->>W: poll nextRetryAt
    W->>O: upsert sale.order
    O-->>W: OK id=123
    W->>OB: SUCCESS resultJson id=123
```

### 11.2 Retry dan dead-letter (Odoo down)

```mermaid
sequenceDiagram
    autonumber
    participant W as Worker
    participant O as Odoo
    participant AR as ActionRun
    participant ADM as Admin Tenant

    W->>O: upsert sale.order
    O--xW: timeout 30 detik
    W->>AR: RETRYING attempts+1 · nextRetryAt = now + exponential backoff
    Note over W,AR: ulangi hingga max attempts
    W->>AR: DEAD setelah retry habis
    AR->>ADM: alert + panel Action Run gagal (payload + error lengkap)
    Note over ADM: perbaiki penyebab → tombol Re-enqueue manual<br/>(idempotencyKey mencegah dobel)
```

### 11.3 Prinsip yang tidak bisa dinegosiasi

| Prinsip | Mekanisme |
|---|---|
| **Atomicity** | Perubahan state node + outbox aksi async dalam satu transaksi DB |
| **Idempotency** | `idempotencyKey = (workflowRunId, actionDefId, triggerContext)` — retry tidak membuat PR/ledger ganda |
| **Blocking vs fire-and-forget** | `blocking: true` → node tujuan menunggu aksi sukses; `onFailure: BLOCK \| CONTINUE` |
| **Durability** | Aksi tidak hilang saat app restart (persist di ActionRun, diproses worker) |
| **Observability** | Setiap eksekusi tercatat: payload, hasil, attempts, error, durasi |

---

## 12. Pemetaan Interview → Komponen

Legenda: 🎛️ dikonfigurasi user · 🌐 global component

| Node | Perilaku interview | Komponen | 
|---|---|---|
| Marketing | Form incoming order + project no auto | 🎛️ FORM + NUMBER_ALLOCATE (🌐 numbering) |
| Marketing | Sync Odoo | 🎛️ ODOO_RPC (🌐 connector + outbox) |
| Marketing | Drawing Request | 🎛️ DOCUMENT |
| Eng Design | Breakdown Final Part List | 🎛️ FANOUT |
| Eng Design | Klasifikasi assy/machining/standard | 🎛️ ROUTING |
| Eng Design | Riwayat revisi drawing | 🌐 document versioning |
| Eng Process | Sequence, mesin, durasi, op type | 🎛️ FORM (🌐 master op type) |
| Eng Process | Margin material | 🎛️ CALC |
| Eng Process | CAM hanya machining | 🎛️ ROUTING (conditional) |
| PPIC | 1 project = 1 MO | 🎛️ FANOUT |
| PPIC | Cek material | 🎛️ STOCK_CHECK (🌐 inventory) |
| PPIC | Jobsheet ×2 QC pair | 🎛️ FANOUT pairing |
| PPIC | Routing tujuan jobsheet | 🎛️ ROUTING |
| PPIC | Assign mesin, 22 jam/hari, pindah = approval | 🎛️ SCHEDULING + APPROVAL (🌐 scheduler) |
| PPIC | Approval 4 tahap, mulai sejak PREPARED | 🎛️ APPROVAL (🌐 approval engine) |
| Warehouse | Stok ada/habis → PR | 🎛️ STOCK_CHECK + PR_CREATE |
| Warehouse | Receiving → Warehouse Done → ready | 🎛️ GATE + LEDGER_POST |
| Warehouse | Partial incoming | 🎛️ INVENTORY_POLICY |
| Warehouse | Cacat → ttd 4 divisi | 🎛️ QC_PATTERN multi-party |
| Purchasing | PR → PO + MoQ | 🎛️ CALC qty + DOCUMENT (🌐 purchasing) |
| Purchasing | Subcon SC- 2 jenis | 🎛️ NUMBER_ALLOCATE prefix + ROUTING sumber |
| Production | Start/stop | 🎛️ TIMER |
| Production | QC inspeksi per op + subcon | 🎛️ QC_PATTERN |
| Production | Breakdown → PAUSE/subcon | 🎛️ ESCALATION (🌐 machine events) |
| Assembly | Ping-pong | 🎛️ QC_PATTERN loop |
| Assembly | Waktu operator vs QC terpisah | 🎛️ TIMER attribution |
| Packing | Tunggu approval Marketing | 🎛️ GATE + APPROVAL |
| Packing | Upload bukti | 🎛️ EVIDENCE (🌐 storage) |
| Delivered | Public tracking | 🌐 portal |
| Delivered | Retur → tiket Urgent | 🎛️ LOOP_BACK edge + ESCALATION |

---

## 13. Skenario Kunci

### 13.1 Material shortage → PR → receiving → ready

```mermaid
sequenceDiagram
    autonumber
    participant PPIC as PPIC Node
    participant INV as Inventory Core
    participant EVT as Event Bus
    participant ACT as Action Executor
    participant ODP as Odoo Procurement
    participant NOT as Notification
    participant JS as Jobsheet

    PPIC->>INV: STOCK_CHECK (raw + margin, standard part)
    INV-->>EVT: STOCK_SHORTAGE (shortfall 3 item)
    EVT->>ACT: trigger EVENT
    ACT->>ODP: PR_CREATE (blocking) → PR-0456
    ACT->>INV: LEDGER_POST RESERVATION (qty yang tersedia)
    ACT->>NOT: NOTIFY Purchasing (PR_CREATED)
    ACT->>JS: GATE_WAIT MATERIAL_READY
    Note over JS: produksi jalan dengan partial (sesuai policy)
    ODP-->>ACT: material datang (partial) → MATERIAL_RECEIVED
    ACT->>INV: LEDGER_POST IN (partial)
    ACT->>JS: GATE_OPEN (ready to machining)
```

### 13.2 Mesin breakdown → PAUSE atau subcon

```mermaid
flowchart TD
    BD["Mesin breakdown dilaporkan"] --> Q{"Bisa diperbaiki?"}
    Q -->|"Ya"| PAU["Jobsheet PAUSE<br/>mesin DOWN + notif maintenance"]
    PAU --> FIX["Perbaikan selesai"]
    FIX --> RES["RESUME jobsheet"]
    Q -->|"Tidak"| SUB["Alihkan ke subcon<br/>PO prefix SC- Process"]
    SUB --> POS["Flag subcon +<br/>riwayat posisi terakhir"]
    SUB --> VND[[Vendor subcon]]
    VND --> QC["Hasil subcon kembali<br/>→ QC pair inspeksi"]
    QC -->|"lolos"| LANJ["Lanjut alur normal"]
    QC -->|"gagal"| RET["Rework / koordinasi vendor"]
```

### 13.3 Assembly ping-pong

```mermaid
sequenceDiagram
    autonumber
    participant OP as Operator
    participant JS as Jobsheet Assembly
    participant QC as QC
    participant TM as Timer

    loop sampai QC menyatakan selesai
        OP->>JS: start (TM: operator start)
        OP->>JS: pause (tahap kerja selesai)
        QC->>JS: inspeksi (TM: QC start)
        alt hasil OK
            QC->>JS: lanjut tahap berikut
        else rework
            QC->>JS: kembali ke operator + catat alasan
        end
    end
    QC->>JS: declare selesai
    JS->>TM: total = start–end · split operator vs QC
```

### 13.4 Retur → tiket revisi Urgent (loop-back)

```mermaid
flowchart LR
    DEL["Delivered"] --> RT{"Retur / komplain"}
    RT -->|"penyebab lain"| REPL["Replacement<br/>(fokus retur)"]
    RT -->|"salah gambar / produksi"| URG["Tiket revisi prioritas URGENT"]
    URG -.->|"LOOP-BACK edge<br/>(bukan edge normal)"| ED["Engineering Design"]
    ED --> DWG2["Drawing revisi baru"]
    DWG2 --> EPR2["Eng Process update operations"]
    EPR2 --> PPIC2["Jobsheet revisi (rencana baru)"]
```

> Loop-back **tidak mengubah** run historis (jobsheet lama tetap tercatat); ia membuat iterasi baru di node tujuan dengan referensi ke tiket retur — pola yang sama dipakai untuk revisi drawing normal.

---

## 14. Data Model

Model inti (ringkas — kolom metadata standar dihilangkan):

```mermaid
erDiagram
    TENANT ||--o{ ORDER_TYPE : memiliki
    ORDER_TYPE ||--o{ WORKFLOW_TEMPLATE : "versi"
    WORKFLOW_TEMPLATE ||--o{ WORKFLOW_NODE_DEF : berisi
    WORKFLOW_TEMPLATE ||--o{ WORKFLOW_EDGE_DEF : berisi
    WORKFLOW_NODE_DEF ||--o{ NODE_COMPONENT : "ditempeli"
    WORKFLOW_EDGE_DEF ||--o{ ACTION_DEF : "aksi on routing"
    ORDER ||--|| WORKFLOW_RUN : "instansiasi template aktif"
    WORKFLOW_RUN ||--o{ WORKFLOW_NODE_RUN : mengeksekusi
    WORKFLOW_NODE_RUN ||--o{ COMPONENT_RUN : menghasilkan
    ACTION_DEF ||--o{ ACTION_RUN : "dieksekusi sebagai"
    WORKFLOW_RUN ||--o{ ACTION_RUN : memicu
    ORDER ||--o{ MANUFACTURING_ORDER : "fan-out"
    MANUFACTURING_ORDER ||--o{ JOBSHEET : "fan-out"
    JOBSHEET ||--o{ MACHINING_TASK : berisi

    ORDER_TYPE {
        string code "REGULAR, FINAL_PART, custom"
        string name
        bool isActive
    }
    WORKFLOW_TEMPLATE {
        int version
        bool isActive "hanya 1 aktif per order type"
    }
    WORKFLOW_NODE_DEF {
        string nodeKey "warehouse-material, dst"
        string businessUnitId "divisi pemilik"
        json config
    }
    WORKFLOW_EDGE_DEF {
        string fromNodeId
        string toNodeId
        json condition "mis part.classification"
        string edgeType "SEQUENTIAL PARALLEL LOOP_BACK EXCEPTION"
    }
    NODE_COMPONENT {
        string kind "FORM APPROVAL ROUTING dll"
        json config
        int order
    }
    ACTION_DEF {
        string triggerType "EDGE NODE_STATE EVENT SCHEDULE"
        string kind "ODOO_RPC PR_CREATE dll"
        json config
        bool blocking
        json retry
    }
    WORKFLOW_RUN {
        string status
        string templateVersion
    }
    WORKFLOW_NODE_RUN {
        string status "PENDING ACTIVE WAITING DONE SKIPPED"
    }
    ACTION_RUN {
        string status "PENDING RUNNING SUCCESS RETRYING DEAD"
        string idempotencyKey "unique"
        int attempts
        json payload
        json result
        datetime nextRetryAt
    }
```

Perubahan dari schema saat ini:

1. `Order.status` (enum) → status turunan dari posisi `WorkflowRun` (tetap dipetakan ke label ringkas untuk dashboard/portal).
2. `Jobsheet.preparedBy/checkedBy/approvedBy` → data `ComponentRun` dari komponen APPROVAL (rantai panjangnya bebas).
3. MO/Jobsheet/Task **tetap ada** — dibuat oleh komponen, bukan dihapus.

---

## 15. Pengalaman Builder untuk End User

```mermaid
flowchart LR
    A["1. Buat / pilih<br/>Order Type"] --> B["2. Susun node<br/>dari katalog node type"]
    B --> C["3. Tempel komponen<br/>ke tiap node<br/>(form, approval, QC, ...)"]
    C --> D["4. Gambar edge<br/>+ kondisi routing"]
    D --> E["5. Klik edge →<br/>tambah actions<br/>(ala Zapier)"]
    E --> F["6. Validasi &<br/>dry-run data contoh"]
    F --> G{"Valid?"}
    G -->|"tidak"| C
    G -->|"ya"| H["7. Publish<br/>sebagai versi baru"]
```

Validasi yang dijalankan sebelum publish:

- **Struktur**: semua node terhubung (tidak ada orphan kecuali terminal), ada minimal 1 node start & end, loop-back hanya pada tipe edge yang diizinkan.
- **Kontrak**: config tiap komponen lolos JSON Schema; referensi dot-path antar aksi (`itemsFrom: "stockCheck.shortfall"`) valid.
- **Semantik**: tidak ada cycle tanpa exit; aksi blocking tidak saling menunggu (deadlock); setiap `GATE_WAIT` punya minimal satu event pembuka.
- **Dry-run**: jalankan dengan data contoh → tampilkan DAG yang dilalui + aksi yang terpicu, sebelum template dipakai order nyata.

---

## 16. Katalog Event

| Domain | Event |
|---|---|
| Order | `ORDER_CREATED` · `ORDER_RELEASED` · `ORDER_CANCELLED` · `ORDER_DELIVERED` |
| Engineering | `DRAWING_REQUEST_CREATED` · `DRAWING_RELEASED` · `DRAWING_REVISED` · `OPERATIONS_DEFINED` · `CAM_CREATED` |
| PPIC | `MO_CREATED` · `JOBSHEET_CREATED` · `JOBSHEET_ROUTED` · `MACHINE_ASSIGNED` · `MACHINE_REASSIGN_REQUESTED` |
| Approval | `APPROVAL_STAGE_PASSED` · `APPROVAL_REJECTED` · `APPROVAL_COMPLETED` |
| Material | `STOCK_CHECKED` · `STOCK_SHORTAGE` · `MATERIAL_RESERVED` · `PR_CREATED` · `PO_ISSUED` · `MATERIAL_PARTIAL_RECEIVED` · `MATERIAL_READY` · `MATERIAL_DEFECT_VERIFIED` |
| Shopfloor | `WORK_STARTED` · `WORK_PAUSED` · `WORK_RESUMED` · `QC_PASSED` · `QC_REJECTED` · `MACHINE_DOWN` · `SUBCON_REDIRECTED` · `SUBCON_RETURNED` |
| Shipment | `PACKING_DONE` · `SHIPMENT_APPROVED` · `DELIVERY_PROOF_UPLOADED` |
| Retur | `RETURN_FILED` · `URGENT_REVISION_TICKET` |

Event adalah **bahasa bersama** antara node components, action triggers, dan SLA/schedule triggers.

---

## 17. Contoh Konfigurasi

### 17.1 Node PPIC

```jsonc
{
  "nodeKey": "ppic",
  "businessUnitId": "bu-ppic",
  "components": [
    { "kind": "FANOUT", "config": { "rule": "ONE_PER_ORDER", "artifact": "MANUFACTURING_ORDER" } },
    { "kind": "FANOUT", "config": { "rule": "PER_OPERATION_X2_QC_PAIR", "artifact": "JOBSHEET", "pairType": "PRODUCTION_QC" } },
    { "kind": "ROUTING", "config": { "mapping": { "machining": "production", "assy": "assembly" } } },
    { "kind": "SCHEDULING", "config": {
        "machineCapacityHoursPerDay": 22,
        "reassignRequiresApproval": true,
        "reassignReasonRequired": true } },
    { "kind": "APPROVAL", "config": {
        "stages": [
          { "name": "PREPARED", "role": "PPIC" },
          { "name": "CHECKED", "role": "PPIC_LEAD" },
          { "name": "APPROVED", "role": "PRODUCTION_MANAGER" },
          { "name": "FINAL JUDGE", "role": "PLANT_MANAGER" } ],
        "workMayStartAtStage": "PREPARED",
        "onReject": "RETURN_TO_STAGE" } }
  ]
}
```

### 17.2 Edge Marketing → Eng Design (dengan actions)

```jsonc
{
  "from": "marketing", "to": "eng-design",
  "condition": { "event": "ORDER_RELEASED" },
  "actions": [
    { "kind": "ODOO_RPC", "order": 1, "blocking": false,
      "config": { "model": "sale.order", "op": "upsert", "fieldMapping": "odoo.so" },
      "retry": { "max": 5, "backoff": "exponential", "timeoutMs": 30000 } },
    { "kind": "DOC_GENERATE", "order": 2, "blocking": true,
      "config": { "template": "drawing-request" } },
    { "kind": "TRACKING_UPDATE", "order": 3,
      "config": { "progressLabel": "Masuk Engineering Design" } }
  ]
}
```

### 17.3 Trigger event: stok kurang

```jsonc
{
  "on": { "event": "STOCK_SHORTAGE", "scope": "warehouse-material" },
  "actions": [
    { "kind": "STOCK_CHECK", "order": 1, "blocking": true,
      "config": { "itemsFrom": "material.requirements",
                  "stockPolicy": { "STANDARD_PART": "STOCKED", "RAW_MATERIAL": "NOT_STOCKED" } } },
    { "kind": "PR_CREATE", "order": 2, "blocking": true,
      "config": { "target": "odoo-procurement", "itemsFrom": "stockCheck.shortfall" } },
    { "kind": "LEDGER_POST", "order": 3,
      "config": { "type": "RESERVATION", "itemsFrom": "stockCheck.available" } },
    { "kind": "NOTIFY", "order": 4,
      "config": { "to": ["ROLE_PURCHASING"], "template": "PR_CREATED" } }
  ]
}
```

---

## 18. Strategi Migrasi dari Sistem Saat Ini

```mermaid
flowchart LR
    P1["Fase 1<br/>Engine berjalan paralel<br/>order baru pakai workflow<br/>order lama tetap enum"] --> P2["Fase 2<br/>Kanban, Gantt, laporan<br/>dibaca dari WorkflowRun<br/>(kompat layer status)"]
    P2 --> P3["Fase 3<br/>Modul statis lama<br/>(UI order/jobsheet hardcoded)<br/>digantikan node UI"]
    P3 --> P4["Fase 4<br/>Enum status dihapus<br/>semua tenant pakai<br/>workflow template"]
```

- **Kompat layer**: `Order.status` tetap terisi (dipetakan dari posisi WorkflowRun) supaya dashboard, portal, dan laporan yang ada tidak rusak di fase transisi.
- **Modul yang tetap dipakai apa adanya**: machine management, inventory, audit, auth — tinggal dibungkus jadi global components.

---

## 19. Roadmap Implementasi

```mermaid
gantt
    title Roadmap indikatif (durasi relatif, bukan tanggal komitmen)
    dateFormat YYYY-MM-DD
    axisFormat %b
    section Fondasi
    Workflow engine DAG + state machine        :f1, 2026-01-05, 25d
    OrderType + template versioning            :f2, after f1, 15d
    section Action Framework
    Trigger + outbox + retry + idempotency     :a1, after f2, 20d
    NOTIFY + panel ActionRun                   :a2, after a1, 10d
    section Komponen Inti
    FORM + DOCUMENT + numbering                :c1, after a2, 20d
    APPROVAL + ROUTING + FANOUT                :c2, after c1, 20d
    section Material Loop
    INVENTORY + PR/PO + Odoo RPC + GATE        :m1, after c2, 25d
    section Shopfloor
    TIMER + QC_PATTERN + SCHEDULING            :s1, after m1, 25d
    section Ketahanan
    ESCALATION + loop-back + SLA schedule      :k1, after s1, 15d
    section Builder
    Visual workflow builder UI + validasi      :b1, after k1, 30d
```

| Fase | Deliverable | Gerbang keluar (definition of done) |
|---|---|---|
| Fondasi | Engine + versioning | 1 order type end-to-end 2 node sederhana di production |
| Action framework | Trigger + outbox | Aksi Odoo gagal → auto-retry → panel admin → re-enqueue manual, tanpa data ganda |
| Komponen inti | FORM/DOCUMENT/APPROVAL/ROUTING/FANOUT | Node PPIC penuh (jobsheet ×2 + approval 4 tahap) berjalan dari config |
| Material loop | INVENTORY + PR/PO + Odoo + GATE | Skenario 13.1 (shortage → ready) lulus uji |
| Shopfloor | TIMER + QC + SCHEDULING | Skenario 13.2 & 13.3 lulus uji |
| Ketahanan | ESCALATION + loop-back | Skenario 13.4 (retur → revisi Urgent) lulus uji |
| Builder | UI visual | Admin tenant non-teknis membuat order type baru tanpa bantuan developer |

> Urutan ini disengaja: **builder UI paling akhir**. Kontrak komponen dan engine harus stabil dulu; kalau tidak, UI builder akan dirombak berulang kali.

---

## 20. Risiko & Keputusan Desain Terbuka

### 20.1 Risiko

| Risiko | Mitigasi |
|---|---|
| Workflow misconfigured membuat order macet | Validasi publish + dry-run + deteksi deadlock + alert node WAITING terlalu lama |
| Aksi ganda (double-PR, ledger dobel) | IdempotencyKey unik + eksekusi single-worker per key |
| Performa (run table membesar) | Indeks per tenant/run; arsip run selesai; artefak domain tetap tabel normal |
| Kompleksitas builder mengagetkan user | Mulai dari template siap-pakai (reference workflow §6) yang bisa di-copy lalu dimodifikasi |
| Perubahan template vs order berjalan | Run terkunci versi; template baru berlaku untuk order berikutnya |

### 20.2 Pertanyaan untuk dikonfirmasi ke user/bisnis

1. **Odoo**: semua tenant pakai Odoo, atau perlu mode tanpa ERP (PR/PO internal penuh)?
2. **Siapa workflow designer**: role baru `WORKFLOW_DESIGNER`? Per-tenant atau global?
3. **Standard part**: cukup routing langsung ke Purchasing (tanpa node tersendiri), atau perlu node proses tersendiri?
4. **CAM**: perlu approval tersendiri sebelum release ke shopfloor?
5. **Retensi ActionRun** berapa lama (audit vs storage)?
6. **Batas ukuran template**: max node/komponen per workflow (guardrail performa)?
7. **SLA numeric per node** (jam) — apakah dibutuhkan di rilis pertama, atau cukup trigger SCHEDULE?

---

*Dokumen ini menjadi single source of truth desain dynamic workflow ManuOS. `DYNAMIC_WORKFLOW_DESIGN.md` (versi awal) dapat diarsipkan.*
