package main

import (
	"database/sql"
	"fmt"
	"net/http"

	"github.com/redis/go-redis/v9"
)

type Server struct {
	db  *sql.DB
	rdb *redis.Client
}

// SYNC-MS-001#svc.hello
func (s *Server) hello(w http.ResponseWriter, r *http.Request) {
	name := r.PathValue("name")
	s.rdb.Incr(r.Context(), "hits")
	row := s.db.QueryRow("select 1")
	_ = row
	fmt.Fprintln(w, greet(name))
}

func greet(name string) string {
	return "hi " + name
}

func main() {
	s := &Server{}
	http.HandleFunc("GET /hello/{name}", s.hello)
	http.ListenAndServe(":8090", nil)
}
