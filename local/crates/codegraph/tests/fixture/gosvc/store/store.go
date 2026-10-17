package store

type Store struct{}

// Open — 가게를 연다
func Open() *Store { return &Store{} }

func (s *Store) Get(k string) string { return k }
