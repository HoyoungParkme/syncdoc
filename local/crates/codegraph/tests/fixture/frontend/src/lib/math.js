// 계산 — JS
export function add(a, b) {
  return a + b;
}

export class Calc {
  sum() {
    return add(1, 2);
  }
}

export const twice = function (x) {
  return add(x, x);
};
