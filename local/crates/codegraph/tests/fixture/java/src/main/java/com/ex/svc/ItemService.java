package com.ex.svc;

public class ItemService {
    public Item find(long id) {
        return find(id, 0);
    }

    public Item find(long id, int v) {
        return null;
    }
}

class Audit {
    Audit() { }
    void log(long id) { }
    static void stamp() { }
}

interface Helper {
    void go();
    default void twice() { go(); go(); }
}
