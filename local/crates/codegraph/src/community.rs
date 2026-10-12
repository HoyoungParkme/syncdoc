//! 커뮤니티 — networkx Louvain(seed 42)과 graphify 허브 라벨 (SYNC-MS-022#codegraph.communities · MS-011 communities, 카드 L13).
//! 파이썬 판은 networkx 3.7 `louvain_communities`·graphify `load_node_link_graph`·`label_communities_by_hub`를 부른다 —
//! 같은 차례·같은 부동소수 계산으로 옮겼다. 난수는 파이썬 `random.Random(42)`(MT19937), modularity 합은 파이썬 3.12
//! `sum`(Neumaier 보정)이다. 가중치는 정수라 차수·내부 선 합은 정확하다

use std::collections::{BTreeSet, HashMap, HashSet};

use indexmap::IndexMap;
use serde_json::{Value, json};
use syncdoc_pycompat::chars::strip;
use syncdoc_pycompat::pysum::py_sum;
use syncdoc_pycompat::random::PyRandom;

use crate::graph::{clean, is_test, node_key, py_str, truthy};
use crate::{Call, Community, Function, Graph};

/// networkx `louvain_communities`의 `threshold`
const THRESHOLD: f64 = 0.0000001;

/// networkx `Graph` — 노드는 번호, 이웃은 넣은 차례(dict). `members`는 노드 속성 `nodes`(원래 노드들)
struct Nx {
    adj: Vec<IndexMap<usize, i64>>,
    members: Vec<Vec<usize>>,
}

impl Nx {
    fn with_nodes(n: usize) -> Nx {
        Nx {
            adj: vec![IndexMap::new(); n],
            members: (0..n).map(|u| vec![u]).collect(),
        }
    }

    /// `add_edge` — 있으면 무게만 바꾸고 자리는 그대로
    fn add_edge(&mut self, a: usize, b: usize, w: i64) {
        self.adj[a].insert(b, w);
        if a != b {
            self.adj[b].insert(a, w);
        }
    }

    /// `edges(data="weight")` — 노드 차례로, 이미 지난 노드 쪽 선은 건너뛴다(자기 고리는 한 번)
    fn edges(&self) -> Vec<(usize, usize, i64)> {
        let mut seen = vec![false; self.adj.len()];
        let mut out = Vec::new();
        for (n, nbrs) in self.adj.iter().enumerate() {
            for (&nbr, &w) in nbrs {
                if !seen[nbr] {
                    out.push((n, nbr, w));
                }
            }
            seen[n] = true;
        }
        out
    }

    /// `degree(weight="weight")` — 자기 고리는 두 번
    fn degree(&self, n: usize) -> i64 {
        self.adj[n].values().sum::<i64>() + self.adj[n].get(&n).copied().unwrap_or(0)
    }
}

/// networkx `modularity`(무향, resolution 1.0) — 군집 기여를 파이썬 `sum`으로
fn modularity(g: &Nx, parts: &[BTreeSet<usize>]) -> f64 {
    let deg: Vec<i64> = (0..g.adj.len()).map(|u| g.degree(u)).collect();
    let deg_sum: i64 = deg.iter().sum();
    let m = deg_sum as f64 / 2.0;
    if m == 0.0 {
        return 0.0;
    }
    let norm = 1.0 / (deg_sum * deg_sum) as f64;
    let contributions: Vec<f64> = parts
        .iter()
        .map(|comm| {
            // 안쪽 선 무게 — 선마다 한 번(자기 고리도 한 번)
            let l_c: i64 = comm
                .iter()
                .flat_map(|&u| g.adj[u].iter().map(move |(&v, &w)| (u, v, w)))
                .filter(|&(u, v, _)| v >= u && comm.contains(&v))
                .map(|(_, _, w)| w)
                .sum();
            let s = comm.iter().map(|&u| deg[u]).sum::<i64>() as f64;
            l_c as f64 / m - 1.0 * s * s * norm
        })
        .collect();
    py_sum(&contributions)
}

