# DemandClean 阅读证据

核对日期 2026-10-06。仅只读论文和代码，未运行训练或修改源仓库。

主文 documents/sigmod2027/demandclean_latexv0818/demandclean_vldbfinalv0818.tex
英文为完整稿。同目录 zh.tex 实际仅含引言，不能当成完整长文。主文标示 PVLDB Vol.20 投稿稿，不能宣称已发表。
代码 DemandClean-Benchmark HEAD 87243b34502601a5b43b082a06a52b207ec382aa；读的是当前工作树。旧 DemandClean HEAD 44e6d3f9cabd0a974d58ccf2b801050a6c01bf8d。

## 关键结论
1. 主文 10 维状态与源码 config.state_size=10 一致。README 8 维仅为旧描述。
2. 两阶段 agent.act 同 state 输入两个网络，中间没有执行 VE；分层动作选择与两阶段 plan/execute 推理是不同概念。
3. clean_base 为检测后 DeleteFix / VE-Fill 伪真值基准，5 折 CV × sqrt(n/N)。训练每轮注入错误，保存注入前值，恢复的是伪真值。
4. 源码训练回放发生在每个 episode 完成后；Double DQN 在线选下一动作，target 网络给该动作估值。
5. no-op 留下的 NaN 在 get_cleaned_data 还会被填补。
6. 主文奖励 N=ceil(K/50)，代码为依据错误数、样本数和 500000 预算的有界公式。主文说 stage1 无代价信号，但训练实际把含费用的 reward 同样给 stage1。
7. 论文 A 是原始单元格分母，V 是各列方差比×保留率；run_demandclean.compute_auth_div 用行级近似比对且删除后未用 keep_mask 对齐，不等价，不能把报告 auth=0 解释为完全错误。
8. --oracle 控制严格先划分后编码及干净验证集，不等于 detector_mode=oracle；可与 auto detector 并存。
9. beers ngt 报告仍记录 RAHA 20 行标注且 apply_raha_truth=true。仅 agent_repair_cost=0，不能称整个流程无真值。
10. 论文容忍度自动模型选择在读取的主调用链未找到对应实现；Trainer 使用已配置的模型适配器。

## 本地输出轻量核对
原始 beers 2410 行、11 列；train dirty=1446，clean=1446；v5 输出 CSV=1317，unique index=1317；按 index 对齐缺失 129 行。
v5 报告 data_shape=[1446,8]、cleaned_shape=[1317,8]、GT=5；baseline RF NoFix .3152，ReplaceAll .3507，DemandClean .3445，FullFix .3549。不同报表评测不能混作同一结果。
v5 报告 RAHA 20 行 + 5 GT 单元格 = 25 的 cost_ratio 混合计数单位，需要单列报告。
真实 CSV 样例 index 477: ounces 16.0 oz→16.0，ibu empty→34.458403865803675，city Michigan City→York。原 clean reference city=Michigan City，不能声称全部改动正确，也不能仅从最终 CSV 推断具体动作。

