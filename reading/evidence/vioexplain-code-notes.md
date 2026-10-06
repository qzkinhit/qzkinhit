# VioExplain v3 代码逐层解读与可复算轨迹

本文件对应 `code_v3/vioexplain` 当前源码。`vioexplain-runtime.json` 保存教学合成数据上真实执行原函数得到的数值。它不是 Rieth/TEP 正式实验，不用于替代论文性能结论。随机森林概率、ridge 足迹、conformal 阈值、LLR、AEC-X 选择以及 Update 结果均由原库函数计算，没有手填预测分数。`trace_vioexplain.py` 只在解释组件外记录输入输出，没有修改库源文件。

## 1. 先厘清它在处理什么

这套方法面向多变量时间序列窗口的异常解释。输入是 `values[n,T,M]`，每行是一个有时间顺序的窗口，不是独立记录的数据清洗表。默认 `T=64`，教学轨迹为 `T=32,M=8`。它回答某个窗口可能包含哪些已知异常事件，以及哪些违反不能由这些事件解释。

输出不是修复后的数据集，而是每窗一个 `ExplainResult`。核心字段有 `events`、`assignment`、`residual`、`unknown_flag`、`scores`、`trace`、`residual_degree`、`llr`、`degrees` 和 `window`。`events` 保留选择顺序，`event_set` 才是忽略次序的集合。`assignment` 的值 `-1` 表示背景，内部张量还用 `-2` 表示此键没有违反。`scores` 只保存最初窗口上的类别概率，扣除后的分数要看执行轨迹，不可把它误认为最后一次评分。

`explain` 始终保留原窗口。发生变化的是描述子工作副本 `cur`，其形状始终为 `[n,D]`。所谓扣除事件是从描述子减去学习的预测足迹，不是对原始传感器信号做一次物理修复，也没有调用动力学仿真反演。

## 2. 真正的调用主线

`api/vioexplain.py` 的 `VioExplain.fit` 第294至373行按下列次序执行。

1. `_labels` 把无事件窗口标成正常标签0，单事件窗口标成该事件，多事件窗口标成-1。`keep=labels>=0` 过滤真实多事件训练窗口。
2. 只把正常训练窗口传给 `backend.fit`。默认后端是 `DetectBackend`，调用 `ConstraintSet.fit` 学习约束及正常窗口的描述子归一化统计量。
3. 对正常和单事件训练窗口计算 `phi[n,D]` 和 `(violated[n,K],degree[n,K])`。
4. 按事件组织 `runs,starts,positions`，构造 `WindowCache`，用 `build_twin_bank` 获取同位置的正常、单事件、搭档及叠加窗口。
5. 从 twin 差异计算支持集、必然表示 `R*`、可能表示 `R+` 及程度分布。
6. 每个事件拟合一个多输出 ridge 足迹模型。
7. 生成扣除一致训练表，拟合 scorer。默认是 stacked，教学主轨迹显式选择 `joint_rf`。
8. 用知识表示的程度样本拟合 `DegreeLikelihood`，建立 `Assigner`。
9. 仅用 calibration 分区估计 `tau0,tau1,tau_u`，组装 AECX。

`VioExplain.explain` 第451至481行按 `chunk` 分块计算描述子和违反，再调用 `AECX.explain`。`VioExplain.update` 第483至545行把选定缓冲中的解释结果转成违反特征记录，调用继承的 Apriori 与图更新算法。`explain/greedy.py`、`primal_dual.py`、`exact.py`、`local_search.py` 等其他求解器没有被当前 `VioExplain.fit/explain` 主线调用。阅读代码时不能因为它们位于同一目录就认为 AEC-X 会自动执行所有求解器。

## 3. 三种编号不能混淆

|对象|作用|教学轨迹规模|
|---|---|---|
|传感器通道 `j`|原始矩阵第三轴|8|
|约束 `c`|一种量及其合法区间，可能涉及多通道|26|
|有方向的键 `k`|每条约束分为超上界与低下界|52|
|描述子单元 `u`|一个单通道统计块或一个多通道关系块|10|
|描述子列 `d`|单元内具体连续统计量|68|
|类别 `class`|正常0及事件1、2、3|4|

代码注释的 `C` 有时表示约束条数，有时表示类别条数。解释时应分别写“约束数26”与“类别数4”，不要直接照搬字母。`constraint.K` 或 `KeyInfo.n_seq` 是该约束涉及的序列数量，和“全局键数K”又是两回事。

