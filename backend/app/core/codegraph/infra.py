"""SYNC-MS-024 — core/codegraph/infra.py. 장비와 실행 단위(카드 CE).

순수 함수다 — DB를 모른다. view_arc `infra.mts`·`stack.mts`의 표와 규칙을 옮겼다(Java 줄은 뺐다).
주소는 호스트·포트만 남긴다 — 비밀번호·키는 읽어도 저장하지 않는다(INFRA C13).
Rust 판(MS-026)이 같은 결과를 낸다 — 폴더는 이름 바이트 순으로 걷고, 정규식은 ASCII 뜻이다.
"""

from __future__ import annotations

import ast
import json
import os
import posixpath
import re
from pathlib import Path

from app.core.codegraph.routes import _read
from app.core.codegraph.steps import _rs_root, _text, _ts_root, _walk

A = re.ASCII
_SQL_IO = r"^(execute\w*|exec|scalars?|get|add|add_all|commit|flush|delete|merge|refresh|query|stream\w*|fetch\w*|copy_\w+|bulk_\w+)$"  # noqa: E501
_MONGO_IO = (
    r"^(find\w*|insert\w*|update\w*|delete\w*|replace_one|aggregate|count_documents|bulk_write)$"  # noqa: E501
)

# 패키지 → (id, kind, name, io, protocol) — view_arc infra.mts LIBS(파이썬·Node) + Rust 줄
LIBS: dict[str, tuple[str, str, str, str, str]] = {
    "sqlalchemy": ("db", "db", "DB", _SQL_IO, "SQL"),
    "sqlmodel": ("db", "db", "DB", _SQL_IO, "SQL"),
    "psycopg2": ("db", "db", "PostgreSQL", _SQL_IO, "SQL"),
    "psycopg": ("db", "db", "PostgreSQL", _SQL_IO, "SQL"),
    "asyncpg": ("db", "db", "PostgreSQL", _SQL_IO, "SQL"),
    "pymysql": ("db", "db", "MySQL", _SQL_IO, "SQL"),
    "sqlite3": ("db", "db", "SQLite", _SQL_IO, "SQL"),
    "aiosqlite": ("db", "db", "SQLite", _SQL_IO, "SQL"),
    "pymongo": ("mongo", "db", "MongoDB", _MONGO_IO, "Mongo"),
    "motor": ("mongo", "db", "MongoDB", _MONGO_IO, "Mongo"),
    "neo4j": ("neo4j", "db", "Neo4j", r"^(run|execute_query|execute_read|execute_write)$", "Bolt"),
    "redis": (
        "redis",
        "cache",
        "Redis",
        r"^(get|set\w*|mget|mset|hget\w*|hset\w*|hdel|incr\w*|decr\w*|expire\w*|delete|exists|[lr]push|[lr]pop|lrange|publish|xadd|xread\w*|zadd|zrange\w*|sadd|smembers|ping|from_url)$",
        "Redis",
    ),  # noqa: E501
    "boto3": (
        "storage",
        "storage",
        "S3 저장소",
        r"^(put_object|get_object|upload_\w+|download_\w+|list_objects\w*|list_buckets|delete_object\w*|head_object|head_bucket|create_bucket|copy_object|generate_presigned_url)$",
        "S3",
    ),  # noqa: E501
    "minio": (
        "storage",
        "storage",
        "MinIO",
        r"^(put_object|get_object|fput_object|fget_object|list_objects|remove_object|stat_object|bucket_exists|make_bucket)$",
        "S3",
    ),  # noqa: E501
    "openai": ("openai", "api", "OpenAI API", r"^(create|parse|stream)$", "HTTPS"),
    "anthropic": ("anthropic", "api", "Anthropic API", r"^(create|stream)$", "HTTPS"),
    "requests": (
        "http",
        "api",
        "외부 HTTP",
        r"^(get|post|put|patch|delete|head|request|send)$",
        "HTTPS",
    ),  # noqa: E501
    "httpx": (
        "http",
        "api",
        "외부 HTTP",
        r"^(get|post|put|patch|delete|head|request|send|stream)$",
        "HTTPS",
    ),  # noqa: E501
    "aiohttp": ("http", "api", "외부 HTTP", r"^(get|post|put|patch|delete|head|request)$", "HTTPS"),
    "urllib": ("http", "api", "외부 HTTP", r"^(urlopen)$", "HTTPS"),
    "elasticsearch": (
        "search",
        "search",
        "Elasticsearch",
        r"^(search|index|get|delete|bulk|update)$",
        "HTTP",
    ),  # noqa: E501
    "opensearchpy": (
        "search",
        "search",
        "OpenSearch",
        r"^(search|index|get|delete|bulk|update)$",
        "HTTP",
    ),  # noqa: E501
    "pika": ("queue", "queue", "메시지 큐", r"^(basic_publish|basic_consume|publish)$", "AMQP"),
    "aio_pika": ("queue", "queue", "메시지 큐", r"^(publish|consume)$", "AMQP"),
    "kafka": ("queue", "queue", "Kafka", r"^(send|poll|produce)$", "Kafka"),
    "aiokafka": ("queue", "queue", "Kafka", r"^(send\w*|getone|getmany)$", "Kafka"),
    "celery": ("queue", "queue", "작업 큐", r"^(delay|apply_async|send_task)$", "AMQP"),
    "pg": ("db", "db", "PostgreSQL", r"^(query|connect)$", "SQL"),
    "@neondatabase/serverless": ("db", "db", "PostgreSQL", r"^(query|connect|transaction)$", "SQL"),
    "mysql2": ("db", "db", "MySQL", r"^(query|execute|getConnection)$", "SQL"),
    "better-sqlite3": ("db", "db", "SQLite", r"^(run|get|all|exec|iterate)$", "SQL"),
    "drizzle-orm": (
        "db",
        "db",
        "DB",
        r"^(select|selectDistinct|insert|update|delete|execute|findMany|findFirst|transaction|batch)$",
        "SQL",
    ),  # noqa: E501
    "@prisma/client": (
        "db",
        "db",
        "DB",
        r"^(findMany|findFirst|findUnique|findUniqueOrThrow|findFirstOrThrow|create|createMany|update|updateMany|upsert|delete|deleteMany|count|aggregate|groupBy|\$queryRaw\w*|\$executeRaw\w*|\$transaction)$",
        "SQL",
    ),  # noqa: E501
    "typeorm": (
        "db",
        "db",
        "DB",
        r"^(find\w*|save|insert|update|delete|remove|softDelete|query|count\w*|getMany|getOne|getRawMany|getRawOne|execute|exist\w*)$",
        "SQL",
    ),  # noqa: E501
    "sequelize": (
        "db",
        "db",
        "DB",
        r"^(findAll|findOne|findByPk|findOrCreate|findAndCountAll|create|bulkCreate|update|destroy|count|query|upsert)$",
        "SQL",
    ),  # noqa: E501
    "knex": ("db", "db", "DB", r"^(select|insert|update|del|delete|raw|first|then)$", "SQL"),
    "mongoose": (
        "mongo",
        "db",
        "MongoDB",
        r"^(find\w*|create|insertMany|update\w*|delete\w*|replaceOne|aggregate|count\w*|save|exec|exists)$",
        "Mongo",
    ),  # noqa: E501
    "mongodb": (
        "mongo",
        "db",
        "MongoDB",
        r"^(find\w*|insert\w*|update\w*|delete\w*|replaceOne|aggregate|countDocuments|bulkWrite|toArray)$",
        "Mongo",
    ),  # noqa: E501
    "ioredis": (
        "redis",
        "cache",
        "Redis",
        r"^(get|set\w*|mget|mset|hget\w*|hset\w*|hdel|incr\w*|decr\w*|expire\w*|del|exists|[lr]push|[lr]pop|lrange|publish|xadd|xread\w*|zadd|zrange\w*|sadd|smembers|ping|eval)$",
        "Redis",
    ),  # noqa: E501
    "@upstash/redis": (
        "redis",
        "cache",
        "Redis",
        r"^(get|set\w*|del|incr\w*|expire|hget\w*|hset\w*|lpush|rpush|lrange)$",
        "HTTPS",
    ),  # noqa: E501
    "bullmq": ("redis", "cache", "Redis", r"^(add|addBulk)$", "Redis"),
    "@aws-sdk/client-s3": ("storage", "storage", "S3 저장소", r"^send$", "S3"),
    "@aws-sdk/lib-storage": ("storage", "storage", "S3 저장소", r"^done$", "S3"),
    "aws-sdk": (
        "storage",
        "storage",
        "S3 저장소",
        r"^(putObject|getObject|upload|deleteObject\w*|listObjects\w*|headObject|getSignedUrl\w*|promise)$",
        "S3",
    ),  # noqa: E501
    "@anthropic-ai/sdk": ("anthropic", "api", "Anthropic API", r"^(create|stream)$", "HTTPS"),
    "@google/generative-ai": (
        "gemini",
        "api",
        "Gemini API",
        r"^(generateContent\w*|embedContent|countTokens|sendMessage\w*)$",
        "HTTPS",
    ),  # noqa: E501
    "@google/genai": (
        "gemini",
        "api",
        "Gemini API",
        r"^(generateContent\w*|embedContent|countTokens|sendMessage\w*)$",
        "HTTPS",
    ),  # noqa: E501
    "axios": ("http", "api", "외부 HTTP", r"^(get|post|put|patch|delete|head|request)$", "HTTPS"),
    "node-fetch": ("http", "api", "외부 HTTP", r"^fetch$", "HTTPS"),
    "undici": ("http", "api", "외부 HTTP", r"^(fetch|request)$", "HTTPS"),
    "fetch": ("http", "api", "외부 HTTP", r"^fetch$", "HTTPS"),
    "kafkajs": ("queue", "queue", "Kafka", r"^(send|sendBatch)$", "Kafka"),
    "amqplib": ("queue", "queue", "RabbitMQ", r"^(publish|sendToQueue)$", "AMQP"),
    "@elastic/elasticsearch": (
        "search",
        "search",
        "Elasticsearch",
        r"^(search|index|get|delete|bulk|update)$",
        "HTTP",
    ),  # noqa: E501
    "neo4j-driver": (
        "neo4j",
        "db",
        "Neo4j",
        r"^(run|executeQuery|executeRead|executeWrite)$",
        "Bolt",
    ),  # noqa: E501
    "@supabase/supabase-js": (
        "supabase",
        "db",
        "Supabase",
        r"^(select|insert|update|delete|upsert|rpc|upload|download)$",
        "HTTPS",
    ),  # noqa: E501
    "sqlx": ("db", "db", "DB", r"^(fetch\w*|execute\w*)$", "SQL"),
    "tokio_postgres": ("db", "db", "PostgreSQL", r"^(query\w*|execute\w*|prepare)$", "SQL"),
    "reqwest": ("http", "api", "외부 HTTP", r"^(send|get|post|put|patch|delete|head)$", "HTTPS"),
    "aws_sdk_s3": ("storage", "storage", "S3 저장소", r"^send$", "S3"),
    # Java — 받는 쪽 타입(JAVA_TYPES·저장소 인터페이스)으로 장비 호출만 골랐다
    "spring-data": ("db", "db", "DB", r".", "SQL"),
    "jdbc": ("db", "db", "DB", r".", "SQL"),
    "jpa": ("db", "db", "DB", r".", "SQL"),
    "jooq": ("db", "db", "DB", r".", "SQL"),
    "mybatis": ("db", "db", "DB", r".", "SQL"),
    "java-mongo": ("mongo", "db", "MongoDB", r".", "Mongo"),
    "java-neo4j": ("neo4j", "db", "Neo4j", r".", "Bolt"),
    "java-redis": ("redis", "cache", "Redis", r".", "Redis"),
    "java-http": ("http", "api", "외부 HTTP", r".", "HTTPS"),
    "java-kafka": ("queue", "queue", "Kafka", r".", "Kafka"),
    "java-amqp": ("queue", "queue", "메시지 큐", r".", "AMQP"),
    "java-s3": ("storage", "storage", "S3 저장소", r".", "S3"),
    "java-search": ("search", "search", "Elasticsearch", r".", "HTTP"),
    "spring-ai": ("llm", "api", "LLM API", r".", "HTTPS"),
    # Go — import 경로(`/vN` 조각을 뗀 것)
    "database/sql": ("db", "db", "DB", r"^(Query\w*|Exec\w*|Prepare\w*|Begin\w*|Ping\w*)$", "SQL"),
    "github.com/jackc/pgx": (
        "db",
        "db",
        "PostgreSQL",
        r"^(Query\w*|Exec\w*|Begin\w*|SendBatch|CopyFrom|Ping)$",
        "SQL",
    ),  # noqa: E501
    "github.com/jackc/pgx/pgxpool": (
        "db",
        "db",
        "PostgreSQL",
        r"^(Query\w*|Exec\w*|Begin\w*|SendBatch|CopyFrom|Ping)$",
        "SQL",
    ),  # noqa: E501
    "gorm.io/gorm": (
        "db",
        "db",
        "DB",
        r"^(Create|Save|First|Find|Take|Last|Delete|Updates?|Exec|Raw|Count|Scan|Pluck|Transaction)$",
        "SQL",
    ),  # noqa: E501
    "go.mongodb.org/mongo-driver/mongo": (
        "mongo",
        "db",
        "MongoDB",
        r"^(Find\w*|Insert\w*|Update\w*|Delete\w*|ReplaceOne|Aggregate|CountDocuments|BulkWrite)$",
        "Mongo",
    ),  # noqa: E501
    "github.com/redis/go-redis": (
        "redis",
        "cache",
        "Redis",
        r"^(Get|Set\w*|Del|Exists|Expire\w*|Incr\w*|Decr\w*|HGet\w*|HSet\w*|HDel|[LR]Push|[LR]Pop|LRange|Publish|Subscribe|XAdd|XRead\w*|ZAdd|ZRange\w*|SAdd|SMembers|Ping)$",
        "Redis",
    ),  # noqa: E501
    "github.com/go-redis/redis": (
        "redis",
        "cache",
        "Redis",
        r"^(Get|Set\w*|Del|Exists|Expire\w*|Incr\w*|Decr\w*|HGet\w*|HSet\w*|HDel|[LR]Push|[LR]Pop|LRange|Publish|Subscribe|XAdd|XRead\w*|ZAdd|ZRange\w*|SAdd|SMembers|Ping)$",
        "Redis",
    ),  # noqa: E501
    "net/http": ("http", "api", "외부 HTTP", r"^(Get|Post|PostForm|Head|Do)$", "HTTPS"),
    "github.com/aws/aws-sdk-go-v2/service/s3": (
        "storage",
        "storage",
        "S3 저장소",
        r"^(PutObject|GetObject|ListObjects\w*|DeleteObjects?|HeadObject|CopyObject|CreateBucket|ListBuckets)$",
        "S3",
    ),  # noqa: E501
    "github.com/sashabaranov/go-openai": (
        "openai",
        "api",
        "OpenAI API",
        r"^(CreateChatCompletion\w*|CreateCompletion\w*|CreateEmbeddings)$",
        "HTTPS",
    ),  # noqa: E501
    "github.com/anthropics/anthropic-sdk-go": (
        "anthropic",
        "api",
        "Anthropic API",
        r"^(New|NewStreaming)$",
        "HTTPS",
    ),  # noqa: E501
    "github.com/segmentio/kafka-go": (
        "queue",
        "queue",
        "Kafka",
        r"^(WriteMessages|ReadMessage|FetchMessage|CommitMessages)$",
        "Kafka",
    ),  # noqa: E501
    "github.com/rabbitmq/amqp091-go": (
        "queue",
        "queue",
        "RabbitMQ",
        r"^(Publish\w*|Consume\w*)$",
        "AMQP",
    ),  # noqa: E501
}
# Java 타입 → LIBS 키 — 필드·매개변수·지역 변수의 타입이 이것이면 그 메서드 호출은 장비 호출
JAVA_TYPES: dict[str, str] = {
    "JdbcTemplate": "jdbc", "NamedParameterJdbcTemplate": "jdbc", "JdbcClient": "jdbc",
    "EntityManager": "jpa", "DSLContext": "jooq", "SqlSession": "mybatis",
    "RestTemplate": "java-http", "WebClient": "java-http", "RestClient": "java-http",
    "OkHttpClient": "java-http", "HttpClient": "java-http", "CloseableHttpClient": "java-http",
    "RedisTemplate": "java-redis", "StringRedisTemplate": "java-redis",
    "ReactiveRedisTemplate": "java-redis", "ReactiveStringRedisTemplate": "java-redis",
    "RedissonClient": "java-redis", "Jedis": "java-redis", "JedisPool": "java-redis",
    "MongoTemplate": "java-mongo", "ReactiveMongoTemplate": "java-mongo",
    "MongoClient": "java-mongo", "MongoDatabase": "java-mongo",
    "KafkaTemplate": "java-kafka", "RabbitTemplate": "java-amqp", "AmqpTemplate": "java-amqp",
    "S3Client": "java-s3", "S3AsyncClient": "java-s3", "AmazonS3": "java-s3",
    "S3Presigner": "java-s3", "MinioClient": "java-s3",
    "ElasticsearchClient": "java-search", "RestHighLevelClient": "java-search",
    "ElasticsearchOperations": "java-search", "OpenSearchClient": "java-search",
    "ChatClient": "spring-ai", "ChatModel": "spring-ai", "EmbeddingModel": "spring-ai",
    "VectorStore": "spring-ai",
}  # fmt: skip
# 저장소 인터페이스가 넓히는 타입 → LIBS 키 (표 차례로 첫 맞는 줄)
REPO_BASES: list[tuple[str, str]] = [
    (r"^(Mongo|ReactiveMongo)Repository$", "java-mongo"),
    (r"^Elasticsearch(Crud)?Repository$", "java-search"),
    (r"^Neo4jRepository$", "java-neo4j"),
    (r"^(Jpa|Crud|ListCrud|PagingAndSorting|ListPagingAndSorting|R2dbc|ReactiveCrud|Revision)\w*$"
     r"|^Repository$|^JpaSpecificationExecutor$|^QuerydslPredicateExecutor$", "spring-data"),
]  # fmt: skip
# Rust redis는 파이썬 redis와 이름이 같다 — 같은 장비라 표 하나로 둔다(io는 파이썬 것)

