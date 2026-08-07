# SQL Agent TPC-DS Test Campaign — Results

- Started: 2026-08-07T11:48:11.240055+00:00
- Finished: 2026-08-07T13:22:06.192626+00:00
- Total wall time: 32.4 min (budget 6.0 h)
- Agent: `litellm/hosted_vllm/qwen-summary via http://host.docker.internal:8445/v1, db=waiting for an agent database response`

## Summary

| Block | Questions | OK | Clarification | Error | Retried OK | Block time |
|---|---|---|---|---|---|---|
| Уровень 1. Базовое исследование схемы | 7 | 0 | 0 | 7 | 0 | 15.3 min |
| Уровень 2. Возвраты и бизнес-метрики | 7 | 0 | 0 | 7 | 0 | 4.0 min |
| Уровень 3. Сравнение каналов | 8 | 0 | 0 | 8 | 0 | 2.3 min |
| Уровень 4. Клиенты и сегментация | 8 | 0 | 0 | 8 | 0 | 2.7 min |
| Уровень 5. Остатки и логистика | 8 | 0 | 0 | 8 | 0 | 3.7 min |
| Уровень 6. Сложные аналитические запросы | 10 | 0 | 0 | 10 | 0 | 4.3 min |

**Total: 0 ok / 0 clarification / 48 error / 0 skipped out of 48**

## Learning stages

```
{
  "survey": {
    "status": "skipped_existing",
    "error": ""
  },
  "explore": {
    "status": "completed",
    "error": ""
  },
  "optimize": {
    "status": "timeout",
    "error": ""
  },
  "evolve": {
    "status": "completed",
    "error": ""
  },
  "verify": {
    "status": "failed",
    "error": "'list' object has no attribute 'items'"
  }
}
```

## Per-question detail

### Уровень 1. Базовое исследование схемы (`level1_schema`)

| # | Question | Status | Time, s | Agent rows | ReAct | Error |
|---|---|---|---|---|---|---|
| 1 | Покажи выручку магазинов по годам | error | 0.1 | - | - | HTTP 500: Internal Server Error |
| 2 | Какие 20 товаров принесли больше всего выручки в магазинах? | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 3 | Покажи продажи по категориям товаров | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 4 | Сколько уникальных покупателей было в каждом году? | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 5 | Какие штаты принесли больше всего интернет-выручки? | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 6 | Покажи средний размер одной покупки по магазинам | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 7 | Какие бренды продавались чаще всего через каталог? | error | 0.0 | - | - | HTTP 500: Internal Server Error |

### Уровень 2. Возвраты и бизнес-метрики (`level2_returns`)

| # | Question | Status | Time, s | Agent rows | ReAct | Error |
|---|---|---|---|---|---|---|
| 1 | Какие товары имеют самый высокий процент возврата в магазинах? | error | 0.1 | - | - | HTTP 500: Internal Server Error |
| 2 | Покажи возвраты по причинам | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 3 | Какие категории приносят высокую выручку, но имеют высокий процент возврата? | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 4 | Сравни прибыль до и после возвратов по магазинам | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 5 | Какие покупатели возвращают более 30% купленных товаров? | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 6 | Покажи среднее число дней между продажей и возвратом | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 7 | Какие товары часто возвращают через интернет, но редко возвращают в магазинах? | error | 0.0 | - | - | HTTP 500: Internal Server Error |

### Уровень 3. Сравнение каналов (`level3_channels`)

| # | Question | Status | Time, s | Agent rows | ReAct | Error |
|---|---|---|---|---|---|---|
| 1 | Сравни выручку магазина, интернета и каталога по кварталам | error | 0.1 | - | - | HTTP 500: Internal Server Error |
| 2 | Для каждой категории покажи наиболее прибыльный канал | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 3 | Какие товары хорошо продаются онлайн, но плохо — в магазинах? | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 4 | Какие клиенты покупали через все три канала? | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 5 | Покажи клиентов, которые перешли из каталога в интернет | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 6 | Как изменилась доля интернет-продаж в общей выручке? | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 7 | Какие промоакции лучше работают онлайн, чем в магазинах? | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 8 | Сравни процент возврата по каждому каналу | error | 0.0 | - | - | HTTP 500: Internal Server Error |

### Уровень 4. Клиенты и сегментация (`level4_customers`)

| # | Question | Status | Time, s | Agent rows | ReAct | Error |
|---|---|---|---|---|---|---|
| 1 | Какие демографические группы дают максимальную выручку? | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 2 | Сравни средний чек по уровням дохода | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 3 | Найди клиентов, которые не покупали последний год, но раньше тратили много | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 4 | Выдели новых и повторных покупателей по месяцам | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 5 | Какие домохозяйства чаще используют каталог, чем интернет? | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 6 | Найди клиентов с растущими расходами три года подряд | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 7 | Покажи retention покупателей по году первой покупки | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 8 | Найди 10% наиболее ценных покупателей и их любимые категории | error | 0.0 | - | - | HTTP 500: Internal Server Error |

### Уровень 5. Остатки и логистика (`level5_inventory`)

| # | Question | Status | Time, s | Agent rows | ReAct | Error |
|---|---|---|---|---|---|---|
| 1 | Какие товары чаще всего заканчивались на складах? | error | 0.1 | - | - | HTTP 500: Internal Server Error |
| 2 | Найди товары с высоким остатком и низкими продажами | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 3 | На каких складах больше всего залежавшихся товаров? | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 4 | Какие товары продавались при почти нулевом остатке? | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 5 | Сравни сроки доставки по способам доставки | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 6 | Какие склады обслуживают самые прибыльные заказы? | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 7 | Найди регионы с высокой выручкой и долгой доставкой | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 8 | Какие товары следует перераспределить между складами? | error | 0.0 | - | - | HTTP 500: Internal Server Error |

### Уровень 6. Сложные аналитические запросы (`level6_analytics`)

| # | Question | Status | Time, s | Agent rows | ReAct | Error |
|---|---|---|---|---|---|---|
| 1 | Найди месяцы, когда продажи категории отклонялись от среднего более чем на два стандартных отклонения | error | 0.1 | - | - | HTTP 500: Internal Server Error |
| 2 | Покажи товары с ростом продаж три квартала подряд | error | 0.1 | - | - | HTTP 500: Internal Server Error |
| 3 | Найди пары товаров, которые часто покупают вместе | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 4 | Рассчитай накопительную выручку каждого магазина по месяцам | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 5 | Покажи вклад каждого товара в выручку своей категории | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 6 | Выдели товары, формирующие первые 80% выручки | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 7 | Найди каннибализацию между магазином и интернетом по регионам | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 8 | Сравни эффективность промоакции до, во время и после её проведения | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 9 | Какие товары имеют сезонный спрос? | error | 0.0 | - | - | HTTP 500: Internal Server Error |
| 10 | Найди аномально большие покупки относительно обычного поведения клиента | error | 0.0 | - | - | HTTP 500: Internal Server Error |

## Environment

```
{
  "provider": "litellm",
  "model": "hosted_vllm/qwen-summary",
  "base_url": "http://host.docker.internal:8445/v1",
  "database": "waiting for an agent database response",
  "api_base": "http://localhost:8000"
}
```
