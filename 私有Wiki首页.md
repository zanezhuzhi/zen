# 私有 Wiki 首页

> 这是当前知识库的主入口。手机端只负责把内容转发给飞书，桌面端从这里看全貌、处理机会、做复盘。

## 今日入口
- [[_本周行动台]]
- [[_收件箱处理台]]
- [[_概念地图]]
- [[_灵感与选题池]]
- [[全局索引]]

## 五个主轴
- [[互联网]]：产品、平台、社区、商业化、趋势。
- [[AI]]：工具、自动化、能力边界、产品机会。
- [[游戏]]：机制、系统、叙事、玩家体验。
- [[投资]]：行业、公司、交易复盘、风险信号。
- [[写作]]：选题、结构、表达、发布反馈。

## 今日飞书摘要
```dataview
TABLE file.mtime AS "生成时间", status AS "状态"
FROM "00_入口收件箱/每日雷达"
WHERE type = "daily-radar"
SORT file.name DESC
LIMIT 7
```

## 每日五领域信息候选
```dataview
TABLE file.mtime AS "生成时间", status AS "状态"
FROM "00_入口收件箱/每日信息候选"
WHERE type = "daily-domain-brief"
SORT file.name DESC
LIMIT 7
```

## 本周待处理
```tasks
not done
path includes 00_入口收件箱
sort by due
sort by priority
```

## 最近概念
```dataview
TABLE status, domain, file.mtime AS "更新"
FROM "20_概念库"
WHERE type = "concept"
SORT file.mtime DESC
LIMIT 20
```

## 输出机会
```dataview
TABLE status, domain, file.mtime AS "更新"
FROM "40_输出库" OR "20_概念库"
WHERE type = "idea" OR contains(tags, "idea") OR status = "seed"
SORT file.mtime DESC
LIMIT 20
```

## 长期问题
- 哪些互联网变化正在被 AI 改写？
- 哪些 AI 能力已经能形成个人工作流或产品机会？
- 哪些游戏机制可以解释用户增长、留存和社区？
- 哪些产业线索值得进入投资观察，而不是只收藏观点？
- 哪些观点值得被写成文章、报告或脚本？

## 每周复盘入口
- [ ] 从最近 7 天每日雷达里挑 3 条原料。
- [ ] 新建或更新 3 张概念卡。
- [ ] 推进 1 个输出选题。
- [ ] 记录 1 条投资观察或写作卡片。
