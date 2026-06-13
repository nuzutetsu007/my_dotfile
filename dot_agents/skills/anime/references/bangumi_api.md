# Bangumi API Reference

## Base URL

```
https://api.bgm.tv
```

## Search Subject

```
GET /search/subject/{keyword}?type=2&responseGroup=medium
```

- `type=2`: 限制为动画 (anime)
- `responseGroup`: `small` | `medium` | `large`

### 响应示例

```json
{
  "results": 1,
  "list": [
    {
      "id": 420723,
      "url": "https://bgm.tv/subject/420723",
      "type": 2,
      "name": "葬送のフリーレン",
      "name_cn": "葬送的芙莉莲",
      "summary": "...",
      "air_date": "2023-09-29",
      "air_weekday": 5,
      "images": { "large": "...", "common": "...", "medium": "...", "small": "...", "grid": "..." },
      "eps": 28,
      "eps_count": 28,
      "rating": { "rank": 12, "total": 21368, "score": 8.7 },
      "collection": { "wish": 1234, "collect": 5678, "doing": 234, "on_hold": 56, "dropped": 12 }
    }
  ]
}
```

## Subject Detail

```
GET /subject/{subject_id}?responseGroup=large
```

### 额外字段 (vs search)

- `eps`: 放送话数信息（含每话标题、放送日）
- `total_episodes`: 总集数
- `series`: 系列作品关联
- `tags`: 标签
- `characters`: 角色列表
- `staff`: 制作人员
- `relations`: 关联条目（续作、前传等）
- `lock`: 锁状态
- `nsfw`: 是否 NSFW

## Subject Episodes

```
GET /subject/{subject_id}/episodes?type=0&limit=100&offset=0
```

- `type=0`: 全部
- `type=1`: 本篇
- `type=2`: SP
- `type=3`: OP
- `type=4`: ED

### 响应

```json
{
  "total": 28,
  "limit": 100,
  "offset": 0,
  "eps": [
    {
      "id": 123456,
      "url": "https://bgm.tv/ep/123456",
      "type": 0,
      "sort": 1,
      "name": "旅立ちの絆",
      "name_cn": "启程之绊",
      "duration": "24m",
      "airdate": "2023-09-29",
      "comment": 456,
      "desc": ""
    }
  ]
}
```

## Related Subjects

```
GET /subject/{subject_id}/relations
```

返回关联的前传、续作、番外等。

```

```json
{
  "subject_id": 420723,
  "relations": [
    {
      "id": 456789,
      "type": "续作",
      "name": "葬送のフリーレン 2期",
      "name_cn": "葬送的芙莉莲 第二季"
    }
  ]
}
```

## 重要字段映射

| Bangumi 字段 | 含义 | 备注 |
|-------------|------|------|
| `id` | Subject ID | 主键标识 |
| `name` | 日文名 | 原始名称 |
| `name_cn` | 中文名 | 正式中文译名 |
| `type` | 条目类型 | 2=动画 |
| `eps` | 当前集数 | 已放送数 |
| `total_episodes` | 总集数 | 完结后不变 |
| `air_date` | 首播日 | |
| `air_weekday` | 放送星期 | 0=周日, 1-6=周一到周六 |
| `rating.score` | 评分 | 0-10 |

## 状态判断

- `eps` < `total_episodes` → 放送中 (airing)
- `eps` >= `total_episodes` → 已完结 (finished)
- 无 `eps` 数据 → 未放送 (not_yet_aired)

## 速率限制

- 未认证: 30 req/min
- 需要认证时返回 429
- 建议: 请求间加 200ms 延迟

## 错误码

| 状态码 | 含义 |
|-------|------|
| 200 | 成功 |
| 404 | 条目不存在 |
| 429 | 速率限制 |
| 500 | 服务器错误 |