# 独立音轨验证

`verify_audio.py` 使用 Python 标准库、FFprobe 和 FFmpeg。它不生成语音，不修改音轨或正在生成的 manifest。未指定 `--collection` 时仍验证 `hot100`。

## 完整验证

在仓库根目录执行，每个集合单独保存一份报告：

```sh
python3 scripts/audio/verify_audio.py --report /tmp/qzkinhit-hot100-verification.json
python3 scripts/audio/verify_audio.py --collection papers --report /tmp/qzkinhit-papers-verification.json
python3 scripts/audio/verify_audio.py --collection bagu --report /tmp/qzkinhit-bagu-verification.json
```

默认要求本集合的稿件、manifest 和非临时 MP3 文件都完整覆盖来源题号，不允许缺少或多出题号。`hot100` 沿用 `reading/09-swipe.html` 的题库。`papers`、`bagu` 分别使用 `scripts/audio/snapshots/papers-20261015.json`、`bagu-20261015.json`，不会自动采用后来新增的页面题目。需要另一个明确快照时，可使用 `--snapshot`，manifest 的 `sourceSnapshot` 必须指向同一文件。

报告保存为 JSON，同时输出到标准输出。成功返回退出码 0，验证失败返回 1。没有指定 `--report` 时只输出，不创建报告文件。报告路径不能覆盖 manifest 或来源快照。

## 验证尚未全部生成的集合

```sh
python3 scripts/audio/verify_audio.py --collection bagu --ids i1,i2 --report /tmp/qzkinhit-bagu-partial.json
```

`--ids` 接受逗号分隔的题号，不能包含重复或快照之外的题号。它只验证指定音轨，不要求其余音轨已经生成。`questionCount` 是本批快照题数，`verifiedNarrationCount` 和 `verifiedIds` 明确本次检查范围，`coverage` 另外列出完整批次仍缺少或多出的题号。部分验证通过不会被报告为整批已经解码或整批哈希已经核对。

生成过程中应选择已经完成、没有同时强制重生成的题号。生成器先替换音频再更新 manifest，恰好在这个更新间隙读取同一题，可能得到真实的瞬时哈希不一致；应在该题更新完成后重试，不应跳过哈希检查。

## 检查项目

脚本核对题号覆盖、题名、段落格式、字符数、生成器记录的文本完整标记、正文及设置哈希、音频文件哈希、文件字节数、时长合理性和编码参数。讲解应为单路 MP3、24 kHz 单声道、64 kbps。新集合还核对每条音轨的 `sourceSha256`，它是完整快照卡片值的 JSON 哈希，包含包装层的题号、题名、分组和 `source`，不是只对正文求哈希。

正文哈希采用 `json.dumps([text, track.settings], ensure_ascii=False, sort_keys=True)`，包括 Python 默认分隔符的空格，和生成器完全一致。每条音轨使用自己的设置，不能用最新 manifest 顶层设置替换已有音轨的设置。正文以两个换行连接段落。文本完整性标记来自生成时的语音边界校验，本脚本没有另外运行语音识别。

完整模式用 FFmpeg 对每条文件解码到结尾，解码错误直接失败。同一次解码中使用 EBU R128 复测响度和真峰值，新的两个集合还同时运行 `silencedetect`。讲解响度允许负 19.2 至负 16.8 LUFS，真峰值不高于负 0.7 dBTP。EBU R128 摘要保留一位小数，与生成器的 loudnorm 测量相比允许 0.3 LU 或 0.3 dB 的差异，但实际值仍必须满足范围限制。

每次也检查同一条独立背景音乐 `reading/audio/music/quiet-study.m4a`，包括音频哈希、生成脚本哈希、AAC-LC、44.1 kHz 双声道、至少 128 kbps、无削波标记和负 6 dBTP 真峰值上限。完整模式会解码并复测音乐响度。

## 实际思考静音

新集合按每条音轨自己的 `settings.introPauseSeconds` 判断是否启用停顿。值为零时，允许省略 `thinkingPause`，不要求也不执行静音块验证；若仍声明停顿，则判为设置冲突。正值至少为 0.3 秒，此时必须有 `thinkingPause.startSeconds` 和 `durationSeconds`，时长应与设置一致，并位于音频内部。

实际静音检测使用负 60 dBFS 阈值，最短事件为 0.05 秒。必须存在一个连续静音区间，覆盖从声明起点加 0.1 秒，到声明终点减 0.1 秒的整个区间。两侧各保留 0.1 秒容差，以容纳压缩边界的短暂过渡；不能把多个被可听声音隔开的区间拼成通过结果。

目前插入的源音频静音为 3.6 秒，以默认 1.2 倍播放时约为 3 秒。报告分别列出启用和关闭停顿的数量，以及启用音轨的源时长、默认倍速下时长、静音元数据通过数量和实际波形通过数量。所选音轨全部关闭停顿时，`applicable` 为假、静音验证数量为零，固定快照和页面变化报告仍然保留。

## 仅检查元数据

```sh
python3 scripts/audio/verify_audio.py --metadata-only
python3 scripts/audio/verify_audio.py --collection bagu --ids i1,i2 --metadata-only
```

这一模式仍核对实际文件哈希、FFprobe 编码和时长，以及 manifest 中记录的响度和静音区间，但不执行逐文件完整解码，不复测波形响度，也不验证实际静音。报告的解码、响度复测和波形静音标记会明确为未执行，`checksSkipped` 列出跳过项目。

## 页面后续变化

对于 `papers`、`bagu`，报告的 `currentPageChanges` 将固定快照与当前页面比较，列出新增、删除以及已有题号的内容变化。比较字段包括 `q`、`a`、`key`、`f`、`plain`、`fq`、`fa`、`nums` 和 `cmp`。这些变化供作者决定是否更新下一批音频，不会扩展或改写本次固定快照的验证范围。当前页面无法解析时，报告会保留这一提示，而固定快照音轨的验证仍可完成。
