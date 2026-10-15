# 听题音频

当前支持 Hot 100、论文面试卡和八股速记三个集合。人声与背景音乐始终分开保存。

刷题页使用两条独立音轨。`reading/audio/hot100-natural/{题目ID}.mp3` 是纯讲解，`reading/audio/music/quiet-study.m4a` 是纯背景音乐。两者没有混音，后续可以独立替换。

人声使用 Microsoft Edge 的晓晓中文神经网络合成音色。它是合成语音，不是真人录音。口播稿根据题库中的题意、示例、代码及复杂度逐题改写，保留在 `narrations/part-01.json` 至 `part-03.json`。包含全部 102 道题，题号还包含 `offer10` 和补充题 `92`。

播放器默认以 **1.2 倍**播放人声。点击播放器中的倍率按钮，可以切换 0.8、1、1.2、1.5、1.8、2 倍，并保存选择。背景音乐始终以原速播放。人声与音乐分别通过 GainNode 调节音量；音乐在暂停、关闭、睡眠定时到期时与人声一起暂停，切题时保持连续。

## 更换背景音乐

开始听题后，展开播放器的声音设置，选择本地音频即可。文件只保存在当前浏览器的 IndexedDB 中，不会上传。若浏览器不允许保存，仍可在当前页面播放，但需要下次重新选择。恢复默认会清除自选音乐。

声音设置中提供本题纯人声与纯音乐的独立下载。要永久修改网站的默认音乐，可替换 `reading/audio/music/quiet-study.m4a`，或修改 `reading/listening-player.js` 中的默认音乐路径。建议保留舒缓、无人声的音乐，并先把响度降到约负 26 LUFS。

手机首次播放需要点击播放按钮。锁屏和后台行为还受设备、浏览器及系统的媒体策略影响。浏览器端自动测试覆盖播放控制，不能替代 iPhone 等实体设备的后台续播验证。

## 重新生成人声

需要 Python 3.9 以上版本、FFmpeg、ffprobe 和可访问 Microsoft Edge 语音服务的网络。以下命令从仓库根目录执行。

```sh
python3 -m venv scripts/audio/.venv
scripts/audio/.venv/bin/python -m pip install -r scripts/audio/requirements.txt
scripts/audio/.venv/bin/python scripts/audio/generate_voice.py --check-only
scripts/audio/.venv/bin/python scripts/audio/generate_voice.py
```

只生成指定题目或修改音色参数时，可以使用以下命令。

```sh
scripts/audio/.venv/bin/python scripts/audio/generate_voice.py --ids 1,15,offer10
scripts/audio/.venv/bin/python scripts/audio/generate_voice.py --voice zh-CN-XiaoxiaoNeural --rate=-3% --pitch=-1Hz
```

生成脚本会校验题号和题名，核对服务返回的朗读文本是否完整，做两遍响度归一化，并检测最终 MP3 的时长、响度和峰值。最终文件为 24 kHz 单声道、64 kb/s MP3。设置目标为负 18 LUFS，生成清单记录编码后的实际值。人声源文件来自重新合成，不是对旧的低码率录音转码。

`reading/audio/hot100-natural/manifest.json` 保存每道题的音频路径、时长、文本与音频校验值、合成参数和实测响度。脚本可断点续跑；脚本内容或参数改变后会重新生成对应音轨。服务连接失败时会有限重试，并明确报告未完成的题号。不要同时启动多个生成人声的进程，以免争用生成清单。

生成后可独立检查完整覆盖、音频校验值与逐文件解码结果。

```sh
python3 scripts/audio/verify_audio.py --report reading/audio/hot100-natural/validation.json
```