# 의존성 패키지 → (id, kind, name, protocol) — view_arc infra.mts DEPS 그대로
DEPS: list[tuple[str, str, str, str, str]] = [
    (
        r"^(pg|postgres|pg-promise|slonik|@neondatabase\/serverless|@vercel\/postgres|org\.postgresql:postgresql|github\.com\/lib\/pq|github\.com\/jackc\/pgx(\/v\d)?|tokio-postgres|npgsql(\..*)?|r2dbc-postgresql)$",
        "db",
        "db",
        "PostgreSQL",
        "SQL",
    ),  # noqa: E501
    (
        r"^(mysql2?|com\.mysql:mysql-connector-j|mysql:mysql-connector-java|org\.mariadb\.jdbc:mariadb-java-client|github\.com\/go-sql-driver\/mysql|mysql_async|mysql\.data|pomelo\.entityframeworkcore\.mysql)$",
        "db",
        "db",
        "MySQL",
        "SQL",
    ),  # noqa: E501
    (
        r"^(better-sqlite3|sqlite3|github\.com\/mattn\/go-sqlite3|rusqlite|microsoft\.data\.sqlite|org\.xerial:sqlite-jdbc)$",
        "db",
        "db",
        "SQLite",
        "SQL",
    ),  # noqa: E501
    (
        r"^(@prisma\/client|drizzle-orm|typeorm|sequelize|knex|kysely|@mikro-orm\/core|org\.springframework\.boot:spring-boot-starter-data-(jpa|jdbc|r2dbc)|org\.springframework\.boot:spring-boot-starter-jdbc|gorm\.io\/gorm|sqlx|diesel|sea-orm|microsoft\.entityframeworkcore(\..*)?|org\.jooq:jooq|org\.mybatis.*)$",
        "db",
        "db",
        "DB",
        "SQL",
    ),  # noqa: E501
    (
        r"^(mongodb|mongoose|org\.springframework\.boot:spring-boot-starter-data-mongodb.*|org\.mongodb:.*|go\.mongodb\.org\/mongo-driver.*|mongodb\.driver)$",
        "mongo",
        "db",
        "MongoDB",
        "Mongo",
    ),  # noqa: E501
    (
        r"^(redis|ioredis|@upstash\/redis|bullmq|bull|org\.springframework\.boot:spring-boot-starter-data-redis.*|redis\.clients:jedis|org\.redisson:.*|github\.com\/(redis|go-redis)\/(go-)?redis(\/v\d)?|stackexchange\.redis|predis\/predis)$",
        "redis",
        "cache",
        "Redis",
        "Redis",
    ),  # noqa: E501
    (
        r"^(minio|io\.minio:minio|github\.com\/minio\/minio-go(\/v\d)?)$",
        "storage",
        "storage",
        "MinIO",
        "S3",
    ),  # noqa: E501
    (
        r"^(@aws-sdk\/client-s3|aws-sdk|software\.amazon\.awssdk:s3|com\.amazonaws:aws-java-sdk-s3|github\.com\/aws\/aws-sdk-go-v2\/service\/s3|aws-sdk-s3|awssdk\.s3|aws\/aws-sdk-php)$",
        "storage",
        "storage",
        "S3 저장소",
        "S3",
    ),  # noqa: E501
    (
        r"^(openai|org\.springframework\.ai:spring-ai-(starter-model-)?openai.*|github\.com\/(sashabaranov|openai)\/(go-)?openai(-go)?|async-openai|com\.openai:openai-java)$",
        "openai",
        "api",
        "OpenAI API",
        "HTTPS",
    ),  # noqa: E501
    (
        r"^(@anthropic-ai\/sdk|com\.anthropic:anthropic-java|github\.com\/anthropics\/anthropic-sdk-go)$",
        "anthropic",
        "api",
        "Anthropic API",
        "HTTPS",
    ),  # noqa: E501
    (r"^(@google\/generative-ai|@google\/genai)$", "gemini", "api", "Gemini API", "HTTPS"),
    (
        r"^(kafkajs|org\.springframework\.kafka:spring-kafka|org\.apache\.kafka:kafka-clients|github\.com\/segmentio\/kafka-go|github\.com\/(ibm|shopify)\/sarama|rdkafka|confluent\.kafka)$",
        "queue",
        "queue",
        "Kafka",
        "Kafka",
    ),  # noqa: E501
    (
        r"^(amqplib|org\.springframework\.boot:spring-boot-starter-amqp|github\.com\/rabbitmq\/amqp091-go|lapin|rabbitmq\.client)$",
        "queue",
        "queue",
        "RabbitMQ",
        "AMQP",
    ),  # noqa: E501
    (
        r"^(@elastic\/elasticsearch|@opensearch-project\/opensearch|org\.springframework\.boot:spring-boot-starter-data-elasticsearch|co\.elastic\.clients:.*|org\.opensearch\.client:.*|github\.com\/elastic\/go-elasticsearch(\/v\d)?|elasticsearch|opensearch)$",
        "search",
        "search",
        "Elasticsearch",
        "HTTP",
    ),  # noqa: E501
    (
        r"^(neo4j-driver|org\.springframework\.boot:spring-boot-starter-data-neo4j|org\.neo4j\.driver:.*|neo4rs)$",
        "neo4j",
        "db",
        "Neo4j",
        "Bolt",
    ),  # noqa: E501
    (r"^@supabase\/supabase-js$", "supabase", "db", "Supabase", "HTTPS"),
    (r"^firebase-admin$", "firebase", "api", "Firebase", "HTTPS"),
]
FRONT_ONLY = re.compile(r"^(react|react-dom|preact|vue|svelte|@angular\/core|solid-js)$", A)
SERVER_DEPS = re.compile(
    r"^(express|fastify|koa|@nestjs\/core|hono|@hapi\/hapi|restify|next|@remix-run\/node|h3|nitropack|elysia)$",
    A,
)  # noqa: E501
IMAGES: list[tuple[str, str, str, str]] = [
    (r"pgvector", "db", "db", "PostgreSQL (pgvector)"),
    (r"postgres|postgis|timescale", "db", "db", "PostgreSQL"),
    (r"mysql|mariadb", "db", "db", "MySQL"),
    (r"mongo", "mongo", "db", "MongoDB"),
    (r"neo4j|memgraph", "neo4j", "db", "Neo4j"),
    (r"redis|valkey|dragonfly", "redis", "cache", "Redis"),
    (r"minio", "storage", "storage", "MinIO (S3)"),
    (r"elasticsearch|opensearch", "search", "search", "Elasticsearch"),
    (r"rabbitmq", "queue", "queue", "RabbitMQ"),
    (r"kafka|redpanda", "queue", "queue", "Kafka"),
]
SCHEMES: list[tuple[str, str, str, str]] = [
    (r"^postgres(ql)?(\+\w+)?$", "db", "db", "PostgreSQL"),
    (r"^mysql(\+\w+)?$|^mariadb", "db", "db", "MySQL"),
    (r"^sqlite(\+\w+)?$", "db", "db", "SQLite"),
    (r"^mongodb(\+srv)?$", "mongo", "db", "MongoDB"),
    (r"^rediss?$", "redis", "cache", "Redis"),
    (r"^(bolt|neo4j)(\+s)?$", "neo4j", "db", "Neo4j"),
    (r"^amqps?$", "queue", "queue", "메시지 큐"),
]
HTTP_KEYS: list[tuple[str, str, str, str]] = [
    (r"STORAGE|S3|MINIO|BUCKET", "storage", "storage", "S3 저장소"),
    (r"ELASTIC|OPENSEARCH|SEARCH_URL", "search", "search", "Elasticsearch"),
]
HOST_KEYS: list[tuple[str, str, str, str]] = [
    (r"redis|valkey", "redis", "cache", "Redis"),
    (r"mongo", "mongo", "db", "MongoDB"),
    (r"rabbit|amqp", "queue", "queue", "RabbitMQ"),
    (r"elastic|opensearch", "search", "search", "Elasticsearch"),
    (r"neo4j", "neo4j", "db", "Neo4j"),
    (r"minio|s3", "storage", "storage", "S3 저장소"),
    (r"^(.*[._-])?(postgres\w*|pg)$", "db", "db", "PostgreSQL"),
    (r"^(.*[._-])?mysql$", "db", "db", "MySQL"),
    (r"^(.*[._-])?(db|database|datasource)$", "db", "db", "DB"),
]
NOT_APP = re.compile(
    r"(^|/)(tests?|scripts?|e2e|evals?|fixtures|examples?|benchmarks?|notebooks?|__tests__)/|(^|/)src/(test|integrationTest|testFixtures|it)/|(^|/)(test_[^/]*|[^/]*_test|conftest)\.py$|(Test|Tests|IT|_test|\.test|\.spec)\.\w+$",
    A,
)  # noqa: E501
PLACEHOLDER = re.compile(
    r"^(host|hostname|server|your[-_.]?\w*|db[-_]?host|database[-_]?host|<.*>|x{3,}|(.*\.)?example\.(com|org|net))$",
    A | re.I,
)  # noqa: E501
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"})

