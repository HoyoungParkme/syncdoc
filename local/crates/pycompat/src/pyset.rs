//! CPython 3.12 정수 `set`의 순회 차례 (SYNC-DOM-004 1장 pycompat, 카드 L8).
//! 파이썬 판 `queries.item_chain`이 폐포를 `set`에 모아 그 차례로 응답을 채운다 — 같은 바이트를 내려고
//! `Objects/setobject.c`의 표를 그대로 흉내 낸다: 열린 주소, 선형 탐사 9, `perturb >>= 5`, `i*5+1+perturb`,
//! 채움(빈 표시 포함)이 3/5을 넘으면 `used*4`(5만 넘으면 `*2`)보다 큰 2의 거듭제곱으로 키움,
//! `discard`는 빈 표시를 남기고 `add`는 지나온 빈 표시 가운데 마지막 것에 넣는다(빈 자리를 만날 때까지 간다).
//! 값은 음이 아닌 작은 정수(행 id) — 파이썬 `hash(n) == n`인 범위다.

/// 선형 탐사 수 — `LINEAR_PROBES`
const LINEAR_PROBES: usize = 9;
/// `PERTURB_SHIFT`
const PERTURB_SHIFT: u32 = 5;
/// 처음 표 크기 — `PySet_MINSIZE`
const MIN_SIZE: usize = 8;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Slot {
    Empty,
    Dummy,
    Key(u64),
}

/// 파이썬 `set[int]` — 넣고·빼고·차례대로 읽는다
#[derive(Clone)]
pub struct IntSet {
    table: Vec<Slot>,
    fill: usize,
    used: usize,
}

impl Default for IntSet {
    fn default() -> Self {
        IntSet::new()
    }
}

impl IntSet {
    pub fn new() -> IntSet {
        IntSet {
            table: vec![Slot::Empty; MIN_SIZE],
            fill: 0,
            used: 0,
        }
    }

    fn mask(&self) -> usize {
        self.table.len() - 1
    }

    pub fn len(&self) -> usize {
        self.used
    }

    pub fn is_empty(&self) -> bool {
        self.used == 0
    }

    /// 있으면 그 자리 — `set_lookkey`
    fn find(&self, key: u64) -> Option<usize> {
        let mask = self.mask();
        let mut perturb = key;
        let mut i = (key as usize) & mask;
        loop {
            let probes = if i + LINEAR_PROBES <= mask {
                LINEAR_PROBES
            } else {
                0
            };
            for j in i..=i + probes {
                match self.table[j] {
                    Slot::Empty => return None,
                    Slot::Key(k) if k == key => return Some(j),
                    _ => {}
                }
            }
            perturb >>= PERTURB_SHIFT;
            i = (i
                .wrapping_mul(5)
                .wrapping_add(1)
                .wrapping_add(perturb as usize))
                & mask;
        }
    }

    pub fn contains(&self, key: u64) -> bool {
        self.find(key).is_some()
    }

    /// `set.add` — `set_add_entry`. 지나온 빈 표시 가운데 **마지막 것**을 다시 쓴다(3.12 원본이 그렇다)
    pub fn add(&mut self, key: u64) {
        let mask = self.mask();
        let mut perturb = key;
        let mut i = (key as usize) & mask;
        let mut freeslot: Option<usize> = None;
        let empty = loop {
            let probes = if i + LINEAR_PROBES <= mask {
                LINEAR_PROBES
            } else {
                0
            };
            let mut hit = None;
            for j in i..=i + probes {
                match self.table[j] {
                    Slot::Empty => {
                        hit = Some(j);
                        break;
                    }
                    Slot::Key(k) if k == key => return,
                    Slot::Dummy => freeslot = Some(j),
                    Slot::Key(_) => {}
                }
            }
            if let Some(j) = hit {
                break j;
            }
            perturb >>= PERTURB_SHIFT;
            i = (i
                .wrapping_mul(5)
                .wrapping_add(1)
                .wrapping_add(perturb as usize))
                & mask;
        };
        if let Some(f) = freeslot {
            self.table[f] = Slot::Key(key);
            self.used += 1;
            return;
        }
        self.table[empty] = Slot::Key(key);
        self.fill += 1;
        self.used += 1;
        if self.fill * 5 < mask * 3 {
            return;
        }
        let minused = if self.used > 50_000 {
            self.used * 2
        } else {
            self.used * 4
        };
        self.resize(minused);
    }

    /// `set.discard` — 빈 표시를 남긴다
    pub fn discard(&mut self, key: u64) {
        if let Some(j) = self.find(key) {
            self.table[j] = Slot::Dummy;
            self.used -= 1;
        }
    }

    /// `set_table_resize` — 옛 표의 차례로 새 표에 넣는다(빈 표시는 버린다)
    fn resize(&mut self, minused: usize) {
        let mut size = MIN_SIZE;
        while size <= minused {
            size <<= 1;
        }
        let old = std::mem::replace(&mut self.table, vec![Slot::Empty; size]);
        self.fill = self.used;
        let mask = size - 1;
        for s in old {
            if let Slot::Key(k) = s {
                insert_clean(&mut self.table, mask, k);
            }
        }
    }

    /// 순회 차례 — 표의 자리 차례
    pub fn iter(&self) -> impl Iterator<Item = u64> + '_ {
        self.table.iter().filter_map(|s| match s {
            Slot::Key(k) => Some(*k),
            _ => None,
        })
    }
}

/// `set_insert_clean` — 빈 표시가 없는 새 표에 넣는다
fn insert_clean(table: &mut [Slot], mask: usize, key: u64) {
    let mut perturb = key;
    let mut i = (key as usize) & mask;
    loop {
        if table[i] == Slot::Empty {
            table[i] = Slot::Key(key);
            return;
        }
        if i + LINEAR_PROBES <= mask
            && let Some(e) = table[i + 1..=i + LINEAR_PROBES]
                .iter_mut()
                .find(|e| **e == Slot::Empty)
        {
            *e = Slot::Key(key);
            return;
        }
        perturb >>= PERTURB_SHIFT;
        i = (i
            .wrapping_mul(5)
            .wrapping_add(1)
            .wrapping_add(perturb as usize))
            & mask;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 파이썬 3.12에서 뜬 차례와 같다 — `xtask/py/pyset_cases.py`
    #[test]
    fn order_like_python_312() {
        let raw = include_str!("../tests/golden/pyset.json");
        let data: serde_json::Value = serde_json::from_str(raw).expect("정답");
        let cases = data["cases"].as_array().expect("사례");
        assert!(cases.len() > 400);
        for (n, c) in cases.iter().enumerate() {
            let mut s = IntSet::new();
            for op in c["ops"].as_array().expect("ops") {
                let v = op[1].as_u64().expect("값");
                match op[0].as_str() {
                    Some("add") => s.add(v),
                    _ => s.discard(v),
                }
            }
            let want: Vec<u64> = c["order"]
                .as_array()
                .expect("차례")
                .iter()
                .map(|x| x.as_u64().expect("값"))
                .collect();
            assert_eq!(s.iter().collect::<Vec<_>>(), want, "사례 {n}");
            assert_eq!(s.len(), want.len());
        }
    }
}
