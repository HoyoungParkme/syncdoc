//! 파이썬 3.12 내장 `sum` — float는 Neumaier 보정 합이다(3.12부터). 시작 값 0(int) 뒤 첫 float로 넘어간다 (카드 L13).
//! networkx `modularity`가 군집 기여를 이것으로 더한다. 정답 `tests/golden/pyrandom.json`의 `sums`

/// `sum(xs)` — 모두 float인 목록
pub fn py_sum(xs: &[f64]) -> f64 {
    let Some((&first, rest)) = xs.split_first() else {
        return 0.0;
    };
    // 0(int) + 첫 float — 정수 0을 float로 바꿔 더한다
    let mut f = 0.0 + first;
    let mut c = 0.0f64;
    for &x in rest {
        let t = f + x;
        if f.abs() >= x.abs() {
            c += (f - t) + x;
        } else {
            c += (x - t) + f;
        }
        f = t;
    }
    if c != 0.0 && c.is_finite() {
        f += c;
    }
    f
}

#[cfg(test)]
mod tests {
    use super::*;

    fn float(hex: &str) -> f64 {
        f64::from_bits(u64::from_str_radix(hex, 16).expect("16진"))
    }

    #[test]
    fn sum_like_python_312() {
        let raw = include_str!("../tests/golden/pyrandom.json");
        let data: serde_json::Value = serde_json::from_str(raw).expect("정답");
        for (i, c) in data["sums"].as_array().expect("합").iter().enumerate() {
            let xs: Vec<f64> = c["xs"]
                .as_array()
                .expect("수")
                .iter()
                .map(|v| float(v.as_str().expect("16진")))
                .collect();
            let want = float(c["sum"].as_str().expect("합"));
            assert_eq!(py_sum(&xs).to_bits(), want.to_bits(), "사례 {i}");
        }
        assert_eq!(py_sum(&[0.1; 10]), 1.0);
    }
}
