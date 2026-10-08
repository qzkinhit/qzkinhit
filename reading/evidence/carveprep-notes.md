# CARVEPrep 本地证据说明

核查日期为 2026-10-06。只读原始仓库，没有重跑训练。

## 版本结论

- 活跃稿件为 Paper1_CARVEPrep_Writing/CARVEPrep_iclr27_v20260925_final_zh.tex，系统实现为 CARVEPrep-Benchmark。Benchmark HEAD 5903558（2026-09-21）。
- Paper1_TabFM_Cleaning README 当前题目为 Clean What the Task Needs: Budgeted Cell-Level Action Allocation for Tabular In-Context Prediction，不能与 CARVEPrep 混作同一实现。
- 活跃主结果来自 results_raw/final_round_v12/f2_merged.csv。文档 NUMBER_OWNERS.md 的前半是旧9月9日口径，末尾 v12 段才对应当前表。
- 原始图表可包含旧辅助批次。这里未混合为额外训练种子。

## 关键核实

1. collect→allocate→execute→diagnose/run_round。核心 facade carveprep/api/carveprep.py。
2. common.py:207 的 training_blob clean=None；api/carveprep.py:379 的 source因此为dirty。action_value.py旧注释及形参clean不可按字面解释为主调用链读取真值。
3. 行身份保持到AllocationResult；execute_training_actions过滤w=0行。训练产物train.csv仍保存原900行，__sample_weight__里保留0。
4. 主表Adult n_rows900、n_deleted270、n_repaired253、cells_changed306、n_acted523、policy=rho_loss_repair@0.3。消费者630行。总干预523超过自身分配预算270，现稿03_problem.tex:27明确完整对比候选不受该b约束。
5. 当前六表所选CARVEPrep均含删除，仅Adult修复，全部n_downweighted=0。
6. action_values是17维状态至4动作LightGBM回归输出；每随机子集用整体准确率差除子集大小作共同目标。不是精确单记录边际因果贡献。
7. ranking使用tier.sum而不是论文记录状态tier_max；max也是动作价值状态的一维。
8. ICL shortlist前k之外加入NoFix和influence/rho_loss强制候选。Adult主info.json实际6个finetune候选。
9. 普通bootstrap不提供无条件测试不下降保证。Cert的冻结候选、独立同分布验收与最终重训转移是额外条件。
10. 源码influence实际为ref likelihood评分；现稿已采用Ref. likelihood命名。
11. 三路数据规模按70/30外层与min(reference_rows, floor(0.4*nfit))参照切分核对。Adult2000=900+500+600；Hospitals1000=420+280+300；Breast699=294+195+210。
12. 教学8行示例仅实现FD/缺失与分配语义，动作价值和标签否定为预设，不执行真实模型。bootstrap浏览器使用固定LCG200次，不声称逐样本复制NumPy seed。

## 产物选取与数据变换

采用证据快照orca_results/v12/e6/adult_carveprep/.../info.json（tag=main）。未用同目录main_absorb/main_lar/main_top5变体。前10行record与train按行序对齐，展示准备后值，不制造未保存的修改前值。原始CSV中零写入mis_rewrite_rate=0.0在解释中明确为无写入而非测得零条件风险。

HTML由本目录build_carveprep.py生成，内嵌源片段、真实摘要和教学JS，不依赖CDN。

## 源码片段行号

- `CARVEPrep-Benchmark/posttrain/tabpfn_lane/common.py` L75–L108
- `CARVEPrep-Benchmark/posttrain/tabpfn_lane/common.py` L207–L215
- `CARVEPrep-Benchmark/carveprep/api/carveprep.py` L127–L132
- `CARVEPrep-Benchmark/carveprep/core/allocation/action_value.py` L226–L261
- `CARVEPrep-Benchmark/carveprep/core/allocation/record_allocator.py` L149–L184
- `CARVEPrep-Benchmark/carveprep/core/adoption/adopt.py` L277–L285
- `CARVEPrep-Benchmark/carveprep/core/adoption/bootstrap_rule.py` L20–L32
- `CARVEPrep-Benchmark/carveprep/training/action_executor.py` L47–L58
- `CARVEPrep-Benchmark/carveprep/training/weighted_loss.py` L21–L33
- `CARVEPrep-Benchmark/carveprep/training/closed_loop.py` L115–L129

