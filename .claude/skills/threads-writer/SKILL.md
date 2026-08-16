---
name: threads-writer
description: Draft or rewrite Threads (脆) posts in TinBoker's voice — a person who just listened to the episode and has one thing worth saying, not a social-media copywriter. Use when asked to turn a podcast episode into a Threads post, write/rewrite 脆文, fix a draft that reads like AI or like 文案, pick a TW posting time, or design the comment-chain funnel for the brand account. Covers the pipeline that feeds pipelines/.../prompts/social_copy_writer.yaml.
---

# Threads Writer (TinBoker)

The failure mode is not "AI 味". It is **文案味** — copy that was obviously
designed to be read. A real human 小編 writes that too. What we want is someone
who happened to have a thought and typed it.

Everything below serves one test, applied at the end:

> 這看起來像「發文」，還是像「有人真的想講這件事」？像前者就重寫。

## Pipeline

Run in this order. Do not skip to the draft.

1. **拿素材** — latest episodes: `curl -s "https://api.tinboker.com/api/episodes/recent?limit=20"`,
   then one episode: `curl -s "https://api.tinboker.com/api/episodes/{id}"` (use
   `modified_summary_content` if present, else `summary_content`; `social_thread`
   is the stored post+comments, often null). Health check first — the API 502s
   during a deploy restart.
2. **抓 3–5 個有意思的點** — claims with a number, a name, or a judgment behind
   them. Skip anything that only restates a headline.
3. **挑一個** — one post carries ONE judgment. The rest go to the comments, not
   into the post. If two ideas both feel essential, that's two posts.
4. **寫五個開頭，先不要寫整篇。** The framing carries most of the 人味, and five
   openings produce five genuinely different posts; five whole drafts produce one
   post wearing five hats. Show the five, pick one, then grow it.
5. **口語草稿** — not "write a Threads post". The instruction to yourself is:
   *你剛聽完這集，傳訊息給一個懂股票的朋友，講裡面一個你覺得值得想的地方。*
   Write it as messages. Don't tidy it.
6. **Threads 化** — line breaks where the breath is, trim what the reader doesn't
   need to follow *this* sentence. Keep the roughness from step 5. This step
   removes, it does not polish.
7. **留言串** — comment 1 is always the permalink
   (`▶ 完整重點：https://tinboker.com/episode/{id}` — matches
   `threads_publisher.link_comment()`). The rest carry the episode's other
   points, one each, in the same loose voice.
8. **Lint (optional)** — the checks in 寫的時候 below are the operative ones.
   For a mechanical pass over 冒號/破折號/翻案句, KKKKhazix/human-writing ships
   `scripts/check_prose.py`; treat its output as advisory and never let it
   rewrite. Its house style is 出版稿, which is the opposite of what we want.

## 寫的時候

- 不必交代完整背景。只補讀者理解「當下這一句」需要的東西。背景邊講邊補。
- 允許半句、口語接續（然後、剛好、如果是這樣的話、反正）、重複、突然插進來的想法。
- 一句只裝一件事。長論證拆成好幾行。
- 標點只服務閱讀。短句直接換行，不一定加句號。行內的停頓可以用半形空格代替逗號。
- 每 2~4 行留一個空行。像訊息一則一則傳出去，不是一整團。
- 中文跟英文、數字之間留半形空格（「波克夏買 Google」）。
- 判斷要落地。整篇只有描述和疑問就是沒講完，先把你怎麼看講出來，再補沒想通的地方。
- 不確定就照常人講法說（「這邊我還沒想通」「不知道是不是我想太多」）。不是每篇都要有。
- 公司名照平常打字的樣子，不用每次都對齊 corporate style。
- 主文 250–350 字之間最自然。太短像抖機靈，太長像整理稿。

## 不要

- **新聞摘要腔**。第一段把人事、職稱、公司名交代完 = 摘要機器。
- **鉤子**。「X 比 Y 更值得看」這種句子沒有錯，但一看就是為了讓人讀下去。
- **反轉、金句、三段式、CTA**。有話講完就停。禁的是回頭替全篇蓋章的收尾句，不是
  你自己的判斷；判斷該講還是要講。
- **每段都是完整論證**。留一點給讀者自己補。
- **強制二選一提問**。真的想問就問，為了衝留言而問會被看出來。
- **業配感**。連結只進留言區，不進主文（見 `references/platform.md`）。

## References

- `references/examples.md` — 開頭範例庫、通過的完整貼文、before/after。**寫之前讀
  這個**，例子比規則有效。
- `references/platform.md` — 演算法權重、台灣發文時段、選題三維度、留言區漏斗、
  防限流。排程或選題時才需要讀。

## 還缺的一塊

`examples.md` 目前只有 Claude 產出、Willy 認可的稿，沒有 Willy 自己寫的貼文。
真正的風格模仿要 20–50 篇他自己覺得自然的舊文做 few-shot。拿到之前，這個 skill
只能保證「不像文案」，不能保證「像他」。
