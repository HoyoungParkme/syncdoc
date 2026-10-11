// API 손잡이 — 객체 리터럴의 메서드와 화살표
export const api = {
  get: (path: string) => fetch(path).then((r) => r.json()),
  post(path: string, body: unknown) {
    return fetch(path, { method: "POST", body: JSON.stringify(body) });
  },
  "del": function (path: string) {
    return fetch(path, { method: "DELETE" });
  },
};

export function joinPath(a: string, b: string): string {
  return `${a}/${b}`;
}