教学数据有8个普通序列单元，各8列；正常数据中 x0 与 x1 相关，因此保留2个函数关系，各2列。总维度为 `8×8+2×2=68`。默认 top-k 可以引入相关度较弱的辅助预测通道，关系 scope 并不一定只有 x0,x1；查看 JSON 中 `constraints[].scope` 才能知道本次实际 scope。

## 4. 约束怎样从正常数据学出来

`detect/constraints.py::fit_constraints` 第582至635行把参考数据按长度分批，计算所有正常点的均值、协方差与标准差。差分、局部方差及滑窗不会跨参考数组行计算。标准差不大于 `1e-12×max(1,|均值|)` 的通道视为常量，不建立对应单通道约束和描述子单元。

四个约束族按 `range,speed,variance,functional` 排列。

|族|受约束量 q|相对于原窗时间轴的偏移|
|---|---|---|
|range|`q[t]=x_j[t]`|0|
|speed|`q[t]=(x_j[t]-x_j[t-lag])/lag`，默认lag=1|lag|
|variance|长度16的滚动子窗的总体方差|15|
|functional|`q[t]=x_target[t]-(intercept+Σcoef_p x_p[t])`|0|

函数关系的默认选择器为 topk。它对每个目标通道取绝对相关系数最高的5个非常量其他通道，再添加配置中存在的控制搭档；若数据通道名不属于 TEP 命名表，默认控制配对不会生效。线性拟合在标准化协方差尺度添加 `1e-6` ridge，用正常样本的 `R²>=0.5` 决定是否保留。默认不按 scope 去重，所以目标互换的两个关系可以同时存在。`forward` 是可选分支，默认最多3个预测量，每次至少增益0.01；并不是默认执行策略。

合法区间不是默认的“均值±3σ”。当前默认是 `window_quantile`。先对每个正常参考窗口求 q 的最大值与最小值，再把最大值的0.999分位数作为上界，把最小值的0.001分位数作为下界。对 speed 或 variance，量的窗宽使用 `window_length-offset`。`calib_stride=4` 用于正常参考长序列内部的取窗；本教学中传入 fit 的已经是长度32的正常窗口，因此每个参考行只贡献一个等长窗口，不会再出现跨行拼接。

其他可选区间规则分别是逐点0.0005与0.9995分位数，以及逐点均值±3σ。区间太窄时保持中心、扩大半宽，默认半宽至少 `max(1e-12,1e-3×正常参考尺度)`，variance 族的尺度用通道方差。

`window_alpha=0.001` 是单个键的经验窗口尾部分位设置，不是整个窗口“有任何违反”的总体误报率，不应被展示为“99.9% 的正常窗口绝不会报警”。后续 unknown 的阈值另有独立校准。

## 5. 原始窗怎样变成违反

对约束区间 `[lo,hi]`，令 `m=(lo+hi)/2`、`h=(hi-lo)/2`，计算 `z[t]=(q[t]-m)/h`。论文风格的点违反程度为 `F[t]=z[t]` 若 `|z[t]|>1`，否则为0。一个窗的区间特征是 `[min(0,min F),max(0,max F)]`。

实现另保存不被阈值抹除的连续有向程度。

* 上方向键编号 `k=2c`，值为 `s_k=max_t z[t]`。
* 下方向键编号 `k=2c+1`，值为 `s_k=max_t(-z[t])=-min_t z[t]`。
* `violated` 条件是严格 `s_k>violation_threshold`，默认阈值1。

下方向键的 degree 在发生低于下界的违反时仍为正值，不是简单把下界违反存为负数。键名末尾 `|-` 表达方向。`WindowViolations` 同时保留 `[n,26]` 的上下区间端点、`[n,52]` 的程度/次数/首末位置。首末位置使用 block offset 对齐原始时间轴；不会把15点后才能得到的滚动方差当成 t=0 的观测。

JSON `samples[].quantities` 保存每条约束的 q、z、F、时间偏移、区间和两个键。`samples[].violations` 只列实际违反，`all_signed_degrees` 列出全部52个键，包括未超过阈值的连续值。

## 6. 描述子不是违反的 one-hot 向量

连续描述子 φ 保留“是否接近边界”“整体偏移多少”“趋势如何”等未必超过违反阈值的信息。它不使用当前窗口自身的均值标准差去归一化整个窗口，否则均值偏移可能被消掉。正常窗口统计量只在 fit 阶段估计，解释时固定使用。