_SKIP = frozenset(
    "node_modules vendor target dist build out venv .venv __pycache__ site-packages coverage"
    " graphify-out".split()
)
_CONFIG_SKIP = _SKIP | {"bin", "obj", "tests", "test", "data", "docs"}
_COMPOSE = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "docker-compose.dev.yml",
)
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*", A)
_PY_EXTS = (".py",)
_TS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs")


def _search(pattern: str, text: str, ignore_case: bool = False) -> bool:
    return re.search(pattern, text, A | (re.I if ignore_case else 0)) is not None


def _dirs(path: Path) -> list[str]:
    """한 단 아래 폴더 이름 — 점·건너뛰는 폴더 빼고, 이름 바이트 순."""
    try:
        names = [e.name for e in os.scandir(path) if e.is_dir(follow_symlinks=False)]
    except OSError:
        return []
    return sorted(
        (n for n in names if not n.startswith(".") and n != "node_modules"),
        key=lambda n: n.encode("utf-8"),
    )


def _entries(path: Path) -> list[os.DirEntry]:
    try:
        return sorted(os.scandir(path), key=lambda e: e.name.encode("utf-8"))
    except OSError:
        return []


def _text_of(path: Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _rel(src_dir: Path, path: Path) -> str:
    return path.relative_to(src_dir).as_posix()


# ---------------------------------------------------------------- 실행 단위


def _manifests(src_dir: Path) -> list[tuple[str, str]]:
    """깊이 3까지의 목록 파일 — [(폴더, 이름)], 폴더는 루트면 ""."""
    out: list[tuple[str, str]] = []

    def visit(path: Path, rel: str, depth: int) -> None:
        for e in _entries(path):
            if e.is_dir(follow_symlinks=False):
                if depth < 3 and not e.name.startswith(".") and e.name not in _SKIP:
                    visit(Path(e.path), f"{rel}/{e.name}" if rel else e.name, depth + 1)
            elif e.name in (
                "package.json",
                "pyproject.toml",
                "requirements.txt",
                "manage.py",
                "Cargo.toml",
                "pom.xml",
                "build.gradle",
                "build.gradle.kts",
                "go.mod",
            ):
                out.append((rel, e.name))

    visit(src_dir, "", 0)
    return out


def _unit_name(d: str) -> str:
    return d.rsplit("/", 1)[-1] if d else "app"


def _node_unit(src_dir: Path, d: str) -> dict | None:
    text = _text_of(src_dir / d / "package.json")
    try:
        pkg = json.loads(text) if text is not None else None
    except ValueError:
        return None
    if not isinstance(pkg, dict):
        return None
    deps = pkg.get("dependencies") if isinstance(pkg.get("dependencies"), dict) else {}
    dev = pkg.get("devDependencies") if isinstance(pkg.get("devDependencies"), dict) else {}
    both = {**deps, **dev}
    kind = framework = None
    for name, fw in (
        ("express", "Express"),
        ("fastify", "Fastify"),
        ("koa", "Koa"),
        ("@nestjs/core", "NestJS"),
        ("hono", "Hono"),
    ):
        if name in deps:
            kind, framework = "server", fw
            break
    if kind is None:
        for name, fw in (
            ("next", "Next.js"),
            ("vite", "Vite"),
            ("react", "React"),
            ("vue", "Vue"),
            ("svelte", "Svelte"),
        ):
            if name in both:
                kind, framework = "web", fw
                break
    if kind is None:
        return None
    scripts = pkg.get("scripts") if isinstance(pkg.get("scripts"), dict) else {}
    command = script = None
    if isinstance(scripts.get("dev"), str):
        command, script = "npm run dev", scripts["dev"]
    elif isinstance(scripts.get("start"), str):
        command, script = "npm start", scripts["start"]
    port = None
    if script:
        m = re.search(r"(?:--port|-p)[ =](\d+)", script, A)
        if m:
            port = int(m.group(1))
    if port is None:
        port = {"Vite": 5173, "Next.js": 3000}.get(framework)
    lang = "typescript" if (src_dir / d / "tsconfig.json").is_file() else "javascript"
    return {
        "name": _unit_name(d),
        "kind": kind,
        "dir": d,
        "lang": lang,
        "framework": framework,
        "command": command,
        "port": port,
    }


def _py_module(rel: str) -> str:
    parts = rel[: -len(".py")].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _py_unit(src_dir: Path, d: str, names: set[str]) -> dict | None:
    from app.core.codegraph.flow import walk
    from app.core.codegraph.graph import _is_test

    base = src_dir / d if d else src_dir
    uv = "uv run " if (base / "uv.lock").is_file() else ""
    if "manage.py" in names:
        return {
            "name": _unit_name(d),
            "kind": "server",
            "dir": d,
            "lang": "python",
            "framework": "Django",
            "command": f"{uv}python manage.py runserver 8000",
            "port": 8000,
        }
    files = sorted(
        (p for p in walk(base) if p.endswith(".py") and not _is_test(p)),
        key=lambda p: p.encode("utf-8"),
    )
    for rel in files:
        text = _text_of(base / rel)
        if text is None:
            continue
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            continue
        for st in tree.body:
            if not (isinstance(st, ast.Assign) and isinstance(st.value, ast.Call)):
                continue
            f = st.value.func
            kind = (
                f.id
                if isinstance(f, ast.Name)
                else f.attr
                if isinstance(f, ast.Attribute)
                else None
            )
            var = next((t.id for t in st.targets if isinstance(t, ast.Name)), None)
            if var is None or kind not in ("FastAPI", "Flask", "Celery"):
                continue
            mod = _py_module(rel)
            if kind == "FastAPI":
                cmd, port, k = f"uvicorn {mod}:{var} --port 8000", 8000, "server"
            elif kind == "Flask":
                cmd, port, k = f"flask --app {mod} run --port 5000", 5000, "server"
            else:
                cmd, port, k = f"celery -A {mod} worker", None, "job"
            return {
                "name": _unit_name(d),
                "kind": k,
                "dir": d,
                "lang": "python",
                "framework": kind,
                "command": uv + cmd,
                "port": port,
            }
    return None


def _toml_tables(text: str) -> dict[str, list[str]]:
    """TOML의 표 이름 → 그 표의 키들(맨 단순 꼴만 — `이름 =`·`이름.workspace =`)."""
    out: dict[str, list[str]] = {}
    table = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[([^\[\]]+)\]$", line)
        if m:
            table = m.group(1).strip()
            out.setdefault(table, [])
            continue
        m = re.match(r"^([A-Za-z0-9_-]+)\s*[.=]", line, A)
        if m:
            out.setdefault(table, []).append(m.group(1))
    return out


def _toml_value(text: str, table: str, key: str) -> str | None:
    cur = ""
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"^\[([^\[\]]+)\]$", line)
        if m:
            cur = m.group(1).strip()
            continue
        if cur == table:
            m = re.match(rf'^{re.escape(key)}\s*=\s*"([^"]*)"', line)
            if m:
                return m.group(1)
    return None


