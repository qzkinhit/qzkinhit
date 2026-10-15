# 扩展八股第二片口播复核

固定来源为 `bagu-20261015-expanded.json` 的 `addedCardIds[99:197]`，共 98 张。本文件只记录科学澄清及限定条件。原问题标题保持一致，没有修改既有 349 张口播稿、页面或共享脚本。

## ga-6、ga-7 · 分词没有把字符信息不可逆删除

明确假设的 strawberry 和数字切分示例，保留 12345、123、45 与 67890。规范化、特殊 token 与异常 token 行为均按模型配置说明。

参考 [来源 1](https://huggingface.co/docs/tokenizers/pipeline)。

## ga-8 至 ga-11 · 词向量目标和复杂度

负采样不是每步仍计算完整 softmax。其正号对数目标应最大化，最小化时取负。1800 只统计示例的输出参数，输入向量也有更新。Huffman 不保证每词路径均为 log V。

参考 [来源 1](https://arxiv.org/abs/1310.4546)，[来源 2](https://arxiv.org/abs/1607.04606)，[来源 3](https://arxiv.org/abs/1607.01759)。

## ga-12、ga-13 · 嵌入梯度的分支和存储口径

只有已查行收到梯度限定查表操作。共享词表输出会给其他行贡献梯度，稀疏非零分布也不等于稀疏张量存储格式。保留原参数量及具体模型示例。

参考 [来源 1](https://docs.pytorch.org/docs/stable/generated/torch.nn.Embedding.html)，[来源 2](https://arxiv.org/abs/1608.05859)。

## ga-15、ga-16 · 预测目标对齐与缓存条件

明确第 t 位输出对齐第 t+1 个 token，避免将标签左移与输入右移混淆。左填充限定常见取最后列 logits 的实现。双向编码器追加输入后不能直接复用旧 KV，不等于固定编码结果不能缓存。

参考 [来源 1](https://huggingface.co/docs/transformers/llm_tutorial)，[来源 2](https://huggingface.co/docs/transformers/cache_explanation)。

## ga-17、ga-18 · 分页和流式窗口的实验条件

16 token 块、约 4 个 attention sink 保留为示例或论文设置，不作跨版本保证。StreamingLLM 改善特定模型的流式稳定，不恢复被驱逐内容。

参考 [来源 1](https://arxiv.org/abs/2309.06180)，[来源 2](https://arxiv.org/abs/2309.17453)。

## ga-20、ga-22 · 线性复杂度需要固定维度

线性注意力的状态复杂度要固定特征维度。S2-Attn 固定组长时是序列长度的线性主项，固定组数时不成立。保留 2048、8192、4 组、1024 位移与 16 倍示例。

参考 [来源 1](https://arxiv.org/abs/2006.16236)，[来源 2](https://arxiv.org/abs/2309.12307)。

## ga-23、ga-24 · 门控和共享头不是无条件保证

门控低秩解释限定单头路径，原注意力权重本身也有非线性。MQA 质量变化和 GQA 的 5% uptraining 结论限定论文设置，平均参数不等于完整保留信息。

参考 [来源 1](https://arxiv.org/abs/2505.06708)，[来源 2](https://arxiv.org/abs/2305.13245)。

## ga-25 至 ga-27 · 归一化的稳定性结论

Post-Norm 预热、Pre-Norm 有效深度、DeepNorm 更新界和 QK-Norm 都有分析或实现条件，不能从结构名称推出绝对稳定。保留 N 层 DeepNorm 的残差及初始化系数。

参考 [来源 1](https://proceedings.mlr.press/v119/xiong20b.html)，[来源 2](https://arxiv.org/abs/2203.00555)。

## ga-28 至 ga-34 · 参数和位置机制的精确范围

FFN 比例限定标准 MHA 与 4 倍中间维。区分位置表长度和训练长度，纯位置内积与实际注意力，T5 编码器的正负方向桶。RoPE 的零索引频率不随 base 改变，较长波长也不消除周期性。ALiBi 通用斜率公式限定相应头数构造。

参考 [来源 1](https://arxiv.org/abs/1706.03762)，[来源 2](https://arxiv.org/abs/1910.10683)，[来源 3](https://arxiv.org/abs/2104.09864)，[来源 4](https://arxiv.org/abs/2108.12409)。

## ga-35 至 ga-37 · 长度单位与架构优劣

字数不等于 token 数。Decoder-only 可有辅助目标。因果矩阵非零对角时满秩，但双向矩阵也可满秩，不能据此推出一般表达力排序。结构优劣需结合训练目标与任务。

参考 [来源 1](https://arxiv.org/abs/1706.03762)，[来源 2](https://arxiv.org/abs/2204.05832)。

## ga-39、ga-40、ga-42 · FLOPs、保存量与实际性能

明确 MHA、标准 FFN、乘加计数及忽略项。s 超过 6h 的阈值只比较层内主项，词表输出需另计。34 和 5 系数依赖保存方案，边界激活不是峰值显存。统一 t 为总前缀长度，计算倍数不等于延迟倍数。

参考 [来源 1](https://arxiv.org/abs/2205.05198)，[来源 2](https://arxiv.org/abs/2205.14135)，[来源 3](https://huggingface.co/docs/transformers/cache_explanation)。

## gt-2 · LSH 是候选检索而非严格阈值判定

MinHash 等式需理想 minwise 假设。候选概率公式不等于确定重复关系；若要求明确阈值，应核验候选，并留意并查集的连锁合并。

参考 [来源 1](http://infolab.stanford.edu/~ullman/mmds/ch3.pdf)。

## gt-4、gt-5 · 采样等价性与多源比例

随机梯度也可以有相同期望，不能说只有全梯度才等价。两两最优不能推出三源最优，保留全部 1:1:6、1:1:4、1:1:3、1:1:2 扫描值，但将默认比例作为待验证起点。

参考 [来源 1](https://arxiv.org/abs/1803.00942)。

## gt-8 至 gt-11 · 继续训练、词表与评价单位

通用回放比例和重新预热不是无条件规则。嵌入行数必须覆盖 token ID。Packing 的损失权重依目标而定。BPB 统一每字节单位，不消除 tokenizer、模型概率与上下文协议的影响。

参考 [来源 1](https://huggingface.co/docs/transformers/perplexity)，[来源 2](https://huggingface.co/docs/transformers/main_classes/tokenizer)。

## gt-13、gt-15 至 gt-17 · 评测敏感性与 SFT 掩码

格式变动后的分数变化不能单独证明污染。回答掩码是目标选择，忽略标签 -100 为接口默认约定。结束符监督有帮助，不是没有它就绝对不能停止。按轮等权不是所有 SFT 的唯一正确目标。

参考 [来源 1](https://docs.pytorch.org/docs/stable/generated/torch.nn.CrossEntropyLoss.html)，[来源 2](https://huggingface.co/docs/transformers/chat_templating)。

## gt-19 至 gt-23 · 数据选择与适配器结论的范围

IFD 大于 1 的剔除是方法规则，不是不匹配的证明。K-Center-Greedy 不保证最优覆盖。LoRA-FA 减半需 A/B 尺寸相同，LoRA 零梯度问题要求非零初始化而非必须随机。保留 QLoRA 和 P-Tuning 的原实证数值。P-Tuning v2 是否采用重参数化编码器是任务相关选择，并非一律删除。

参考 [来源 1](https://arxiv.org/abs/2308.12032)，[来源 2](https://arxiv.org/abs/2305.14314)，[来源 3](https://arxiv.org/abs/2106.09685)，[来源 4](https://arxiv.org/abs/2110.07602)。

## gt-24 至 gt-26 · 蒸馏散度方向与可表示性

两个各 0.5 的离散模式若学生可表达，正反 KL 最优解都为教师分布，反向 KL 不必塌缩。教师减学生对数概率是负 KL 样本奖励。逐 token 比较要求分词对齐，跨分词器需另设方法。

参考 [来源 1](https://arxiv.org/abs/2306.08543)，[来源 2](https://arxiv.org/abs/2306.13649)。

## gt-27 至 gt-31 · 奖励与策略梯度的统计口径

奖励模型成对损失不识别提示内公共偏移。k3 无偏解释需当前策略采样及支持条件。SFT 单项方向不保证每个 token 的实际概率都上升，PPO 简化梯度只能在比率为一等条件下省略比率。

参考 [来源 1](https://arxiv.org/abs/2203.02155)，[来源 2](https://arxiv.org/abs/2402.03300)，[来源 3](https://arxiv.org/abs/1707.06347)。

## gt-32 至 gt-35 · 偏好目标不能混用

DPO 闭式推导需相应正则条件。IPO 的间隔按对数比定义。ORPO 原文使用平均 token 对数似然构造概率分数，再求 odds，不能无条件改成整条未归一化概率。

参考 [来源 1](https://arxiv.org/abs/2305.18290)，[来源 2](https://arxiv.org/abs/2403.07691)。

## gt-36 至 gt-39 · 裁剪、基线与 GSPO

0.28 为上侧裁剪余量，对应比率上界 1.28。RLOO 无偏要有条件独立性，GRPO 组统计不能直接套同一证明。单样本重要性估计仍可纠偏，GSPO 的长度归一化序列分数不是未经修改的轨迹比率。

参考 [来源 1](https://arxiv.org/abs/2503.14476)，[来源 2](https://arxiv.org/abs/2507.18071)。

## gt-40 至 gt-43 · 指标和评判流程

BLEU 空候选要另行处理，ROUGE 需区分版本与分母。相关性依赖评价分布和人工标注质量。提高温度本身不保证评分稳定，需独立验证提示与聚合方案。

参考 [来源 1](https://aclanthology.org/P02-1040/)，[来源 2](https://aclanthology.org/W04-1013/)，[来源 3](https://arxiv.org/abs/2306.05685)。

## gt-44 至 gt-48 · 价值方法的条件

无限折扣回报及唯一价值结论需严格小于一的折扣和有界奖励等条件。MC/TD 的偏差方差不是无条件排序。SARSA 与 Q-learning 悬崖路线比较依赖保留探索的具体设置。

参考 [来源 1](http://incompleteideas.net/book/the-book-2nd.html)。

## gt-49 至 gt-54 · 策略梯度、基线与终止

策略梯度存在异策略形式，旧数据不能无校正使用。任意基线未必减方差，GRPO 自含样本的组统计与动作独立基线有区别。Critic TD 目标需停止梯度，GAE 的回报等价需正确终止边界。PPO 裁剪并不硬限制实际比率。

参考 [来源 1](http://incompleteideas.net/book/the-book-2nd.html)，[来源 2](https://arxiv.org/abs/1506.02438)，[来源 3](https://arxiv.org/abs/1707.06347)。

## go-1 至 go-3 · BERT 静态掩码与去噪比较

保留 15%、80/10/10、50% 和 512。BERT 静态预生成可以有多个掩码版本，不是每轮只有同一掩码。监督比例和目标长度不能单独推出普遍收敛或质量排序。

参考 [来源 1](https://arxiv.org/abs/1810.04805)，[来源 2](https://arxiv.org/abs/1907.11692)，[来源 3](https://arxiv.org/abs/1910.10683)，[来源 4](https://arxiv.org/abs/1910.13461)。

## go-5 至 go-8 · Llama 设置和格式项的条件概率

Llama 2 论文表 1 的 34B、70B 采用 GQA，未把全部规格混称。保留全部原始训练量和设置。Llama 3 的 chosen NLL 系数 0.2 已核对原文，重复 token 在不同前缀下不是同一个条件概率的数学冲突。

参考 [来源 1](https://arxiv.org/abs/2302.13971)，[来源 2](https://arxiv.org/abs/2307.09288)，[来源 3](https://arxiv.org/abs/2407.21783)。

## go-9 至 go-11 · 版本和掩码设计

多轮前缀训练的拆分依赖具体可见性设计。Qwen2 配置已经有百万 RoPE 基数，避免将一万到一百万统一归于 Qwen2.5。保留 18T、36T、4K、32K 和二十多类任务等原材料数字，并限定原始双模式 Qwen3 的格式。

参考 [来源 1](https://arxiv.org/abs/2103.10360)，[来源 2](https://huggingface.co/Qwen/Qwen2-7B/blob/main/config.json)，[来源 3](https://arxiv.org/abs/2412.15115)，[来源 4](https://arxiv.org/abs/2505.09388)。