每个正常单通道单元默认有8列。

1. `range_max`、`range_min`、`range_mean`、`range_median` 分别是 range z 的最大、最小、均值、中位数。
2. `speed_maxabs` 是最小配置 lag 的 speed z 的最大绝对值。若配置多个 lag，违反检测会有多个约束，描述子此项仍只取最小 lag。
3. `speed_slope` 使用中心化时间 `t_c=t-(T-1)/2` 的最小二乘斜率 `Σt_c x[t]/Σt_c²`，再用正常窗口斜率的均值标准差做 z 标准化。
4. `speed_endstart` 为末8点均值减前8点均值，再做正常参考标准化。
5. `variance_logsd` 是全窗标准差取对数后做正常参考标准化。它不是直接取上面长度16的滚动方差违反次数。标准差对数前有相对通道标准差的 `1e-6` 下限，归一化分母也有数值下限。

每个函数关系单元有 `functional_mean=mean(z)`、`functional_maxabs=max|z|` 两列。PCA pseudo-unit 默认关闭，仅在显式启用时加入 log mean SPE 和 log max SPE 两列；它不生成 typed violation key。不能把默认代码解释成使用 PCA 相关性检测，也不能将 `models/chronos2.py`、`moment.py`、`mantis.py` 的存在等同于当前解释器必须加载这些模型。

## 7. 正常孪生、单事件孪生和组合窗

同一 `(run,start)` 有正常窗 `X0` 及事件窗 `Xh`。`ArrayTwins.combo` 构造 `X0+Σ(Xh-X0)`，即先在原始时间序列空间叠加效应，再计算 φ。它没有假设 `φ(Xh+XB-X0)=φ(Xh)+φ(XB)-φ(X0)`。max、方差、对数等描述子通常不满足这种线性关系。

`build_twin_bank` 对每个事件的每个窗口，从其他允许事件中均匀抽取一个搭档B。默认每窗一个搭档、`allowed_pairs=None`，不是穷举所有组合。随机抽取先按事件升序完成，再计算每个事件的 bank，保证固定随机种子的抽样次序。没有合法搭档时 partners=-1，combo 复制事件窗描述子、partner 复制正常窗描述子，这些行不会被当成真正的组合训练样本。

`WindowCache` 按 `(label,run,start)` 复用原来已计算过的正常与单事件 φ 和违反，避免重复计算。叠加窗仍会实际从 accessor 获取，不能把 cache 理解成真实组合试验集。

教学主数据每个已知事件128个窗口，有128个搭档。三个事件合计384组单事件孪生及384组随机配对叠加。fit 的原始训练窗只有正常和单事件512行；组合信息是训练时合成的。在线 explain 不需要真实事件标签或真实正常孪生。页面中把 test 正常孪生也显示出来只是为了教学比较，它不被模型的在线 explain 使用。

## 8. 从 twin 得到表示和支持集

首先计算 but-for 指示 `Z_h[i,k]=violated(Xh)[i,k] AND NOT violated(X0)[i,k]`。如果正常孪生也违反同一个键，即使事件窗违反程度更大，当前默认此键该行的 Z 仍为0。它判断“移除事件后违反是否消失”，不是简单比较两个 degree 的差。

频率 `p_h(k)=mean_i Z_h[i,k]`。`R*(h)` 收录频率≥0.9的键，`R+(h)` 收录0.05≤频率<0.9的键，其权重就是频率。只在 `Z=1` 的行收集事件 degree；区间为这些样本的5%与95%分位数。单键样本最多512条，过多时用均匀次序统计量缩减，不是前512条。

若提供 positions，还分别构造 `all`、`early`、`steady` 三组，early 指注入后窗口序号<2。教学脚本提供该信息，因此前两个窗口和后两个窗口能分别检查表示。需要明确，当前 `DegreeLikelihood.fit` 使用 `representation(event)` 的默认 `all`，AEC-X 在线运行没有自动依窗口位置切换 early/steady 分布。

支持集是另一对象。默认 `support_rule='effect'`，先用正常 φ 各列的标准差加 `1e-8` 作为 scale，再检查单事件 twin 差 `|φ(Xh)-φ(X0)|/scale>3`。若某单元至少50%的 twin 窗口中有至少一列超过3，则该单元进入支持集。支持集决定足迹模型“看哪些输入列”。它不限定输出变化只能发生在那些列。