/// networkx `_one_level` — 노드를 섞은 차례로 옮겨 본다. (원래 노드의 분할, 이 단계 노드의 분할, 나아졌나)
fn one_level(
    g: &Nx,
    partition: Vec<BTreeSet<usize>>,
    m: f64,
    rng: &mut PyRandom,
) -> (Vec<BTreeSet<usize>>, Vec<BTreeSet<usize>>, bool) {
    let n = g.adj.len();
    let mut partition = partition;
    let mut node2com: Vec<usize> = (0..n).collect();
    let mut inner: Vec<BTreeSet<usize>> = (0..n).map(|u| BTreeSet::from([u])).collect();
    let gamma = 1.0 / 2.0;
    let degrees: Vec<i64> = (0..n).map(|u| g.degree(u)).collect();
    let mut stot = degrees.clone();
    let nbrs: Vec<Vec<(usize, i64)>> = (0..n)
        .map(|u| {
            g.adj[u]
                .iter()
                .filter(|&(&v, _)| v != u)
                .map(|(&v, &w)| (v, w))
                .collect()
        })
        .collect();
    let mut rand_nodes: Vec<usize> = (0..n).collect();
    rng.shuffle(&mut rand_nodes);
    let mut nb_moves = 1;
    let mut improvement = false;
    while nb_moves > 0 {
        nb_moves = 0;
        for &u in &rand_nodes {
            let u_com = node2com[u];
            // defaultdict(float) — 처음 본 차례
            let mut by_com: IndexMap<usize, f64> = IndexMap::new();
            for &(nbr, wt) in &nbrs[u] {
                *by_com.entry(node2com[nbr]).or_insert(0.0) += wt as f64;
            }
            let degree = degrees[u];
            stot[u_com] -= degree;
            let x = stot[u_com] * degree;
            // 파이썬은 `u_deg_by_com[u_com]`을 읽으며 없던 자리를 끝에 만든다
            let own = *by_com.entry(u_com).or_insert(0.0);
            let remove_cost = own * m - gamma * x as f64;
            let mut best_gain = remove_cost;
            let mut best_com = u_com;
            for (&nbr_com, &wt) in &by_com {
                let x = stot[nbr_com] * degree;
                let gain = wt * m - gamma * x as f64;
                if gain > best_gain {
                    best_gain = gain;
                    best_com = nbr_com;
                }
            }
            stot[best_com] += degree;
            if best_com != u_com {
                for x in &g.members[u] {
                    partition[u_com].remove(x);
                    partition[best_com].insert(*x);
                }
                inner[u_com].remove(&u);
                inner[best_com].insert(u);
                improvement = true;
                nb_moves += 1;
                node2com[u] = best_com;
            }
        }
    }
    partition.retain(|p| !p.is_empty());
    inner.retain(|p| !p.is_empty());
    (partition, inner, improvement)
}

/// networkx `_aggregate_graph` — 군집 하나가 노드 하나, 선 무게는 더한다
fn aggregate(g: &Nx, inner: &[BTreeSet<usize>]) -> Nx {
    let mut h = Nx::with_nodes(inner.len());
    let mut node2com = vec![0usize; g.adj.len()];
    for (i, part) in inner.iter().enumerate() {
        let mut nodes = BTreeSet::new();
        for &node in part {
            node2com[node] = i;
            nodes.extend(g.members[node].iter().copied());
        }
        h.members[i] = nodes.into_iter().collect();
    }
    for (a, b, wt) in g.edges() {
        let (c1, c2) = (node2com[a], node2com[b]);
        let w = match h.adj[c1].get(&c2) {
            Some(old) => wt + old,
            None => wt,
        };
        h.add_edge(c1, c2, w);
    }
    h
}

/// networkx `louvain_communities(G, resolution=1.0, seed=42)` — 마지막 분할(원래 노드 번호)
fn louvain(n: usize, pairs: &[(usize, usize)]) -> Vec<BTreeSet<usize>> {
    let mut orig = Nx::with_nodes(n);
    for &(a, b) in pairs {
        orig.add_edge(a, b, 1);
    }
    // louvain_partitions — 무게 붙인 새 그래프에 원래 선 차례로
    let mut g = Nx::with_nodes(n);
    for (a, b, w) in orig.edges() {
        g.add_edge(a, b, w);
    }
    let mut rng = PyRandom::new(42);
    let singletons: Vec<BTreeSet<usize>> = (0..n).map(|u| BTreeSet::from([u])).collect();
    let mut modv = modularity(&orig, &singletons);
    let m = (0..n).map(|u| orig.degree(u)).sum::<i64>() as f64 / 2.0;
    let (mut p, mut inner, _) = one_level(&g, singletons, m, &mut rng);
    loop {
        let last = p.clone();
        let new_mod = modularity(&g, &inner);
        if new_mod - modv <= THRESHOLD {
            return last;
        }
        modv = new_mod;
        g = aggregate(&g, &inner);
        let (np, ni, improvement) = one_level(&g, p, m, &mut rng);
        p = np;
        inner = ni;
        if !improvement {
            return last;
        }
    }
}

