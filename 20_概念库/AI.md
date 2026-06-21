---
type: domain
domain: AI
status: active
tags:
  - domain
---

# AI

## 我关心的问题
- AI 能替代、放大或改变哪些工作流？
- 哪些能力已经可产品化？
- 哪些能力还只是演示，不适合投入？

## 关键概念
```dataview
TABLE status, file.mtime AS "更新"
FROM "20_概念库"
WHERE type = "concept" AND domain = "AI"
SORT file.mtime DESC
LIMIT 30
```

## 近期输入
```dataview
TABLE file.mtime AS "更新"
FROM "00_入口收件箱/每日雷达"
WHERE type = "daily-radar" AND contains(file.outlinks, [[AI]])
SORT file.name DESC
LIMIT 10
```

## 可输出方向
- 工具评测
- 自动化工作流
- 产品机会

## 待验证判断
- 哪些 AI 能力能稳定进入个人工作流？
- 哪些 AI 产品机会只是演示，不值得投入？
- 哪些 AI 工具能放大写作、投资、游戏设计效率？
