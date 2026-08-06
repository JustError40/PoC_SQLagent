# SQLagent PoC

End-to-end PoC самоадаптирующейся database-skill среды. Агент сам строит и
улучшает свой skill для той БД, к которой подключён, — без подгонки кода под
конкретную схему:

`Surveyor → Explorer → Query Agent → trajectories → Evolution → Evaluator → promotion`

Все знания о конкретной БД живут только в skill workspace (артефактах), а не в
коде: Surveyor извлекает их детерминированными коллекторами и LLM из данных,
Explorer итеративно исследует БД read-only probe-запросами и дозаписывает
проверенные templates/правила, Evolution улучшает skill по trajectories.

## Быстрый запуск

```bash
cp .env.example .env
uv sync
docker compose up -d postgres ollama
python -m sqlagent seed
python -m sqlagent demo-load
python -m sqlagent survey
python -m sqlagent explore
python -m sqlagent ask "выручка новых клиентов по месяцам"
python -m sqlagent evaluate
```

Модель задаётся переменной `OLLAMA_MODEL`; текущий дефолт — `openbmb/minicpm5:fp16`.
После загрузки модели в контейнер можно проверить её так:

```bash
docker exec -it sqlagent-ollama ollama list
docker exec -it sqlagent-ollama ollama run openbmb/minicpm5:fp16
```

OpenBMB для Ollama документирует MiniCPM5 через GGUF и Modelfile с chat template,
stop-токенами `<|im_end|>`/`</s>`, `num_ctx 8192`, `temperature 0.7` и `top_p 0.95`.
В SQL Agent runtime-контекст расширен до `num_ctx 16384` для schema-aware ReAct repair.
Если registry-tag отсутствует, используйте cookbook из репозитория: скачайте GGUF,
создайте Modelfile и затем `ollama create` с тем именем, которое указано в
`OLLAMA_MODEL`.

## Основной датасет PoC: TPC-DS SF10

TPC-DS генерируется официальным `dsdgen` из публичного toolkit и загружается в
отдельную БД `tpcds`; текущий `warehouse` остаётся быстрым smoke-fixture.

```bash
python -m sqlagent tpcds-bootstrap --scale 10
export DATABASE_URL=postgresql://warehouse@localhost:5432/tpcds
export WORKSPACE_PATH=skills/tpcds_sf10
python -m sqlagent survey
python -m sqlagent ask "total store sales by month"
```

Генерация SF10 может занять заметное время и создать порядка 10 GB raw-файлов;
данные находятся в `.data/` и не попадают в git. Для повторного запуска без
перегенерации используется `tpcds-bootstrap` без `--force`; `--replace` пересоздаёт
только отдельную БД `tpcds`.

## Field Console и telemetry

После `docker compose up -d --build api` UI доступен на `http://localhost:8000`.
Статусная линия `ingest → reason → learn → promote` обновляется event hooks от
реальных DB/Ollama/agent-ответов; `/api/status` не вызывает Ollama `api/tags`,
Postgres или backend health probes. Skill workspace примонтирован в контейнер,
поэтому trajectories и git-состояние сохраняются между перезапусками.

Неоднозначные вопросы не получают SQL наугад: Query Agent сохраняет telemetry и
возвращает запрос уточнения в trajectory:

```json
{
  "telemetry": {
    "ambiguity_detected": true,
    "possible_metrics": ["net_revenue", "net_profit", "customer_count", "year_over_year_growth"],
    "clarification_requested": true
  }
}
```

## Команды

- `seed` пересоздаёт тестовую БД и наполняет её детерминированными данными. `SEED_ORDERS` управляет размером факта.
- `demo-load` восстанавливает скачанный `db_seed/demo/dvdrental.sql` в отдельную БД `dvdrental`; `warehouse` при этом не меняется.
- `survey` запускает LangGraph Surveyor: inventory, profiles, проверка FK-joins на реальных данных (verified/dangerous по измеренному fanout), семантика таблиц и домены через LLM. Ничего не знает о конкретной БД.
- `explore` запускает Explorer: модель итеративно планирует read-only probe-запросы, выполняет их через те же safety-gates (validate → EXPLAIN → execute) и дозаписывает в skill только проверенные артефакты — templates, dangerous joins, learned rules. `EXPLORER_ROUNDS`/`EXPLORER_PROBES_PER_ROUND` ограничивают бюджет.
- `bootstrap` = `survey` + `explore`, но только если workspace ещё не построен; используется при старте контейнера.
- `ask` запускает read-only Query Agent: LLM-router по `manifest.yaml`, EXPLAIN gate, invariant check (правила читаются из `evals/invariants.yaml` skill'а) и JSONL trajectory.
- `evaluate` переигрывает `evals/regression.jsonl` и выводит correctness, unsafe, p95 и tool calls.
- `evolve` создаёт ветку `evolution/<id>`; мутацию предлагает LLM по trajectories (максимум 3 файла, только разрешённые поверхности), без LLM — детерминированный fallback.
- `promote` сравнивает текущую evolution-ветку с `main`, применяет gate и при успехе делает merge + tag `promoted-<date>`.

## Адаптация к новой БД

Код агента DB-агностичен; адаптация задаётся двумя переменными:

```bash
export DATABASE_URL=postgresql://warehouse@localhost:5432/dvdrental
export WORKSPACE_PATH=skills/dvdrental
python -m sqlagent bootstrap   # survey + explore строят новый skill с нуля
python -m sqlagent ask "top rented film categories"
```

При старте docker-контейнера `docker-entrypoint.sh` автоматически запускает
`python -m sqlagent bootstrap` (отключается `BOOTSTRAP_ON_START=0`): пустой
`WORKSPACE_PATH` → агент сам исследует свою БД до старта API, существующий
manifest → сразу API. «Второй агент для другой БД» — это второй контейнер с
другими `DATABASE_URL`, `WORKSPACE_PATH` и volume под skill.

## Безопасность и воспроизводимость

Подключение Query Agent переводится в PostgreSQL read-only transaction, SQL пропускается
через `sqlparse`, разрешён только один `SELECT`/`WITH`, а опасные one-to-many joins
описаны отдельно от verified joins. LLM используется для семантики и неизвестных запросов;
детерминированные collectors, templates и fallback позволяют запускать seed/survey/eval
до завершения загрузки модели.