def _rust_unit(src_dir: Path, d: str) -> dict | None:
    text = _text_of(src_dir / d / "Cargo.toml")
    if text is None:
        return None
    tables = _toml_tables(text)
    if "package" not in tables:
        return None  # 작업 공간 루트
    deps = tables.get("dependencies", []) + tables.get("workspace.dependencies", [])
    framework = "Axum" if "axum" in deps else "Actix" if "actix-web" in deps else None
    if framework is None:
        return None
    name = _toml_value(text, "package", "name")
    return {
        "name": _unit_name(d),
        "kind": "server",
        "dir": d,
        "lang": "rust",
        "framework": framework,
        "command": f"cargo run -p {name}" if name else None,
        "port": None,
    }


def _spring_port(src_dir: Path, d: str) -> int:
    """`src/main/resources/application.yml|yaml|properties`의 `server.port` — 없으면 8080."""
    for f in ("application.yml", "application.yaml", "application.properties"):
        text = _text_of(src_dir / d / "src/main/resources" / f)
        if text is None:
            continue
        text = re.sub(r"\$\{[\w.]+:-?([^}]*)\}", r"\1", text, flags=A)
        m = re.search(r"^server:\s*\n(?:\s+.*\n)*?\s+port:\s*(\d+)", text, re.M | A) or re.search(
            r"^server\.port\s*=\s*(\d+)", text, re.M | A
        )
        if m:
            return int(m.group(1))
    return 8080


def _java_unit(src_dir: Path, d: str, names: set[str]) -> dict | None:
    """Spring Boot — `pom.xml`·`build.gradle(.kts)`(그 차례로 첫 것)에 `spring-boot`가 있으면."""
    for file in ("pom.xml", "build.gradle", "build.gradle.kts"):
        if file not in names:
            continue
        text = _text_of(src_dir / d / file) or ""
        if not re.search(r"spring-boot|springframework\.boot", text):
            return None
        gradle = file != "pom.xml"
        wrapper = (src_dir / d / ("gradlew" if gradle else "mvnw")).is_file()
        if gradle:
            command = f"{'./gradlew' if wrapper else 'gradle'} bootRun"
        else:
            command = f"{'./mvnw' if wrapper else 'mvn'} spring-boot:run"
        return {
            "name": _unit_name(d),
            "kind": "server",
            "dir": d,
            "lang": "java",
            "framework": "Spring Boot",
            "command": command,
            "port": _spring_port(src_dir, d),
        }
    return None


_GO_FRAMEWORKS = (("gin-gonic/gin", "Gin"), ("labstack/echo", "Echo"), ("go-chi/chi", "chi"),
                  ("gofiber/fiber", "Fiber"), ("gorilla/mux", "gorilla/mux"))  # fmt: skip


def _go_unit(src_dir: Path, d: str) -> dict | None:
    """Go — `go.mod` 폴더 아래 깊이 4까지 `.go`(테스트 빼고, 경로 바이트 순) 중 `package main`과
    `func main(`이 든 첫 파일. net/http는 그 파일이 `net/http`를 가져올 때만."""
    from app.core.codegraph.graph import _is_test

    mod = _text_of(src_dir / d / "go.mod") or ""
    framework = next((fw for pat, fw in _GO_FRAMEWORKS if pat in mod), "net/http")
    found: list[str] = []

    def visit(path: Path, rel: str, depth: int) -> None:
        for e in _entries(path):
            r = f"{rel}/{e.name}" if rel else e.name
            if e.is_dir(follow_symlinks=False):
                if depth < 4 and not e.name.startswith(".") and e.name not in _SKIP:
                    visit(Path(e.path), r, depth + 1)
            elif e.name.endswith(".go") and not _is_test(e.name):
                found.append(r)

    visit(src_dir / d, "", 1)
    for rel in sorted(found, key=lambda x: x.encode("utf-8")):
        text = _text_of(src_dir / d / rel) or ""
        if not (re.search(r"^package main\b", text, re.M | A) and "func main(" in text):
            continue
        if framework == "net/http" and "net/http" not in text:
            return None
        main_dir = posixpath.dirname(rel)
        port = re.search(r"[\"'`](?:[\w.]*):(\d{4,5})[\"'`]", text, A)
        return {
            "name": _unit_name(d),
            "kind": "server",
            "dir": d,
            "lang": "go",
            "framework": framework,
            "command": "go run ." if not main_dir else f"go run ./{main_dir}",
            "port": int(port.group(1)) if port else 8080,
        }
    return None


def units(src_dir: Path, graph: dict) -> list[dict]:
    """SYNC-MS-024#infra.units

    실행 단위 — `package.json`(서버·화면) · 파이썬(Django·FastAPI·Flask·Celery) · `Cargo.toml`(Axum·
    Actix) · Spring Boot · Go. 깊이 3까지, `(dir, name)` 바이트 순.
    """
    by_dir: dict[str, set[str]] = {}
    for d, name in _manifests(src_dir):
        by_dir.setdefault(d, set()).add(name)
    out: list[dict] = []
    for d in sorted(by_dir, key=lambda x: x.encode("utf-8")):
        names = by_dir[d]
        if "package.json" in names:
            u = _node_unit(src_dir, d)
            if u:
                out.append(u)
        if names & {"pyproject.toml", "requirements.txt", "manage.py"}:
            u = _py_unit(src_dir, d, names)
            if u:
                out.append(u)
        if "Cargo.toml" in names:
            u = _rust_unit(src_dir, d)
            if u:
                out.append(u)
        if names & {"pom.xml", "build.gradle", "build.gradle.kts"}:
            u = _java_unit(src_dir, d, names)
            if u:
                out.append(u)
        if "go.mod" in names:
            u = _go_unit(src_dir, d)
            if u:
                out.append(u)
    out.sort(key=lambda u: (u["dir"].encode("utf-8"), u["name"].encode("utf-8")))
    return out


# ---------------------------------------------------------------- 함수의 패키지


def _pkg_norm(spec: str) -> str | None:
    if spec.startswith((".", "/")) or spec.startswith("node:"):
        return None
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") and len(parts) > 1 else parts[0]


def _py_root(n: ast.expr) -> ast.expr:
    while True:
        if isinstance(n, ast.Attribute):
            n = n.value
        elif isinstance(n, ast.Call):
            n = n.func
        elif isinstance(n, ast.Subscript):
            n = n.value
        elif isinstance(n, ast.Await):
            n = n.value
        else:
            return n