可选 `representation` 支持规则由 `R*` 的键涉及通道映射到单元，`union` 取两种支持并集。`support_channel_mode='any'` 是默认值。不要把默认效应支持说成“先找所有必然违反再得到支持”，二者在代码中独立计算。

## 9. 足迹回归具体学什么

事件 h 的 ridge 输入只取支持单元的列 `S_h`，目标覆盖全部D列。

|训练来源|输入|回归目标|
|---|---|---|
|单事件 twin|`φ(Xh)[S_h]`|`φ(Xh)-φ(X0)`|
|组合 twin|`φ(Xh+XB-X0)[S_h]`|`φ(Xh+XB-X0)-φ(XB)`|

后者保持同一底噪与搭档B，仅移除h，告诉回归器“有另一事件时h的足迹如何变化”。默认两类都用，教学每个事件256行足迹训练样本。没有支持列的事件没有算子，扣除将返回 φ 的 float32 副本。

`ridge_fit` 第36至57行先中心化 X,Y，然后解 `(XcᵀXc+αI)W=XcᵀYc`，再计算截距 `b=mean(Y)-mean(X)W`。默认α=10，默认 float64 求解。预测 `Δ_h(r)=r[S_h]W+b`，扣除 `r_next=r-Δ_h(r)`，返回 float32。后续事件的足迹输入是上一步残差r，而不是永远使用初始φ，所以两个事件的扣除一般不交换。

`relative_error` 是全部D列的 Frobenius 相对误差，不是仅支持列误差，也不是时间序列重构误差。JSON 保留每个事件实际 coef、intercept、列选择、矩阵形状及单事件足迹误差，可逐项算矩阵乘积。系数正负和范围没有额外裁剪，减去足迹后部分描述子可能落到原物理统计量不可能对应的位置；方法通过扣除一致训练缓和这种分布差异，不保证所有残差都是可实现原始信号的描述子。

## 10. 训练表怎样从512行变成1022行

原表为128正常窗和3×128单事件窗，共512行。描述子表 `[512,68]` 的前512行原样进入 scorer 训练表。之后按事件1、2、3依次添加两段。

* 128行 `φ(Xh+XB-X0)-Δ_B(.)`，标签h。此时被减去的是搭档B，目的在于教 scorer 识别“扣掉别的事件后剩下h”的描述子。
* 随机抽42行 `φ(Xh)-Δ_h(.)`，标签正常0，因为 `128//3=42`。它教 scorer 识别自扣除后应接近正常的工作空间。

每个事件增加170行，总数 `512+3×128+3×42=1022`。label0最终254行，三个事件各256行。多事件样本没有多标签喂给 scorer；它们被当作产生“剩余单事件”训练行的材料。所有新增行保留原 run 分组。`training.segments` 列出每段半开区间起止行号、来源事件、监督标签和第一行φ。

## 11. 两条评分分支

主轨迹的 `joint_rf` 把68维连续描述子直接输入随机森林，训练120棵树，`random_state=0,n_jobs=1`。库默认该分支是500棵树。类别顺序强制为正常0、事件1、2、3。`JointRFScorer.fit` 接收 groups 但忽略它，随机森林这条分支没有 per-unit 交叉拟合。

正式默认 scorer 是 `stacked`。每个单元有一个多类别 HistGradientBoostingClassifier，预测4类，不是每事件一个互不相关的二元分类器。默认150次迭代、学习率0.1、叶节点最多15；默认5折，把同一 run 的所有原始及增广行放在同一折。先用其他折拟合，然后只给本折输出 out-of-fold 概率；最后每单元在全部训练行上重拟合供在线使用。

教学实际补充执行 `stacked_diagnostic` 使用30次迭代、3折，不冒充默认150次/5折正式实验。形状依次为 `[1022,10,4]` OOF log概率、`[1022,10,3]` OOF 事件相对正常 log-odds。按单元展开后30列，默认再拼接原φ68列，形成98列输入。计算该训练输入的每列均值和标准差，标准化后拟合多类别 LogisticRegression，`C=0.1,max_iter=2000`。在线改用每单元全量拟合模型的概率，然后走同一个标准化和逻辑回归。

JSON 补充轨迹存了4个训练行的每单元 OOF log概率、log-odds、98列输入、标准化结果、分类器 `[4,98]` 系数、logits 和 softmax。用矩阵乘法重组成的 softmax 已与原 LogisticRegression 的预测核对。它还实际重新校准了三个阈值并输出少量测试窗口，避免把 RF 阈值套给 stacked。

