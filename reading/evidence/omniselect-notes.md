# OmniSelect 本地阅读证据

读取日期：2026-10-06。仅阅读原库，未训练、未改原库。

论文主线：Paper2_OmniSelect/papers/vldb2027/omniselect_vldb_zh.tex

主代码：OmniSelect-Benchmark-public；HEAD 85cc0ff032722e6ba74b4539b7811a6dd6824209。

旧代码 OmniSelect-Benchmark HEAD 0fd1ed777957a25a4b4e7b104e25419b58ab9c8a，仅做差异比较。

论文库 HEAD dd1fd1d4a4a66a17b1b458297e0560d9a2c02a11。

发布归档 results/paper/records/main_v2_3.tar.gz 内 R1v22/vision/cifar100n/clip_vitb32/seed_2。目录名保留历史别名，config.json batch 为 R1v23，protocol 为 v2_2。

实际运行 start_time=2026-09-30T13:19:28+0800，运行 git sha=5cfa44b9adc8c24ba2278124718c96118c6620fc。

实际数据 4000 pool, 240 con, 400 rank, 160 conf, 2000 test；k=2000。

当选 coop gate=authenticity rho=1.15 within=kcenter；selection sha cc6240a97224，2000 唯一下标。

pool 干净比例0.592，当选0.8025；测试准确率0.3955，random0.323，full0.4405。

排序参照0.4175，挑战者0.44，差0.0225，边际0.0062625。确认配对差-0.025，e=1<60，未认证；audit 不改变选举。

融合20个不同子集筛至4；协同14筛至3；82次拟合，154次缓存命中，41.5全数据训练当量。

学习洁净度来源分类交叉验证 AUC=0.5134427083333334；这是区分 con 与 pool 的 AUC，不是任务或噪声检测 AUC。

主表 11任务×3种子，14.9279% 相对随机平均增益。selected_seeds.json 根据结果选择3种子；其统计并非所有已运行种子的无选择偏差估计。

当前源码 authenticity_v2.py 的复合真实性是候选 auth2_only 路径；CLIP signals 主真实性仍为 knn_agreement_and_novelty 的标签一致率。

current v2_2 preset 不自动打开 influence_within_class；论文 main 队列用 track-set influence_within_class=true 和 influence_ref_n=1000000。

本文流程中的 2300 准入条数由 ceil(1.15×2000) 推导；发布归档未提供每个 veto 中间计数，不编造真实删除数。

教学点云和分数为合成数据，浏览器复现协同顺序和公式；未运行真实分类器、CLIP、训练回调。

代码证据：

- tracks/common/experiment.py:132-160，SHA256 54a8baeccfd8c10def028093b928760d8c4a7733335d9d7f211dce6d0468f118；load 返回记录、数组、ID、划分和预算。每条赛道最终经过同一个 run_cell。

- omniselect/core/adjudication/controller.py:142-179，SHA256 3e17b3349e02338821b15411abe790aad7d27a4eaafbbfe97869438ed7f9bae5；scores 的方向是 channels × records。归一化后，每条策略独立生成一份候选下标。

- omniselect/core/selection/fusion_grid.py:80-104，SHA256 33ab2a476553b93a276f90d0c6ccfdbb2b00908a64b3bbc774c1d74b4958b24e；q 是分位数，不是绝对概率阈值。λ=0 走稳定 top-k；λ>0 在准入集合里执行预算选择。

- omniselect/core/selection/budget_select.py:66-77，SHA256 ff55d37f5e6f0dba697f0cc4808627bb01e61ae6f2f503ac5b2f7a50bcb5c0e1；max_sim 从零开始，所以负余弦相似度不会增加额外惩罚。选中后更新所有点和当前集合的最大相似度。

- omniselect/core/signals/influence.py:92-107，SHA256 36d76ca24c750aecc34024267f63bbfa380ea3697422e22efbad152d73f3a898；在同一观测类别内求百分位数。单例类别取 0.5；有并列值时稳定排序按原索引打破并列。

- omniselect/core/signals/cleanliness.py:130-164，SHA256 83fd9e5979353ffd77e1cfd6085ccc368b612e1e41cbab71b9f7023c9dd03264；两种来源各占一半总权重，pool 的标签 0 表示来源而不是已知脏样本。

- omniselect/core/selection/cooperative.py:281-322，SHA256 ee943e21b930e370b9f4bfa9d0f07f6d4ca0825514bf33ea9bab1dd719092cc2；先准入，再 veto，再回填，再内部选择。代码记录每步计数，但本页读取的发布归档没有保存该候选的 scores.json。

- omniselect/core/adjudication/synthesis.py:21-43，SHA256 a5b3d6428b3b60155a171f32949ebf3e638ebf83f8a7b3347aaaf56810e56b28；最好的 3 个候选按相对 random 的构造增益投票。同一条记录可以获得多票，最后仍返回不重复的 k 个下标。

- omniselect/core/adjudication/synthesis.py:104-139，SHA256 a5b3d6428b3b60155a171f32949ebf3e638ebf83f8a7b3347aaaf56810e56b28；尝试把某一维权重加减 0.15，截断至非负并归一化。只有构造效用变大才接受。默认最多 2 轮。

- omniselect/core/adjudication/controller.py:287-302，SHA256 3e17b3349e02338821b15411abe790aad7d27a4eaafbbfe97869438ed7f9bae5；从这里开始候选不再变化。每个候选调用 gain_rank，以最大的参照策略为比较对象。

- omniselect/core/gates/margin.py:12-30，SHA256 9349e274b4fba9cfa5b6a6fb31caafbf14f36ef824238af2c6d6f161fa33bb4c；只有严格大于阈值才切换。这个函数本身没有统计置信保证。

- omniselect/core/adjudication/cache.py:80-104，SHA256 512c20310b1636e8401a55565f86410c144989a80d8e024db23039a0b1bf7098；相同子集哈希与相同 fidelity 命中缓存。相同子集但训练步数不同不算同一次拟合。

论文关键位置：

- omniselect_vldb_zh.tex:155-156 摘要。

- 260-300 问题定义与方法结构。

- 306-346 信号、融合和协同/洁净度。

- 392-410 算法1及确认核验。

- 414-497 条件和理论。

- 519-548 主表。

- 568-590 评测协议和主结论。

结果来源：Paper2_OmniSelect/papers/vldb2027/sources/results/selected_seeds.json

报告种子公开来源：OmniSelect-Benchmark-public/results/paper/seeds_reported.json

公开归档中抽取的 JSON 已保存 evidence/omniselect/，没有重新训练。

深读扩展覆盖、边界和验证见 [omniselect-depth-review.md](omniselect-depth-review.html)。主构建脚本调用 omniselect_deep.py 与 omniselect_deep.js，最终 HTML 仍为离线自包含。