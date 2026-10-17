import httpx


def helper(x):
    return x


class Svc:
    def __init__(self):
        self.client = httpx.Client()

    async def fetch(self, item_id):
        r = self.client.get(f"https://example.org/items/{item_id}")
        return r.json()