需要理解交叉拟合范围。`UnitModels` 的折外预测发生在已经构造好的描述子/知识/足迹/一致训练表上，默认代码没有对每个证据折重新拟合整条约束和足迹管线。不能据此声称“每一层所有参数都做了严格嵌套折外训练”。

## 12. 三个阈值各自校准什么

`tau0` 防止正常窗轻易选入已知事件。正常 calibration 窗口计算 `gate=max_E log(max(p_E,eps))-log(max(p0,eps))`，从这些 gate 值求高分位数。正常p0并不是必须超过0.5；实际判别依据学到的阈值。

`tau1` 防止已经解释完真实单事件后继续添一个多余事件。对每个 calibration 单事件窗，根据真实训练标签减去该事件足迹，重新评分，并把真实事件对应列设为负无穷，再取其他事件的最大 log-odds。把这些最大值的高分位数当成停止阈值。这里校准阶段已知真实事件，与在线依模型预测事件扣除不同。如果调用者提供 calibration_truth 且启用 `tau1_effective_only`，只保留 truth 非空的单事件窗；教学没有传这个可选真值，实际使用所有单事件窗。

`tau_u` 校准“正常或已知单事件完全给定正确事件集时，仍可能留下多少未解释违反程度”。正常窗用空集，已知单事件窗用其标签，通过 assigner 求 `ρ=Σ背景键|degree|`，对ρ求高分位。在线改用预测H，unknown 条件严格 `ρ>tau_u`。

三个α默认均0.05，conformal 阶次 `k=ceil((1-α)(n+1))`，取第k小值。浮点实现减 `1e-12` 避免接近整数误进位。k>n或无样本时阈值为正无穷。n=5、α=.05时不会得到一个冒险的有限门限，门将不开。

默认每个校准 run 取一个随机位置，固定seed0。`run_keys=label×1,000,000+run`，所以 tau0 取40个值，tau1取120个值，tau_u取160个值；原始 cal 是640窗。校准中不同标签共享同一个正常底噪时仍具有依赖，代码将它们视为不同 class-run，不等于数学上自动保证联合交换性。理论有限样本界需要对应统计量的交换性，未知比例、数据漂移、窗口依赖和强概率离散均应区分讨论。

`per_event=False` 默认关闭 Mondrian。打开后 τ1 在线按首先选中的事件查阈值，小组阈值非有限时回退全局阈值。tau0虽可保存分层值，`AECX.select` 当前用 `_value(tau0)` 取 pooled value，不按第一个候选查分层。停止选入条件为 `best>=tau1`，不是严格大于；而 conformal 常见超阈尾部界讨论的是严格大于，因此离散评分在等于阈值处不能不加说明地沿用完全相同的界。

## 13. AEC-X 一轮一轮究竟做了什么

`explain/aecx.py::select` 第148至184行只复制 φ，不复制/改写传感器原窗。先评分原φ，若 `gate>tau0`，选择事件概率最高的一个已知事件。门没开时 H=空，即使 p_E 中有最大值也不选。

默认 `k_max=3`，后面最多执行两次“扣除并尝试添事件”。每次只处理当前恰好已经选入 step+1 个事件的窗口。把最近一次入选事件的足迹从当前 cur 扣掉，重评分，把正常类和已经选择的事件列都屏蔽为负无穷，取剩余事件的最大 stop statistic。若 `best>=tau1`，加入该事件；否则该窗口不再成为后面轮次的 active 行。

注意两个控制流细节。第一，初始事件的选入不经过tau1，只经过tau0。第二，如果已经到 `k_max`，代码不会再扣除最后一个事件做额外停止评分；因此“最终描述子残差”与H中所有事件全部扣完后的人工计算值可能不同。H由到达上限或下一事件分数不足共同决定。

tie 默认沿 numpy.argmax 取第一个类别列，类别按升序排列。已经选入的事件不能重复选入。`step_pick` 是被评估的最优候选，不表示它必然加入H；应结合 `step_max>=tau1` 判断。没有到达的轮次 `step_max` 为NaN，JSON显示字符串 `nan`；`step_pick=-1`。

“扣除后正常概率上升”可以帮助理解，但不是每窗必然现象。学习足迹可能有误差，另一事件可能仍然存在，概率重新分配也不是逐项线性相减。可视化应使用 JSON 中真实 `calls[].proba`，不应该为了动画顺滑而假设概率一定单调。