## 原文证据索引
- 论文英文完整稿: documents/sigmod2027/demandclean_latexv0818/demandclean_vldbfinalv0818.tex:298-378; sha256=9eb67874a7129667463842a4321e8306284c060ee65e29e3c082bc7e8d8856ac
- 论文训练与推理: documents/sigmod2027/demandclean_latexv0818/demandclean_vldbfinalv0818.tex:487-625; sha256=9eb67874a7129667463842a4321e8306284c060ee65e29e3c082bc7e8d8856ac
- 原始 CSV 编码: DemandClean-Benchmark/run_demandclean/run_demandclean_base.py:337-405; sha256=57177d85fd17bcf69f18b06562c4816a41225878ce5b30c40ac887ee58fda51e
- 训练集拟合与 NaN 保留: DemandClean-Benchmark/run_demandclean/run_demandclean_base.py:500-531; sha256=57177d85fd17bcf69f18b06562c4816a41225878ce5b30c40ac887ee58fda51e
- 严格划分入口: DemandClean-Benchmark/run_demandclean/run_demandclean_base.py:2774-2848; sha256=57177d85fd17bcf69f18b06562c4816a41225878ce5b30c40ac887ee58fda51e
- 四阶段错误检测: DemandClean-Benchmark/demandclean/detectors/auto_detector.py:1570-1599; sha256=99e1daa5ef8797ca9ceae0c5bb9953b9f1c3ebd504b5b5148416eb1bfa6fd928
- RAHA 标注预修复: DemandClean-Benchmark/demandclean/api/demand_clean.py:720-766; sha256=5dc0c0e4c8c762aa6cf1387cc1c2df7c99eab32ee675caa3e4e7a00060e62606
- 候选基准的选择: DemandClean-Benchmark/demandclean/training/trainer.py:927-978; sha256=7414354386d949854917e105bc647c53a33c2bfdd831c44cdf9acfce1b02f37e
- 注入与决策训练循环: DemandClean-Benchmark/demandclean/training/trainer.py:393-423; sha256=7414354386d949854917e105bc647c53a33c2bfdd831c44cdf9acfce1b02f37e
- 轨迹、经验回放和最佳权重: DemandClean-Benchmark/demandclean/training/trainer.py:460-553; sha256=7414354386d949854917e105bc647c53a33c2bfdd831c44cdf9acfce1b02f37e
- 8 个局部及质量特征: DemandClean-Benchmark/demandclean/core/state/classification_state.py:45-108; sha256=0f4093c4c32e7ee663b8d1deb1483b8757ae9e8c327d5cdc2044ea2c9e9b080c
- 添加 2 个全局特征: DemandClean-Benchmark/demandclean/core/environments/cleaning_env.py:415-443; sha256=1629210c997454b91c630b805fdbfd210f645e6dcbf75f01e8f0e05426dc6599
- 方差保留率计算: DemandClean-Benchmark/demandclean/core/state/state_extractor.py:182-225; sha256=4ed0ffe34947c2f7e6f3f2da3a8e8c894b24c2fce3c0c0e3d2a0a4d26eb7c475
- 两阶段动作映射: DemandClean-Benchmark/demandclean/core/agents/dueling_two_stage_agent.py:95-119; sha256=be77e280a1c3efae4b6803310b4bcef13ffc45de84c4ab89e61856fc41818cfd
- Dueling 网络: DemandClean-Benchmark/demandclean/core/agents/dueling_network.py:24-47; sha256=252f15d949f2d3452c77ef56564e47766694e19360731546393223f64ecf6bec
- Double DQN 学习: DemandClean-Benchmark/demandclean/core/agents/dueling_two_stage_agent.py:133-173; sha256=be77e280a1c3efae4b6803310b4bcef13ffc45de84c4ab89e61856fc41818cfd
- 环境真正修改数据的位置: DemandClean-Benchmark/demandclean/core/environments/cleaning_env.py:520-604; sha256=1629210c997454b91c630b805fdbfd210f645e6dcbf75f01e8f0e05426dc6599
- 中间步与评估步奖励: DemandClean-Benchmark/demandclean/core/environments/cleaning_env.py:621-660; sha256=1629210c997454b91c630b805fdbfd210f645e6dcbf75f01e8f0e05426dc6599
- 优先级与预算奖励: DemandClean-Benchmark/demandclean/core/environments/cleaning_env.py:678-741; sha256=1629210c997454b91c630b805fdbfd210f645e6dcbf75f01e8f0e05426dc6599
- 值估计优先级链: DemandClean-Benchmark/demandclean/core/environments/value_estimation.py:261-326; sha256=8f77e656c7fde368d669b4ae360a79e3a2b3c677a73895e847d57edb623dba65
- 计划阶段和占位估计: DemandClean-Benchmark/demandclean/core/environments/two_phase_env.py:276-350; sha256=3a92d59ca11b4182ad3041500e6c51be6240ac1d6283e84307af7f8dee4bd567
- 回填计划内真值: DemandClean-Benchmark/demandclean/core/environments/two_phase_env.py:458-509; sha256=3a92d59ca11b4182ad3041500e6c51be6240ac1d6283e84307af7f8dee4bd567
- 旧结果中的真实性、多样性算法: DemandClean-Benchmark/run_demandclean/run_demandclean_base.py:830-872; sha256=57177d85fd17bcf69f18b06562c4816a41225878ce5b30c40ac887ee58fda51e

