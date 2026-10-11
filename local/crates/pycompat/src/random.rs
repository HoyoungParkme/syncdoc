//! 파이썬 3.12 `random.Random` — MT19937과 정수 씨앗(`init_by_array`), `getrandbits`·`shuffle` (카드 L13).
//! networkx Louvain(`seed=42`)이 노드를 섞는 차례를 같게 내려고 쓴다. 정답 `tests/golden/pyrandom.json`

const N: usize = 624;
const M: usize = 397;

/// `random.Random(seed)` — 정수 씨앗만
pub struct PyRandom {
    mt: [u32; N],
    index: usize,
}

impl PyRandom {
    /// 파이썬 `random_seed` — `abs(seed)`를 32비트 낱말(작은 것부터)로 `init_by_array`
    pub fn new(seed: u128) -> PyRandom {
        let mut key = Vec::new();
        let mut n = seed;
        loop {
            key.push((n & 0xffff_ffff) as u32);
            n >>= 32;
            if n == 0 {
                break;
            }
        }
        let mut r = PyRandom {
            mt: [0; N],
            index: N,
        };
        r.init_by_array(&key);
        r
    }

    fn init_genrand(&mut self, s: u32) {
        self.mt[0] = s;
        for i in 1..N {
            let prev = self.mt[i - 1];
            self.mt[i] = 1_812_433_253u32
                .wrapping_mul(prev ^ (prev >> 30))
                .wrapping_add(i as u32);
        }
        self.index = N;
    }

    fn init_by_array(&mut self, key: &[u32]) {
        self.init_genrand(19_650_218);
        let (mut i, mut j) = (1usize, 0usize);
        for _ in 0..N.max(key.len()) {
            let prev = self.mt[i - 1];
            self.mt[i] = (self.mt[i] ^ (prev ^ (prev >> 30)).wrapping_mul(1_664_525))
                .wrapping_add(key[j])
                .wrapping_add(j as u32);
            i += 1;
            j += 1;
            if i >= N {
                self.mt[0] = self.mt[N - 1];
                i = 1;
            }
            if j >= key.len() {
                j = 0;
            }
        }
        for _ in 0..N - 1 {
            let prev = self.mt[i - 1];
            self.mt[i] = (self.mt[i] ^ (prev ^ (prev >> 30)).wrapping_mul(1_566_083_941))
                .wrapping_sub(i as u32);
            i += 1;
            if i >= N {
                self.mt[0] = self.mt[N - 1];
                i = 1;
            }
        }
        self.mt[0] = 0x8000_0000;
    }

    fn genrand_u32(&mut self) -> u32 {
        const UPPER: u32 = 0x8000_0000;
        const LOWER: u32 = 0x7fff_ffff;
        const MATRIX: u32 = 0x9908_b0df;
        if self.index >= N {
            for k in 0..N {
                let y = (self.mt[k] & UPPER) | (self.mt[(k + 1) % N] & LOWER);
                let mag = if y & 1 == 1 { MATRIX } else { 0 };
                self.mt[k] = self.mt[(k + M) % N] ^ (y >> 1) ^ mag;
            }
            self.index = 0;
        }
        let mut y = self.mt[self.index];
        self.index += 1;
        y ^= y >> 11;
        y ^= (y << 7) & 0x9d2c_5680;
        y ^= (y << 15) & 0xefc6_0000;
        y ^ (y >> 18)
    }

    /// 파이썬 `getrandbits(k)` — `k`는 1~32
    pub fn getrandbits(&mut self, k: u32) -> u32 {
        assert!((1..=32).contains(&k), "getrandbits는 1~32비트만");
        self.genrand_u32() >> (32 - k)
    }

    /// 파이썬 `_randbelow_with_getrandbits(n)` — `n > 0`
    pub fn randbelow(&mut self, n: u32) -> u32 {
        let k = 32 - n.leading_zeros();
        let mut r = self.getrandbits(k);
        while r >= n {
            r = self.getrandbits(k);
        }
        r
    }

    /// 파이썬 `shuffle(x)` — 뒤에서부터 `randbelow(i + 1)`과 바꾼다
    pub fn shuffle<T>(&mut self, x: &mut [T]) {
        for i in (1..x.len()).rev() {
            let j = self.randbelow(i as u32 + 1) as usize;
            x.swap(i, j);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mt19937_like_python_312() {
        let raw = include_str!("../tests/golden/pyrandom.json");
        let data: serde_json::Value = serde_json::from_str(raw).expect("정답");
        // 씨앗마다 한 객체로 차례대로 섞는다(파이썬 사례와 같은 차례)
        let mut current: Option<(String, PyRandom)> = None;
        for c in data["shuffles"].as_array().expect("섞기") {
            let seed = c["seed"].as_str().expect("씨앗").to_string();
            if current.as_ref().is_none_or(|(s, _)| *s != seed) {
                let r = PyRandom::new(seed.parse().expect("수"));
                current = Some((seed.clone(), r));
            }
            let r = &mut current.as_mut().expect("객체").1;
            let n = c["n"].as_u64().expect("n") as usize;
            let mut xs: Vec<u64> = (0..n as u64).collect();
            r.shuffle(&mut xs);
            let want: Vec<u64> = c["order"]
                .as_array()
                .expect("차례")
                .iter()
                .map(|v| v.as_u64().expect("수"))
                .collect();
            assert_eq!(xs, want, "seed {seed} n {n}");
        }
        let mut r = PyRandom::new(42);
        for kv in data["getrandbits"].as_array().expect("비트") {
            let k = kv[0].as_u64().expect("k") as u32;
            assert_eq!(u64::from(r.getrandbits(k)), kv[1].as_u64().expect("값"));
        }
    }
}