## 14. 用 LLR 把原始违反指派给 H

事件选择和违反指派是两步。AEC-X 根据连续描述子选择H；指派仍针对原始输入窗口检测出的违反，未重新把残差φ转换成传感器信号并再做约束检测。

每个候选事件E、键k及 degree d 的得分是

`g_k(E)=log p_E(k)+log f_E,k(log|d|)-log p_0(k)-log f_0,k(log|d|)`。

这里 p_E 是 but-for频率，p0 是正常违反率，p0至少 `1/(n_normal+1)`；教学 n_normal=128，因此频率下限为1/129。分布实际在 `log|degree|` 空间使用高斯KDE，表格范围 `log(.5)` 至 `log(10000)`，256个网格点，查询用线性插值，超网格值按 numpy.interp 使用端点。Silverman带宽不低于0.1，density下限1e-12；每键不足5个样本时回退来源样本池。事件没有程度样本的新增可能键可回退正常表，因此 Update 新键的分数不能当成新事件数据训练出的可靠似然。

代码中函数名/注释通常把它简写成 degree 密度；页面精确解释应说明它计算的是 log程度密度比。因为同一变换的 Jacobian 在事件/正常比中相消，密度比不需要额外补一个|d|项。

只有 `k∈R*(E)∪R+(E)` 才是候选，否则 g=-∞；而实际指派又只考虑 `E∈H`。得分矩阵可有“某未入选事件LLR很好”，它仍不能成为owner。最优值必须严格大于0，等于0保留背景。

默认 `multi_first=True`。代码先统一处理所有 `n_seq>1` 的键，并非在3序列、6序列等不同多序列键之间逐层排序。它记录每事件已指派的多序列键覆盖哪些通道。单通道违反若落在已覆盖通道，且该事件LLR>0，就在这些“有覆盖引导的候选”里选分最高的一个；没有有效引导才使用所有H候选的普通最大LLR。这可以使某单通道键不被指给全局LLR最高事件，而指给关系约束所引导的另一正LLR事件。应在动画中先显示多通道owner，再说明单通道的引导来源。

`assignment_detail` 逐键保存所有事件的表示成员资格、H成员资格、LLR四项与最终owner。不能把 `in_representation` 与 `in_selected_H` 合并成一个状态。

## 15. residual 和 unknown 的真实含义

`V_res` 是 owner=-1 的原始违反键集合，`ρ` 为这些键的 |degree| 之和。它与描述子工作残差r不是同一个对象，单位与维度也不同。ρ不是除以总键数或阈值后的平均值。指派涉及几个相互关联键时，它们会逐键累加，没有按通道合并。

一个窗口可以 `H={1}` 且 unknown=True，含义是识别出已知部分后还有无法解释的违反。也可以 H为空且 unknown=False。unknown=False 不证明原始数据完全正常；unknown=True 也不证明出现了一个此前不存在的新事件，它可能来自模型误差、分布漂移、约束偶发违反或不准确的知识表示。

本次合成测试每种条件32窗。未知9单独与1+9两组均32/32被标记，但正常组有3/32被标记，正常空集恢复为28/32。这些是脚本一次固定种子的小样本结果，不是性能估计的置信保证。9个详细样例为了教学采用“首个事件集正确的窗”或“首个unknown窗”，选择规则已逐条记录。总体计数保留了失败例，避免把精挑样例当成100%准确。

## 16. Update 究竟改了哪些对象

`VioExplain.update` 不自动筛选 unknown，调用者传什么 buffer 就处理什么。教学显式从未知9组筛选前12个 unknown=True 结果。每条违反记录是 `(key,degree,degree,n_seq)`，即一个退化程度区间；已有知识用训练时的程度分位区间。事务包含该窗所有实际违反键，并分出已解释集合C与背景集合D。

原型 Constraint 的“相等”是同名且两个区间端点各相差小于全局阈值。这不是严格等价关系，因为不保证传递性。adapter按首次出现的相似特征去重。Apriori默认 support=.2, confidence=.7,max_itemset=3，在事务上真正挖关联规则。

`build_graph` 对规则“前件A⇒后件B”建立 B→A 的回溯边，边权是规则置信度。不是按规则文字方向画A→B。多元素前件只有在某现有事件表示包含其所有名称时才建边，并且实现只连到前件集合的第一个元素，不把整个多元素前件画成所有节点的独立边。