## 原始样例 JSON
```json
[
  {
    "index": "1395",
    "dirty": {
      "index": "1395",
      "id": "719",
      "beer_name": "Sweet Georgia Brown",
      "style": "American Brown Ale",
      "ounces": "16.0 OZ.",
      "abv": "0.05%",
      "ibu": "empty",
      "brewery_id": "514",
      "brewery_name": "Monkey Paw Pub & Brewery",
      "city": "San Diego",
      "state": "CA"
    },
    "reference": {
      "index": "1395",
      "id": "719",
      "beer_name": "Sweet Georgia Brown",
      "style": "American Brown Ale",
      "ounces": "16",
      "abv": "0.054",
      "ibu": "empty",
      "brewery_id": "514",
      "brewery_name": "Monkey Paw Pub & Brewery",
      "city": "San Diego",
      "state": "CA"
    },
    "result": null
  },
  {
    "index": "477",
    "dirty": {
      "index": "477",
      "id": "2607",
      "beer_name": "Black Beer'd",
      "style": "American Black Ale",
      "ounces": "16.0 oz",
      "abv": "0.068",
      "ibu": "empty",
      "brewery_id": "24",
      "brewery_name": "Burn 'Em Brewing",
      "city": "Michigan City",
      "state": "IN"
    },
    "reference": {
      "index": "477",
      "id": "2607",
      "beer_name": "Black Beer'd",
      "style": "American Black Ale",
      "ounces": "16",
      "abv": "0.068",
      "ibu": "empty",
      "brewery_id": "24",
      "brewery_name": "Burn 'Em Brewing",
      "city": "Michigan City",
      "state": "IN"
    },
    "result": {
      "index": "477",
      "id": "2607",
      "beer_name": "the Kimmie, the Yink and the Holy Gose",
      "style": "American Black Ale",
      "ounces": "16.0",
      "abv": "0.068",
      "ibu": "34.458403865803675",
      "brewery_id": "24.0",
      "brewery_name": "Wynkoop Brewing Company",
      "city": "York",
      "state": "WY"
    }
  },
  {
    "index": "1178",
    "dirty": {
      "index": "1178",
      "id": "1666",
      "beer_name": "King Street Hefeweizen",
      "style": "Hefeweizen",
      "ounces": "12.0 oz. Alumi-Tek",
      "abv": "0.06%",
      "ibu": "10",
      "brewery_id": "102",
      "brewery_name": "King Street Brewing Company",
      "city": "Anchorage",
      "state": "AK"
    },
    "reference": {
      "index": "1178",
      "id": "1666",
      "beer_name": "King Street Hefeweizen",
      "style": "Hefeweizen",
      "ounces": "12",
      "abv": "0.057",
      "ibu": "10",
      "brewery_id": "102",
      "brewery_name": "King Street Brewing Company",
      "city": "Anchorage",
      "state": "AK"
    },
    "result": {
      "index": "1178",
      "id": "1666",
      "beer_name": "the Kimmie, the Yink and the Holy Gose",
      "style": "Hefeweizen",
      "ounces": "12.0",
      "abv": "0.06",
      "ibu": "10.0",
      "brewery_id": "102.0",
      "brewery_name": "Wynkoop Brewing Company",
      "city": "York",
      "state": "MN"
    }
  },
  {
    "index": "1090",
    "dirty": {
      "index": "1090",
      "id": "2199",
      "beer_name": "Hopworks IPA",
      "style": "American IPA",
      "ounces": "16.0 oz.",
      "abv": "0.07%",
      "ibu": "75",
      "brewery_id": "80",
      "brewery_name": "Hopworks Urban Brewery",
      "city": "Portland",
      "state": "OR"
    },
    "reference": {
      "index": "1090",
      "id": "2199",
      "beer_name": "Hopworks IPA",
      "style": "American IPA",
      "ounces": "16",
      "abv": "0.066",
      "ibu": "75",
      "brewery_id": "80",
      "brewery_name": "Hopworks Urban Brewery",
      "city": "Portland",
      "state": "OR"
    },
    "result": null
  },
  {
    "index": "1172",
    "dirty": {
      "index": "1172",
      "id": "59",
      "beer_name": "Lift Bridge Brown Ale",
      "style": "American Brown Ale",
      "ounces": "12.0 oz. Alumi-Tek",
      "abv": "empty",
      "ibu": "empty",
      "brewery_id": "84",
      "brewery_name": "Keweenaw Brewing Company",
      "city": "Houghton",
      "state": "MI"
    },
    "reference": {
      "index": "1172",
      "id": "59",
      "beer_name": "Lift Bridge Brown Ale",
      "style": "American Brown Ale",
      "ounces": "12",
      "abv": "empty",
      "ibu": "empty",
      "brewery_id": "84",
      "brewery_name": "Keweenaw Brewing Company",
      "city": "Houghton",
      "state": "MI"
    },
    "result": null
  },
  {
    "index": "1001",
    "dirty": {
      "index": "1001",
      "id": "2339",
      "beer_name": "Little Red Cap",
      "style": "Altbier",
      "ounces": "12.0 oz.",
      "abv": "0.063",
      "ibu": "43",
      "brewery_id": "144",
      "brewery_name": "Grimm Brothers Brewhouse",
      "city": "Loveland",
      "state": "CO"
    },
    "reference": {
      "index": "1001",
      "id": "2339",
      "beer_name": "Little Red Cap",
      "style": "Altbier",
      "ounces": "12",
      "abv": "0.063",
      "ibu": "43",
      "brewery_id": "144",
      "brewery_name": "Grimm Brothers Brewhouse",
      "city": "Loveland",
      "state": "CO"
    },
    "result": null
  },
  {
    "index": "1877",
    "dirty": {
      "index": "1877",
      "id": "512",
      "beer_name": "Autumnation (2011-12) (2011)",
      "style": "Pumpkin Ale",
      "ounces": "16.0 ounce",
      "abv": "0.06",
      "ibu": "48",
      "brewery_id": "46",
      "brewery_name": "Sixpoint Craft Ales",
      "city": "Brooklyn",
      "state": "NY"
    },
    "reference": {
      "index": "1877",
      "id": "512",
      "beer_name": "Autumnation (2011-12) (2011)",
      "style": "Pumpkin Ale",
      "ounces": "16",
      "abv": "0.06",
      "ibu": "48",
      "brewery_id": "46",
      "brewery_name": "Sixpoint Craft Ales",
      "city": "Brooklyn",
      "state": "NY"
    },
    "result": null
  },
  {
    "index": "1383",
    "dirty": {
      "index": "1383",
      "id": "337",
      "beer_name": "Boneshaker Brown Ale",
      "style": "English Brown Ale",
      "ounces": "24.0 ounce",
      "abv": "0.06%",
      "ibu": "empty",
      "brewery_id": "547",
      "brewery_name": "Moat Mountain Smoke House & Brew...",
      "city": "North Conway",
      "state": "NH"
    },
    "reference": {
      "index": "1383",
      "id": "337",
      "beer_name": "Boneshaker Brown Ale",
      "style": "English Brown Ale",
      "ounces": "24",
      "abv": "0.055",
      "ibu": "empty",
      "brewery_id": "547",
      "brewery_name": "Moat Mountain Smoke House & Brew...",
      "city": "North Conway",
      "state": "NH"
    },
    "result": {
      "index": "1383",
      "id": "337",
      "beer_name": "the Kimmie, the Yink and the Holy Gose",
      "style": "English Brown Ale",
      "ounces": "24.0",
      "abv": "0.06",
      "ibu": "46.88565523304422",
      "brewery_id": "547.0",
      "brewery_name": "Wynkoop Brewing Company",
      "city": "York",
      "state": "WY"
    }
  }
]
```

## 深度升级
共24节、31项论文目录覆盖、22帧episode执行器、Dueling/Double计算器、检测与VE条件台、数据隔离和9段逐段源码解释。详见 demandclean-coverage.md。