## 读取文件 SHA-256

- `Paper1_CARVEPrep_Writing/sections_zh/03_problem.tex`
  `eb4e56e361d62e943b3bb03a21545baace4174a9a3f350d0f8088a64eed26305`
- `Paper1_CARVEPrep_Writing/sections_zh/04_method.tex`
  `a7d807c35089377e55a4c0b8dccd8d2d3ce7a1eab5784c4833c42a86cb09c181`
- `Paper1_CARVEPrep_Writing/sections_zh/05_experiments.tex`
  `08cb12fbbf45eabad1329fccc3536715ae7163eb7f57e732773129f7b4e8a499`
- `Paper1_CARVEPrep_Writing/docs/NUMBER_OWNERS.md`
  `c3c99021729028d9e09d6e2542ab02427af7cfbc8acb0c11c06e74f191147991`
- `Paper1_CARVEPrep_Writing/tables/table1_effect_zh.tex`
  `b137816c67b23f2f21f4bfca7d1f891d9e4569e9d271bb0a68f811a3ec4e65b9`
- `Paper1_CARVEPrep_Writing/results_raw/final_round_v12/f2_merged.csv`
  `4bab625e1217c8e8a134359c1624d9b6f38ee48155b4f586632bb415c2fcc338`
- `CARVEPrep-evidence-20260914/orca_results/v12/e6/adult_carveprep/f2/artifacts/adult/rho0.4/seed1/carveprep/info.json`
  `cf2de85986b8518cbe2db1e0f3edc0bc1cc6b25c584bd0909d4a95188267528f`
- `CARVEPrep-evidence-20260914/orca_results/v12/e6/adult_carveprep/f2/artifacts/adult/rho0.4/seed1/carveprep/records.csv`
  `ab547e357fe044533d00dfdbda58eedac4d050a245a2938fb7fcf11f6fda719a`
- `CARVEPrep-evidence-20260914/orca_results/v12/e6/adult_carveprep/f2/artifacts/adult/rho0.4/seed1/carveprep/train.csv`
  `3d5c0661c2b518dfce792c5f1fb66bf8d9fe2e6aec20fddcc92ca21a936276b9`
- `CARVEPrep-Benchmark/posttrain/tabpfn_lane/common.py`
  `bf2596feba083b125a455a7eef83112b8c6783e330aaf0ee520781b574e2a525`
- `CARVEPrep-Benchmark/carveprep/api/carveprep.py`
  `6b05d6820ca4d8d69b9e878561782d4b4eaa5929981bb2db6e30b1fd7335be14`
- `CARVEPrep-Benchmark/carveprep/core/allocation/action_value.py`
  `e231edf007dfe1165069e0bc479f80b3e99c5b6154fc04ab53d0c9b057a5018b`
- `CARVEPrep-Benchmark/carveprep/core/allocation/record_allocator.py`
  `26f348a640e62d6c3f6cdfdd11451028d220021acc0f02b0567510c785c5a950`
- `CARVEPrep-Benchmark/carveprep/core/adoption/adopt.py`
  `bd14810974739cd4d6e9b0f9faeb404d18d761967e383d6567e9e80f20a763b7`
- `CARVEPrep-Benchmark/carveprep/core/adoption/bootstrap_rule.py`
  `7b4db9ebc1a36119d0632cedeedaf6f28c4d0bd875d3d24623578548c9e09516`
- `CARVEPrep-Benchmark/carveprep/training/action_executor.py`
  `8e07a525980e15ca4ee1dd8f40623fde4560710ad69dcc2e5a468bc0f353407d`
- `CARVEPrep-Benchmark/carveprep/training/weighted_loss.py`
  `3b1b7e4463fd4f1318b3fe975cd707b007c9165cc65b70aaabdf8ff2569d9c40`
