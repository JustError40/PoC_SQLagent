# SQL Agent PoC

Самоэволюционирующий SQL-agent: `Surveyor → Explorer → Query Agent → durable
failure queue → Evolution → hermetic Evaluator → promotion`.

Каждый запуск начинает только с credentials и создаёт новый skill в
`runs/<run_id>/skill`. Старые database-specific skills не используются и готовые
TPC-DS вопросы не передаются Surveyor/learner как знания или golden answers.

## Кампания

```bash
cp .env.example .env
uv sync
scripts/run_test_campaign.sh
```

Preflight сначала генерирует TPC-DS, измеряет dataset, рассчитывает tmpfs с
запасом и сверяет его с `MemAvailable`. PostgreSQL data directory монтируется
только в Docker `tmpfs`; при нехватке RAM запуск останавливается, disk fallback
отсутствует. Затем одноразовый `loader` загружает SF10 в свежий tmpfs, и только
после этого запускаются API/Surveyor. `RUN_ID` по умолчанию создаётся из UTC
timestamp.

Ручной запуск требует результата preflight:

```bash
export RUN_ID=manual-$(date -u +%Y%m%d-%H%M%S)
campaign_env_file="$(mktemp)"
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/campaign_preflight.py --env-file "$campaign_env_file"
. "$campaign_env_file"
rm -f "$campaign_env_file"
export POSTGRES_TMPFS_SIZE_BYTES TPCDS_DATASET_BYTES
docker compose up -d --build
```

## Runtime-контракты

- `Database.explain_estimate()` делает только `EXPLAIN (FORMAT JSON)`.
- `execute_preview()` исполняет выбранный SQL один раз и ограничивает только UI
  preview переменной `MAX_RESULT_ROWS`.
- `explain_analyze()` доступен отдельно для диагностики.
- `compare_queries_full()` сравнивает полные мультимножества двусторонним
  PostgreSQL `EXCEPT ALL`, включая строки после preview, дубликаты и `NULL`.
- Сложные запросы компилируются из DAG стадий `scan`, `filter`, `join`,
  `aggregate`, `union_all`, `window`, `rank`, `project`. Join cardinality и grain
  валидируются детерминированно.
- Scratch executor принимает только read-only stage SQL, материализует стадии в
  автоматически названные `pg_temp` таблицы на одной connection и ограничивает
  строки, bytes и timeout.

LiteLLM и PostgreSQL имеют отдельные priority-aware AIMD limiter'ы: старт 12,
диапазон 1–12. 429, timeout и pool saturation уменьшают concurrency; стабильные
окна постепенно восстанавливают его. Интерактивные запросы имеют приоритет над
единственным background learner.

## API ошибок и telemetry

`POST /api/ask` возвращает `request_id`, один из статусов `answered`, `clarified`,
`pipeline_failed`, telemetry spans и при ошибке:

```json
{
  "type": "execution_timeout",
  "stage": "execution",
  "retryable": true,
  "message": "...",
  "sqlstate": null,
  "learning_job_id": "..."
}
```

Каждая ошибка сразу попадает в run-local SQLite/WAL queue. Infra failures
сохраняются как incidents и не мутируют skill. Skill failure создаёт отдельный
`evolution/<request_id>-<surface>` Git worktree; shared main checkout не
переключается. Артефакт promotion получает immutable provenance record в
`runs/<run_id>/provenance/`.

Spans фиксируют фактические LLM/DB/tool latency, attempts, cache hit,
provider/model, finish reason, provider token usage, DB wait/execute time,
rows/truncation и estimates. Не сообщённые provider usage-поля остаются `null`.

## Evaluation и отчёт

Evaluator запускает baseline/candidate из detached worktree на фиксированных SHA
в `read_only_evaluation`: запрещены trajectories, manifest metrics, learned
templates, commits и cache writes. Corpus/telemetry находятся вне skill; manifest
фиксирует corpus checksum, DB snapshot, commit и tree hash. Изменение filesystem
или Git tree считается ошибкой evaluator.

Promotion gate не использует accuracy oracle. Он требует rescued target,
`unsafe=0`, отсутствие превращения ранее отвечавших cases в pipeline failures,
полную эквивалентность неизменяемых ответов и последовательное performance
сравнение. Acceptance report показывает completion, useful outcomes, failure
attribution, rescued retries, tokens/tool calls и latency — accuracy/correctness
не вычисляется.

## Команды разработки

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q
python -m sqlagent survey
python -m sqlagent explore
python -m sqlagent ask "накопительная выручка по месяцам"
python -m sqlagent evaluate
python -m sqlagent evolve
python -m sqlagent promote
```