从D节点做 DFS。遇到已有解释键，就把相关新违反加入对应旧事件的可能表示；不能接到旧事件的孤立违反会创建 `unnamed_new_f`。等待队列里违反的跨边权积严格大于min_conf=.6时才传播。当前代码保留了原型控制流的若干特殊行为，不能美化成任意图上的标准连通分量算法。

* 当前节点D→已解释C的直接扩充没有再检查边权>min_conf，边本身先受规则confidence阈值筛选。
* 等待项加入的循环可能对不覆盖终点的理由也产生加入，已有测试 `test_waitlist_chain_attaches_upstream_violation` 明确保留此行为。
* `D = D - {nextVertex.id}` 从 Vertex 集合减 Constraint，实际上不生效。
* 某些未知链终点可能被重复创建新 reason，测试也保留该原型行为。
* B局部更新不会作为一个全局已处理集合返回；递归每层复制waitlist。

代码按顶点插入次序遍历D，减少基于对象地址的不可复算顺序。追加表示的权重 `w=1/update_num` 中计数是该特征在算法中被加入的次数，不一定等于最终不同事件数。不能直接把 w解释成校准概率或置信区间。

API把扩充项加入所有现有表示分组的R+，已有R*不动。新建项从当前最大已知事件编号+1分配本地数字标签，没有把它和测试真值9匹配。教学新增标签可能恰好也达到9，但它不代表成功恢复注入事件9。`Knowledge.add_possible` 不根据新数据学习新的degree样本或区间，不增加新支持集，不拟合新ridge。API最后重拟合 likelihood并替换assigner，scorer及其classes完全没更新，新标签不会自动进入下一次AEC-X候选类。

本次真实12窗buffer挖到0条规则，却创建6个标签，包括未知的range:x7|+以及一些偶发速度/方差键。这暴露了原型Update的限制，不能写成“发现一个新故障，并已经具备稳定识别能力”。`update_micro_demo` 另提供独立、明确标注的5事务教学表，真实运行两个旧理由扩充同一new_x并各得权重0.5，isolated_z单独新建；它用于演示规则路径，不能和真实buffer混为同一次结果。

## 17. 边界与未经执行的部分

纯detect会拒绝NaN/inf、通道数不匹配或窗长不足；描述子进一步要求窗长等于拟合时T。API `_describe` 在空数组时直接拼接空列表，因此空输入不是它显式支持的正常分支。fit若没有正常类或没有足够事件/校准数据也不能假设会自动补全。`k_max` 在构造AECX时只转int，源码没有完整校验其正值；正常配置为3。

所有已知事件都已经选入后，剩余stop statistic可能全是-∞，argmax会返回第一个索引但正常情况下-∞小于有限tau1而停止。若用户人为设tau1=-∞，不能继续假设normal列不会被加入，尽管默认校准设置不会设计为这种极端情况。

`fit_summary` 是fit时概要，不包含完整bank或每次工作残差，所以教学脚本用只读记录包装器保存这些中间量。Update修改knowledge后没有全面刷新最初fit_summary。页面显示“当前知识”应读取 update.after，而不是用旧fit_summary推断更新结果。

`not_executed` 字段列出未进行的正式数据实验、默认150迭代5折stacked训练及时间序列大模型。无法从小型合成回放推出真实工业动态中线性叠加成立、足迹回归无偏，或未知事件识别具有同等效果。

## 18. JSON 可视化使用建议

`samples[].values`、`normal_twin`、`injected_delta` 都为 `[32,8]`，适合按通道切换的同轴折线。`quantities` 可按族/约束切换，画合法区间与逐点z，明确时间offset。`phi` 及每次calls input/output是68维，可按layout.units列范围显示分组热图；不要把不同量纲的原始通道与标准化描述子画在同一个纵轴。

选择回放的时间线应按calls顺序显示。每个score行显示正常及三个事件概率；gate仅在第一行测试，stop在后续行测试。deduct行显示输入r、预测Δ及输出r_next三列并排，保留负值。分配阶段使用原窗口violations，不沿用扣除后的degree。

阈值视图可显示 calibration.selected_values 的排序、所选阶次rank和实际τ。N是去重后参与分位数的校准样本数，不是640个原始校准窗。Update视图应把真实buffer与独立规则教学表分两个选项，并固定显示“知识变化后类别头未更新”。

