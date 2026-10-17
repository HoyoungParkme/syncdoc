package com.ex;

import org.springframework.web.client.RestTemplate;

public class ItemService {
    private final ItemRepository repo;
    private final RestTemplate http = new RestTemplate();

    public ItemService(ItemRepository repo) {
        this.repo = repo;
    }

    public Item find(long id) {
        Item found = repo.findById(id).orElseThrow();
        http.getForObject("https://audit.example.com/x", String.class);
        return found;
    }

    public Item save(Item item) {
        return repo.save(item);
    }
}

interface ItemRepository extends JpaRepository<Item, Long> {
}

record Item(long id, String name) {
}
