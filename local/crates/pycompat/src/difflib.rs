//! 파이썬 3.12 `difflib` — `SequenceMatcher`·`get_grouped_opcodes`·`unified_diff` (SYNC-DOM-004 1장 pycompat).
//! 알고리즘째 옮긴다 — 다른 diff(최소 편집 거리 등)는 같은 변경을 다른 줄 묶음으로 보여 준다.
//! `isjunk=None`, `autojunk=True`만 — 명세 엔진이 쓰는 꼴(SYNC-MS-014#SpecService.diff_bodies).
//! 파이썬 원본의 차례(큐를 뒤에서 꺼내기·같은 길이면 앞의 것)를 그대로 지킨다.

use std::collections::{HashMap, HashSet};

/// `(tag, i1, i2, j1, j2)` — tag는 `equal`·`replace`·`delete`·`insert`
pub type Opcode = (&'static str, usize, usize, usize, usize);

/// `SequenceMatcher(None, a, b)` — 줄(문자열)끼리 비교
pub struct SequenceMatcher<'s> {
    a: &'s [&'s str],
    b: &'s [&'s str],
    /// b의 원소 → 나오는 자리(오름차순). autojunk로 뺀 인기 원소는 없다
    b2j: HashMap<&'s str, Vec<usize>>,
}

impl<'s> SequenceMatcher<'s> {
    pub fn new(a: &'s [&'s str], b: &'s [&'s str]) -> Self {
        let mut b2j: HashMap<&'s str, Vec<usize>> = HashMap::new();
        for (i, &elt) in b.iter().enumerate() {
            b2j.entry(elt).or_default().push(i);
        }
        // autojunk — 200줄 이상이면 1%+1번 넘게 나오는 원소를 뺀다(junk 집합에는 안 넣는다)
        let n = b.len();
        if n >= 200 {
            let ntest = n / 100 + 1;
            let popular: HashSet<&str> = b2j
                .iter()
                .filter(|(_, idxs)| idxs.len() > ntest)
                .map(|(&elt, _)| elt)
                .collect();
            for elt in popular {
                b2j.remove(elt);
            }
        }
        SequenceMatcher { a, b, b2j }
    }

    /// `find_longest_match(alo, ahi, blo, bhi)` — junk가 없으니 넓히기는 앞 두 고리만 일한다
    fn find_longest_match(
        &self,
        alo: usize,
        ahi: usize,
        blo: usize,
        bhi: usize,
    ) -> (usize, usize, usize) {
        let (a, b) = (self.a, self.b);
        let (mut besti, mut bestj, mut bestsize) = (alo, blo, 0usize);
        let mut j2len: HashMap<usize, usize> = HashMap::new();
        for (i, &ai) in a.iter().enumerate().take(ahi).skip(alo) {
            let mut newj2len: HashMap<usize, usize> = HashMap::new();
            if let Some(js) = self.b2j.get(ai) {
                for &j in js {
                    if j < blo {
                        continue;
                    }
                    if j >= bhi {
                        break;
                    }
                    let prev = if j == 0 {
                        0
                    } else {
                        j2len.get(&(j - 1)).copied().unwrap_or(0)
                    };
                    let k = prev + 1;
                    newj2len.insert(j, k);
                    if k > bestsize {
                        besti = i + 1 - k;
                        bestj = j + 1 - k;
                        bestsize = k;
                    }
                }
            }
            j2len = newj2len;
        }
        while besti > alo && bestj > blo && a[besti - 1] == b[bestj - 1] {
            besti -= 1;
            bestj -= 1;
            bestsize += 1;
        }
        while besti + bestsize < ahi
            && bestj + bestsize < bhi
            && a[besti + bestsize] == b[bestj + bestsize]
        {
            bestsize += 1;
        }
        (besti, bestj, bestsize)
    }

    /// `get_matching_blocks()` — 끝에 `(len(a), len(b), 0)`
    pub fn get_matching_blocks(&self) -> Vec<(usize, usize, usize)> {
        let (la, lb) = (self.a.len(), self.b.len());
        let mut queue = vec![(0, la, 0, lb)];
        let mut blocks = Vec::new();
        while let Some((alo, ahi, blo, bhi)) = queue.pop() {
            let (i, j, k) = self.find_longest_match(alo, ahi, blo, bhi);
            if k > 0 {
                blocks.push((i, j, k));
                if alo < i && blo < j {
                    queue.push((alo, i, blo, j));
                }
                if i + k < ahi && j + k < bhi {
                    queue.push((i + k, ahi, j + k, bhi));
                }
            }
        }
        blocks.sort_unstable();
        let (mut i1, mut j1, mut k1) = (0, 0, 0);
        let mut out = Vec::new();
        for (i2, j2, k2) in blocks {
            if i1 + k1 == i2 && j1 + k1 == j2 {
                k1 += k2;
            } else {
                if k1 > 0 {
                    out.push((i1, j1, k1));
                }
                (i1, j1, k1) = (i2, j2, k2);
            }
        }
        if k1 > 0 {
            out.push((i1, j1, k1));
        }
        out.push((la, lb, 0));
        out
    }

    /// `get_opcodes()`
    pub fn get_opcodes(&self) -> Vec<Opcode> {
        let (mut i, mut j) = (0, 0);
        let mut answer = Vec::new();
        for (ai, bj, size) in self.get_matching_blocks() {
            let tag = if i < ai && j < bj {
                "replace"
            } else if i < ai {
                "delete"
            } else if j < bj {
                "insert"
            } else {
                ""
            };
            if !tag.is_empty() {
                answer.push((tag, i, ai, j, bj));
            }
            (i, j) = (ai + size, bj + size);
            if size > 0 {
                answer.push(("equal", ai, i, bj, j));
            }
        }
        answer
    }

    /// `get_grouped_opcodes(n)`
    pub fn get_grouped_opcodes(&self, n: usize) -> Vec<Vec<Opcode>> {
        let mut codes = self.get_opcodes();
        if codes.is_empty() {
            codes = vec![("equal", 0, 1, 0, 1)];
        }
        if let Some(first) = codes.first_mut()
            && first.0 == "equal"
        {
            let (tag, i1, i2, j1, j2) = *first;
            *first = (
                tag,
                i1.max(i2.saturating_sub(n)),
                i2,
                j1.max(j2.saturating_sub(n)),
                j2,
            );
        }
        if let Some(last) = codes.last_mut()
            && last.0 == "equal"
        {
            let (tag, i1, i2, j1, j2) = *last;
            *last = (tag, i1, i2.min(i1 + n), j1, j2.min(j1 + n));
        }
        let nn = n + n;
        let mut groups = Vec::new();
        let mut group: Vec<Opcode> = Vec::new();
        for (tag, mut i1, i2, mut j1, j2) in codes {
            if tag == "equal" && i2 - i1 > nn {
                group.push((tag, i1, i2.min(i1 + n), j1, j2.min(j1 + n)));
                groups.push(std::mem::take(&mut group));
                i1 = i1.max(i2.saturating_sub(n));
                j1 = j1.max(j2.saturating_sub(n));
            }
            group.push((tag, i1, i2, j1, j2));
        }
        if !group.is_empty() && !(group.len() == 1 && group[0].0 == "equal") {
            groups.push(group);
        }
        groups
    }
}