def _py_env(text: str) -> tuple[dict[str, str], dict[int, dict[str, str]]]:
    """파이썬 파일 → (파일 표: 이름 → 패키지, 함수 def 줄 → 변수 표)."""
    tree = ast.parse(text)
    table: dict[str, str] = {}
    for st in ast.walk(tree):
        if isinstance(st, ast.Import):
            for a in st.names:
                top = a.name.split(".")[0]
                table[a.asname or top] = top
        elif isinstance(st, ast.ImportFrom) and st.module and not st.level:
            top = st.module.split(".")[0]
            for a in st.names:
                table[a.asname or a.name] = top

    def pkg_of_value(v: ast.expr | None) -> str | None:
        if v is None:
            return None
        r = _py_root(v)
        return table.get(r.id) if isinstance(r, ast.Name) else None

    def pkg_of_ann(ann: ast.expr | None) -> str | None:
        if ann is None:
            return None
        for n in ast.walk(ann):
            if isinstance(n, ast.Name) and n.id in table:
                return table[n.id]
        return None

    module_vars: dict[str, str] = {}
    for st in tree.body:
        if isinstance(st, ast.Assign):
            p = pkg_of_value(st.value)
            if p:
                for t in st.targets:
                    if isinstance(t, ast.Name):
                        module_vars[t.id] = p
    funcs: dict[int, dict[str, str]] = {}

    def self_attrs(cls: ast.ClassDef) -> dict[str, str]:
        out: dict[str, str] = {}
        for item in cls.body:
            if (
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == "__init__"
            ):
                for st in ast.walk(item):
                    target, p = None, None
                    if isinstance(st, ast.Assign) and len(st.targets) == 1:
                        target, p = st.targets[0], pkg_of_value(st.value)
                    elif isinstance(st, ast.AnnAssign):
                        target, p = st.target, pkg_of_ann(st.annotation) or pkg_of_value(st.value)
                    if (
                        p
                        and isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                    ):
                        out[f"self.{target.attr}"] = p
        return out

    def visit(node: ast.AST, inherited: dict[str, str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, {**inherited, **self_attrs(child)})
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                env = dict(module_vars)
                env.update(inherited)
                args = child.args
                for a in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
                    if a is not None:
                        p = pkg_of_ann(a.annotation)
                        if p:
                            env[a.arg] = p
                for st in ast.walk(child):
                    if isinstance(st, ast.Assign):
                        p = pkg_of_value(st.value)
                        if p:
                            for t in st.targets:
                                if isinstance(t, ast.Name):
                                    env[t.id] = p
                    elif isinstance(st, (ast.With, ast.AsyncWith)):
                        for item in st.items:
                            p = pkg_of_value(item.context_expr)
                            if p and isinstance(item.optional_vars, ast.Name):
                                env[item.optional_vars.id] = p
                    elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                        p = pkg_of_ann(st.annotation) or pkg_of_value(st.value)
                        if p:
                            env[st.target.id] = p
                lines = {child.lineno}
                if child.decorator_list:
                    lines.add(child.decorator_list[0].lineno)
                for ln in lines:
                    funcs.setdefault(ln, env)
                visit(child, inherited)
            else:
                visit(child, inherited)

    visit(tree, {})
    return table, funcs


def _ts_root_name(n, src: bytes) -> str | None:
    while n is not None:
        t = n.type
        if t == "identifier":
            return _text(n, src)
        if t == "member_expression":
            n = n.child_by_field_name("object")
        elif t == "call_expression":
            n = n.child_by_field_name("function")
        elif t == "new_expression":
            n = n.child_by_field_name("constructor")
        elif t in ("await_expression", "parenthesized_expression", "non_null_expression"):
            n = n.named_children[0] if n.named_children else None
        else:
            return None
    return None


def _ts_env(file: str, src: bytes) -> tuple[dict[str, str], dict[int, dict[str, str]]]:
    from app.core.codegraph.steps import _ts_defs

    root = _ts_root(file, src)
    table: dict[str, str] = {}
    for st in root.children:
        if st.type == "import_statement":
            source = st.child_by_field_name("source")
            spec = _string(source, src)
            pkg = _pkg_norm(spec) if spec else None
            if not pkg:
                continue
            for n in _walk(st):
                if n.type == "import_specifier":
                    alias = n.child_by_field_name("alias") or n.child_by_field_name("name")
                    if alias is not None:
                        table[_text(alias, src)] = pkg
                elif n.type == "namespace_import":
                    ident = next((c for c in n.named_children if c.type == "identifier"), None)
                    if ident is not None:
                        table[_text(ident, src)] = pkg
                elif n.type == "import_clause":
                    ident = next((c for c in n.named_children if c.type == "identifier"), None)
                    if ident is not None:
                        table[_text(ident, src)] = pkg
    for n in _walk(root):
        if n.type == "variable_declarator":
            val = n.child_by_field_name("value")
            name = n.child_by_field_name("name")
            if (
                val is None
                or name is None
                or name.type != "identifier"
                or val.type != "call_expression"
            ):
                continue
            f = val.child_by_field_name("function")
            if f is not None and _text(f, src) == "require":
                args = val.child_by_field_name("arguments")
                arg = args.named_children[0] if args is not None and args.named_children else None
                spec = _string(arg, src)
                pkg = _pkg_norm(spec) if spec else None
                if pkg:
                    table[_text(name, src)] = pkg

    def var_pkgs(scope) -> dict[str, str]:
        env: dict[str, str] = {}
        for n in _walk(scope):
            if n.type == "variable_declarator":
                name, val = n.child_by_field_name("name"), n.child_by_field_name("value")
                if name is None or val is None or name.type != "identifier":
                    continue
                r = _ts_root_name(val, src)
                if r is not None and r in table:
                    env[_text(name, src)] = table[r]
            elif n.type in ("required_parameter", "optional_parameter"):
                pat, ty = n.child_by_field_name("pattern"), n.child_by_field_name("type")
                if pat is None or ty is None or pat.type != "identifier":
                    continue
                hit = next(
                    (
                        _text(c, src)
                        for c in _walk(ty)
                        if c.type == "type_identifier" and _text(c, src) in table
                    ),
                    None,
                )
                if hit:
                    env[_text(pat, src)] = table[hit]
        return env

    module_env: dict[str, str] = {}
    for st in root.children:
        target = st.named_children[0] if st.type == "export_statement" and st.named_children else st
        if target.type in ("lexical_declaration", "variable_declaration"):
            module_env.update(var_pkgs(target))
    funcs: dict[int, dict[str, str]] = {}
    for ln, node in _ts_defs(root).items():
        env = dict(module_env)
        env.update(var_pkgs(node))
        funcs[ln] = env
    return table, funcs


def _string(n, src: bytes) -> str | None:
    if n is None or n.type != "string":
        return None
    return "".join(_text(c, src) for c in n.named_children if c.type == "string_fragment")


def _rs_env(src: bytes) -> tuple[dict[str, str], dict[int, dict[str, str]]]:
    from app.core.codegraph.steps import _rs_defs

    root = _rs_root(src)
    table: dict[str, str] = {}

    def use_names(n, crate: str | None) -> None:
        t = n.type
        if t == "use_as_clause":
            path, alias = n.child_by_field_name("path"), n.child_by_field_name("alias")
            first = _text(path, src).split("::")[0] if path is not None else None
            c = crate or first
            if alias is not None and c:
                table[_text(alias, src)] = c
            if c:
                table[c] = c
        elif t == "scoped_use_list":
            path = n.child_by_field_name("path")
            c = crate or (_text(path, src).split("::")[0] if path is not None else None)
            lst = n.child_by_field_name("list")
            if c:
                table[c] = c
            if lst is not None:
                for ch in lst.named_children:
                    use_names(ch, c)
        elif t == "use_list":
            for ch in n.named_children:
                use_names(ch, crate)
        elif t in ("scoped_identifier", "identifier"):
            parts = _text(n, src).split("::")
            c = crate or parts[0]
            if c in ("crate", "self", "super"):
                return
            table[parts[-1]] = c
            table[c] = c

    for st in root.children:
        if st.type == "use_declaration":
            arg = st.child_by_field_name("argument")
            if arg is not None:
                use_names(arg, None)

    def root_name(n) -> str | None:
        while n is not None:
            t = n.type
            if t == "identifier":
                return _text(n, src)
            if t == "scoped_identifier":
                return _text(n, src).split("::")[0]
            if t == "field_expression":
                n = n.child_by_field_name("value")
            elif t == "call_expression":
                n = n.child_by_field_name("function")
            elif t in (
                "await_expression",
                "try_expression",
                "reference_expression",
                "parenthesized_expression",
            ):
                n = n.named_children[0] if n.named_children else None
            elif t == "generic_function":
                n = n.child_by_field_name("function")
            else:
                return None
        return None

    funcs: dict[int, dict[str, str]] = {}
    for ln, fn in _rs_defs(root).items():
        env: dict[str, str] = {}
        params = fn.child_by_field_name("parameters")
        if params is not None:
            for p in params.named_children:
                if p.type != "parameter":
                    continue
                pat, ty = p.child_by_field_name("pattern"), p.child_by_field_name("type")
                if pat is None or ty is None:
                    continue
                hit = next(
                    (
                        _text(c, src)
                        for c in _walk(ty)
                        if c.type == "type_identifier" and _text(c, src) in table
                    ),
                    None,
                )
                if hit:
                    env[_text(pat, src)] = table[hit]
        body = fn.child_by_field_name("body")
        if body is not None:
            for n in _walk(body):
                if n.type == "let_declaration":
                    pat, val = n.child_by_field_name("pattern"), n.child_by_field_name("value")
                    if pat is None or val is None or pat.type != "identifier":
                        continue
                    r = root_name(val)
                    if r is not None and r in table:
                        env[_text(pat, src)] = table[r]
        funcs[ln] = env
    return table, funcs


def _java_repos(src_dir: Path, files: list[str]) -> dict[str, str]:
    """저장소 인터페이스 → LIBS 키 — `interface R extends JpaRepository<…>` (REPO_BASES 첫 줄)."""
    from app.core.codegraph.javago import _jtype, _parse

    out: dict[str, str] = {}
    for file in files:
        src = _read(src_dir, file)
        if src is None:
            continue
        for n in _walk(_parse("java", src)):
            if n.type != "interface_declaration":
                continue
            name = n.child_by_field_name("name")
            ext = next((c for c in n.named_children if c.type == "extends_interfaces"), None)
            if name is None or ext is None:
                continue
            bases = [b for t in _walk(ext) if t.type in ("type_identifier", "generic_type",
                     "scoped_type_identifier") and t.parent is not None
                     and t.parent.type == "type_list" and (b := _jtype(t, src))]  # fmt: skip
            hit = next(
                (lib for pat, lib in REPO_BASES for b in bases if re.search(pat, b, A)), None
            )
            if hit:
                out.setdefault(_text(name, src), hit)
    return out


def _java_env(
    src: bytes, known: dict[str, str]
) -> tuple[dict[str, str], dict[int, dict[str, str]]]:
    """Java — 정의 첫 줄 → {변수: LIBS 키}. 둘러싼 클래스의 필드·매개변수·지역 변수의 타입이
    `known`(JAVA_TYPES와 저장소 인터페이스)에 있을 때. 파일 표는 비어 있다."""
    from app.core.codegraph.javago import _java_locals, _jtype, _parse

    funcs: dict[int, dict[str, str]] = {}
    for cls in _walk(_parse("java", src)):
        if cls.type not in ("class_declaration", "enum_declaration", "record_declaration"):
            continue
        body = cls.child_by_field_name("body")
        if body is None:
            continue
        fields: dict[str, str] = {}
        for m in body.named_children:
            if m.type != "field_declaration":
                continue
            t = _jtype(m.child_by_field_name("type"), src)
            for d in m.named_children:
                dn = d.child_by_field_name("name") if d.type == "variable_declarator" else None
                if t in known and dn is not None:
                    fields[_text(dn, src)] = known[t]
        for m in body.named_children:
            if m.type not in ("method_declaration", "constructor_declaration"):
                continue
            if m.child_by_field_name("body") is None:
                continue
            env = dict(fields)
            for v, t in _java_locals(m, src).items():
                if t in known:
                    env[v] = known[t]
            funcs.setdefault(m.start_point[0] + 1, env)
    return {}, funcs


def _go_path(path: str) -> str:
    """Go import 경로의 `/vN` 조각을 뗀다 — `github.com/redis/go-redis/v9` → `…/go-redis`."""
    return re.sub(r"/v\d+(?=/|$)", "", path)


# 패키지 이름이 경로의 마지막 조각에서 안 나오는 것
GO_NAMES = {"github.com/rabbitmq/amqp091-go": "amqp",
            "github.com/anthropics/anthropic-sdk-go": "anthropic"}  # fmt: skip


def _go_name(path: str) -> str:
    """import 경로 → 패키지 이름 — `/vN`을 떼고 GO_NAMES, 아니면 마지막 조각.

    마지막 조각은 앞 `go-`·뒤 `-go`를 뗀다(`go-openai` → openai · `kafka-go` → kafka).
    """
    path = _go_path(path)
    if path in GO_NAMES:
        return GO_NAMES[path]
    last = path.rsplit("/", 1)[-1]
    last = last[3:] if last.startswith("go-") else last
    return last[:-3] if last.endswith("-go") else last


def _go_env(src: bytes) -> tuple[dict[str, str], dict[int, dict[str, str]]]:
    """Go — import 표 {이름: 경로}와 정의 줄 → {변수: 경로}. 매개변수·`var x T`의 타입 `p.T`,
    `x := p.F(…)`·`x := &p.T{…}`의 맨 앞 이름, 받는 쪽 구조체(같은 파일)의 필드 `r.f`."""
    from app.core.codegraph.javago import _parse

    root = _parse("go", src)
    table: dict[str, str] = {}
    structs: dict[str, dict[str, str]] = {}
    for c in root.named_children:
        if c.type == "import_declaration":
            for spec in _walk(c):
                if spec.type != "import_spec":
                    continue
                path_node, alias = (
                    spec.child_by_field_name("path"),
                    spec.child_by_field_name("name"),
                )
                if path_node is None:
                    continue
                path = _text(path_node, src).strip('"`')
                name = _text(alias, src) if alias is not None else _go_name(path)
                if name not in ("_", "."):
                    table[name] = _go_path(path)

    def pkg_of_type(t) -> str | None:
        while t is not None and t.type in ("pointer_type", "generic_type", "parenthesized_type"):
            t = t.named_children[0] if t.named_children else None
        if t is None or t.type != "qualified_type":
            return None
        pk = t.child_by_field_name("package")
        return table.get(_text(pk, src)) if pk is not None else None

    def pkg_of_value(v) -> str | None:
        while v is not None:
            if v.type == "unary_expression":
                v = v.child_by_field_name("operand")
            elif v.type == "composite_literal":
                return pkg_of_type(v.child_by_field_name("type"))
            elif v.type == "call_expression":
                v = v.child_by_field_name("function")
            elif v.type == "selector_expression":
                v = v.child_by_field_name("operand")
            elif v.type == "identifier":
                return table.get(_text(v, src))
            else:
                return None
        return None

    for c in root.named_children:
        if c.type != "type_declaration":
            continue
        for spec in c.named_children:
            if spec.type != "type_spec":
                continue
            name, ty = spec.child_by_field_name("name"), spec.child_by_field_name("type")
            if name is None or ty is None or ty.type != "struct_type":
                continue
            fields: dict[str, str] = {}
            for fd in _walk(ty):
                if fd.type != "field_declaration":
                    continue
                pkg = pkg_of_type(fd.child_by_field_name("type"))
                for nm in fd.named_children:
                    if nm.type == "field_identifier" and pkg:
                        fields[_text(nm, src)] = pkg
            structs[_text(name, src)] = fields

    funcs: dict[int, dict[str, str]] = {}
    for fn in root.named_children:
        if fn.type not in ("function_declaration", "method_declaration"):
            continue
        env: dict[str, str] = {}
        recv = fn.child_by_field_name("receiver") if fn.type == "method_declaration" else None
        for p in recv.named_children if recv is not None else []:
            if p.type != "parameter_declaration":
                continue
            rn, rt = p.child_by_field_name("name"), p.child_by_field_name("type")
            while rt is not None and rt.type in ("pointer_type", "generic_type"):
                rt = rt.named_children[0] if rt.named_children else None
            if rn is not None and rt is not None and rt.type == "type_identifier":
                for f_, pkg in structs.get(_text(rt, src), {}).items():
                    env[f"{_text(rn, src)}.{f_}"] = pkg
        params = fn.child_by_field_name("parameters")
        for p in params.named_children if params is not None else []:
            if p.type != "parameter_declaration":
                continue
            pkg = pkg_of_type(p.child_by_field_name("type"))
            for nm in p.named_children:
                if nm.type == "identifier" and pkg:
                    env[_text(nm, src)] = pkg
        body = fn.child_by_field_name("body")
        for n in _walk(body) if body is not None else []:
            if n.type == "short_var_declaration":
                left, right = n.child_by_field_name("left"), n.child_by_field_name("right")
                names = [x for x in left.named_children] if left is not None else []
                vals = [x for x in right.named_children] if right is not None else []
                if names and vals and names[0].type == "identifier":
                    pkg = pkg_of_value(vals[0])
                    if pkg:
                        env[_text(names[0], src)] = pkg
            elif n.type == "var_spec":
                pkg = pkg_of_type(n.child_by_field_name("type"))
                if pkg is None:
                    val = n.child_by_field_name("value")
                    pkg = (
                        pkg_of_value(val.named_children[0])
                        if val is not None and val.named_children
                        else None
                    )
                for nm in n.named_children:
                    if nm.type == "identifier" and pkg:
                        env[_text(nm, src)] = pkg
                        break
        funcs.setdefault(fn.start_point[0] + 1, env)
    return table, funcs


def _label_root(label: str, lang: str) -> str | None:
    m = _IDENT.match(label)
    if not m:
        return None
    root = m.group(0)
    if lang == "java" and root == "this" and label.startswith("this."):
        m2 = _IDENT.match(label[5:])
        return m2.group(0) if m2 else None
    if lang == "py" and root == "self" and label.startswith("self."):
        m2 = _IDENT.match(label[5:])
        if m2:
            return f"self.{m2.group(0)}"
    return root


# ---------------------------------------------------------------- 설정 읽기


def _deps(src_dir: Path) -> list[tuple[str, str]]:
    """깊이 3까지 의존성 목록 — [(이름, 파일)], 걷는 차례."""
    out: list[tuple[str, str]] = []

    def visit(path: Path, rel: str, depth: int) -> None:
        for e in _entries(path):
            full = Path(e.path)
            r = f"{rel}/{e.name}" if rel else e.name
            if e.is_dir(follow_symlinks=False):
                if (
                    depth < 3
                    and not e.name.startswith(".")
                    and e.name not in _SKIP
                    and not re.match(r"^(tests?|examples?|fixtures|docs)$", e.name)
                ):
                    visit(full, r, depth + 1)
                continue
            names: list[str] = []
            name = e.name
            if name == "package.json":
                text = _text_of(full)
                try:
                    pkg = json.loads(text) if text is not None else None
                except ValueError:
                    continue
                deps = pkg.get("dependencies") if isinstance(pkg, dict) else None
                deps = list(deps) if isinstance(deps, dict) else []
                if any(FRONT_ONLY.match(d) for d in deps) and not any(
                    SERVER_DEPS.match(d) for d in deps
                ):
                    continue
                names = deps
            elif name == "Cargo.toml":
                text = _text_of(full) or ""
                for table, keys in _toml_tables(text).items():
                    if table.endswith("dependencies"):
                        names.extend(keys)
            elif name == "pyproject.toml":
                text = _text_of(full) or ""
                m = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.M | re.S)
                if m:
                    for q in re.findall(r"[\"']([^\"']+)[\"']", m.group(1)):
                        nm = re.match(r"^\s*([A-Za-z0-9_.-]+)", q, A)
                        if nm:
                            names.append(nm.group(1))
            elif name == "pom.xml":
                text = _text_of(full) or ""
                pom = r"<dependency>[\s\S]*?<groupId>([^<]+)</groupId>[\s\S]*?<artifactId>([^<]+)<"
                for m in re.finditer(pom, text):
                    names.append(f"{m.group(1).strip()}:{m.group(2).strip()}")
            elif name in ("build.gradle", "build.gradle.kts"):
                text = _text_of(full) or ""
                for m in re.finditer(r"(?:implementation|api|runtimeOnly|compileOnly)\s*\(?\s*"
                                     r"[\"']([\w.-]+):([\w.-]+)", text, A):  # fmt: skip
                    names.append(f"{m.group(1)}:{m.group(2)}")
            elif name == "go.mod":
                text = _text_of(full) or ""
                for m in re.finditer(r"^\s*(?:require\s+)?([\w.-]+\.[\w.-]+/[\w./-]+)\s+v[\d.]",
                                     text, re.M | A):  # fmt: skip
                    names.append(m.group(1))
            elif re.match(r"^requirements[^/]*\.txt$", name):
                text = _text_of(full) or ""
                for line in text.splitlines():
                    line = line.strip()
                    if not line or line.startswith(("#", "-")):
                        continue
                    nm = re.match(r"^([A-Za-z0-9_.-]+)", line, A)
                    if nm:
                        names.append(nm.group(1))
            else:
                continue
            seen: set[str] = set()
            for n in names:
                if n not in seen:
                    seen.add(n)
                    out.append((n, r))

    visit(src_dir, "", 0)
    return out


