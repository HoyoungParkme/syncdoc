import redis


def go():
    redis.Redis().set("a", 1)
