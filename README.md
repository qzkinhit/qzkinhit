# Zekai Qian

Ph.D. student in Computer Science at Harbin Institute of Technology. I work on **data-centric AI**, with a focus on data cleaning, data quality governance, demand-driven data preparation, and reliable ML/AutoML pipelines over imperfect tabular data.

<p>
  <a href="https://qzkinhit.github.io/qzkinhit/"><img alt="Homepage" src="https://img.shields.io/badge/Homepage-qzkinhit.github.io-0f766e?style=flat-square"></a>
  <a href="https://scholar.google.com/citations?user=T2CXrMwAAAAJ"><img alt="Google Scholar" src="https://img.shields.io/badge/Google%20Scholar-Zekai%20Qian-2563eb?style=flat-square"></a>
  <a href="https://dblp.org/pid/414/5427.html"><img alt="DBLP" src="https://img.shields.io/badge/DBLP-414%2F5427-b7791f?style=flat-square"></a>
  <a href="https://github.com/qzkinhit"><img alt="GitHub" src="https://img.shields.io/badge/GitHub-qzkinhit-111827?style=flat-square"></a>
  <a href="https://www.cnblogs.com/zekaiblogs"><img alt="CNBlogs" src="https://img.shields.io/badge/CNBlogs-zekaiblogs-e85d4f?style=flat-square"></a>
</p>

## Now

- Building agentic and task-aware data preparation systems that decide **what to clean, how much to intervene, and which operators to trust** before committing data-side changes.
- Recent work includes **DMCO** at ICML 2026, **DemandClean** and **UniClean** in PVLDB 2025, and open artifacts around **DemandPrep**, **UniClean**, **DemandClean**, and **MADClean**.
- I enjoy turning research systems into reproducible software: cached artifacts, baseline runners, traceable workflows, and interactive demos.

## Selected Papers

| Year | Venue | Work |
| --- | --- | --- |
| 2026 | ICML | [DMCO: Budget-Aware Co-Optimization of Data Cleaning and AutoML](https://icml.cc/virtual/2026/poster/64882) |
| 2025 | PVLDB | [DemandClean: A Multi-Objective Learning Framework for Balancing Model Tolerance to Data Authenticity and Diversity](https://doi.org/10.14778/3750601.3750666) |
| 2025 | PVLDB | [UniClean: A Scalable Data Cleaning Solution for Mixed Errors based on Unified Cleaners and Optimized Cleaning Workflow](https://doi.org/10.14778/3749646.3749681) |
| 2025 | ICDE | [UniClean: A Multi-Signal Fusion Pipeline for Optimizing Data Cleaning Workflow](https://doi.org/10.1109/ICDE65448.2025.00362) |
| 2025 | ICDE | [$t$DCDiscover: Mining Threshold Denial Constraints from Time Series Data](https://doi.org/10.1109/ICDE65448.2025.00193) |
| 2025 | ICDE | [CBAClean: A Comprehensive System for Recommending Data Cleaning Solutions Through Cost-Benefit Analysis in Data Quality Management](https://doi.org/10.1109/ICDE65448.2025.00371) |

## Open Source

| Project | What it is |
| --- | --- |
| [DemandPrep-artifact](https://github.com/qzkinhit/DemandPrep-artifact) | Reproducible artifact for demand-driven data preparation via action allocation and operator-grounded execution. |
| [DemandClean](https://github.com/qzkinhit/DemandClean) | RL-based framework for learning data cleaning actions under authenticity, diversity, and downstream model tolerance. |
| [UniClean-bench-Result](https://github.com/qzkinhit/UniClean-bench-Result) | Benchmark-style release with native dirty datasets, cleaned outputs, logs, and baseline comparisons for UniClean. |
| [MADClean](https://github.com/qzkinhit/MADClean) | Model-aware data cleaning framework for improving SVM utility and data quality under constrained cleaning cost. |
| [MDCBaseline](https://github.com/qzkinhit/MDCBaseline) | Unified runner and evaluation support for classic data cleaning baselines. |

## Research Taste

I like systems that expose the control boundary between data, operators, and downstream models:

- **Task demand first**: a cleaning action should be justified by downstream utility, not only by data-level neatness.
- **Operator grounding**: agents should produce inspectable repair plans, traces, and provenance instead of opaque edits.
- **Reproducible evidence**: papers should ship artifacts that let others rerun cached summaries, full experiments, and baseline comparisons.

<p>
  <img height="165" alt="GitHub stats" src="https://github-readme-stats.vercel.app/api?username=qzkinhit&show_icons=true&hide_title=true&rank_icon=github&theme=default">
  <img height="165" alt="Top languages" src="https://github-readme-stats.vercel.app/api/top-langs/?username=qzkinhit&layout=compact&hide_title=true&theme=default">
</p>