def parse_compose(text: str) -> list[dict]:
    """docker-compose의 services만 — 이름·image·이 PC에 연 포트 (view_arc parseCompose)."""
    out: list[dict] = []
    in_services = False
    svc_indent = -1
    cur: dict | None = None
    in_ports = False
    for raw in re.split(r"\r?\n", text):
        line = re.sub(r"\s+#.*$", "", raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        t = line.strip()
        if indent == 0:
            in_services = t == "services:"
            cur = None
            continue
        if not in_services:
            continue
        if svc_indent < 0:
            svc_indent = indent
        if indent == svc_indent and re.match(r"^[\w.-]+:\s*$", t, A):
            cur = {"name": t[:-1], "image": None, "ports": []}
            out.append(cur)
            in_ports = False
            continue
        if cur is None:
            continue
        if indent == svc_indent + 2 or (
            indent > svc_indent and re.match(r"^[a-z_]+:", t) and not t.startswith("-")
        ):  # noqa: E501
            in_ports = re.match(r"^ports:\s*$", t) is not None
        m = re.match(r"^image:\s*[\"']?([^\"'\s]+)", t)
        if m:
            cur["image"] = m.group(1)
        if in_ports and t.startswith("-"):
            spec = re.sub(r"[\"']$", "", re.sub(r"^-\s*[\"']?", "", t))
            parts = spec.split(":")
            try:
                port = int(parts[-2] if len(parts) >= 2 else parts[0])
            except ValueError:
                continue
            cur["ports"].append(port)
    return out


def _env_pairs(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in _config_entries(".env", text):
        out[e[0]] = re.sub(r"^[\"']|[\"']$", "", e[1])
    return out


def _compose_vars(env: dict[str, str], text: str) -> str:
    def braced(m: re.Match) -> str:
        return env.get(m.group(1)) or (m.group(2) or "")

    text = re.sub(r"\$\{(\w+)(?::?-([^}]*))?\}", braced, text, flags=A)
    return re.sub(r"\$(\w+)", lambda m: env.get(m.group(1), m.group(0)), text, flags=A)


def _defaults(text: str) -> str:
    return re.sub(r"\$\{[\w.]+:-?([^}]*)\}", r"\1", text, flags=A)


def _config_entries(file: str, text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if re.search(r"\.ya?ml$", file):
        stack: list[tuple[int, str]] = []
        for raw in re.split(r"\r?\n", text):
            m = re.match(r"^(\s*)([\w.-]+)\s*:\s*(.*?)\s*(?:\s#.*)?$", raw, A)
            if not m or raw.strip().startswith("#"):
                continue
            indent = len(m.group(1))
            while stack and stack[-1][0] >= indent:
                stack.pop()
            key = ".".join([k for _, k in stack] + [m.group(2)])
            if m.group(3):
                out.append((key, m.group(3)))
            else:
                stack.append((indent, m.group(2)))
        return out
    for raw in re.split(r"\r?\n", text):
        m = re.match(r"^\s*(?:export\s+)?([\w.-]+)\s*[=:]\s*(.*?)\s*$", raw, A)
        if m and not raw.strip().startswith("#"):
            out.append((m.group(1), m.group(2)))
    return out


def _config_files(src_dir: Path) -> list[tuple[Path, int]]:
    out: list[tuple[Path, int]] = []
    for d in [src_dir, *(src_dir / n for n in _dirs(src_dir))]:
        for n in (".env", ".env.local", ".env.development"):
            if (d / n).is_file():
                out.append((d / n, 4))
        for n in (".env.example", ".env.sample", ".env.template"):
            if (d / n).is_file():
                out.append((d / n, 1))

    def walk(path: Path, depth: int) -> None:
        if depth > 7:
            return
        for e in _entries(path):
            if e.name.startswith(".") or e.name in _CONFIG_SKIP:
                continue
            full = Path(e.path)
            if e.is_dir(follow_symlinks=False):
                walk(full, depth + 1)
            elif re.match(r"^(config|settings|conf)\.py$", e.name):
                out.append((full, 3))
            elif re.match(
                r"^(application|bootstrap)(-[\w.]+)?\.(ya?ml|properties)$", e.name, A
            ) and not re.search(r"(^|/)test/", _rel(src_dir, full)):
                out.append((full, 3))

    walk(src_dir, 0)
    return out


def _host_of(scheme: str, rest: str) -> tuple[str, int | None, str] | None:
    if scheme.startswith("sqlite"):
        file = re.sub(r"^/+", "", rest).split("?")[0]
        return ("file", None, posixpath.basename(file) if file else "메모리")
    authority = re.split(r"[/?#]", rest)[0].split("@")[-1]
    m = re.match(r"^\[?([^\]:]+)\]?(?::(\d+))?$", authority.split(",")[0], A)
    if (
        not m
        or not m.group(1)
        or "{" in m.group(1)
        or "$" in m.group(1)
        or PLACEHOLDER.match(m.group(1))
    ):  # noqa: E501
        return None
    port = int(m.group(2)) if m.group(2) else None
    return (m.group(1), port, f"{m.group(1)}:{port}" if port else m.group(1))


def _orm_files(src_dir: Path) -> list[Path]:
    dirs = [src_dir]
    subs = [src_dir / n for n in _dirs(src_dir)]
    dirs += subs
    for s in subs:
        dirs += [s / n for n in _dirs(s)]
    out: list[Path] = []
    for d in dirs:
        for n in (
            "schema.prisma",
            "prisma/schema.prisma",
            "drizzle.config.ts",
            "drizzle.config.js",
            "drizzle.config.mjs",
        ):
            p = d / n
            if p.is_file() and p not in out:
                out.append(p)
    return out


def _better(a: str, b: str) -> str:
    def score(s: str) -> int:
        return 0 if s == "DB" else len(s)

    return b if score(b) > score(a) else a


# ---------------------------------------------------------------- 묶기


def infra(src_dir: Path, graph: dict) -> dict:
    """SYNC-MS-024#infra.infra

    장비(코드 호출·의존성·compose·설정 주소·ORM)와 연결 — `graph["infra"] = {nodes, links}`.
    호출 순서 중 장비로 가는 호출에 `infra`를 단다. 주소는 호스트·포트만.
    """
    from app.core.codegraph.routes import _is_front

    funcs = graph["functions"]
    unit_list = graph.get("units", [])
    web_dirs = [u["dir"] for u in unit_list if u.get("kind") == "web"]
    idents = graph.get("_idents", {})
    found: dict[str, dict] = {}
    seen_at: dict[str, list[str]] = {}

    def at(fid: str, file: str) -> None:
        lst = seen_at.setdefault(fid, [])
        if file not in lst:
            lst.append(file)

    def add(
        fid: str,
        kind: str,
        name: str,
        where: str | None,
        host: str | None,
        evidence: list[str],
        protocol: str | None,
        rank: int,
    ) -> None:
        cur = found.get(fid)
        if cur is None:
            found[fid] = {
                "id": fid,
                "kind": kind,
                "name": name,
                "where": where,
                "host": host,
                "evidence": list(evidence),
                "protocol": protocol,
                "rank": rank,
            }
            return
        for e in evidence:
            if e not in cur["evidence"]:
                cur["evidence"].append(e)
        if rank > cur["rank"]:
            cur["where"] = where if where is not None else cur["where"]
            cur["host"] = host if host is not None else cur["host"]
            cur["rank"] = rank
        elif cur["host"] is None and host is not None:
            cur["host"] = host  # 주소가 비어 있으면 순위가 낮아도 채운다
        cur["name"] = _better(cur["name"], name)
        if cur["protocol"] is None:
            cur["protocol"] = protocol

    # 1·2. 코드 — 호출 순서에 장비를 단다
    java_files = sorted(
        {x["path"] for x in graph.get("files", []) if x["path"].endswith(".java")},
        key=lambda x: x.encode("utf-8"),
    )
    java_known = {**JAVA_TYPES, **_java_repos(src_dir, java_files)}
    envs: dict[str, tuple[dict, dict]] = {}
    files_of: dict[str, list[str]] = {}
    libs_of: dict[str, list[str]] = {}
    for f in funcs:
        file = f["file"]
        lang = (
            "py"
            if file.endswith(_PY_EXTS)
            else "ts"
            if file.endswith(_TS_EXTS)
            else "rs"
            if file.endswith(".rs")
            else "java"
            if file.endswith(".java")
            else "go"
            if file.endswith(".go")
            else None
        )  # noqa: E501
        if lang is None or NOT_APP.search(file) or _is_front(file, web_dirs):
            continue
        if file not in envs:
            src = _read(src_dir, file)
            try:
                if src is None:
                    raise ValueError
                text = src.decode("utf-8")
                envs[file] = (
                    _py_env(text)
                    if lang == "py"
                    else _ts_env(file, src)
                    if lang == "ts"
                    else _rs_env(src)
                    if lang == "rs"
                    else _java_env(src, java_known)
                    if lang == "java"
                    else _go_env(src)
                )
            except (SyntaxError, ValueError):
                envs[file] = ({}, {})
        table, fenv = envs[file]
        env = fenv.get(f["line"], {})
        ids = idents.get(f["key"], [])
        for i, st in enumerate(f.get("steps", [])):
            if st["k"] != "call" or "to" in st:
                continue
            root = _label_root(st["label"], lang)
            if root is None:
                continue
            two = re.match(r"^([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)", st["label"], A)
            pkg = (
                (env.get(two.group(1)) if lang == "go" and two else None)
                or env.get(root)
                or table.get(root)
            )
            if pkg is None and lang == "ts" and root == "fetch":
                pkg = "fetch"
            lib = LIBS.get(pkg) if pkg else None
            ident = ids[i] if i < len(ids) else None
            if lib is None or ident is None or not re.search(lib[3], ident, A):
                continue
            st["infra"] = f"infra:{lib[0]}"
            lst = libs_of.setdefault(lib[0], [])
            if pkg not in lst:
                lst.append(pkg)
            fl = files_of.setdefault(lib[0], [])
            if file not in fl:
                fl.append(file)
    for fid, fl in files_of.items():
        lib = next(v for v in LIBS.values() if v[0] == fid)
        more = f" 외 {len(fl) - 1}개 파일" if len(fl) > 1 else ""
        ev = f"코드: {', '.join(libs_of.get(fid, [])) or lib[2]} — {fl[0]}{more}"
        add(fid, lib[1], lib[2], "external" if lib[1] == "api" else None, None, [ev], lib[4], 1)
        for x in fl:
            at(fid, x)

    # 3. 의존성
    for dep, dfile in _deps(src_dir):
        hit = next((d for d in DEPS if re.search(d[0], dep, A | re.I)), None)
        if hit is None:
            continue
        _, fid, kind, name, protocol = hit
        where = "external" if kind == "api" or fid == "supabase" else None
        add(fid, kind, name, where, None, [f"의존성: {dep} — {dfile}"], protocol, 1)
        at(fid, dfile)

    # 4. docker-compose
    compose_hosts: dict[str, str] = {}
    published: dict[int, str] = {}
    for d in [src_dir, *(src_dir / n for n in _dirs(src_dir))]:
        for n in _COMPOSE:
            p = d / n
            if not p.is_file():
                continue
            text = _text_of(p) or ""
            env_text = _text_of(d / ".env")
            env = _env_pairs(env_text) if env_text is not None else {}
            for svc in parse_compose(_compose_vars(env, text)):
                hit = next((i for i in IMAGES if re.search(i[0], svc["image"] or "", A)), None)
                if hit is None:
                    continue
                _, fid, kind, name = hit
                compose_hosts[svc["name"]] = fid
                for port in svc["ports"]:
                    published[port] = fid
                ports = f", 포트 {', '.join(str(x) for x in svc['ports'])}" if svc["ports"] else ""
                ev = f"docker-compose: {svc['name']} ({svc['image']}{ports}) — {_rel(src_dir, p)}"
                add(fid, kind, name, "container", None, [ev], None, 2)

    # 5. 설정 주소
    def where_of(scheme: str, host: str, port: int | None) -> str:
        if scheme.startswith("sqlite"):
            return "local"
        if host in compose_hosts or (host in LOCAL_HOSTS and port and port in published):
            return "container"
        return "local" if host in LOCAL_HOSTS else "external"

    def from_url(key: str, scheme: str, rest: str, rel: str, rank: int) -> None:
        parsed = _host_of(scheme, rest)
        hit = next((s for s in SCHEMES if re.search(s[0], scheme, A)), None)
        if hit is None and re.match(r"^https?$", scheme):
            hit = next((h for h in HTTP_KEYS if re.search(h[0], key, A | re.I)), None)
        if hit is None or parsed is None:
            return
        _, fid, kind, name = hit
        ev = f"설정: {rel}{' ' + key if key else ''} → {parsed[2]}"
        add(fid, kind, name, where_of(scheme, parsed[0], parsed[1]), parsed[2], [ev], None, rank)
        at(fid, rel)

    url_any = re.compile(
        r"(?:^|[\"'\s=:])([A-Z][A-Z0-9_]*)?\s*[=:,(]?\s*[\"']?([a-z][a-z0-9+.-]*)://([^\s\"'`]*)",
        re.M | A,
    )  # noqa: E501
    for path, rank in _config_files(src_dir):
        rel = _rel(src_dir, path)
        raw = _text_of(path)
        if raw is None:
            continue
        text = _defaults(raw)
        if re.search(r"\.(ya?ml|properties)$|(^|/)\.env[^/]*$", path.as_posix()):
            entries = _config_entries(path.name, text)
            by_key = {k.lower(): v for k, v in entries}
            for key, value in entries:
                url = re.match(
                    r"^[\"']?(?:jdbc:)?([a-z][a-z0-9+.-]*)://([^\s\"'`]*)", value, A | re.I
                )
                if url:
                    from_url(key, url.group(1).lower(), url.group(2), rel, rank)
                    continue
                hk = re.match(r"^(.*?)[._-]?host(name)?$", key, A | re.I)
                if not hk:
                    continue
                hit = next((h for h in HOST_KEYS if re.search(h[0], hk.group(1), A | re.I)), None)
                host = re.sub(r"^[\"']|[\"']$", "", value).strip()
                if hit is None or not host or re.search(r"[\s/$]", host) or PLACEHOLDER.match(host):
                    continue
                port_key = hk.group(1) + re.sub(
                    r"host(name)?$", "port", key[len(hk.group(1)) :], flags=re.I
                )  # noqa: E501
                port_raw = by_key.get(port_key.lower())
                port = (
                    int(port_raw.strip())
                    if port_raw and re.match(r"^\d+$", port_raw.strip())
                    else None
                )
                _, fid, kind, name = hit
                label = f"{host}:{port}" if port else host
                add(
                    fid,
                    kind,
                    name,
                    where_of("", host, port),
                    label,
                    [f"설정: {rel} {key} → {label}"],
                    None,
                    rank,
                )
                at(fid, rel)
        else:
            for m in url_any.finditer(text):
                from_url(m.group(1) or "", m.group(2).lower(), m.group(3), rel, rank)

    # 6. ORM
    orm_names = {
        "postgresql": "PostgreSQL",
        "postgres": "PostgreSQL",
        "mysql": "MySQL",
        "sqlite": "SQLite",
        "mongodb": "MongoDB",
        "sqlserver": "SQL Server",
        "cockroachdb": "CockroachDB",
    }
    for path in _orm_files(src_dir):
        text = _text_of(path) or ""
        i = text.find("datasource")
        # view_arc: text.slice(text.indexOf('datasource')) — 없으면 마지막 한 글자
        m = re.search(r'provider\s*=\s*"(\w+)"', text[i:] if i >= 0 else text[-1:], A)
        kind = m.group(1) if m else None
        if kind is None:
            m2 = re.search(r"dialect\s*:\s*[\"'](\w+)[\"']", text)
            kind = m2.group(1) if m2 else None
        name = orm_names.get(kind or "")
        if name:
            rel = _rel(src_dir, path)
            add(
                "mongo" if kind == "mongodb" else "db",
                "db",
                name,
                None,
                None,
                [f"ORM 설정: {rel} ({kind})"],
                "SQL",
                1,
            )
            at("mongo" if kind == "mongodb" else "db", rel)

    # 8. 노드
    front_fns = any(_is_front(f["file"], web_dirs) for f in funcs)
    back_fns = any(
        not _is_front(f["file"], web_dirs)
        and f["file"].endswith(_PY_EXTS + _TS_EXTS + (".rs", ".java", ".go"))
        for f in funcs
    )
    nodes: list[dict] = []
    has_browser = front_fns or bool(web_dirs)
    if has_browser:
        nodes.append(
            {
                "id": "infra:browser",
                "kind": "browser",
                "name": "브라우저",
                "where": "local",
                "host": None,
                "evidence": ["화면 코드가 브라우저에서 돈다"],
                "dir": None,
            }
        )
    servers = [
        {
            "id": f"infra:server:{u['name']}",
            "kind": "backend",
            "name": f"{u['framework']} 서버",
            "where": "local",
            "host": f"localhost:{u['port']}" if u.get("port") else None,
            "evidence": [f"{u['framework']} — {u['dir'] or '루트'}"],
            "dir": u["dir"],
        }
        for u in unit_list
        if u.get("kind") == "server"
    ]
    if back_fns and not servers:
        servers = [
            {
                "id": "infra:backend",
                "kind": "backend",
                "name": "백엔드 서버",
                "where": "local",
                "host": None,
                "evidence": ["백엔드 코드가 이 PC에서 돈다"],
                "dir": "",
            }
        ]
    nodes.extend(servers)
    for fid in sorted(found, key=lambda x: x.encode("utf-8")):
        fd = found[fid]
        nodes.append(
            {
                "id": f"infra:{fid}",
                "kind": fd["kind"],
                "name": fd["name"],
                "where": fd["where"] or ("external" if fd["kind"] == "api" else "local"),
                "host": fd["host"],
                "evidence": fd["evidence"],
                "dir": None,
            }
        )

    # 9. 선
    def server_of(file: str) -> dict | None:
        best = None
        for s in servers:
            d = s["dir"] or ""
            if d and file != d and not file.startswith(d + "/"):
                continue
            if best is None or len(d) > len(best["dir"] or ""):
                best = s
        return best

    links: list[dict] = []
    if servers:
        if has_browser:
            by_key = {f["key"]: f for f in funcs}
            called = {
                server_of(by_key[h["to"]]["file"])["id"]
                for h in graph.get("http", [])
                if h["to"] in by_key and server_of(by_key[h["to"]]["file"]) is not None
            }
            for s in servers:
                if not called or s["id"] in called:
                    links.append({"from": "infra:browser", "to": s["id"], "protocol": "HTTP"})
        for fid in sorted(found, key=lambda x: x.encode("utf-8")):
            fd = found[fid]
            protocol = fd["protocol"] or next((v[4] for v in LIBS.values() if v[0] == fid), "")
            users = {s["id"] for x in seen_at.get(fid, []) if (s := server_of(x)) is not None}
            for s in servers:
                if not users or s["id"] in users or len(servers) == 1:
                    links.append({"from": s["id"], "to": f"infra:{fid}", "protocol": protocol})
    graph["infra"] = {"nodes": nodes, "links": links}
    return graph
