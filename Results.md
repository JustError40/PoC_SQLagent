# SQL Agent TPC-DS Test Campaign — Results

- Started: 2026-08-14T12:16:56.984226+00:00
- Finished: 2026-08-14T13:57:47.310882+00:00
- Total wall time: 96.0 min (budget 6.0 h)
- Agent: `litellm/hosted_vllm/qwen-summary via http://host.docker.internal:8445/v1, db=waiting for an agent database response`

## Summary

| Block | Questions | Answered | Clarified | Pipeline failed | Rescued | Block time |
|---|---|---|---|---|---|---|
| Уровень 1. Базовое исследование схемы | 7 | 7 | 0 | 0 | 0 | 1.6 min |
| Уровень 2. Возвраты и бизнес-метрики | 7 | 5 | 0 | 2 | 0 | 8.8 min |
| Уровень 3. Сравнение каналов | 8 | 6 | 0 | 2 | 0 | 11.8 min |
| Уровень 4. Клиенты и сегментация | 8 | 6 | 0 | 2 | 1 | 41.5 min |
| Уровень 5. Остатки и логистика | 8 | 5 | 0 | 3 | 0 | 15.2 min |
| Уровень 6. Сложные аналитические запросы | 10 | 6 | 1 | 3 | 0 | 17.0 min |

**Total: 35 answered / 1 clarified / 12 pipeline failed / 0 skipped out of 48**

Useful outcomes: 36; rescued retries: 1; tool calls: 596; prompt/completion tokens: 652448/614950.

## Learning stages

```
{
  "survey": {
    "status": "skipped_existing",
    "error": ""
  },
  "explore": {
    "status": "skipped_env",
    "error": ""
  },
  "optimize": {
    "status": "skipped_env",
    "error": ""
  },
  "evolve": {
    "status": "completed",
    "error": ""
  },
  "promote": {
    "status": "failed",
    "error": "promotion requires an evolution/* candidate branch"
  },
  "verify": {
    "status": "completed",
    "error": ""
  }
}
```

## Per-question detail

### Уровень 1. Базовое исследование схемы (`level1_schema`)

| # | Question | Status | Time, s | Rows | Tools | Error type/stage |
|---|---|---|---|---|---|---|
| 1 | Покажи выручку магазинов по годам | answered | 42.9 | 60 | 8 | /:  |
| 2 | Какие 20 товаров принесли больше всего выручки в магазинах? | answered | 42.3 | 20 | 8 | /:  |
| 3 | Покажи продажи по категориям товаров | answered | 17.2 | 11 | 4 | /:  |
| 4 | Сколько уникальных покупателей было в каждом году? | answered | 40.6 | 6 | 9 | /:  |
| 5 | Какие штаты принесли больше всего интернет-выручки? | answered | 75.8 | 3 | 9 | /:  |
| 6 | Покажи средний размер одной покупки по магазинам | answered | 57.4 | 10 | 8 | /:  |
| 7 | Какие бренды продавались чаще всего через каталог? | answered | 39.5 | 500 | 9 | /:  |

### Уровень 2. Возвраты и бизнес-метрики (`level2_returns`)

