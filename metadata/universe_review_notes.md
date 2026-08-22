# Final semiconductor universe decisions

## Classification philosophy

This is a researcher-defined economic universe for studying conditional information transmission and relative price discovery. Membership and tiering reflect semiconductor business role, value-chain position, product category, and economic exposure. They do not use stock correlations, returns, profitability, or trading behavior.

`universe_tier` is a research-design recommendation, not a point-in-time eligibility decision:

- `core` identifies economically direct companies recommended for the primary universe.
- `extension` identifies relevant companies useful for global or robustness analysis where business mix, specialized role, listing market, or short history adds complexity.

Classification is final. The retained universe uses only `core` and `extension` tiers.

## Companies added

| ticker | company | subsector | status | tier | rationale |
|---|---|---|---|---|---|
| CDNS | Cadence Design Systems | eda_ip | CLEAR | core | Adds a second major EDA platform alongside Synopsys. |
| FORM | FormFactor | packaging_testing | CLEAR | extension | Adds probe cards and test-and-measurement exposure. |
| 6857.T | Advantest | packaging_testing | CLEAR | core | Adds a major global automatic test equipment supplier. |
| AMKR | Amkor Technology | packaging_testing | CLEAR | core | Adds a major independent OSAT provider. |
| 285A.T | Kioxia Holdings | memory | CLEAR | core | Adds major NAND exposure to a DRAM/HBM-heavy memory group. |
| 3436.T | SUMCO | semiconductor_materials | CLEAR | extension | Adds silicon-wafer supply exposure for robustness analysis. |
| 4063.T | Shin-Etsu Chemical | semiconductor_materials | CLEAR | extension | Adds wafers and process materials for robustness analysis but has broad chemicals exposure. |
| SOI.PA | Soitec | semiconductor_materials | CLEAR | extension | Adds engineered semiconductor substrates for robustness analysis. |
| 6963.T | ROHM | analog_mixed_signal | CLEAR | extension | Adds Japanese power and silicon-carbide semiconductor exposure. |

## Researcher decisions and removals

- Every retained company has an explicit `universe_tier`; the three removals below are direct researcher decisions.
- Samsung Electronics was removed by researcher decision because diversified electronics and foundry activities make the parent-company signal too broad for this universe.
- Broadcom was removed by researcher decision because its infrastructure-software exposure materially dilutes the semiconductor signal.
- Teradyne was removed by researcher decision because its industrial-automation exposure complicates interpretation of semiconductor test-equipment information.
- ASML remains `CLEAR` and `core`. Its note now explicitly reserves global listing and time-zone handling for the later eligibility stage.
- Coherent is finalized as `CLEAR` in `extension`; its photonics, lasers, and optical-communications exposure makes it a robustness company rather than a pure semiconductor core company.
- Cerebras remains economically relevant but moves to `extension` because its May 2026 listing provides little public history and its model combines accelerators, systems, and services.
- Qnity is finalized as `CLEAR` in `extension`; its recent separation/listing and broader interconnect exposure keep it outside the core.
- All semiconductor-materials companies are robustness-only and therefore assigned to `extension`, including Entegris.
- Global Unichip is confirmed as `fabless_compute` and remains in `extension` because its design-service model is specialized.

## Later implementation work

1. Divide `packaging_testing` before role-specific analysis into OSAT services, automatic test equipment, and probe/test-interface suppliers. The present taxonomy remains unchanged until that later design step.
2. Apply the materials group only in robustness analysis; determine the exact specification and minimum peer count after the packaging/testing split is designed.
3. Apply later point-in-time rules to recent listings, especially Cerebras, CXMT, and Qnity, without changing their economic classification retrospectively.
4. Select ADR versus local share lines for dual-listed companies before constructing the investable or synchronized panel.

## Core universe recommendation

The recommended 36-company core is:

NVDA, TSM, MU, 000660.KS, AMD, ASML, INTC, LRCX, AMAT, ARM, TXN, KLAC, MRVL, 2454.TW, ADI, QCOM, 8035.T, ASX, IFX.DE, SNPS, MPWR, NXPI, ASM, UMC, STM, CRDO, 6146.T, MCHP, 6723.T, ON, GFS, TSEM, CDNS, 6857.T, AMKR, and 285A.T.

This set covers compute design, mobile/connectivity, logic IDM, memory, foundry, equipment, materials, packaging/testing, EDA/IP, and analog/power. It is an economic recommendation only; later eligibility filters may produce a smaller dated panel.

## Extension universe recommendation

The recommended 18-company extension is:

688825.SS, 688256.SS, 0981.HK, 002371.SZ, COHR, 688012.SS, CBRS, 603986.SS, Q, 1347.HK, 3443.TW, ENTG, TPRO.MI, FORM, 3436.T, 4063.T, SOI.PA, and 6963.T.

These firms add China and other international listings, recent issuers, specialized ASIC/test roles, and robustness-only materials coverage. COHR and Q are finalized as extension companies.