/// `_format_range_unified(start, stop)`
fn format_range_unified(start: usize, stop: usize) -> String {
    let mut beginning = start + 1;
    let length = stop - start;
    if length == 1 {
        return beginning.to_string();
    }
    if length == 0 {
        beginning -= 1;
    }
    format!("{beginning},{length}")
}

/// `unified_diff(a, b, n=n, lineterm="")` — 파일 이름·날짜는 빈 값
pub fn unified_diff(a: &[&str], b: &[&str], n: usize) -> Vec<String> {
    let mut out = Vec::new();
    let sm = SequenceMatcher::new(a, b);
    for (g, group) in sm.get_grouped_opcodes(n).iter().enumerate() {
        if g == 0 {
            out.push("--- ".to_string());
            out.push("+++ ".to_string());
        }
        let (first, last) = (group[0], group[group.len() - 1]);
        out.push(format!(
            "@@ -{} +{} @@",
            format_range_unified(first.1, last.2),
            format_range_unified(first.3, last.4)
        ));
        for &(tag, i1, i2, j1, j2) in group {
            if tag == "equal" {
                out.extend(a[i1..i2].iter().map(|l| format!(" {l}")));
                continue;
            }
            if tag == "replace" || tag == "delete" {
                out.extend(a[i1..i2].iter().map(|l| format!("-{l}")));
            }
            if tag == "replace" || tag == "insert" {
                out.extend(b[j1..j2].iter().map(|l| format!("+{l}")));
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::unified_diff;

    #[test]
    fn like_python_small() {
        // difflib.unified_diff(["x","---","y"], ["x","y"], lineterm="")
        assert_eq!(
            unified_diff(&["x", "---", "y"], &["x", "y"], 3),
            ["--- ", "+++ ", "@@ -1,3 +1,2 @@", " x", "----", " y"]
        );
        assert!(unified_diff(&["a"], &["a"], 3).is_empty());
        assert_eq!(
            unified_diff(&[], &["a"], 0),
            ["--- ", "+++ ", "@@ -0,0 +1 @@", "+a"]
        );
    }
}