/// graphify `load_node_link_graph`로 읽은 그래프 — 노드(넣은 차례)·`label` 속성·차수·양 끝 쌍
struct Linked {
    ids: Vec<String>,
    labels: HashMap<String, Value>,
    degree: HashMap<String, i64>,
    pairs: BTreeSet<(String, String)>,
}

/// networkx `node_link_graph` — `directed`·`multigraph`(없으면 무향·다중)로 같은 차수를 낸다
fn linked(raw: &Value, key: &str) -> Linked {
    let directed = raw.get("directed").is_some_and(|v| truthy(Some(v)));
    let multigraph = raw.get("multigraph").is_none_or(|v| truthy(Some(v)));
    let mut ids = Vec::new();
    let mut known: HashSet<String> = HashSet::new();
    let mut labels = HashMap::new();
    for n in raw
        .get("nodes")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let Some(id) = n.get("id") else { continue };
        let id = py_str(id);
        if known.insert(id.clone()) {
            ids.push(id.clone());
        }
        if let Some(l) = n.get("label") {
            labels.insert(id, l.clone()); // 같은 노드를 다시 넣으면 속성을 덮는다
        }
    }
    let mut degree: HashMap<String, i64> = HashMap::new();
    let mut pairs = BTreeSet::new();
    let mut seen: HashSet<String> = HashSet::new();
    for e in raw.get(key).and_then(Value::as_array).into_iter().flatten() {
        let (Some(s), Some(t)) = (e.get("source"), e.get("target")) else {
            continue;
        };
        let (s, t) = (py_str(s), py_str(t));
        let (lo, hi) = if s <= t {
            (s.clone(), t.clone())
        } else {
            (t.clone(), s.clone())
        };
        pairs.insert((lo.clone(), hi.clone()));
        // 같은 선인가 — 단순 그래프는 양 끝(무향이면 차례 없이), 다중은 key가 같을 때만
        let ends = if directed {
            (s.clone(), t.clone())
        } else {
            (lo, hi)
        };
        let dup_key = if multigraph {
            match e.get("key") {
                Some(k) if !k.is_null() => Some(format!("{}:{}:{}", ends.0, ends.1, k)),
                _ => None,
            }
        } else {
            Some(format!("{}:{}", ends.0, ends.1))
        };
        if let Some(k) = dup_key
            && !seen.insert(k)
        {
            continue;
        }
        *degree.entry(s).or_insert(0) += 1;
        *degree.entry(t).or_insert(0) += 1;
    }
    Linked {
        ids,
        labels,
        degree,
        pairs,
    }
}

/// 파이썬 `_louvain` — 노드를 이름 순으로, 선은 양 끝을 정렬해 정렬한 차례로. 번호는 크기 내림차순(같으면 정렬한 노드)
fn louvain_names(g: &Linked) -> Vec<Vec<String>> {
    let mut names = g.ids.clone();
    names.sort();
    let index: HashMap<&str, usize> = names
        .iter()
        .enumerate()
        .map(|(i, s)| (s.as_str(), i))
        .collect();
    let pairs: Vec<(usize, usize)> = g
        .pairs
        .iter()
        .filter_map(|(a, b)| Some((*index.get(a.as_str())?, *index.get(b.as_str())?)))
        .collect();
    let comms: Vec<BTreeSet<usize>> = if pairs.is_empty() {
        (0..names.len()).map(|u| BTreeSet::from([u])).collect()
    } else {
        louvain(names.len(), &pairs)
    };
    let mut out: Vec<Vec<String>> = comms
        .into_iter()
        .map(|c| {
            let mut v: Vec<String> = c.into_iter().map(|i| names[i].clone()).collect();
            v.sort();
            v
        })
        .collect();
    out.sort_by(|a, b| b.len().cmp(&a.len()).then_with(|| a.cmp(b)));
    out
}

