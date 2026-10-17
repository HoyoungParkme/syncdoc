//! 장비와 실행 단위 (SYNC-MS-026 · MS-024 infra, 카드 L24).
//! view_arc `infra.mts`·`stack.mts`의 표와 규칙 — 파이썬 판 `core/codegraph/infra.py`와 같은 표·같은 차례다.
//! 주소는 호스트·포트만 남긴다 — 비밀번호·키는 읽어도 저장하지 않는다(INFRA C13).
//! 폴더는 이름 바이트 순으로 걷고, 파이썬 판이 `re.ASCII`로 쓴 정규식은 ASCII 뜻으로 옮긴다(MS-026 0장).

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

use indexmap::IndexMap;
use regex::Regex;
use serde_json::{Map, Value, json};
use tree_sitter::Node;

use syncdoc_pycompat::chars::{decimal_value, lstrip, py_splitlines, strip};
use syncdoc_pycompat::re::compile as py_re;

use super::routes::is_front;
use super::steps::{rs_defs, ts_defs};
use super::{
    ascii, children, named_children, read, rs_parse, text, ts_parse, unparen, walk, walk_files,
};
use crate::graph::is_test;
use crate::python;

/// 패키지 → (id, kind, name, io, protocol) — 파이썬 판 `LIBS`와 같은 차례
const LIBS: &[(&str, &str, &str, &str, &str, &str)] = &[
    (
        "sqlalchemy",
        "db",
        "db",
        "DB",
        r#"^(execute\w*|exec|scalars?|get|add|add_all|commit|flush|delete|merge|refresh|query|stream\w*|fetch\w*|copy_\w+|bulk_\w+)$"#,
        "SQL",
    ),
    (
        "sqlmodel",
        "db",
        "db",
        "DB",
        r#"^(execute\w*|exec|scalars?|get|add|add_all|commit|flush|delete|merge|refresh|query|stream\w*|fetch\w*|copy_\w+|bulk_\w+)$"#,
        "SQL",
    ),
    (
        "psycopg2",
        "db",
        "db",
        "PostgreSQL",
        r#"^(execute\w*|exec|scalars?|get|add|add_all|commit|flush|delete|merge|refresh|query|stream\w*|fetch\w*|copy_\w+|bulk_\w+)$"#,
        "SQL",
    ),
    (
        "psycopg",
        "db",
        "db",
        "PostgreSQL",
        r#"^(execute\w*|exec|scalars?|get|add|add_all|commit|flush|delete|merge|refresh|query|stream\w*|fetch\w*|copy_\w+|bulk_\w+)$"#,
        "SQL",
    ),
    (
        "asyncpg",
        "db",
        "db",
        "PostgreSQL",
        r#"^(execute\w*|exec|scalars?|get|add|add_all|commit|flush|delete|merge|refresh|query|stream\w*|fetch\w*|copy_\w+|bulk_\w+)$"#,
        "SQL",
    ),
    (
        "pymysql",
        "db",
        "db",
        "MySQL",
        r#"^(execute\w*|exec|scalars?|get|add|add_all|commit|flush|delete|merge|refresh|query|stream\w*|fetch\w*|copy_\w+|bulk_\w+)$"#,
        "SQL",
    ),
    (
        "sqlite3",
        "db",
        "db",
        "SQLite",
        r#"^(execute\w*|exec|scalars?|get|add|add_all|commit|flush|delete|merge|refresh|query|stream\w*|fetch\w*|copy_\w+|bulk_\w+)$"#,
        "SQL",
    ),
    (
        "aiosqlite",
        "db",
        "db",
        "SQLite",
        r#"^(execute\w*|exec|scalars?|get|add|add_all|commit|flush|delete|merge|refresh|query|stream\w*|fetch\w*|copy_\w+|bulk_\w+)$"#,
        "SQL",
    ),
    (
        "pymongo",
        "mongo",
        "db",
        "MongoDB",
        r#"^(find\w*|insert\w*|update\w*|delete\w*|replace_one|aggregate|count_documents|bulk_write)$"#,
        "Mongo",
    ),
    (
        "motor",
        "mongo",
        "db",
        "MongoDB",
        r#"^(find\w*|insert\w*|update\w*|delete\w*|replace_one|aggregate|count_documents|bulk_write)$"#,
        "Mongo",
    ),
    (
        "neo4j",
        "neo4j",
        "db",
        "Neo4j",
        r#"^(run|execute_query|execute_read|execute_write)$"#,
        "Bolt",
    ),
    (
        "redis",
        "redis",
        "cache",
        "Redis",
        r#"^(get|set\w*|mget|mset|hget\w*|hset\w*|hdel|incr\w*|decr\w*|expire\w*|delete|exists|[lr]push|[lr]pop|lrange|publish|xadd|xread\w*|zadd|zrange\w*|sadd|smembers|ping|from_url)$"#,
        "Redis",
    ),
    (
        "boto3",
        "storage",
        "storage",
        "S3 저장소",
        r#"^(put_object|get_object|upload_\w+|download_\w+|list_objects\w*|list_buckets|delete_object\w*|head_object|head_bucket|create_bucket|copy_object|generate_presigned_url)$"#,
        "S3",
    ),
    (
        "minio",
        "storage",
        "storage",
        "MinIO",
        r#"^(put_object|get_object|fput_object|fget_object|list_objects|remove_object|stat_object|bucket_exists|make_bucket)$"#,
        "S3",
    ),
    (
        "openai",
        "openai",
        "api",
        "OpenAI API",
        r#"^(create|parse|stream)$"#,
        "HTTPS",
    ),
    (
        "anthropic",
        "anthropic",
        "api",
        "Anthropic API",
        r#"^(create|stream)$"#,
        "HTTPS",
    ),
    (
        "requests",
        "http",
        "api",
        "외부 HTTP",
        r#"^(get|post|put|patch|delete|head|request|send)$"#,
        "HTTPS",
    ),
    (
        "httpx",
        "http",
        "api",
        "외부 HTTP",
        r#"^(get|post|put|patch|delete|head|request|send|stream)$"#,
        "HTTPS",
    ),
    (
        "aiohttp",
        "http",
        "api",
        "외부 HTTP",
        r#"^(get|post|put|patch|delete|head|request)$"#,
        "HTTPS",
    ),
    (
        "urllib",
        "http",
        "api",
        "외부 HTTP",
        r#"^(urlopen)$"#,
        "HTTPS",
    ),
    (
        "elasticsearch",
        "search",
        "search",
        "Elasticsearch",
        r#"^(search|index|get|delete|bulk|update)$"#,
        "HTTP",
    ),
    (
        "opensearchpy",
        "search",
        "search",
        "OpenSearch",
        r#"^(search|index|get|delete|bulk|update)$"#,
        "HTTP",
    ),
    (
        "pika",
        "queue",
        "queue",
        "메시지 큐",
        r#"^(basic_publish|basic_consume|publish)$"#,
        "AMQP",
    ),
    (
        "aio_pika",
        "queue",
        "queue",
        "메시지 큐",
        r#"^(publish|consume)$"#,
        "AMQP",
    ),
    (
        "kafka",
        "queue",
        "queue",
        "Kafka",
        r#"^(send|poll|produce)$"#,
        "Kafka",
    ),
    (
        "aiokafka",
        "queue",
        "queue",
        "Kafka",
        r#"^(send\w*|getone|getmany)$"#,
        "Kafka",
    ),
    (
        "celery",
        "queue",
        "queue",
        "작업 큐",
        r#"^(delay|apply_async|send_task)$"#,
        "AMQP",
    ),
    (
        "pg",
        "db",
        "db",
        "PostgreSQL",
        r#"^(query|connect)$"#,
        "SQL",
    ),
    (
        "@neondatabase/serverless",
        "db",
        "db",
        "PostgreSQL",
        r#"^(query|connect|transaction)$"#,
        "SQL",
    ),
    (
        "mysql2",
        "db",
        "db",
        "MySQL",
        r#"^(query|execute|getConnection)$"#,
        "SQL",
    ),
    (
        "better-sqlite3",
        "db",
        "db",
        "SQLite",
        r#"^(run|get|all|exec|iterate)$"#,
        "SQL",
    ),
    (
        "drizzle-orm",
        "db",
        "db",
        "DB",
        r#"^(select|selectDistinct|insert|update|delete|execute|findMany|findFirst|transaction|batch)$"#,
        "SQL",
    ),
    (
        "@prisma/client",
        "db",
        "db",
        "DB",
        r#"^(findMany|findFirst|findUnique|findUniqueOrThrow|findFirstOrThrow|create|createMany|update|updateMany|upsert|delete|deleteMany|count|aggregate|groupBy|\$queryRaw\w*|\$executeRaw\w*|\$transaction)$"#,
        "SQL",
    ),
    (
        "typeorm",
        "db",
        "db",
        "DB",
        r#"^(find\w*|save|insert|update|delete|remove|softDelete|query|count\w*|getMany|getOne|getRawMany|getRawOne|execute|exist\w*)$"#,
        "SQL",
    ),
    (
        "sequelize",
        "db",
        "db",
        "DB",
        r#"^(findAll|findOne|findByPk|findOrCreate|findAndCountAll|create|bulkCreate|update|destroy|count|query|upsert)$"#,
        "SQL",
    ),
    (
        "knex",
        "db",
        "db",
        "DB",
        r#"^(select|insert|update|del|delete|raw|first|then)$"#,
        "SQL",
    ),
    (
        "mongoose",
        "mongo",
        "db",
        "MongoDB",
        r#"^(find\w*|create|insertMany|update\w*|delete\w*|replaceOne|aggregate|count\w*|save|exec|exists)$"#,
        "Mongo",
    ),
    (
        "mongodb",
        "mongo",
        "db",
        "MongoDB",
        r#"^(find\w*|insert\w*|update\w*|delete\w*|replaceOne|aggregate|countDocuments|bulkWrite|toArray)$"#,
        "Mongo",
    ),
    (
        "ioredis",
        "redis",
        "cache",
        "Redis",
        r#"^(get|set\w*|mget|mset|hget\w*|hset\w*|hdel|incr\w*|decr\w*|expire\w*|del|exists|[lr]push|[lr]pop|lrange|publish|xadd|xread\w*|zadd|zrange\w*|sadd|smembers|ping|eval)$"#,
        "Redis",
    ),
    (
        "@upstash/redis",
        "redis",
        "cache",
        "Redis",
        r#"^(get|set\w*|del|incr\w*|expire|hget\w*|hset\w*|lpush|rpush|lrange)$"#,
        "HTTPS",
    ),
    (
        "bullmq",
        "redis",
        "cache",
        "Redis",
        r#"^(add|addBulk)$"#,
        "Redis",
    ),
    (
        "@aws-sdk/client-s3",
        "storage",
        "storage",
        "S3 저장소",
        r#"^send$"#,
        "S3",
    ),
    (
        "@aws-sdk/lib-storage",
        "storage",
        "storage",
        "S3 저장소",
        r#"^done$"#,
        "S3",
    ),
    (
        "aws-sdk",
        "storage",
        "storage",
        "S3 저장소",
        r#"^(putObject|getObject|upload|deleteObject\w*|listObjects\w*|headObject|getSignedUrl\w*|promise)$"#,
        "S3",
    ),
    (
        "@anthropic-ai/sdk",
        "anthropic",
        "api",
        "Anthropic API",
        r#"^(create|stream)$"#,
        "HTTPS",
    ),
    (
        "@google/generative-ai",
        "gemini",
        "api",
        "Gemini API",
        r#"^(generateContent\w*|embedContent|countTokens|sendMessage\w*)$"#,
        "HTTPS",
    ),
    (
        "@google/genai",
        "gemini",
        "api",
        "Gemini API",
        r#"^(generateContent\w*|embedContent|countTokens|sendMessage\w*)$"#,
        "HTTPS",
    ),
    (
        "axios",
        "http",
        "api",
        "외부 HTTP",
        r#"^(get|post|put|patch|delete|head|request)$"#,
        "HTTPS",
    ),
    (
        "node-fetch",
        "http",
        "api",
        "외부 HTTP",
        r#"^fetch$"#,
        "HTTPS",
    ),
    (
        "undici",
        "http",
        "api",
        "외부 HTTP",
        r#"^(fetch|request)$"#,
        "HTTPS",
    ),
    ("fetch", "http", "api", "외부 HTTP", r#"^fetch$"#, "HTTPS"),
    (
        "kafkajs",
        "queue",
        "queue",
        "Kafka",
        r#"^(send|sendBatch)$"#,
        "Kafka",
    ),
    (
        "amqplib",
        "queue",
        "queue",
        "RabbitMQ",
        r#"^(publish|sendToQueue)$"#,
        "AMQP",
    ),
    (
        "@elastic/elasticsearch",
        "search",
        "search",
        "Elasticsearch",
        r#"^(search|index|get|delete|bulk|update)$"#,
        "HTTP",
    ),
    (
        "neo4j-driver",
        "neo4j",
        "db",
        "Neo4j",
        r#"^(run|executeQuery|executeRead|executeWrite)$"#,
        "Bolt",
    ),
    (
        "@supabase/supabase-js",
        "supabase",
        "db",
        "Supabase",
        r#"^(select|insert|update|delete|upsert|rpc|upload|download)$"#,
        "HTTPS",
    ),
    (
        "sqlx",
        "db",
        "db",
        "DB",
        r#"^(fetch\w*|execute\w*)$"#,
        "SQL",
    ),
    (
        "tokio_postgres",
        "db",
        "db",
        "PostgreSQL",
        r#"^(query\w*|execute\w*|prepare)$"#,
        "SQL",
    ),
    (
        "reqwest",
        "http",
        "api",
        "외부 HTTP",
        r#"^(send|get|post|put|patch|delete|head)$"#,
        "HTTPS",
    ),
    (
        "aws_sdk_s3",
        "storage",
        "storage",
        "S3 저장소",
        r#"^send$"#,
        "S3",
    ),
];
/// 의존성 패키지 → (id, kind, name, protocol) — 파이썬 판 `DEPS`
const DEPS: &[(&str, &str, &str, &str, &str)] = &[
    (
        r#"^(pg|postgres|pg-promise|slonik|@neondatabase\/serverless|@vercel\/postgres|org\.postgresql:postgresql|github\.com\/lib\/pq|github\.com\/jackc\/pgx(\/v\d)?|tokio-postgres|npgsql(\..*)?|r2dbc-postgresql)$"#,
        "db",
        "db",
        "PostgreSQL",
        "SQL",
    ),
    (
        r#"^(mysql2?|com\.mysql:mysql-connector-j|mysql:mysql-connector-java|org\.mariadb\.jdbc:mariadb-java-client|github\.com\/go-sql-driver\/mysql|mysql_async|mysql\.data|pomelo\.entityframeworkcore\.mysql)$"#,
        "db",
        "db",
        "MySQL",
        "SQL",
    ),
    (
        r#"^(better-sqlite3|sqlite3|github\.com\/mattn\/go-sqlite3|rusqlite|microsoft\.data\.sqlite|org\.xerial:sqlite-jdbc)$"#,
        "db",
        "db",
        "SQLite",
        "SQL",
    ),
    (
        r#"^(@prisma\/client|drizzle-orm|typeorm|sequelize|knex|kysely|@mikro-orm\/core|org\.springframework\.boot:spring-boot-starter-data-(jpa|jdbc|r2dbc)|org\.springframework\.boot:spring-boot-starter-jdbc|gorm\.io\/gorm|sqlx|diesel|sea-orm|microsoft\.entityframeworkcore(\..*)?|org\.jooq:jooq|org\.mybatis.*)$"#,
        "db",
        "db",
        "DB",
        "SQL",
    ),
    (
        r#"^(mongodb|mongoose|org\.springframework\.boot:spring-boot-starter-data-mongodb.*|org\.mongodb:.*|go\.mongodb\.org\/mongo-driver.*|mongodb\.driver)$"#,
        "mongo",
        "db",
        "MongoDB",
        "Mongo",
    ),
    (
        r#"^(redis|ioredis|@upstash\/redis|bullmq|bull|org\.springframework\.boot:spring-boot-starter-data-redis.*|redis\.clients:jedis|org\.redisson:.*|github\.com\/(redis|go-redis)\/(go-)?redis(\/v\d)?|stackexchange\.redis|predis\/predis)$"#,
        "redis",
        "cache",
        "Redis",
        "Redis",
    ),
    (
        r#"^(minio|io\.minio:minio|github\.com\/minio\/minio-go(\/v\d)?)$"#,
        "storage",
        "storage",
        "MinIO",
        "S3",
    ),
    (
        r#"^(@aws-sdk\/client-s3|aws-sdk|software\.amazon\.awssdk:s3|com\.amazonaws:aws-java-sdk-s3|github\.com\/aws\/aws-sdk-go-v2\/service\/s3|aws-sdk-s3|awssdk\.s3|aws\/aws-sdk-php)$"#,
        "storage",
        "storage",
        "S3 저장소",
        "S3",
    ),
    (
        r#"^(openai|org\.springframework\.ai:spring-ai-(starter-model-)?openai.*|github\.com\/(sashabaranov|openai)\/(go-)?openai(-go)?|async-openai|com\.openai:openai-java)$"#,
        "openai",
        "api",
        "OpenAI API",
        "HTTPS",
    ),
    (
        r#"^(@anthropic-ai\/sdk|com\.anthropic:anthropic-java|github\.com\/anthropics\/anthropic-sdk-go)$"#,
        "anthropic",
        "api",
        "Anthropic API",
        "HTTPS",
    ),
    (
        r#"^(@google\/generative-ai|@google\/genai)$"#,
        "gemini",
        "api",
        "Gemini API",
        "HTTPS",
    ),
    (
        r#"^(kafkajs|org\.springframework\.kafka:spring-kafka|org\.apache\.kafka:kafka-clients|github\.com\/segmentio\/kafka-go|github\.com\/(ibm|shopify)\/sarama|rdkafka|confluent\.kafka)$"#,
        "queue",
        "queue",
        "Kafka",
        "Kafka",
    ),
    (
        r#"^(amqplib|org\.springframework\.boot:spring-boot-starter-amqp|github\.com\/rabbitmq\/amqp091-go|lapin|rabbitmq\.client)$"#,
        "queue",
        "queue",
        "RabbitMQ",
        "AMQP",
    ),
    (
        r#"^(@elastic\/elasticsearch|@opensearch-project\/opensearch|org\.springframework\.boot:spring-boot-starter-data-elasticsearch|co\.elastic\.clients:.*|org\.opensearch\.client:.*|github\.com\/elastic\/go-elasticsearch(\/v\d)?|elasticsearch|opensearch)$"#,
        "search",
        "search",
        "Elasticsearch",
        "HTTP",
    ),
    (
        r#"^(neo4j-driver|org\.springframework\.boot:spring-boot-starter-data-neo4j|org\.neo4j\.driver:.*|neo4rs)$"#,
        "neo4j",
        "db",
        "Neo4j",
        "Bolt",
    ),
    (
        r#"^@supabase\/supabase-js$"#,
        "supabase",
        "db",
        "Supabase",
        "HTTPS",
    ),
    (
        r#"^firebase-admin$"#,
        "firebase",
        "api",
        "Firebase",
        "HTTPS",
    ),
];
const IMAGES: &[(&str, &str, &str, &str)] = &[
    (r#"pgvector"#, "db", "db", "PostgreSQL (pgvector)"),
    (r#"postgres|postgis|timescale"#, "db", "db", "PostgreSQL"),
    (r#"mysql|mariadb"#, "db", "db", "MySQL"),
    (r#"mongo"#, "mongo", "db", "MongoDB"),
    (r#"neo4j|memgraph"#, "neo4j", "db", "Neo4j"),
    (r#"redis|valkey|dragonfly"#, "redis", "cache", "Redis"),
    (r#"minio"#, "storage", "storage", "MinIO (S3)"),
    (
        r#"elasticsearch|opensearch"#,
        "search",
        "search",
        "Elasticsearch",
    ),
    (r#"rabbitmq"#, "queue", "queue", "RabbitMQ"),
    (r#"kafka|redpanda"#, "queue", "queue", "Kafka"),
];
const SCHEMES: &[(&str, &str, &str, &str)] = &[
    (r#"^postgres(ql)?(\+\w+)?$"#, "db", "db", "PostgreSQL"),
    (r#"^mysql(\+\w+)?$|^mariadb"#, "db", "db", "MySQL"),
    (r#"^sqlite(\+\w+)?$"#, "db", "db", "SQLite"),
    (r#"^mongodb(\+srv)?$"#, "mongo", "db", "MongoDB"),
    (r#"^rediss?$"#, "redis", "cache", "Redis"),
    (r#"^(bolt|neo4j)(\+s)?$"#, "neo4j", "db", "Neo4j"),
    (r#"^amqps?$"#, "queue", "queue", "메시지 큐"),
];
const HTTP_KEYS: &[(&str, &str, &str, &str)] = &[
    (
        r#"STORAGE|S3|MINIO|BUCKET"#,
        "storage",
        "storage",
        "S3 저장소",
    ),
    (
        r#"ELASTIC|OPENSEARCH|SEARCH_URL"#,
        "search",
        "search",
        "Elasticsearch",
    ),
];
const HOST_KEYS: &[(&str, &str, &str, &str)] = &[
    (r#"redis|valkey"#, "redis", "cache", "Redis"),
    (r#"mongo"#, "mongo", "db", "MongoDB"),
    (r#"rabbit|amqp"#, "queue", "queue", "RabbitMQ"),
    (r#"elastic|opensearch"#, "search", "search", "Elasticsearch"),
    (r#"neo4j"#, "neo4j", "db", "Neo4j"),
    (r#"minio|s3"#, "storage", "storage", "S3 저장소"),
    (r#"^(.*[._-])?(postgres\w*|pg)$"#, "db", "db", "PostgreSQL"),
    (r#"^(.*[._-])?mysql$"#, "db", "db", "MySQL"),
    (r#"^(.*[._-])?(db|database|datasource)$"#, "db", "db", "DB"),
];
const FRONT_ONLY_RE: &str = r#"^(react|react-dom|preact|vue|svelte|@angular\/core|solid-js)$"#;
const SERVER_DEPS_RE: &str = r#"^(express|fastify|koa|@nestjs\/core|hono|@hapi\/hapi|restify|next|@remix-run\/node|h3|nitropack|elysia)$"#;
const NOT_APP_RE: &str = r#"(^|/)(tests?|scripts?|e2e|evals?|fixtures|examples?|benchmarks?|notebooks?|__tests__)/|(^|/)src/(test|integrationTest|testFixtures|it)/|(^|/)(test_[^/]*|[^/]*_test|conftest)\.py$|(Test|Tests|IT|_test|\.test|\.spec)\.\w+$"#;
const PLACEHOLDER_RE: &str = r#"^(host|hostname|server|your[-_.]?\w*|db[-_]?host|database[-_]?host|<.*>|x{3,}|(.*\.)?example\.(com|org|net))$"#;
const IDENT_RE: &str = r#"^[A-Za-z_][A-Za-z0-9_]*"#;

const LOCAL_HOSTS: [&str; 5] = [
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "host.docker.internal",
];
const SKIP: [&str; 12] = [
    "node_modules",
    "vendor",
    "target",
    "dist",
    "build",
    "out",
    "venv",
    ".venv",
    "__pycache__",
    "site-packages",
    "coverage",
    "graphify-out",
];
const CONFIG_SKIP_MORE: [&str; 6] = ["bin", "obj", "tests", "test", "data", "docs"];
const COMPOSE: [&str; 5] = [
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "docker-compose.dev.yml",
];
const MANIFESTS: [&str; 5] = [
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "manage.py",
    "Cargo.toml",
];

struct Compiled {
    libs_io: Vec<Regex>,
    deps: Vec<Regex>,
    images: Vec<Regex>,
    schemes: Vec<Regex>,
    http_keys: Vec<Regex>,
    host_keys: Vec<Regex>,
    front_only: Regex,
    server_deps: Regex,
    not_app: Regex,
    placeholder: Regex,
    ident: Regex,
}

static RE: LazyLock<Compiled> = LazyLock::new(|| Compiled {
    libs_io: LIBS.iter().map(|l| ascii(l.4, false)).collect(),
    deps: DEPS.iter().map(|d| ascii(d.0, true)).collect(),
    images: IMAGES.iter().map(|d| ascii(d.0, false)).collect(),
    schemes: SCHEMES.iter().map(|d| ascii(d.0, false)).collect(),
    http_keys: HTTP_KEYS.iter().map(|d| ascii(d.0, true)).collect(),
    host_keys: HOST_KEYS.iter().map(|d| ascii(d.0, true)).collect(),
    front_only: ascii(FRONT_ONLY_RE, false),
    server_deps: ascii(SERVER_DEPS_RE, false),
    not_app: ascii(NOT_APP_RE, false),
    placeholder: ascii(PLACEHOLDER_RE, true),
    ident: ascii(IDENT_RE, false),
});

macro_rules! lazy_re {
    ($name:ident, $make:expr) => {
        static $name: LazyLock<Regex> = LazyLock::new(|| $make);
    };
}

lazy_re!(PORT_FLAG, ascii(r"(?:--port|-p)[ =](\d+)", false));
lazy_re!(TOML_TABLE, Regex::new(r"^\[([^\[\]]+)\]$").expect("toml"));
lazy_re!(TOML_KEY, ascii(r"^([A-Za-z0-9_-]+)\s*[.=]", false));
lazy_re!(TOML_NAME, py_re(r#"^name\s*=\s*"([^"]*)""#));
lazy_re!(
    DEP_DIR_SKIP,
    Regex::new(r"^(tests?|examples?|fixtures|docs)$").expect("dir")
);
lazy_re!(PYPROJECT_DEPS, py_re(r"(?ms)^dependencies\s*=\s*\[(.*?)\]"));
lazy_re!(QUOTED, Regex::new(r#"["']([^"']+)["']"#).expect("quoted"));
lazy_re!(REQ_NAME_SP, ascii(r"^\s*([A-Za-z0-9_.-]+)", false));
lazy_re!(REQ_NAME, ascii(r"^([A-Za-z0-9_.-]+)", false));
lazy_re!(
    REQ_FILE,
    Regex::new(r"^requirements[^/]*\.txt$").expect("req")
);
lazy_re!(LINE_SPLIT, Regex::new(r"\r?\n").expect("split"));
lazy_re!(COMMENT_TAIL, py_re(r"\s+#.*$"));
lazy_re!(SVC_LINE, ascii(r"^[\w.-]+:\s*$", false));
lazy_re!(KEY_LINE, Regex::new(r"^[a-z_]+:").expect("key"));
lazy_re!(PORTS_LINE, py_re(r"^ports:\s*$"));
lazy_re!(IMAGE_LINE, py_re(r#"^image:\s*["']?([^"'\s]+)"#));
lazy_re!(PORT_DASH, py_re(r#"^-\s*["']?"#));
lazy_re!(QUOTE_END, Regex::new(r#"["']$"#).expect("q"));
lazy_re!(QUOTE_EDGES, Regex::new(r#"^["']|["']$"#).expect("q"));
lazy_re!(BRACED, ascii(r"\$\{(\w+)(?::?-([^}]*))?\}", false));
lazy_re!(DOLLAR, ascii(r"\$(\w+)", false));
lazy_re!(DEFAULTS, ascii(r"\$\{[\w.]+:-?([^}]*)\}", false));
lazy_re!(YAML_FILE, Regex::new(r"\.ya?ml$").expect("yaml"));
lazy_re!(
    YAML_LINE,
    ascii(r"^(\s*)([\w.-]+)\s*:\s*(.*?)\s*(?:\s#.*)?$", false)
);
lazy_re!(
    ENV_LINE,
    ascii(r"^\s*(?:export\s+)?([\w.-]+)\s*[=:]\s*(.*?)\s*$", false)
);
lazy_re!(
    CONFIG_PY,
    Regex::new(r"^(config|settings|conf)\.py$").expect("cfg")
);
lazy_re!(
    APP_YAML,
    ascii(
        r"^(application|bootstrap)(-[\w.]+)?\.(ya?ml|properties)$",
        false
    )
);
lazy_re!(TEST_DIR, Regex::new(r"(^|/)test/").expect("test"));
lazy_re!(SLASHES, Regex::new(r"^/+").expect("slash"));
lazy_re!(AUTH_SPLIT, Regex::new(r"[/?#]").expect("auth"));
lazy_re!(HOST_PORT, ascii(r"^\[?([^\]:]+)\]?(?::(\d+))?$", false));
lazy_re!(HTTPS, Regex::new(r"^https?$").expect("https"));
lazy_re!(
    URL_ANY,
    ascii(
        r#"(?m)(?:^|["'\s=:])([A-Z][A-Z0-9_]*)?\s*[=:,(]?\s*["']?([a-z][a-z0-9+.-]*)://([^\s"'`]*)"#,
        false
    )
);
lazy_re!(
    CONFIG_FILE,
    Regex::new(r"\.(ya?ml|properties)$|(^|/)\.env[^/]*$").expect("cfg file")
);
lazy_re!(
    URL_VALUE,
    ascii(r#"^["']?(?:jdbc:)?([a-z][a-z0-9+.-]*)://([^\s"'`]*)"#, true)
);
lazy_re!(HOST_KEY, ascii(r"^(.*?)[._-]?host(name)?$", true));
lazy_re!(HOST_BAD, py_re(r"[\s/$]"));
lazy_re!(HOST_TAIL, py_re(r"(?i)host(name)?$"));
lazy_re!(DIGITS, py_re(r"^\d+$"));
lazy_re!(PRISMA_PROVIDER, ascii(r#"provider\s*=\s*"(\w+)""#, false));
lazy_re!(DIALECT, py_re(r#"dialect\s*:\s*["'](\w+)["']"#));

fn lib_of(pkg: &str) -> Option<usize> {
    LIBS.iter().position(|l| l.0 == pkg)
}

// ---------------------------------------------------------------- 파일 걷기

/// 한 폴더의 항목 — (이름, 경로, 폴더인가(링크는 따르지 않는다)), 이름 바이트 순
fn entries(path: &Path) -> Vec<(String, PathBuf, bool)> {
    let Ok(rd) = std::fs::read_dir(path) else {
        return Vec::new();
    };
    let mut out: Vec<(String, PathBuf, bool)> = rd
        .flatten()
        .map(|e| {
            let is_dir = e.file_type().is_ok_and(|t| t.is_dir());
            (
                e.file_name().to_string_lossy().into_owned(),
                e.path(),
                is_dir,
            )
        })
        .collect();
    out.sort_by(|a, b| a.0.as_bytes().cmp(b.0.as_bytes()));
    out
}

/// 한 단 아래 폴더 이름 — 점·`node_modules` 빼고, 이름 바이트 순
fn dirs(path: &Path) -> Vec<String> {
    entries(path)
        .into_iter()
        .filter(|(n, _, d)| *d && !n.starts_with('.') && n != "node_modules")
        .map(|(n, _, _)| n)
        .collect()
}

fn text_of(path: &Path) -> Option<String> {
    String::from_utf8(std::fs::read(path).ok()?).ok()
}

fn is_file(path: &Path) -> bool {
    path.is_file()
}

/// 파이썬 `int(s)` — 앞뒤 공백, 부호, 십진 숫자(유니코드), 숫자 사이 밑줄 하나
fn py_int(s: &str) -> Option<i64> {
    let t = strip(s);
    let (neg, body) = match t.strip_prefix('-') {
        Some(b) => (true, b),
        None => (false, t.strip_prefix('+').unwrap_or(t)),
    };
    if body.is_empty() || body.starts_with('_') || body.ends_with('_') || body.contains("__") {
        return None;
    }
    let mut v: i64 = 0;
    for c in body.chars() {
        if c == '_' {
            continue;
        }
        let d = decimal_value(c)?;
        v = v.checked_mul(10)?.checked_add(i64::from(d))?;
    }
    Some(if neg { -v } else { v })
}

/// 파이썬 `len(s)` — 코드 포인트 수
fn plen(s: &str) -> usize {
    s.chars().count()
}

// ---------------------------------------------------------------- 실행 단위

/// 깊이 3까지의 목록 파일 — [(폴더, 이름)], 폴더는 루트면 ""
fn manifests(src_dir: &Path) -> Vec<(String, String)> {
    fn visit(path: &Path, rel: &str, depth: usize, out: &mut Vec<(String, String)>) {
        for (name, full, is_dir) in entries(path) {
            if is_dir {
                if depth < 3 && !name.starts_with('.') && !SKIP.contains(&name.as_str()) {
                    let r = if rel.is_empty() {
                        name.clone()
                    } else {
                        format!("{rel}/{name}")
                    };
                    visit(&full, &r, depth + 1, out);
                }
            } else if MANIFESTS.contains(&name.as_str()) {
                out.push((rel.to_string(), name));
            }
        }
    }
    let mut out = Vec::new();
    visit(src_dir, "", 0, &mut out);
    out
}

fn unit_name(d: &str) -> String {
    if d.is_empty() {
        "app".into()
    } else {
        d.rsplit('/').next().unwrap_or(d).to_string()
    }
}

fn sub(src_dir: &Path, d: &str) -> PathBuf {
    if d.is_empty() {
        src_dir.to_path_buf()
    } else {
        src_dir.join(d)
    }
}

fn unit(
    name: String,
    kind: &str,
    d: &str,
    lang: &str,
    framework: &str,
    command: Option<String>,
    port: Option<i64>,
) -> Value {
    json!({
        "name": name,
        "kind": kind,
        "dir": d,
        "lang": lang,
        "framework": framework,
        "command": command,
        "port": port,
    })
}

fn obj(v: Option<&Value>) -> Option<&Map<String, Value>> {
    v.and_then(Value::as_object)
}

fn node_unit(src_dir: &Path, d: &str) -> Option<Value> {
    let base = sub(src_dir, d);
    let text = text_of(&base.join("package.json"))?;
    let pkg: Value = serde_json::from_str(&text).ok()?;
    let pkg = pkg.as_object()?;
    let empty = Map::new();
    let deps = obj(pkg.get("dependencies")).unwrap_or(&empty);
    let dev = obj(pkg.get("devDependencies")).unwrap_or(&empty);
    let mut found: Option<(&str, &str)> = None;
    for (name, fw) in [
        ("express", "Express"),
        ("fastify", "Fastify"),
        ("koa", "Koa"),
        ("@nestjs/core", "NestJS"),
        ("hono", "Hono"),
    ] {
        if deps.contains_key(name) {
            found = Some(("server", fw));
            break;
        }
    }
    if found.is_none() {
        for (name, fw) in [
            ("next", "Next.js"),
            ("vite", "Vite"),
            ("react", "React"),
            ("vue", "Vue"),
            ("svelte", "Svelte"),
        ] {
            if deps.contains_key(name) || dev.contains_key(name) {
                found = Some(("web", fw));
                break;
            }
        }
    }
    let (kind, framework) = found?;
    let scripts = obj(pkg.get("scripts")).unwrap_or(&empty);
    let (mut command, mut script) = (None, None);
    if let Some(s) = scripts.get("dev").and_then(Value::as_str) {
        (command, script) = (Some("npm run dev".to_string()), Some(s));
    } else if let Some(s) = scripts.get("start").and_then(Value::as_str) {
        (command, script) = (Some("npm start".to_string()), Some(s));
    }
    let mut port = None;
    if let Some(s) = script.filter(|s| !s.is_empty())
        && let Some(m) = PORT_FLAG.captures(s)
    {
        port = m[1].parse::<i64>().ok();
    }
    if port.is_none() {
        port = match framework {
            "Vite" => Some(5173),
            "Next.js" => Some(3000),
            _ => None,
        };
    }
    let lang = if is_file(&base.join("tsconfig.json")) {
        "typescript"
    } else {
        "javascript"
    };
    Some(unit(unit_name(d), kind, d, lang, framework, command, port))
}

fn py_module(rel: &str) -> String {
    let mut parts: Vec<&str> = rel[..rel.len() - ".py".len()].split('/').collect();
    if parts.last() == Some(&"__init__") {
        parts.pop();
    }
    parts.join(".")
}

/// 파이썬 `ast.parse`처럼 읽는다 — BOM·NUL은 문법 오류다
fn py_parse(text: &str) -> Option<python::PyFile> {
    if text.starts_with('\u{feff}') || text.contains('\0') {
        return None;
    }
    python::parse(text)
}

/// 맨 위 `ast.Assign` — (대상들, 값). 사슬 `a = b = v`는 대상 둘
fn py_assign(n: Node) -> Option<(Vec<Node>, Option<Node>)> {
    if n.kind() != "assignment" || n.child_by_field_name("type").is_some() {
        return None;
    }
    let mut targets = Vec::new();
    let mut cur = n;
    loop {
        if let Some(l) = cur.child_by_field_name("left") {
            targets.push(l);
        }
        match cur.child_by_field_name("right") {
            Some(r) if r.kind() == "assignment" && r.child_by_field_name("type").is_none() => {
                cur = r
            }
            r => return Some((targets, r)),
        }
    }
}

/// 사슬 대입의 안쪽 노드인가 — `ast`에는 따로 없다
fn chained(n: Node) -> bool {
    n.parent().is_some_and(|p| {
        p.kind() == "assignment"
            && p.child_by_field_name("type").is_none()
            && p.child_by_field_name("right") == Some(n)
    })
}

fn module_assigns(root: Node) -> Vec<(Vec<Node>, Option<Node>)> {
    named_children(root)
        .into_iter()
        .filter(|st| st.kind() == "expression_statement")
        .filter_map(|st| named_children(st).into_iter().next())
        .filter_map(py_assign)
        .collect()
}

fn py_unit(src_dir: &Path, d: &str, names: &HashSet<String>) -> Option<Value> {
    let base = sub(src_dir, d);
    let uv = if is_file(&base.join("uv.lock")) {
        "uv run "
    } else {
        ""
    };
    if names.contains("manage.py") {
        return Some(unit(
            unit_name(d),
            "server",
            d,
            "python",
            "Django",
            Some(format!("{uv}python manage.py runserver 8000")),
            Some(8000),
        ));
    }
    let mut files: Vec<String> = walk_files(&base)
        .into_iter()
        .filter(|p| p.ends_with(".py") && !is_test(p))
        .collect();
    files.sort();
    for rel in files {
        let Some(text) = text_of(&base.join(&rel)) else {
            continue;
        };
        let Some(pf) = py_parse(&text) else { continue };
        let src = &pf.src;
        for (targets, value) in module_assigns(pf.tree.root_node()) {
            let Some(value) = value.map(unparen).filter(|v| v.kind() == "call") else {
                continue;
            };
            let Some(f) = value.child_by_field_name("function").map(unparen) else {
                continue;
            };
            let kind = match f.kind() {
                "identifier" => Some(python::text(f, src).to_string()),
                "attribute" => f
                    .child_by_field_name("attribute")
                    .map(|a| python::text(a, src).to_string()),
                _ => None,
            };
            let var = targets
                .iter()
                .find(|t| t.kind() == "identifier")
                .map(|t| python::text(*t, src).to_string());
            let (Some(var), Some(kind)) = (var, kind) else {
                continue;
            };
            let m = py_module(&rel);
            let (cmd, port, k) = match kind.as_str() {
                "FastAPI" => (
                    format!("uvicorn {m}:{var} --port 8000"),
                    Some(8000),
                    "server",
                ),
                "Flask" => (
                    format!("flask --app {m} run --port 5000"),
                    Some(5000),
                    "server",
                ),
                "Celery" => (format!("celery -A {m} worker"), None, "job"),
                _ => continue,
            };
            return Some(unit(
                unit_name(d),
                k,
                d,
                "python",
                &kind,
                Some(format!("{uv}{cmd}")),
                port,
            ));
        }
    }
    None
}

/// TOML의 표 이름 → 그 표의 키들(맨 단순 꼴만), 처음 본 차례
fn toml_tables(text: &str) -> Vec<(String, Vec<String>)> {
    let mut out: Vec<(String, Vec<String>)> = Vec::new();
    fn slot<'a>(out: &'a mut Vec<(String, Vec<String>)>, t: &str) -> &'a mut Vec<String> {
        let i = match out.iter().position(|(n, _)| n == t) {
            Some(i) => i,
            None => {
                out.push((t.to_string(), Vec::new()));
                out.len() - 1
            }
        };
        &mut out[i].1
    }
    let mut table = String::new();
    for raw in py_splitlines(text) {
        let line = strip(raw);
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some(m) = TOML_TABLE.captures(line) {
            table = strip(&m[1]).to_string();
            slot(&mut out, &table);
            continue;
        }
        if let Some(m) = TOML_KEY.captures(line) {
            slot(&mut out, &table).push(m[1].to_string());
        }
    }
    out
}

fn toml_package_name(text: &str) -> Option<String> {
    let mut cur = String::new();
    for raw in py_splitlines(text) {
        let line = strip(raw);
        if let Some(m) = TOML_TABLE.captures(line) {
            cur = strip(&m[1]).to_string();
            continue;
        }
        if cur == "package"
            && let Some(m) = TOML_NAME.captures(line)
        {
            return Some(m[1].to_string());
        }
    }
    None
}

fn rust_unit(src_dir: &Path, d: &str) -> Option<Value> {
    let text = text_of(&sub(src_dir, d).join("Cargo.toml"))?;
    let tables = toml_tables(&text);
    let get = |t: &str| -> Vec<String> {
        tables
            .iter()
            .find(|(n, _)| n == t)
            .map(|(_, k)| k.clone())
            .unwrap_or_default()
    };
    if !tables.iter().any(|(n, _)| n == "package") {
        return None; // 작업 공간 루트
    }
    let mut deps = get("dependencies");
    deps.extend(get("workspace.dependencies"));
    let framework = if deps.iter().any(|x| x == "axum") {
        "Axum"
    } else if deps.iter().any(|x| x == "actix-web") {
        "Actix"
    } else {
        return None;
    };
    let name = toml_package_name(&text).filter(|n| !n.is_empty());
    Some(unit(
        unit_name(d),
        "server",
        d,
        "rust",
        framework,
        name.map(|n| format!("cargo run -p {n}")),
        None,
    ))
}

/// SYNC-MS-026#infra.units
///
/// 실행 단위 — `package.json`(서버·화면) · 파이썬(Django·FastAPI·Flask·Celery) · `Cargo.toml`(Axum·
/// Actix). 깊이 3까지, `(dir, name)` 바이트 순.
pub fn units(src_dir: &Path) -> Vec<Value> {
    let mut by_dir: IndexMap<String, HashSet<String>> = IndexMap::new();
    for (d, name) in manifests(src_dir) {
        by_dir.entry(d).or_default().insert(name);
    }
    let mut dirs_sorted: Vec<&String> = by_dir.keys().collect();
    dirs_sorted.sort();
    let mut out = Vec::new();
    for d in dirs_sorted {
        let names = &by_dir[d];
        if names.contains("package.json")
            && let Some(u) = node_unit(src_dir, d)
        {
            out.push(u);
        }
        if ["pyproject.toml", "requirements.txt", "manage.py"]
            .iter()
            .any(|n| names.contains(*n))
            && let Some(u) = py_unit(src_dir, d, names)
        {
            out.push(u);
        }
        if names.contains("Cargo.toml")
            && let Some(u) = rust_unit(src_dir, d)
        {
            out.push(u);
        }
    }
    let key = |u: &Value| {
        (
            u["dir"].as_str().unwrap_or_default().to_string(),
            u["name"].as_str().unwrap_or_default().to_string(),
        )
    };
    out.sort_by_key(key);
    out
}

// ---------------------------------------------------------------- 함수의 패키지

type Env = HashMap<String, String>;
type FileEnv = (Env, HashMap<i64, Env>);

fn pkg_norm(spec: &str) -> Option<String> {
    if spec.starts_with('.') || spec.starts_with('/') || spec.starts_with("node:") {
        return None;
    }
    let parts: Vec<&str> = spec.split('/').collect();
    Some(if spec.starts_with('@') && parts.len() > 1 {
        parts[..2].join("/")
    } else {
        parts[0].to_string()
    })
}

/// 파이썬 `_py_root` — 속성·호출·첨자·await를 벗긴 뿌리 이름
fn py_root<'t>(mut n: Node<'t>) -> Node<'t> {
    loop {
        n = unparen(n);
        let next = match n.kind() {
            "attribute" => n.child_by_field_name("object"),
            "call" => n.child_by_field_name("function"),
            "subscript" => n.child_by_field_name("value"),
            "await" => named_children(n)
                .into_iter()
                .find(|c| c.kind() != "comment"),
            _ => None,
        };
        match next {
            Some(x) => n = x,
            None => return n,
        }
    }
}

/// `ast.Name`에 해당하는 식별자인가 — 속성 이름·키워드 인자 이름은 아니다
fn is_name(n: Node) -> bool {
    if n.kind() != "identifier" {
        return false;
    }
    match n.parent() {
        Some(p) if p.kind() == "attribute" => p.child_by_field_name("attribute") != Some(n),
        Some(p) if p.kind() == "keyword_argument" => p.child_by_field_name("name") != Some(n),
        _ => true,
    }
}

fn py_env(text: &str) -> Option<FileEnv> {
    let pf = py_parse(text)?;
    let src = &pf.src;
    let root = pf.tree.root_node();
    let mut table: Env = HashMap::new();
    for st in python::walk(root) {
        match st.kind() {
            "import_statement" => {
                for al in named_children(st) {
                    let (name, asname) = match al.kind() {
                        "dotted_name" => (python::dotted(al, src), None),
                        "aliased_import" => (
                            al.child_by_field_name("name")
                                .map(|x| python::dotted(x, src))
                                .unwrap_or_default(),
                            al.child_by_field_name("alias")
                                .map(|x| python::text(x, src).to_string()),
                        ),
                        _ => continue,
                    };
                    let top = name.split('.').next().unwrap_or("").to_string();
                    table.insert(asname.unwrap_or_else(|| top.clone()), top);
                }
            }
            "import_from_statement" => {
                let (level, module) = python::from_module(st, src);
                if module.is_empty() || level > 0 {
                    continue;
                }
                let top = module.split('.').next().unwrap_or("").to_string();
                let module_node = st.child_by_field_name("module_name");
                for al in named_children(st) {
                    if Some(al) == module_node {
                        continue;
                    }
                    let (name, asname) = match al.kind() {
                        "dotted_name" => (python::dotted(al, src), None),
                        "aliased_import" => (
                            al.child_by_field_name("name")
                                .map(|x| python::dotted(x, src))
                                .unwrap_or_default(),
                            al.child_by_field_name("alias")
                                .map(|x| python::text(x, src).to_string()),
                        ),
                        "wildcard_import" => ("*".to_string(), None),
                        _ => continue,
                    };
                    table.insert(asname.unwrap_or(name), top.clone());
                }
            }
            _ => {}
        }
    }
    let pkg_of_value = |v: Option<Node>| -> Option<String> {
        let r = py_root(v?);
        (r.kind() == "identifier")
            .then(|| table.get(python::text(r, src)).cloned())
            .flatten()
    };
    let pkg_of_ann = |ann: Option<Node>| -> Option<String> {
        python::walk(ann?)
            .into_iter()
            .filter(|n| is_name(*n))
            .find_map(|n| table.get(python::text(n, src)).cloned())
    };
    let mut module_vars: Env = HashMap::new();
    for (targets, value) in module_assigns(root) {
        if let Some(p) = pkg_of_value(value) {
            for t in targets {
                if t.kind() == "identifier" {
                    module_vars.insert(python::text(t, src).to_string(), p.clone());
                }
            }
        }
    }
    let self_attrs = |cls: Node| -> Env {
        let mut out = Env::new();
        let Some(body) = cls.child_by_field_name("body") else {
            return out;
        };
        for item in named_children(body) {
            let item = if item.kind() == "decorated_definition" {
                match item.child_by_field_name("definition") {
                    Some(d) => d,
                    None => continue,
                }
            } else {
                item
            };
            if item.kind() != "function_definition"
                || item
                    .child_by_field_name("name")
                    .map(|n| python::text(n, src))
                    != Some("__init__")
            {
                continue;
            }
            for st in walk_def(item) {
                if st.kind() != "assignment" || chained(st) {
                    continue;
                }
                let (target, p) = if st.child_by_field_name("type").is_some() {
                    (
                        st.child_by_field_name("left"),
                        pkg_of_ann(st.child_by_field_name("type"))
                            .or_else(|| pkg_of_value(st.child_by_field_name("right"))),
                    )
                } else {
                    let Some((targets, value)) = py_assign(st) else {
                        continue;
                    };
                    if targets.len() != 1 {
                        continue;
                    }
                    (Some(targets[0]), pkg_of_value(value))
                };
                let (Some(p), Some(target)) = (p, target) else {
                    continue;
                };
                if target.kind() == "attribute"
                    && let Some(o) = target.child_by_field_name("object")
                    && o.kind() == "identifier"
                    && python::text(o, src) == "self"
                    && let Some(a) = target.child_by_field_name("attribute")
                {
                    out.insert(format!("self.{}", python::text(a, src)), p);
                }
            }
        }
        out
    };
    let mut funcs: HashMap<i64, Env> = HashMap::new();
    struct Ctx<'a, 's> {
        src: &'s str,
        module_vars: &'a Env,
        pkg_of_value: &'a dyn Fn(Option<Node>) -> Option<String>,
        pkg_of_ann: &'a dyn Fn(Option<Node>) -> Option<String>,
        self_attrs: &'a dyn Fn(Node) -> Env,
    }
    fn param_name<'t>(p: Node<'t>) -> Option<Node<'t>> {
        let n = match p.kind() {
            "typed_parameter" => named_children(p).into_iter().next()?,
            "typed_default_parameter" => p.child_by_field_name("name")?,
            _ => return None,
        };
        match n.kind() {
            "identifier" => Some(n),
            "list_splat_pattern" | "dictionary_splat_pattern" => named_children(n)
                .into_iter()
                .find(|c| c.kind() == "identifier"),
            _ => None,
        }
    }
    fn visit(n: Node, inherited: &Env, cx: &Ctx, funcs: &mut HashMap<i64, Env>) {
        for child in named_children(n) {
            match child.kind() {
                "class_definition" => {
                    let mut inh = inherited.clone();
                    inh.extend((cx.self_attrs)(child));
                    visit(child, &inh, cx, funcs);
                }
                "function_definition" => {
                    let mut env = cx.module_vars.clone();
                    env.extend(inherited.iter().map(|(k, v)| (k.clone(), v.clone())));
                    if let Some(params) = child.child_by_field_name("parameters") {
                        for p in named_children(params) {
                            let Some(name) = param_name(p) else { continue };
                            if let Some(pkg) = (cx.pkg_of_ann)(p.child_by_field_name("type")) {
                                env.insert(python::text(name, cx.src).to_string(), pkg);
                            }
                        }
                    }
                    for st in walk_def(child) {
                        match st.kind() {
                            "assignment" if !chained(st) => {
                                if st.child_by_field_name("type").is_some() {
                                    let Some(t) = st.child_by_field_name("left") else {
                                        continue;
                                    };
                                    if t.kind() != "identifier" {
                                        continue;
                                    }
                                    let p = (cx.pkg_of_ann)(st.child_by_field_name("type"))
                                        .or_else(|| {
                                            (cx.pkg_of_value)(st.child_by_field_name("right"))
                                        });
                                    if let Some(p) = p {
                                        env.insert(python::text(t, cx.src).to_string(), p);
                                    }
                                } else if let Some((targets, value)) = py_assign(st)
                                    && let Some(p) = (cx.pkg_of_value)(value)
                                {
                                    for t in targets {
                                        if t.kind() == "identifier" {
                                            env.insert(
                                                python::text(t, cx.src).to_string(),
                                                p.clone(),
                                            );
                                        }
                                    }
                                }
                            }
                            "with_item" => {
                                let Some(v) = st.child_by_field_name("value") else {
                                    continue;
                                };
                                if v.kind() != "as_pattern" {
                                    continue;
                                }
                                let ctx_expr = named_children(v).into_iter().next();
                                let alias = v
                                    .child_by_field_name("alias")
                                    .and_then(|a| {
                                        if a.kind() == "as_pattern_target" {
                                            let k = named_children(a);
                                            (k.len() == 1).then(|| k[0])
                                        } else {
                                            Some(a)
                                        }
                                    })
                                    .filter(|a| a.kind() == "identifier");
                                if let Some(alias) = alias
                                    && let Some(p) = (cx.pkg_of_value)(ctx_expr)
                                {
                                    env.insert(python::text(alias, cx.src).to_string(), p);
                                }
                            }
                            _ => {}
                        }
                    }
                    let mut lines = vec![child.start_position().row as i64 + 1];
                    if let Some(d) = child
                        .parent()
                        .filter(|p| p.kind() == "decorated_definition")
                        .and_then(|p| {
                            named_children(p)
                                .into_iter()
                                .find(|c| c.kind() == "decorator")
                        })
                    {
                        lines.push(d.start_position().row as i64 + 1);
                    }
                    for ln in lines {
                        funcs.entry(ln).or_insert_with(|| env.clone());
                    }
                    visit(child, inherited, cx, funcs);
                }
                _ => visit(child, inherited, cx, funcs),
            }
        }
    }
    let cx = Ctx {
        src,
        module_vars: &module_vars,
        pkg_of_value: &pkg_of_value,
        pkg_of_ann: &pkg_of_ann,
        self_attrs: &self_attrs,
    };
    visit(root, &Env::new(), &cx, &mut funcs);
    Some((table, funcs))
}

/// 정의를 너비 우선으로 — 데코레이터까지(파이썬 `ast.walk(FunctionDef)`)
fn walk_def(fn_node: Node) -> Vec<Node> {
    let mut nodes = python::walk(fn_node);
    if let Some(p) = fn_node
        .parent()
        .filter(|p| p.kind() == "decorated_definition")
    {
        for d in named_children(p)
            .into_iter()
            .filter(|c| c.kind() == "decorator")
        {
            nodes.extend(python::walk(d));
        }
    }
    nodes
}

fn ts_root_name(n: Node, src: &[u8]) -> Option<String> {
    let mut n = Some(n);
    while let Some(cur) = n {
        match cur.kind() {
            "identifier" => return Some(text(cur, src)),
            "member_expression" => n = cur.child_by_field_name("object"),
            "call_expression" => n = cur.child_by_field_name("function"),
            "new_expression" => n = cur.child_by_field_name("constructor"),
            "await_expression" | "parenthesized_expression" | "non_null_expression" => {
                n = named_children(cur).into_iter().next()
            }
            _ => return None,
        }
    }
    None
}

fn ts_string(n: Option<Node>, src: &[u8]) -> Option<String> {
    let n = n.filter(|n| n.kind() == "string")?;
    Some(
        named_children(n)
            .into_iter()
            .filter(|c| c.kind() == "string_fragment")
            .map(|c| text(c, src))
            .collect(),
    )
}

fn type_hit(ty: Node, src: &[u8], table: &Env) -> Option<String> {
    walk(ty)
        .into_iter()
        .filter(|c| c.kind() == "type_identifier")
        .map(|c| text(c, src))
        .find(|t| table.contains_key(t))
}

fn ts_env(file: &str, src: &[u8]) -> FileEnv {
    let Some(tree) = ts_parse(file, src) else {
        return (Env::new(), HashMap::new());
    };
    let root = tree.root_node();
    let mut table: Env = HashMap::new();
    for st in children(root) {
        if st.kind() != "import_statement" {
            continue;
        }
        let Some(spec) = ts_string(st.child_by_field_name("source"), src).filter(|s| !s.is_empty())
        else {
            continue;
        };
        let Some(pkg) = pkg_norm(&spec).filter(|p| !p.is_empty()) else {
            continue;
        };
        for n in walk(st) {
            match n.kind() {
                "import_specifier" => {
                    if let Some(a) = n
                        .child_by_field_name("alias")
                        .or_else(|| n.child_by_field_name("name"))
                    {
                        table.insert(text(a, src), pkg.clone());
                    }
                }
                "namespace_import" | "import_clause" => {
                    if let Some(i) = named_children(n)
                        .into_iter()
                        .find(|c| c.kind() == "identifier")
                    {
                        table.insert(text(i, src), pkg.clone());
                    }
                }
                _ => {}
            }
        }
    }
    for n in walk(root) {
        if n.kind() != "variable_declarator" {
            continue;
        }
        let (Some(val), Some(name)) = (
            n.child_by_field_name("value"),
            n.child_by_field_name("name"),
        ) else {
            continue;
        };
        if name.kind() != "identifier" || val.kind() != "call_expression" {
            continue;
        }
        if val
            .child_by_field_name("function")
            .map(|f| text(f, src))
            .as_deref()
            == Some("require")
        {
            let arg = val
                .child_by_field_name("arguments")
                .and_then(|a| named_children(a).into_iter().next());
            if let Some(spec) = ts_string(arg, src).filter(|s| !s.is_empty())
                && let Some(pkg) = pkg_norm(&spec).filter(|p| !p.is_empty())
            {
                table.insert(text(name, src), pkg);
            }
        }
    }
    let var_pkgs = |scope: Node| -> Env {
        let mut env = Env::new();
        for n in walk(scope) {
            match n.kind() {
                "variable_declarator" => {
                    let (Some(name), Some(val)) = (
                        n.child_by_field_name("name"),
                        n.child_by_field_name("value"),
                    ) else {
                        continue;
                    };
                    if name.kind() != "identifier" {
                        continue;
                    }
                    if let Some(r) = ts_root_name(val, src)
                        && let Some(p) = table.get(&r)
                    {
                        env.insert(text(name, src), p.clone());
                    }
                }
                "required_parameter" | "optional_parameter" => {
                    let (Some(pat), Some(ty)) = (
                        n.child_by_field_name("pattern"),
                        n.child_by_field_name("type"),
                    ) else {
                        continue;
                    };
                    if pat.kind() != "identifier" {
                        continue;
                    }
                    if let Some(hit) = type_hit(ty, src, &table) {
                        env.insert(text(pat, src), table[&hit].clone());
                    }
                }
                _ => {}
            }
        }
        env
    };
    let mut module_env = Env::new();
    for st in children(root) {
        let target = if st.kind() == "export_statement" {
            named_children(st).into_iter().next().unwrap_or(st)
        } else {
            st
        };
        if matches!(
            target.kind(),
            "lexical_declaration" | "variable_declaration"
        ) {
            module_env.extend(var_pkgs(target));
        }
    }
    let mut funcs = HashMap::new();
    for (ln, node) in ts_defs(root) {
        let mut env = module_env.clone();
        env.extend(var_pkgs(node));
        funcs.insert(ln, env);
    }
    (table, funcs)
}

fn rs_env(src: &[u8]) -> FileEnv {
    let Some(tree) = rs_parse(src) else {
        return (Env::new(), HashMap::new());
    };
    let root = tree.root_node();
    let mut table: Env = HashMap::new();
    fn first_seg(n: Option<Node>, src: &[u8]) -> Option<String> {
        n.map(|p| text(p, src).split("::").next().unwrap_or("").to_string())
    }
    fn use_names(n: Node, crate_: Option<&str>, src: &[u8], table: &mut Env) {
        match n.kind() {
            "use_as_clause" => {
                let first = first_seg(n.child_by_field_name("path"), src);
                let c = crate_
                    .map(str::to_string)
                    .or(first)
                    .filter(|c| !c.is_empty());
                if let (Some(alias), Some(c)) = (n.child_by_field_name("alias"), &c) {
                    table.insert(text(alias, src), c.clone());
                }
                if let Some(c) = c {
                    table.insert(c.clone(), c);
                }
            }
            "scoped_use_list" => {
                let c = crate_
                    .map(str::to_string)
                    .or_else(|| first_seg(n.child_by_field_name("path"), src))
                    .filter(|c| !c.is_empty());
                if let Some(c) = &c {
                    table.insert(c.clone(), c.clone());
                }
                if let Some(lst) = n.child_by_field_name("list") {
                    for ch in named_children(lst) {
                        use_names(ch, c.as_deref(), src, table);
                    }
                }
            }
            "use_list" => {
                for ch in named_children(n) {
                    use_names(ch, crate_, src, table);
                }
            }
            "scoped_identifier" | "identifier" => {
                let t = text(n, src);
                let parts: Vec<&str> = t.split("::").collect();
                let c = match crate_ {
                    Some(c) if !c.is_empty() => c.to_string(),
                    _ => parts[0].to_string(),
                };
                if matches!(c.as_str(), "crate" | "self" | "super") {
                    return;
                }
                table.insert(parts[parts.len() - 1].to_string(), c.clone());
                table.insert(c.clone(), c);
            }
            _ => {}
        }
    }
    for st in children(root) {
        if st.kind() == "use_declaration"
            && let Some(arg) = st.child_by_field_name("argument")
        {
            use_names(arg, None, src, &mut table);
        }
    }
    fn root_name(n: Node, src: &[u8]) -> Option<String> {
        let mut n = Some(n);
        while let Some(cur) = n {
            match cur.kind() {
                "identifier" => return Some(text(cur, src)),
                "scoped_identifier" => {
                    return Some(text(cur, src).split("::").next().unwrap_or("").to_string());
                }
                "field_expression" => n = cur.child_by_field_name("value"),
                "call_expression" | "generic_function" => n = cur.child_by_field_name("function"),
                "await_expression"
                | "try_expression"
                | "reference_expression"
                | "parenthesized_expression" => n = named_children(cur).into_iter().next(),
                _ => return None,
            }
        }
        None
    }
    let mut funcs = HashMap::new();
    for (ln, f) in rs_defs(root) {
        let mut env = Env::new();
        if let Some(params) = f.child_by_field_name("parameters") {
            for p in named_children(params) {
                if p.kind() != "parameter" {
                    continue;
                }
                let (Some(pat), Some(ty)) = (
                    p.child_by_field_name("pattern"),
                    p.child_by_field_name("type"),
                ) else {
                    continue;
                };
                if let Some(hit) = type_hit(ty, src, &table) {
                    env.insert(text(pat, src), table[&hit].clone());
                }
            }
        }
        if let Some(body) = f.child_by_field_name("body") {
            for n in walk(body) {
                if n.kind() != "let_declaration" {
                    continue;
                }
                let (Some(pat), Some(val)) = (
                    n.child_by_field_name("pattern"),
                    n.child_by_field_name("value"),
                ) else {
                    continue;
                };
                if pat.kind() != "identifier" {
                    continue;
                }
                if let Some(r) = root_name(val, src)
                    && let Some(p) = table.get(&r)
                {
                    env.insert(text(pat, src), p.clone());
                }
            }
        }
        funcs.insert(ln, env);
    }
    (table, funcs)
}

fn label_root(label: &str, lang: &str) -> Option<String> {
    let root = RE.ident.find(label)?.as_str().to_string();
    if lang == "py"
        && root == "self"
        && label.starts_with("self.")
        && let Some(m2) = RE.ident.find(&label[5..])
    {
        return Some(format!("self.{}", m2.as_str()));
    }
    Some(root)
}

// ---------------------------------------------------------------- 설정 읽기

/// 깊이 3까지 의존성 목록 — [(이름, 파일)], 걷는 차례
fn deps(src_dir: &Path) -> Vec<(String, String)> {
    fn visit(path: &Path, rel: &str, depth: usize, out: &mut Vec<(String, String)>) {
        for (name, full, is_dir) in entries(path) {
            let r = if rel.is_empty() {
                name.clone()
            } else {
                format!("{rel}/{name}")
            };
            if is_dir {
                if depth < 3
                    && !name.starts_with('.')
                    && !SKIP.contains(&name.as_str())
                    && !DEP_DIR_SKIP.is_match(&name)
                {
                    visit(&full, &r, depth + 1, out);
                }
                continue;
            }
            let mut names: Vec<String> = Vec::new();
            if name == "package.json" {
                let pkg: Option<Value> = match text_of(&full) {
                    Some(t) => match serde_json::from_str(&t) {
                        Ok(v) => Some(v),
                        Err(_) => continue,
                    },
                    None => None,
                };
                let ds: Vec<String> = pkg
                    .as_ref()
                    .and_then(|p| p.get("dependencies"))
                    .and_then(Value::as_object)
                    .map(|m| m.keys().cloned().collect())
                    .unwrap_or_default();
                if ds.iter().any(|d| RE.front_only.is_match(d))
                    && !ds.iter().any(|d| RE.server_deps.is_match(d))
                {
                    continue;
                }
                names = ds;
            } else if name == "Cargo.toml" {
                let t = text_of(&full).unwrap_or_default();
                for (table, keys) in toml_tables(&t) {
                    if table.ends_with("dependencies") {
                        names.extend(keys);
                    }
                }
            } else if name == "pyproject.toml" {
                let t = text_of(&full).unwrap_or_default();
                if let Some(m) = PYPROJECT_DEPS.captures(&t) {
                    for q in QUOTED.captures_iter(&m[1]) {
                        if let Some(nm) = REQ_NAME_SP.captures(&q[1]) {
                            names.push(nm[1].to_string());
                        }
                    }
                }
            } else if REQ_FILE.is_match(&name) {
                let t = text_of(&full).unwrap_or_default();
                for line in py_splitlines(&t) {
                    let line = strip(line);
                    if line.is_empty() || line.starts_with('#') || line.starts_with('-') {
                        continue;
                    }
                    if let Some(nm) = REQ_NAME.captures(line) {
                        names.push(nm[1].to_string());
                    }
                }
            } else {
                continue;
            }
            let mut seen = HashSet::new();
            for n in names {
                if seen.insert(n.clone()) {
                    out.push((n, r.clone()));
                }
            }
        }
    }
    let mut out = Vec::new();
    visit(src_dir, "", 0, &mut out);
    out
}

struct Service {
    name: String,
    image: Option<String>,
    ports: Vec<i64>,
}

/// docker-compose의 services만 — 이름·image·이 PC에 연 포트 (view_arc parseCompose)
fn parse_compose(text: &str) -> Vec<Service> {
    let mut out: Vec<Service> = Vec::new();
    let mut in_services = false;
    let mut svc_indent: i64 = -1;
    let mut cur = false;
    let mut in_ports = false;
    for raw in LINE_SPLIT.split(text) {
        let line = COMMENT_TAIL.replace(raw, "");
        if strip(&line).is_empty() {
            continue;
        }
        let indent = (plen(&line) - plen(lstrip(&line))) as i64;
        let t = strip(&line);
        if indent == 0 {
            in_services = t == "services:";
            cur = false;
            continue;
        }
        if !in_services {
            continue;
        }
        if svc_indent < 0 {
            svc_indent = indent;
        }
        if indent == svc_indent && SVC_LINE.is_match(t) {
            out.push(Service {
                name: t[..t.len() - 1].to_string(),
                image: None,
                ports: Vec::new(),
            });
            cur = true;
            in_ports = false;
            continue;
        }
        if !cur {
            continue;
        }
        let svc = out.last_mut().expect("서비스");
        if indent == svc_indent + 2
            || (indent > svc_indent && KEY_LINE.is_match(t) && !t.starts_with('-'))
        {
            in_ports = PORTS_LINE.is_match(t);
        }
        if let Some(m) = IMAGE_LINE.captures(t) {
            svc.image = Some(m[1].to_string());
        }
        if in_ports && t.starts_with('-') {
            let spec = QUOTE_END
                .replace(&PORT_DASH.replace(t, ""), "")
                .into_owned();
            let parts: Vec<&str> = spec.split(':').collect();
            let p = if parts.len() >= 2 {
                parts[parts.len() - 2]
            } else {
                parts[0]
            };
            if let Some(port) = py_int(p) {
                svc.ports.push(port);
            }
        }
    }
    out
}

fn config_entries(file: &str, text: &str) -> Vec<(String, String)> {
    let mut out = Vec::new();
    if YAML_FILE.is_match(file) {
        let mut stack: Vec<(usize, String)> = Vec::new();
        for raw in LINE_SPLIT.split(text) {
            let Some(m) = YAML_LINE.captures(raw) else {
                continue;
            };
            if strip(raw).starts_with('#') {
                continue;
            }
            let indent = m[1].len();
            while stack.last().is_some_and(|(i, _)| *i >= indent) {
                stack.pop();
            }
            let mut key: Vec<&str> = stack.iter().map(|(_, k)| k.as_str()).collect();
            key.push(&m[2]);
            let key = key.join(".");
            if !m[3].is_empty() {
                out.push((key, m[3].to_string()));
            } else {
                stack.push((indent, m[2].to_string()));
            }
        }
        return out;
    }
    for raw in LINE_SPLIT.split(text) {
        if let Some(m) = ENV_LINE.captures(raw)
            && !strip(raw).starts_with('#')
        {
            out.push((m[1].to_string(), m[2].to_string()));
        }
    }
    out
}

fn env_pairs(text: &str) -> HashMap<String, String> {
    config_entries(".env", text)
        .into_iter()
        .map(|(k, v)| (k, QUOTE_EDGES.replace_all(&v, "").into_owned()))
        .collect()
}

fn compose_vars(env: &HashMap<String, String>, text: &str) -> String {
    let t = BRACED.replace_all(text, |c: &regex::Captures| {
        match env.get(&c[1]).filter(|v| !v.is_empty()) {
            Some(v) => v.clone(),
            None => c.get(2).map(|m| m.as_str().to_string()).unwrap_or_default(),
        }
    });
    DOLLAR
        .replace_all(&t, |c: &regex::Captures| {
            env.get(&c[1]).cloned().unwrap_or_else(|| c[0].to_string())
        })
        .into_owned()
}

fn defaults(text: &str) -> String {
    DEFAULTS.replace_all(text, "$1").into_owned()
}

/// 설정 파일 — (경로, 저장소 상대 경로, 순위)
fn config_files(src_dir: &Path) -> Vec<(PathBuf, String, i64)> {
    let mut out = Vec::new();
    let mut ds: Vec<(PathBuf, String)> = vec![(src_dir.to_path_buf(), String::new())];
    ds.extend(dirs(src_dir).into_iter().map(|n| (src_dir.join(&n), n)));
    for (d, rel) in &ds {
        let join = |n: &str| {
            if rel.is_empty() {
                n.to_string()
            } else {
                format!("{rel}/{n}")
            }
        };
        for n in [".env", ".env.local", ".env.development"] {
            if is_file(&d.join(n)) {
                out.push((d.join(n), join(n), 4));
            }
        }
        for n in [".env.example", ".env.sample", ".env.template"] {
            if is_file(&d.join(n)) {
                out.push((d.join(n), join(n), 1));
            }
        }
    }
    fn visit(path: &Path, rel: &str, depth: usize, out: &mut Vec<(PathBuf, String, i64)>) {
        if depth > 7 {
            return;
        }
        for (name, full, is_dir) in entries(path) {
            if name.starts_with('.')
                || SKIP.contains(&name.as_str())
                || CONFIG_SKIP_MORE.contains(&name.as_str())
            {
                continue;
            }
            let r = if rel.is_empty() {
                name.clone()
            } else {
                format!("{rel}/{name}")
            };
            if is_dir {
                visit(&full, &r, depth + 1, out);
            } else if CONFIG_PY.is_match(&name)
                || (APP_YAML.is_match(&name) && !TEST_DIR.is_match(&r))
            {
                out.push((full, r, 3));
            }
        }
    }
    visit(src_dir, "", 0, &mut out);
    out
}

/// (호스트, 포트, 표시) — sqlite는 파일 이름
fn host_of(scheme: &str, rest: &str) -> Option<(String, Option<i64>, String)> {
    if scheme.starts_with("sqlite") {
        let file = SLASHES.replace(rest, "");
        let file = file.split('?').next().unwrap_or("");
        let base = file.rsplit('/').next().unwrap_or("");
        return Some((
            "file".into(),
            None,
            if file.is_empty() {
                "메모리".into()
            } else {
                base.to_string()
            },
        ));
    }
    let first = AUTH_SPLIT.split(rest).next().unwrap_or("");
    let authority = first.rsplit('@').next().unwrap_or("");
    let m = HOST_PORT.captures(authority.split(',').next().unwrap_or(""))?;
    let host = m.get(1).map(|x| x.as_str()).unwrap_or("");
    if host.is_empty() || host.contains('{') || host.contains('$') || RE.placeholder.is_match(host)
    {
        return None;
    }
    let port = m.get(2).and_then(|p| p.as_str().parse::<i64>().ok());
    let label = match port {
        Some(p) if p != 0 => format!("{host}:{p}"),
        _ => host.to_string(),
    };
    Some((host.to_string(), port, label))
}

/// ORM 설정 파일 — (경로, 저장소 상대 경로)
fn orm_files(src_dir: &Path) -> Vec<(PathBuf, String)> {
    let mut ds: Vec<(PathBuf, String)> = vec![(src_dir.to_path_buf(), String::new())];
    let subs: Vec<(PathBuf, String)> = dirs(src_dir)
        .into_iter()
        .map(|n| (src_dir.join(&n), n))
        .collect();
    ds.extend(subs.iter().cloned());
    for (s, rel) in &subs {
        ds.extend(
            dirs(s)
                .into_iter()
                .map(|n| (s.join(&n), format!("{rel}/{n}"))),
        );
    }
    let mut out: Vec<(PathBuf, String)> = Vec::new();
    for (d, rel) in &ds {
        for n in [
            "schema.prisma",
            "prisma/schema.prisma",
            "drizzle.config.ts",
            "drizzle.config.js",
            "drizzle.config.mjs",
        ] {
            let p = d.join(n);
            if is_file(&p) && !out.iter().any(|(q, _)| *q == p) {
                let r = if rel.is_empty() {
                    n.to_string()
                } else {
                    format!("{rel}/{n}")
                };
                out.push((p, r));
            }
        }
    }
    out
}

fn better(a: &str, b: &str) -> String {
    let score = |s: &str| if s == "DB" { 0 } else { plen(s) };
    if score(b) > score(a) {
        b.into()
    } else {
        a.into()
    }
}

// ---------------------------------------------------------------- 묶기

struct Found {
    kind: String,
    name: String,
    where_: Option<String>,
    host: Option<String>,
    evidence: Vec<String>,
    protocol: Option<String>,
    rank: i64,
}

#[derive(Default)]
struct Book {
    found: IndexMap<String, Found>,
    seen_at: IndexMap<String, Vec<String>>,
}

impl Book {
    fn at(&mut self, fid: &str, file: &str) {
        let lst = self.seen_at.entry(fid.to_string()).or_default();
        if !lst.iter().any(|x| x == file) {
            lst.push(file.to_string());
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn add(
        &mut self,
        fid: &str,
        kind: &str,
        name: &str,
        where_: Option<&str>,
        host: Option<&str>,
        evidence: &[String],
        protocol: Option<&str>,
        rank: i64,
    ) {
        let Some(cur) = self.found.get_mut(fid) else {
            self.found.insert(
                fid.to_string(),
                Found {
                    kind: kind.into(),
                    name: name.into(),
                    where_: where_.map(Into::into),
                    host: host.map(Into::into),
                    evidence: evidence.to_vec(),
                    protocol: protocol.map(Into::into),
                    rank,
                },
            );
            return;
        };
        for e in evidence {
            if !cur.evidence.contains(e) {
                cur.evidence.push(e.clone());
            }
        }
        if rank > cur.rank {
            if let Some(w) = where_ {
                cur.where_ = Some(w.into());
            }
            if let Some(h) = host {
                cur.host = Some(h.into());
            }
            cur.rank = rank;
        } else if cur.host.is_none()
            && let Some(h) = host
        {
            cur.host = Some(h.into()); // 주소가 비어 있으면 순위가 낮아도 채운다
        }
        cur.name = better(&cur.name, name);
        if cur.protocol.is_none() {
            cur.protocol = protocol.map(Into::into);
        }
    }
}

fn lang_of(file: &str) -> Option<&'static str> {
    if file.ends_with(".py") {
        Some("py")
    } else if [".ts", ".tsx", ".js", ".jsx", ".mjs"]
        .iter()
        .any(|e| file.ends_with(e))
    {
        Some("ts")
    } else if file.ends_with(".rs") {
        Some("rs")
    } else {
        None
    }
}

fn s(v: &Value, k: &str) -> String {
    v.get(k)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string()
}

/// SYNC-MS-026#infra.infra
///
/// 장비(코드 호출·의존성·compose·설정 주소·ORM)와 연결 — `graph["infra"] = {nodes, links}`.
/// 호출 순서 중 장비로 가는 호출에 `infra`를 단다. 주소는 호스트·포트만.
pub fn infra(src_dir: &Path, graph: &mut Value, idents: &HashMap<String, Vec<Option<String>>>) {
    let unit_list: Vec<Value> = graph
        .get("units")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let web_dirs: Vec<String> = unit_list
        .iter()
        .filter(|u| u.get("kind").and_then(Value::as_str) == Some("web"))
        .map(|u| s(u, "dir"))
        .collect();
    let mut book = Book::default();

    // 1·2. 코드 — 호출 순서에 장비를 단다
    let mut envs: HashMap<String, FileEnv> = HashMap::new();
    let mut files_of: IndexMap<&'static str, Vec<String>> = IndexMap::new();
    let mut libs_of: IndexMap<&'static str, Vec<String>> = IndexMap::new();
    if let Some(funcs) = graph.get_mut("functions").and_then(Value::as_array_mut) {
        for f in funcs.iter_mut() {
            let file = s(f, "file");
            let Some(lang) = lang_of(&file) else { continue };
            if RE.not_app.is_match(&file) || is_front(&file, &web_dirs) {
                continue;
            }
            if !envs.contains_key(&file) {
                let env = read(src_dir, &file)
                    .and_then(|src| match lang {
                        "py" => py_env(std::str::from_utf8(&src).ok()?),
                        "ts" => Some(ts_env(&file, &src)),
                        _ => Some(rs_env(&src)),
                    })
                    .unwrap_or_default();
                envs.insert(file.clone(), env);
            }
            let (table, fenv) = &envs[&file];
            let empty = Env::new();
            let env = fenv.get(&f["line"].as_i64().unwrap_or(0)).unwrap_or(&empty);
            let key = s(f, "key");
            let ids = idents.get(&key).cloned().unwrap_or_default();
            let Some(steps) = f.get_mut("steps").and_then(Value::as_array_mut) else {
                continue;
            };
            for (i, st) in steps.iter_mut().enumerate() {
                if st["k"] != "call" || st.get("to").is_some() {
                    continue;
                }
                let Some(root) = label_root(st["label"].as_str().unwrap_or_default(), lang) else {
                    continue;
                };
                let mut pkg = env.get(&root).or_else(|| table.get(&root)).cloned();
                if pkg.is_none() && lang == "ts" && root == "fetch" {
                    pkg = Some("fetch".into());
                }
                let Some(pkg) = pkg else { continue };
                let Some(li) = lib_of(&pkg) else { continue };
                let Some(Some(ident)) = ids.get(i) else {
                    continue;
                };
                if !RE.libs_io[li].is_match(ident) {
                    continue;
                }
                let lib = LIBS[li];
                if let Some(o) = st.as_object_mut() {
                    o.insert("infra".into(), format!("infra:{}", lib.1).into());
                }
                let lst = libs_of.entry(lib.1).or_default();
                if !lst.contains(&pkg) {
                    lst.push(pkg.clone());
                }
                let fl = files_of.entry(lib.1).or_default();
                if !fl.contains(&file) {
                    fl.push(file.clone());
                }
            }
        }
    }
    for (fid, fl) in &files_of {
        let lib = LIBS.iter().find(|l| l.1 == *fid).expect("LIBS");
        let more = if fl.len() > 1 {
            format!(" 외 {}개 파일", fl.len() - 1)
        } else {
            String::new()
        };
        let joined = libs_of.get(fid).map(|v| v.join(", ")).unwrap_or_default();
        let ev = format!(
            "코드: {} — {}{more}",
            if joined.is_empty() {
                lib.3.to_string()
            } else {
                joined
            },
            fl[0]
        );
        let where_ = (lib.2 == "api").then_some("external");
        book.add(fid, lib.2, lib.3, where_, None, &[ev], Some(lib.5), 1);
        for x in fl {
            book.at(fid, x);
        }
    }

    // 3. 의존성
    for (dep, dfile) in deps(src_dir) {
        let Some(i) = RE.deps.iter().position(|r| r.is_match(&dep)) else {
            continue;
        };
        let (_, fid, kind, name, protocol) = DEPS[i];
        let where_ = (kind == "api" || fid == "supabase").then_some("external");
        book.add(
            fid,
            kind,
            name,
            where_,
            None,
            &[format!("의존성: {dep} — {dfile}")],
            Some(protocol),
            1,
        );
        book.at(fid, &dfile);
    }

    // 4. docker-compose
    let mut compose_hosts: HashMap<String, String> = HashMap::new();
    let mut published: HashMap<i64, String> = HashMap::new();
    let mut ds: Vec<(PathBuf, String)> = vec![(src_dir.to_path_buf(), String::new())];
    ds.extend(dirs(src_dir).into_iter().map(|n| (src_dir.join(&n), n)));
    for (d, rel) in &ds {
        for n in COMPOSE {
            let p = d.join(n);
            if !is_file(&p) {
                continue;
            }
            let t = text_of(&p).unwrap_or_default();
            let env = text_of(&d.join(".env"))
                .map(|e| env_pairs(&e))
                .unwrap_or_default();
            for svc in parse_compose(&compose_vars(&env, &t)) {
                let image = svc.image.clone().unwrap_or_default();
                let Some(i) = RE.images.iter().position(|r| r.is_match(&image)) else {
                    continue;
                };
                let (_, fid, kind, name) = IMAGES[i];
                compose_hosts.insert(svc.name.clone(), fid.to_string());
                for port in &svc.ports {
                    published.insert(*port, fid.to_string());
                }
                let ports = if svc.ports.is_empty() {
                    String::new()
                } else {
                    let ps: Vec<String> = svc.ports.iter().map(i64::to_string).collect();
                    format!(", 포트 {}", ps.join(", "))
                };
                let r = if rel.is_empty() {
                    n.to_string()
                } else {
                    format!("{rel}/{n}")
                };
                let ev = format!("docker-compose: {} ({image}{ports}) — {r}", svc.name);
                book.add(fid, kind, name, Some("container"), None, &[ev], None, 2);
            }
        }
    }

    // 5. 설정 주소
    let where_of = |scheme: &str, host: &str, port: Option<i64>| -> &'static str {
        if scheme.starts_with("sqlite") {
            return "local";
        }
        let local = LOCAL_HOSTS.contains(&host);
        if compose_hosts.contains_key(host)
            || (local && port.is_some_and(|p| p != 0 && published.contains_key(&p)))
        {
            return "container";
        }
        if local { "local" } else { "external" }
    };
    let from_url = |book: &mut Book, key: &str, scheme: &str, rest: &str, rel: &str, rank: i64| {
        let parsed = host_of(scheme, rest);
        let mut hit = RE
            .schemes
            .iter()
            .position(|r| r.is_match(scheme))
            .map(|i| SCHEMES[i]);
        if hit.is_none() && HTTPS.is_match(scheme) {
            hit = RE
                .http_keys
                .iter()
                .position(|r| r.is_match(key))
                .map(|i| HTTP_KEYS[i]);
        }
        let (Some((_, fid, kind, name)), Some((host, port, label))) = (hit, parsed) else {
            return;
        };
        let sep = if key.is_empty() {
            String::new()
        } else {
            format!(" {key}")
        };
        let ev = format!("설정: {rel}{sep} → {label}");
        book.add(
            fid,
            kind,
            name,
            Some(where_of(scheme, &host, port)),
            Some(&label),
            &[ev],
            None,
            rank,
        );
        book.at(fid, rel);
    };
    for (path, rel, rank) in config_files(src_dir) {
        let Some(raw) = text_of(&path) else { continue };
        let t = defaults(&raw);
        if CONFIG_FILE.is_match(&rel) {
            let fname = rel.rsplit('/').next().unwrap_or("");
            let entries = config_entries(fname, &t);
            let by_key: HashMap<String, String> = entries
                .iter()
                .map(|(k, v)| (k.to_lowercase(), v.clone()))
                .collect();
            for (key, value) in &entries {
                if let Some(u) = URL_VALUE.captures(value) {
                    from_url(&mut book, key, &u[1].to_lowercase(), &u[2], &rel, rank);
                    continue;
                }
                let Some(hk) = HOST_KEY.captures(key) else {
                    continue;
                };
                let g1 = hk.get(1).map(|x| x.as_str()).unwrap_or("");
                let hit = RE
                    .host_keys
                    .iter()
                    .position(|r| r.is_match(g1))
                    .map(|i| HOST_KEYS[i]);
                let host = strip(&QUOTE_EDGES.replace_all(value, "")).to_string();
                let Some((_, fid, kind, name)) = hit else {
                    continue;
                };
                if host.is_empty() || HOST_BAD.is_match(&host) || RE.placeholder.is_match(&host) {
                    continue;
                }
                let port_key = format!("{g1}{}", HOST_TAIL.replace(&key[g1.len()..], "port"));
                let port = by_key
                    .get(&port_key.to_lowercase())
                    .map(|p| strip(p))
                    .filter(|p| DIGITS.is_match(p))
                    .and_then(|p| {
                        p.chars().try_fold(0i64, |acc, c| {
                            acc.checked_mul(10)?
                                .checked_add(i64::from(decimal_value(c)?))
                        })
                    });
                let label = match port {
                    Some(p) if p != 0 => format!("{host}:{p}"),
                    _ => host.clone(),
                };
                let ev = format!("설정: {rel} {key} → {label}");
                book.add(
                    fid,
                    kind,
                    name,
                    Some(where_of("", &host, port)),
                    Some(&label),
                    &[ev],
                    None,
                    rank,
                );
                book.at(fid, &rel);
            }
        } else {
            for m in URL_ANY.captures_iter(&t) {
                let key = m.get(1).map(|x| x.as_str()).unwrap_or("");
                from_url(&mut book, key, &m[2].to_lowercase(), &m[3], &rel, rank);
            }
        }
    }

    // 6. ORM
    let orm_name = |k: &str| -> Option<&'static str> {
        Some(match k {
            "postgresql" | "postgres" => "PostgreSQL",
            "mysql" => "MySQL",
            "sqlite" => "SQLite",
            "mongodb" => "MongoDB",
            "sqlserver" => "SQL Server",
            "cockroachdb" => "CockroachDB",
            _ => return None,
        })
    };
    for (path, rel) in orm_files(src_dir) {
        let t = text_of(&path).unwrap_or_default();
        // view_arc: text.slice(text.indexOf('datasource')) — 없으면 마지막 한 글자
        let hay = match t.find("datasource") {
            Some(i) => &t[i..],
            None => t.char_indices().last().map_or("", |(i, _)| &t[i..]),
        };
        let mut kind = PRISMA_PROVIDER.captures(hay).map(|m| m[1].to_string());
        if kind.is_none() {
            kind = DIALECT.captures(&t).map(|m| m[1].to_string());
        }
        let kind = kind.unwrap_or_default();
        if let Some(name) = orm_name(&kind) {
            let fid = if kind == "mongodb" { "mongo" } else { "db" };
            book.add(
                fid,
                "db",
                name,
                None,
                None,
                &[format!("ORM 설정: {rel} ({kind})")],
                Some("SQL"),
                1,
            );
            book.at(fid, &rel);
        }
    }

    // 8. 노드
    let funcs: Vec<Value> = graph["functions"].as_array().cloned().unwrap_or_default();
    let code_ext = |f: &str| lang_of(f).is_some();
    let front_fns = funcs.iter().any(|f| is_front(&s(f, "file"), &web_dirs));
    let back_fns = funcs.iter().any(|f| {
        let file = s(f, "file");
        !is_front(&file, &web_dirs) && code_ext(&file)
    });
    let mut nodes: Vec<Value> = Vec::new();
    let has_browser = front_fns || !web_dirs.is_empty();
    if has_browser {
        nodes.push(json!({
            "id": "infra:browser",
            "kind": "browser",
            "name": "브라우저",
            "where": "local",
            "host": null,
            "evidence": ["화면 코드가 브라우저에서 돈다"],
            "dir": null,
        }));
    }
    let mut servers: Vec<Value> = unit_list
        .iter()
        .filter(|u| u.get("kind").and_then(Value::as_str) == Some("server"))
        .map(|u| {
            let fw = s(u, "framework");
            let d = s(u, "dir");
            let host = u
                .get("port")
                .and_then(Value::as_i64)
                .filter(|p| *p != 0)
                .map(|p| format!("localhost:{p}"));
            json!({
                "id": format!("infra:server:{}", s(u, "name")),
                "kind": "backend",
                "name": format!("{fw} 서버"),
                "where": "local",
                "host": host,
                "evidence": [format!("{fw} — {}", if d.is_empty() { "루트" } else { &d })],
                "dir": d,
            })
        })
        .collect();
    if back_fns && servers.is_empty() {
        servers.push(json!({
            "id": "infra:backend",
            "kind": "backend",
            "name": "백엔드 서버",
            "where": "local",
            "host": null,
            "evidence": ["백엔드 코드가 이 PC에서 돈다"],
            "dir": "",
        }));
    }
    nodes.extend(servers.iter().cloned());
    let mut fids: Vec<&String> = book.found.keys().collect();
    fids.sort();
    for fid in &fids {
        let fd = &book.found[*fid];
        let where_ = fd
            .where_
            .clone()
            .filter(|w| !w.is_empty())
            .unwrap_or_else(|| {
                if fd.kind == "api" {
                    "external".into()
                } else {
                    "local".into()
                }
            });
        nodes.push(json!({
            "id": format!("infra:{fid}"),
            "kind": fd.kind,
            "name": fd.name,
            "where": where_,
            "host": fd.host,
            "evidence": fd.evidence,
            "dir": null,
        }));
    }

    // 9. 선
    let server_of = |file: &str| -> Option<&Value> {
        let mut best: Option<&Value> = None;
        for sv in &servers {
            let d = s(sv, "dir");
            if !d.is_empty() && file != d && !file.starts_with(&format!("{d}/")) {
                continue;
            }
            if best.is_none_or(|b| plen(&d) > plen(&s(b, "dir"))) {
                best = Some(sv);
            }
        }
        best
    };
    let mut links: Vec<Value> = Vec::new();
    if !servers.is_empty() {
        if has_browser {
            let mut by_key: HashMap<String, &Value> = HashMap::new();
            for f in &funcs {
                by_key.insert(s(f, "key"), f);
            }
            let mut called: HashSet<String> = HashSet::new();
            if let Some(hs) = graph.get("http").and_then(Value::as_array) {
                for h in hs {
                    if let Some(f) = by_key.get(&s(h, "to"))
                        && let Some(sv) = server_of(&s(f, "file"))
                    {
                        called.insert(s(sv, "id"));
                    }
                }
            }
            for sv in &servers {
                let id = s(sv, "id");
                if called.is_empty() || called.contains(&id) {
                    links.push(json!({"from": "infra:browser", "to": id, "protocol": "HTTP"}));
                }
            }
        }
        for fid in &fids {
            let fd = &book.found[*fid];
            let protocol = fd
                .protocol
                .clone()
                .filter(|p| !p.is_empty())
                .or_else(|| {
                    LIBS.iter()
                        .find(|l| l.1 == fid.as_str())
                        .map(|l| l.5.to_string())
                })
                .unwrap_or_default();
            let users: HashSet<String> = book
                .seen_at
                .get(*fid)
                .map(|xs| {
                    xs.iter()
                        .filter_map(|x| server_of(x))
                        .map(|sv| s(sv, "id"))
                        .collect()
                })
                .unwrap_or_default();
            for sv in &servers {
                let id = s(sv, "id");
                if users.is_empty() || users.contains(&id) || servers.len() == 1 {
                    links.push(
                        json!({"from": id, "to": format!("infra:{fid}"), "protocol": protocol}),
                    );
                }
            }
        }
    }
    if let Some(o) = graph.as_object_mut() {
        o.insert("infra".into(), json!({"nodes": nodes, "links": links}));
    }
}