语音服务调用通过 [edge-tts](https://github.com/rany2/edge-tts) 完成。静态网页直接播放生成文件，无需浏览器保存任何 API 密钥。

## 论文面试卡与八股速记

第一批以 `snapshots/papers-20261015.json` 的 90 张论文卡和 `snapshots/bagu-20261015.json` 的 349 张八股卡为固定范围。后续按用户要求增加 295 张八股卡，扩展批次保存在 `snapshots/bagu-20261015-expanded.json`，共 644 张。原 349 张的可朗读内容未变，保留其已核对的来源记录与音频，只生成新增题号。口播稿分别保存到 `narrations-papers/` 与 `narrations-bagu/`，音轨输出到 `reading/audio/papers-natural/` 与 `reading/audio/bagu-natural/`。

每张卡先读主题与完整问题，然后插入 3.6 秒静音，以默认 1.2 倍播放时约为 3 秒。再讲解答案、公式与需要记忆的数字。所有静音都在人声音轨内，背景音乐独立播放。源卡中已确认的技术口径问题及口播中的澄清，记录在相应口播稿目录的 `review-notes.md` 或 `review-part02.md`。

```sh
scripts/audio/.venv/bin/python scripts/audio/generate_voice.py --collection papers
scripts/audio/.venv/bin/python scripts/audio/generate_voice.py --collection bagu
scripts/audio/.venv/bin/python scripts/audio/generate_voice.py --collection bagu --ids i1,j19,g1-1
python3 scripts/audio/verify_audio.py --collection papers --report reading/audio/papers-natural/validation.json
python3 scripts/audio/verify_audio.py --collection bagu --report reading/audio/bagu-natural/validation.json
```

两类卡片沿用晓晓音色、24 kHz 单声道、64 kb/s MP3 和约负 18 LUFS 的人声响度。论文页已有的 `reading/audio/papers/*.m4a` 保留为备用。生成器按集合锁定输出目录，同一集合不能并发启动多个生成进程，避免清单被相互覆盖。

新增卡片时，先捕获一个新的来源快照并补充对应题号的口播稿，再指定快照生成。已有内容和参数未改变的音轨会复用。

```sh
python3 scripts/audio/capture_card_sources.py --collection bagu --output scripts/audio/snapshots/bagu-next.json
scripts/audio/.venv/bin/python scripts/audio/generate_voice.py --collection bagu --snapshot scripts/audio/snapshots/bagu-next.json --ids 新增题号
```

生成清单包含来源快照路径、每题来源校验值和静音位置，可核对后续页面是否修改了已有题目。未经明确指定，捕获工具不会覆盖既有快照。

生成和验证默认使用当前 manifest 记录的来源快照。切换到扩展批次时，首次生成需明确指定新快照，之后可继续断点运行。

```sh
scripts/audio/.venv/bin/python scripts/audio/generate_voice.py --collection bagu --snapshot scripts/audio/snapshots/bagu-20261015-expanded.json --quiet-cached
```

## 接入仍在更新的卡片页面

公共控件保存在 `reading/listening-player.html`，播放逻辑保存在 `reading/listening-player.js`。两页从音频清单派生媒体版本，避免浏览器继续使用配音生成前缓存的错误响应。八股页按清单识别已配音内容，自动连播会略过尚未配音卡片，手动点选则显示未配音状态。返回页面或显式重试时可刷新清单，刷新包含超时、请求合并和冷却。

页面构建程序在写文件时调用统一入口，保留本次构建得到的全部题库数据。

```python
write_integrated_page(output_path, generated_html, collection="papers")
write_integrated_page(output_path, generated_html, collection="bagu")
```

该函数位于 `scripts/audio/integrate_listening_player.py`。页面构建器和命令行后处理共用文件锁，在锁内原子写出，避免两者交错覆盖。现有页面也可直接更新播放器。

```sh
python3 scripts/audio/integrate_listening_player.py papers
python3 scripts/audio/integrate_listening_player.py bagu
python3 scripts/audio/integrate_listening_player.py papers --check
python3 scripts/audio/integrate_listening_player.py bagu --check
```

后处理逐字节确认 `id=data` 未变，遇到未知页面结构会报错。配音快照独立于持续增长的网页题库，更新播放器时始终保留网页当前的完整题目数据。

## 重新生成背景音乐

运行 `python3 scripts/audio/generate_music.py`。该脚本使用 NumPy 合成原创键盘、旋律及和声，再通过 FFmpeg 编码。详细的配器、循环衔接和响度数据见 `reading/audio/music/README.md` 与同目录的元数据文件。音乐生成与人声生成互相独立。