| # | Question | Status | Time, s | Rows | Tools | Error type/stage |
|---|---|---|---|---|---|---|
| 1 | Какие товары имеют самый высокий процент возврата в магазинах? | pipeline_failed | 78.0 | 0 | 7 | llm_schema_violation/react: ReAct repair failed: LiteLLM model 'hosted_vllm/qwen-summary' did not return JSON: LLM schema violation at $: missing fr |
| 2 | Покажи возвраты по причинам | answered | 18.4 | 45 | 4 | /:  |
| 3 | Какие категории приносят высокую выручку, но имеют высокий процент возврата? | answered | 81.5 | 11 | 11 | /:  |
| 4 | Сравни прибыль до и после возвратов по магазинам | answered | 51.2 | 42 | 8 | /:  |
| 5 | Какие покупатели возвращают более 30% купленных товаров? | answered | 38.8 | 500 | 9 | /:  |
| 6 | Покажи среднее число дней между продажей и возвратом | pipeline_failed | 97.9 | 500 | 31 | react_exhausted/react: ReAct repair budget exhausted after 15 attempts: EXPLAIN failed: cannot cast type integer to interval
LINE 1: ...FROM (d |
| 7 | Какие товары часто возвращают через интернет, но редко возвращают в магазинах? | answered | 19.9 | 50 | 8 | /:  |

### Уровень 3. Сравнение каналов (`level3_channels`)

| # | Question | Status | Time, s | Rows | Tools | Error type/stage |
|---|---|---|---|---|---|---|
| 1 | Сравни выручку магазина, интернета и каталога по кварталам | answered | 41.3 | 63 | 8 | /:  |
| 2 | Для каждой категории покажи наиболее прибыльный канал | answered | 185.0 | 11 | 16 | /:  |
| 3 | Какие товары хорошо продаются онлайн, но плохо — в магазинах? | answered | 307.6 | 0 | 14 | /:  |
| 4 | Какие клиенты покупали через все три канала? | answered | 182.7 | 500 | 14 | /:  |
| 5 | Покажи клиентов, которые перешли из каталога в интернет | answered | 69.2 | 500 | 12 | /:  |
| 6 | Как изменилась доля интернет-продаж в общей выручке? | pipeline_failed | 59.6 | 42 | 7 | llm_schema_violation/react: ReAct repair failed: LiteLLM model 'hosted_vllm/qwen-summary' did not return JSON: LLM schema violation at $: missing sq |
| 7 | Какие промоакции лучше работают онлайн, чем в магазинах? | pipeline_failed | 103.4 | 500 | 11 | llm_schema_violation/react: ReAct repair failed: LiteLLM model 'hosted_vllm/qwen-summary' did not return JSON: LLM schema violation at $: missing sq |
| 8 | Сравни процент возврата по каждому каналу | answered | 40.2 | 2 | 9 | /:  |

### Уровень 4. Клиенты и сегментация (`level4_customers`)

| # | Question | Status | Time, s | Rows | Tools | Error type/stage |
|---|---|---|---|---|---|---|
| 1 | Какие демографические группы дают максимальную выручку? | answered | 12.9 | 500 | 4 | /:  |
| 2 | Сравни средний чек по уровням дохода | answered | 45.1 | 20 | 8 | /:  |
| 3 | Найди клиентов, которые не покупали последний год, но раньше тратили много | answered | 227.1 | 0 | 19 | /:  |
| 4 | Выдели новых и повторных покупателей по месяцам | answered | 60.7 | 61 | 11 | /:  |
| 5 | Какие домохозяйства чаще используют каталог, чем интернет? | answered | 201.1 | 500 | 12 | /:  |
| 6 | Найди клиентов с растущими расходами три года подряд | pipeline_failed | 384.1 | 500 | 17 | sql_validation_failed/react: ReAct repair failed: LiteLLM model 'hosted_vllm/qwen-summary' did not return JSON: LLM provider response did not contain |
| 7 | Покажи retention покупателей по году первой покупки | pipeline_failed | 1170.3 | 100 | 38 | llm_schema_violation/react: ReAct repair failed: LiteLLM model 'hosted_vllm/qwen-summary' did not return JSON: LLM schema violation at $: missing sq |
| 8 | Найди 10% наиболее ценных покупателей и их любимые категории | answered | 389.0 | 500 | 22 | /:  |

### Уровень 5. Остатки и логистика (`level5_inventory`)

| # | Question | Status | Time, s | Rows | Tools | Error type/stage |
|---|---|---|---|---|---|---|
| 1 | Какие товары чаще всего заканчивались на складах? | answered | 151.3 | 30 | 10 | /:  |
| 2 | Найди товары с высоким остатком и низкими продажами | pipeline_failed | 88.0 | 30 | 7 | llm_schema_violation/react: ReAct repair failed: LiteLLM model 'hosted_vllm/qwen-summary' did not return JSON: LLM schema violation at $: missing sq |
| 3 | На каких складах больше всего залежавшихся товаров? | answered | 165.0 | 10 | 12 | /:  |
| 4 | Какие товары продавались при почти нулевом остатке? | answered | 171.9 | 30 | 12 | /:  |
| 5 | Сравни сроки доставки по способам доставки | pipeline_failed | 83.2 | 0 | 34 | react_exhausted/react: ReAct repair budget exhausted after 15 attempts: EXPLAIN failed: function pg_catalog.extract(unknown, integer) does not  |
| 6 | Какие склады обслуживают самые прибыльные заказы? | answered | 302.3 | 10 | 16 | /:  |
| 7 | Найди регионы с высокой выручкой и долгой доставкой | pipeline_failed | 275.0 | 18 | 35 | react_exhausted/react: ReAct repair budget exhausted after 15 attempts: EXPLAIN failed: operator does not exist: integer - date
LINE 1: ...venu |
| 8 | Какие товары следует перераспределить между складами? | answered | 186.0 | 100 | 12 | /:  |

### Уровень 6. Сложные аналитические запросы (`level6_analytics`)

| # | Question | Status | Time, s | Rows | Tools | Error type/stage |
|---|---|---|---|---|---|---|
| 1 | Найди месяцы, когда продажи категории отклонялись от среднего более чем на два стандартных отклонения | answered | 108.4 | 0 | 17 | /:  |
| 2 | Покажи товары с ростом продаж три квартала подряд | answered | 78.1 | 0 | 17 | /:  |
| 3 | Найди пары товаров, которые часто покупают вместе | pipeline_failed | 54.7 | 11 | 7 | llm_schema_violation/react: ReAct repair failed: LiteLLM model 'hosted_vllm/qwen-summary' did not return JSON: LLM schema violation at $: missing sq |
| 4 | Рассчитай накопительную выручку каждого магазина по месяцам | answered | 28.1 | 500 | 8 | /:  |
| 5 | Покажи вклад каждого товара в выручку своей категории | pipeline_failed | 16.9 | 11 | 7 | llm_schema_violation/react: ReAct repair failed: LiteLLM model 'hosted_vllm/qwen-summary' did not return JSON: LLM schema violation at $: missing sq |
| 6 | Выдели товары, формирующие первые 80% выручки | answered | 207.8 | 500 | 13 | /:  |
| 7 | Найди каннибализацию между магазином и интернетом по регионам | answered | 203.9 | 500 | 13 | /:  |
| 8 | Сравни эффективность промоакции до, во время и после её проведения | clarified | 21.9 | 0 | 1 | /:  |
| 9 | Какие товары имеют сезонный спрос? | pipeline_failed | 22.7 | 500 | 7 | llm_schema_violation/react: ReAct repair failed: LiteLLM model 'hosted_vllm/qwen-summary' did not return JSON: LLM schema violation at $: missing sq |
| 10 | Найди аномально большие покупки относительно обычного поведения клиента | answered | 264.2 | 100 | 13 | /:  |

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