- `CARVEPrep-Benchmark/carveprep/training/closed_loop.py`
  `80ee29a999f86c0464da51d89c5bfd9c06b1c57d4968905dc6fd60c3ce58b438`

## 第二轮深度覆盖与自审

读取活跃主文件的全部正文输入及现用07_appendix.tex（876行）、09_search_space.tex（55行），生成40个section/subsection/subsubsection覆盖节点。coverage JSON保留真实标题、行号、用途、公式/算法/定理标签、源码映射。02_related.tex只是占位，不纳入。

新增8行教学数据的中间轨迹由原库纯函数实际生成。源输入与概率、动作价值V是明确标注的预设；collect_evidence、record_features、record_rank、allocate_records为原函数。状态8×17，单元矩阵8×4，4种菜单×9个预算共36组合。无TabPFN/LightGBM拟合。generate_carveprep_trace.py可在Benchmark既有.venv-smoke中复现。

新核实与解释边界如下。

- 最新附录明确层级求和排序、min-max常数映为0及同分输入顺序，正文tier_max与排名tier_sum是用途区别，不是算法冲突。
- latest附录区分标签重抽触发与实际错标后验，后者有(1-q)因子。部署q≤b为似然比规则，不能称为知道噪声率情况下的严格Bayes错标删除条件。
- action_value训练episode直接collect_evidence，未拟合record_prior，故该输入维通常为0；应用期完整collect可提供非零值。代码仍可通过排名使用该先验，不能假定回归器在此默认episode中学到非零该维效应。
- 短后训练probe传reference=None并固定周期，最终重训才参照早停。
- support_replay_plan顶部旧注释讲取整，但实际函数保证所有正权重至少出现一次；加权ICL筛选走weighted_inclusion_draws，二者语义需分开。
- ordinal_encode将数值无法解析项用首帧中位数填充，这是接口编码，不计为准备表原值修复。共同词表/数值判断涉及所有传入特征帧，独立验收的完整函数冻结必须覆盖编码；本页未确认完整独立性保证成立。
- latest记录级校准引理使用独立记录上的B-alpha*A和Hoeffding；现库ltt_risk_gate.py按单修复布尔结果用Clopper-Pearson，与最新引理非逐字对应实现。
- 未在已读主执行链找到最终重训后额外独立无标签分歧样本的采集，重训保证被标为有条件理论扩展。
- 默认多数恢复界q*=0.4，要求rho<q*；主混合实验rho=0.4并不满足严格条件，不能直接给全部组套该指数恢复保证。

自审修正了覆盖标题中的同行label提取、三阶段矩阵维度、episode至少8个可疑记录、排名定义层次、预设概率与实算中间量标注。40章节节点包含原文公式；17类实验、12类流程对照各有独立协议说明。未重新验证全部引用文献，未训练模型，未重跑全量实验，未把每条理论保证映射成已执行证书。

页面逻辑检查通过：82个唯一ID，61个有效内部锚点；360个矩阵阶段/菜单/预算视图组合，21个episode组合，12个隔离视图组合；解析风险全四动作0、仅RD5/72、禁修复1/16、禁分数权重1/144；4种交互场景。Node --check通过。浏览器390px复检由根任务完成。

## 真实浏览器390px复检

通过系统Chrome无头浏览器与Playwright测试，全部details展开后document.scrollWidth=390，与视口一致，所有交互完成后仍为390，pageerror为空。初检发现两个未包裹的details表格和网格项min-content导致溢出，已在carveprep_deep.py内同步修正。17维state表在手机上保留可读列宽，通过局部横向滚动阅读。

实测trace的r6正确显示修复并降权，预算0退回保留；所有10类矩阵视图可切换；episode删除target0.10000、修复target0.06667；4种理论菜单预算3时风险分别0、0.069444、0.062500、0.006944；删除＋修复交互风险0；独立验收示例短训练维度3×500；章节搜索正常。浏览器报告为carveprep-browser-report.json，检查脚本carveprep_browser_check.cjs，截图carveprep-trace-390.png和carveprep-theory-390.png。