源码精确行号及片段见 JSON `sources`，每项保存 path/start/end/code/file_sha256。以下静态行号是当前读到的版本，若源文件后来改变，以同次生成JSON中的SHA和片段为准。


|函数/类|文件|起止行|
|---|---|---|
|VioExplain.fit|code_v3/vioexplain/api/vioexplain.py|294至373|
|VioExplain._calibrate|code_v3/vioexplain/api/vioexplain.py|375至427|
|VioExplain.explain|code_v3/vioexplain/api/vioexplain.py|451至481|
|VioExplain.update|code_v3/vioexplain/api/vioexplain.py|483至545|
|DetectBackend|code_v3/vioexplain/api/vioexplain.py|177至221|
|VioExplainConfig|code_v3/vioexplain/api/vioexplain.py|55至134|
|fit_constraints|code_v3/vioexplain/core/detect/constraints.py|582至634|
|select_relations|code_v3/vioexplain/core/detect/constraints.py|776至840|
|_learn_bounds|code_v3/vioexplain/core/detect/constraints.py|952至1000|
|rolling_variance|code_v3/vioexplain/core/detect/constraints.py|324至339|
|Block.quantity|code_v3/vioexplain/core/detect/constraints.py|303至321|
|evaluate|code_v3/vioexplain/core/detect/violations.py|310至377|
|pointwise_degree|code_v3/vioexplain/core/detect/violations.py|400至417|
|build_layout|code_v3/vioexplain/core/detect/descriptors.py|243至290|
|window_statistics|code_v3/vioexplain/core/detect/descriptors.py|293至305|
|_fill_chunk|code_v3/vioexplain/core/detect/descriptors.py|495至537|
|but_for_indicator|code_v3/vioexplain/core/knowledge/representation.py|233至239|
|fit_representation|code_v3/vioexplain/core/knowledge/representation.py|366至405|
|support_from_effects|code_v3/vioexplain/core/knowledge/representation.py|250至280|
|fit_knowledge|code_v3/vioexplain/core/knowledge/representation.py|530至622|
|Knowledge.add_possible|code_v3/vioexplain/core/knowledge/representation.py|464至490|
|build_twin_bank|code_v3/vioexplain/core/knowledge/twins.py|295至362|
|ArrayTwins.combo|code_v3/vioexplain/core/knowledge/twins.py|93至103|
|ridge_fit|code_v3/vioexplain/core/knowledge/footprint.py|36至57|
|Footprint.fit|code_v3/vioexplain/core/knowledge/footprint.py|102至129|
|Footprint.deduct|code_v3/vioexplain/core/knowledge/footprint.py|142至151|
|consistent_training_set|code_v3/vioexplain/core/evidence/scorer.py|41至83|
|StackedScorer|code_v3/vioexplain/core/evidence/scorer.py|122至184|
|JointRFScorer|code_v3/vioexplain/core/evidence/scorer.py|86至119|
|UnitModels|code_v3/vioexplain/core/evidence/unit_models.py|101至181|
|_fit_unit|code_v3/vioexplain/core/evidence/unit_models.py|83至98|
|fold_assignment|code_v3/vioexplain/core/evidence/unit_models.py|47至70|
|gate_statistic|code_v3/vioexplain/core/explain/aecx.py|41至53|
|stop_statistic|code_v3/vioexplain/core/explain/aecx.py|56至71|
|AECX.select|code_v3/vioexplain/core/explain/aecx.py|148至184|
|AECX.explain|code_v3/vioexplain/core/explain/aecx.py|186至252|
|DegreeLikelihood|code_v3/vioexplain/core/evidence/likelihood.py|58至189|
|Assigner._block|code_v3/vioexplain/core/explain/assign.py|93至141|
|Assigner.assign|code_v3/vioexplain/core/explain/assign.py|143至165|
|conformal_quantile|code_v3/vioexplain/core/calibrate/conformal.py|41至47|
|fit_threshold|code_v3/vioexplain/core/calibrate/conformal.py|132至167|
|Threshold.lookup|code_v3/vioexplain/core/calibrate/conformal.py|109至122|
|run_update|code_v3/vioexplain/core/update/adapter.py|73至129|
|build_graph|code_v3/vioexplain/core/update/update_graph.py|141至161|
|Update|code_v3/vioexplain/core/update/update_graph.py|164至205|
|dfsvisit|code_v3/vioexplain/core/update/update_graph.py|224至299|