/// 파이썬 `_drop_tests` — 테스트 노드와 그 선을 뺀 (노드, 선 열쇠, 선)
fn drop_tests(raw: &Value) -> Value {
    let nodes: Vec<Value> = raw
        .get("nodes")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter(|n| {
            !is_test(
                &n.get("source_file")
                    .filter(|v| truthy(Some(v)))
                    .map(py_str)
                    .unwrap_or_default(),
            )
        })
        .cloned()
        .collect();
    let keep: HashSet<String> = nodes
        .iter()
        .filter_map(|n| n.get("id").map(py_str))
        .collect();
    let key = if raw.get("links").is_some() {
        "links"
    } else {
        "edges"
    };
    let links: Vec<Value> = raw
        .get(key)
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter(|e| {
            let inside = |k: &str| e.get(k).is_some_and(|v| keep.contains(&py_str(v)));
            inside("source") && inside("target")
        })
        .cloned()
        .collect();
    let mut out = raw.clone();
    if let Some(o) = out.as_object_mut() {
        o.insert("nodes".into(), Value::Array(nodes));
        o.insert(key.into(), Value::Array(links));
    }
    out
}

/// 파이썬 `_owns` — 노드가 그 커뮤니티의 함수를 품었나(함수 자신 · 메서드가 든 클래스 · 함수가 든 파일)
fn owns(
    n: &Value,
    keys: &HashSet<&str>,
    files: &HashSet<&str>,
    owners: &HashSet<(String, String)>,
) -> bool {
    let file = n
        .get("source_file")
        .filter(|v| truthy(Some(v)))
        .map(py_str)
        .unwrap_or_default();
    if file.is_empty() {
        return false;
    }
    if truthy(n.get("_callable_class")) {
        let label = n.get("label").map(py_str).unwrap_or_default();
        return owners.contains(&(file, clean(&label)));
    }
    if truthy(n.get("_callable")) {
        return node_key(n).is_some_and(|(f, l)| keys.contains(format!("{f}:{l}").as_str()));
    }
    files.contains(file.as_str())
}

/// 파이썬 `_hub_labels` + graphify `label_communities_by_hub` — 후보 중 차수 최고(같으면 이름 순)의 이름
fn hub_labels(
    g: &Linked,
    found: &[Vec<String>],
    nodes: &IndexMap<String, Value>,
    functions: &[Function],
) -> HashMap<i64, String> {
    let empty = Value::Object(serde_json::Map::new());
    let mut labels = HashMap::new();
    for (cid, members) in found.iter().enumerate() {
        let cid = cid as i64;
        let fs: Vec<&Function> = functions
            .iter()
            .filter(|f| f.community == Some(cid))
            .collect();
        let keys: HashSet<&str> = fs.iter().map(|f| f.key.as_str()).collect();
        let files: HashSet<&str> = fs.iter().map(|f| f.file.as_str()).collect();
        let owners: HashSet<(String, String)> = fs
            .iter()
            .filter_map(|f| {
                f.qual
                    .rsplit_once('.')
                    .map(|(owner, _)| (f.file.clone(), owner.to_string()))
            })
            .collect();
        let node = |m: &str| nodes.get(m).unwrap_or(&empty);
        let code: Vec<&String> = members
            .iter()
            .filter(|m| match node(m).get("file_type") {
                None => true,
                Some(v) => v.as_str() == Some("code"),
            })
            .collect();
        let owned: Vec<&String> = code
            .iter()
            .copied()
            .filter(|m| owns(node(m), &keys, &files, &owners))
            .collect();
        let cands = if owned.is_empty() { code } else { owned };
        let label = match cands.iter().min_by(|a, b| {
            let da = g.degree.get(a.as_str()).copied().unwrap_or(0);
            let db = g.degree.get(b.as_str()).copied().unwrap_or(0);
            db.cmp(&da).then_with(|| a.cmp(b))
        }) {
            None => format!("Community {cid}"),
            Some(hub) => {
                let name = match g.labels.get(hub.as_str()) {
                    Some(l) if truthy(Some(l)) => py_str(l),
                    _ => (*hub).clone(),
                };
                let name = strip(&name);
                let name = name.strip_suffix("()").unwrap_or(name);
                if name.is_empty() {
                    format!("Community {cid}")
                } else {
                    name.to_string()
                }
            }
        };
        labels.insert(cid, clean(&label));
    }
    labels
}

