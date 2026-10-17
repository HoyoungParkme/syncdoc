package com.ex.web;

import com.ex.svc.ItemService;

@RestController
public class ItemController {
    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    /**
     * SYNC-MS-001#items.read
     * 둘째 줄은 항목이 아니다
     */
    @GetMapping("/{id}")
    public Item read(long id) {
        Runnable r = new Runnable() {
            public void run() { helper(); }
        };
        var audit = new Audit();
        audit.log(id);
        this.service.find(id);
        Audit.stamp();
        return check(id);
    }

    // SYNC-MS-001#items.check
    private Item check(long id) {
        Helper h = null;
        h.go();
        return null;
    }

    static class Inner {
        void deep() { }
    }
}
