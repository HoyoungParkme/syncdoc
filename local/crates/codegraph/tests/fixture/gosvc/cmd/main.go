package main

import (
	"net/http"

	st "example.com/shop/store"
	"example.com/shop/util"
)

// SYNC-MS-001#svc.hello
// 둘째 줄은 항목이 아니다
func hello(w http.ResponseWriter, r *http.Request) {
	s := &st.Store{}
	_ = s
	st.Open()
	util.Clean()
	greet()
	var c Cart
	c.Add()
	go func() { greet() }()
}

func greet() {}

type Cart struct{}

func (c *Cart) Add() {
	c.Sum()
}

func (c Cart) Sum() int { return 0 }

func main() {
	http.HandleFunc("/hello", hello)
	h := Cart{}
	h.Add()
}