/// SYNC-MS-022#codegraph.widen
///
/// 추출 원형에 보강이 찾은 함수(`파일:줄` 노드)와 호출 선을 더한다 — 추출은 TS/JS·Rust를 파일 노드로만 두어 그 함수들이
/// 커뮤니티를 못 받았다(카드 L20). 커밋된 graph.json 원형에는 부르지 않는다(파이썬 판과 바이트로 같은 길)
pub fn widen(raw: &Value, graph: &Graph) -> Value {
    let key = if raw.get("links").is_some() {
        "links"
    } else {
        "edges"
    };
    let mut nodes: Vec<Value> = raw
        .get("nodes")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut links: Vec<Value> = raw
        .get(key)
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut ids: HashSet<String> = nodes
        .iter()
        .filter_map(|n| n.get("id").map(py_str))
        .collect();
    let mut keys: HashSet<String> = nodes
        .iter()
        .filter_map(node_key)
        .map(|(f, l)| format!("{f}:{l}"))
        .collect();
    // 무향 — 양 끝을 정렬한 쌍으로 같은 선을 한 번만
    let pair = |a: &str, b: &str| {
        if a <= b {
            (a.to_string(), b.to_string())
        } else {
            (b.to_string(), a.to_string())
        }
    };
    let end = |e: &Value, k: &str| e.get(k).map(py_str).unwrap_or_default();
    let mut pairs: HashSet<(String, String)> = links
        .iter()
        .map(|e| pair(&end(e, "source"), &end(e, "target")))
        .collect();
    for f in &graph.functions {
        if !keys.insert(f.key.clone()) {
            continue;
        }
        nodes.push(
            json!({"id": f.key, "label": format!("{}()", f.name), "file_type": "code",
            "source_file": f.file, "source_location": format!("L{}", f.line), "_callable": true}),
        );
        ids.insert(f.key.clone());
        if ids.contains(&f.file) && pairs.insert(pair(&f.file, &f.key)) {
            links.push(
                json!({"source": f.file, "target": f.key, "relation": "contains",
                "confidence": "EXTRACTED"}),
            );
        }
    }
    for Call(from, to, _) in &graph.calls {
        if ids.contains(from) && ids.contains(to) && pairs.insert(pair(from, to)) {
            links.push(json!({"source": from, "target": to, "relation": "calls",
                "confidence": "EXTRACTED"}));
        }
    }
    let mut out = raw.clone();
    if let Some(o) = out.as_object_mut() {
        o.insert("nodes".into(), Value::Array(nodes));
        o.insert(key.into(), Value::Array(links));
    }
    out
}

/// SYNC-MS-022#codegraph.communities
///
/// 원형(파일·클래스·호출 선이 다 든 것)을 Louvain으로 묶어 함수마다 커뮤니티 번호를 붙이고 `communities`를 더한다.
/// 테스트 노드와 그 선은 빼고 묶는다. 보강이 더한 함수는 파일의 커뮤니티를 받는다
pub fn communities(raw: &Value, graph: Graph) -> Graph {
    let mut graph = graph;
    let raw = drop_tests(raw);
    let mut nodes: IndexMap<String, Value> = IndexMap::new();
    for n in raw
        .get("nodes")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        if let Some(id) = n.get("id") {
            nodes.insert(py_str(id), n.clone());
        }
    }
    let mut by_key: HashMap<String, i64> = HashMap::new();
    let mut votes: HashMap<String, HashMap<i64, i64>> = HashMap::new();
    let mut found: Vec<Vec<String>> = Vec::new();
    let key = if raw.get("links").is_some() {
        "links"
    } else {
        "edges"
    };
    let g = linked(&raw, key);
    if !nodes.is_empty() {
        found = louvain_names(&g);
        for (cid, members) in found.iter().enumerate() {
            for nid in members {
                let Some((file, line)) = nodes.get(nid).and_then(node_key) else {
                    continue;
                };
                by_key.insert(format!("{file}:{line}"), cid as i64);
                *votes
                    .entry(file)
                    .or_default()
                    .entry(cid as i64)
                    .or_insert(0) += 1;
            }
        }
    }
    let by_file: HashMap<String, i64> = votes
        .into_iter()
        .filter_map(|(f, v)| {
            v.into_iter()
                .min_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)))
                .map(|(cid, _)| (f, cid))
        })
        .collect();
    let mut sizes: HashMap<i64, i64> = HashMap::new();
    for f in &mut graph.functions {
        let cid = by_key.get(&f.key).or_else(|| by_file.get(&f.file)).copied();
        f.community = cid;
        if let Some(c) = cid {
            *sizes.entry(c).or_insert(0) += 1;
        }
    }
    let labels = if found.is_empty() {
        HashMap::new()
    } else {
        hub_labels(&g, &found, &nodes, &graph.functions)
    };
    let mut list: Vec<(i64, i64)> = sizes.into_iter().collect();
    list.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    graph.communities = Some(
        list.into_iter()
            .map(|(id, size)| Community {
                id,
                label: labels.get(&id).cloned().unwrap_or_else(|| id.to_string()),
                size,
            })
            .collect(),
    );
    graph
}
