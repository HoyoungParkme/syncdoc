package com.ex;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/items")
public class ItemController {
    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    /** SYNC-MS-001#items.read */
    @GetMapping("/{id}")
    public Item read(@PathVariable long id) {
        if (id < 0) {
            throw new IllegalArgumentException("bad");
        }
        return service.find(id);
    }

    @PostMapping
    public Item make(@RequestBody Item item) {
        return service.save(item);
    }
}
