//! starlette `Request.form()` — starlette 1.6.0 `formparsers.py`(`FormParser`·`MultiPartParser`)와 그 밑의
//! python-multipart 0.0.32(`parse_options_header`·`QuerystringParser`·`MultipartParser`)를 옮겼다 (SYNC-DOM-004 1장 compat, L15).
//! 깨진 본문의 답까지 파이썬 판과 같다 — starlette가 던지는 `MultiPartException`은 그 문장이 제목인 400이고,
//! python-multipart의 파싱 오류는 FastAPI가 덮어 400 `There was an error parsing the body`다.
//! 정답 `tests/golden/form.json`(`xtask/py/form_cases.py`)

use axum::http::HeaderMap;
use indexmap::IndexMap;
use syncdoc_core::errors::Problem;
use syncdoc_core::pycompat::chars::{lstrip, rstrip, strip};

use super::uvicorn::unquote;

/// starlette `Request.form()`의 기본 상한
const MAX_FILES: usize = 1000;
const MAX_FIELDS: usize = 1000;
const MAX_PART_SIZE: usize = 1024 * 1024;
/// python-multipart의 부분마다 머리 상한
const MAX_HEADER_COUNT: usize = 8;
const MAX_HEADER_SIZE: usize = 4096 + 128;
const MAX_BOUNDARY_LENGTH: usize = 256;

/// 올린 파일 하나 — starlette `UploadFile`의 이름·종류(부분 머리의 첫 `content-type`, 없으면 없음)·바이트
pub struct Upload {
    pub filename: Option<String>,
    pub content_type: Option<String>,
    pub data: Vec<u8>,
}

/// 폼 값 하나 — starlette `FormData`의 값
pub enum FormValue {
    Text(String),
    File(Upload),
}

/// 해석이 멈춘 까닭
enum Stop {
    /// starlette `MultiPartException` — 그 문장이 제목인 400
    Starlette(String),
    /// python-multipart의 파싱 오류 — FastAPI가 덮는 400
    Parser,
}

impl Stop {
    fn problem(self) -> Problem {
        let title = match self {
            Stop::Starlette(m) => m,
            Stop::Parser => "There was an error parsing the body".to_string(),
        };
        Problem::Blank {
            status: 400,
            title,
            detail: None,
        }
    }
}

fn latin1(b: &[u8]) -> String {
    b.iter().map(|&c| char::from(c)).collect()
}

/// latin-1 글자열 → 바이트 (글자는 다 U+00FF 아래다)
fn latin1_bytes(s: &str) -> Vec<u8> {
    s.chars()
        .map(|c| u8::try_from(u32::from(c)).unwrap_or(b'?'))
        .collect()
}

/// 첫 머리 값 (starlette `Headers.get` — latin-1)
fn first_header(headers: &HeaderMap, name: &str) -> Option<String> {
    headers.get(name).map(|v| latin1(v.as_bytes()))
}

// ── 파이썬 str 색인 (자르기 규칙으로 맞춘 find·count) ──

fn norm(i: isize, len: isize) -> isize {
    if i < 0 { (i + len).max(0) } else { i.min(len) }
}

fn find(s: &[char], sub: &[char], start: isize, end: isize) -> isize {
    let len = s.len() as isize;
    let (a, b) = (norm(start, len), norm(end, len));
    let m = sub.len() as isize;
    let mut i = a;
    while i + m <= b {
        if s[i as usize..(i + m) as usize] == *sub {
            return i;
        }
        i += 1;
    }
    -1
}

fn count(s: &[char], sub: &[char], start: isize, end: isize) -> isize {
    let len = s.len() as isize;
    let (a, b) = (norm(start, len), norm(end, len));
    let m = sub.len() as isize;
    let (mut i, mut n) = (a, 0);
    while i + m <= b {
        if s[i as usize..(i + m) as usize] == *sub {
            n += 1;
            i += m;
        } else {
            i += 1;
        }
    }
    n
}

fn slice(s: &[char], a: isize, b: isize) -> String {
    let len = s.len() as isize;
    let (a, b) = (norm(a, len), norm(b, len));
    if a >= b {
        return String::new();
    }
    s[a as usize..b as usize].iter().collect()
}

fn py_lower(s: &str) -> String {
    s.chars().flat_map(char::to_lowercase).collect()
}

/// python-multipart `_parseparam` — 따옴표 안의 `;`는 나누지 않는다(그 판의 고리 그대로)
fn parseparam(value: &str) -> Vec<String> {
    let s: Vec<char> = std::iter::once(';').chain(value.chars()).collect();
    let len = s.len() as isize;
    let (semi, quote, esc, eq) = ([';'], ['"'], ['\\', '"'], ['=']);
    let mut plist = Vec::new();
    let mut start: isize = 0;
    while find(&s, &semi, start, len) == start {
        start += 1;
        let mut end = find(&s, &semi, start, len);
        let (mut ind, mut diff) = (start, 0isize);
        while end > 0 {
            diff += count(&s, &quote, ind, end) - count(&s, &esc, ind, end);
            if diff % 2 == 0 {
                break;
            }
            let next = find(&s, &semi, end + 1, len);
            end = ind;
            ind = next;
        }
        if end < 0 {
            end = len;
        }
        let i = find(&s, &eq, start, end);
        let f = if i == -1 {
            slice(&s, start, end)
        } else {
            format!(
                "{}={}",
                py_lower(rstrip(&slice(&s, start, i))),
                lstrip(&slice(&s, i + 1, end))
            )
        };
        plist.push(strip(&f).to_string());
        start = end;
    }
    plist
}

/// python-multipart `parse_options_header` — (종류, 선택지). 글자는 latin-1
fn parse_options_header(value: Option<&str>) -> (String, IndexMap<String, String>) {
    let mut options = IndexMap::new();
    let Some(value) = value.filter(|v| !v.is_empty()) else {
        return (String::new(), options);
    };
    if !value.contains(';') {
        return (strip(&py_lower(value)).to_string(), options);
    }
    let mut parts = parseparam(value).into_iter();
    let ctype = parts.next().unwrap_or_default();
    for segment in parts {
        let (key, val) = segment.split_once('=').unwrap_or((segment.as_str(), ""));
        if key.contains('*') {
            continue;
        }
        let mut val = val.to_string();
        let n = val.chars().count();
        if n >= 2 && val.starts_with('"') && val.ends_with('"') {
            let inner: String = val.chars().skip(1).take(n - 2).collect();
            val = inner.replace("\\\\", "\\").replace("\\\"", "\"");
        }
        if key == "filename" {
            let c: Vec<char> = val.chars().collect();
            if slice(&c, 1, 3) == ":\\" || slice(&c, 0, 2) == "\\\\" {
                val = val.rsplit('\\').next().unwrap_or("").to_string();
            }
        }
        options.insert(key.to_string(), val);
    }
    (ctype, options)
}

/// starlette `_user_safe_decode` — 그 문자 집합으로, 못 읽으면(없는 이름 포함) latin-1.
/// 파이썬 코덱 가운데 UTF-8·latin-1·ASCII 이름만 안다 — 그 밖의 이름은 없는 이름처럼 latin-1로 읽는다
fn safe_decode(src: &[u8], charset: &str) -> String {
    let mut name = String::new();
    let mut gap = false;
    for c in charset.chars().flat_map(char::to_lowercase) {
        if c.is_alphanumeric() || c == '.' {
            if gap && !name.is_empty() {
                name.push('_');
            }
            gap = false;
            name.push(c);
        } else {
            gap = true;
        }
    }
    const UTF8: [&str; 7] = [
        "utf_8",
        "utf8",
        "u8",
        "utf",
        "utf8_ucs2",
        "utf8_ucs4",
        "cp65001",
    ];
    if UTF8.contains(&name.as_str())
        && let Ok(s) = std::str::from_utf8(src)
    {
        return s.to_string();
    }
    latin1(src)
}

// ── python-multipart 파서 ──

/// starlette 콜백이 받는 것
trait Sink {
    fn part_begin(&mut self);
    fn part_data(&mut self, d: &[u8]) -> Result<(), Stop>;
    fn part_end(&mut self);
    fn header_field(&mut self, d: &[u8]);
    fn header_value(&mut self, d: &[u8]);
    fn header_end(&mut self);
    fn headers_finished(&mut self) -> Result<(), Stop>;
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum State {
    Start,
    StartBoundary,
    HeaderFieldStart,
    HeaderField,
    HeaderValueStart,
    HeaderValue,
    HeaderValueAlmostDone,
    HeadersAlmostDone,
    PartDataStart,
    PartData,
    EndBoundary,
    End,
}

const FLAG_PART_BOUNDARY: u8 = 1;
const FLAG_LAST_BOUNDARY: u8 = 2;
const CR: u8 = b'\r';
const LF: u8 = b'\n';
const HYPHEN: u8 = b'-';

fn is_token(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&b)
}

fn bfind(data: &[u8], needle: &[u8], start: isize, end: isize) -> isize {
    let (a, b) = (start.max(0) as usize, end.max(0) as usize);
    if needle.is_empty() || a > b || b - a < needle.len() {
        return if needle.is_empty() && a <= b {
            a as isize
        } else {
            -1
        };
    }
    data[a..b]
        .windows(needle.len())
        .position(|w| w == needle)
        .map_or(-1, |p| (a + p) as isize)
}

fn brfind(data: &[u8], needle: &[u8], start: isize, end: isize) -> isize {
    let (a, b) = (start.max(0) as usize, end.max(0) as usize);
    if needle.is_empty() || a > b || b - a < needle.len() {
        return -1;
    }
    data[a..b]
        .windows(needle.len())
        .rposition(|w| w == needle)
        .map_or(-1, |p| (a + p) as isize)
}

/// 표시 셋 — 머리 이름·머리 값·부분 데이터
#[derive(Default)]
struct Marks {
    header_field: Option<isize>,
    header_value: Option<isize>,
    part_data: Option<isize>,
}

#[derive(Clone, Copy)]
enum Mark {
    HeaderField,
    HeaderValue,
    PartData,
}

impl Marks {
    fn slot(&mut self, m: Mark) -> &mut Option<isize> {
        match m {
            Mark::HeaderField => &mut self.header_field,
            Mark::HeaderValue => &mut self.header_value,
            Mark::PartData => &mut self.part_data,
        }
    }
}

/// python-multipart `MultipartParser` — 본문 전부를 한 번에 쓴다(`write` 하나 + `finalize`).
/// 조각으로 나눠 써도 같은 콜백을 내도록 만든 파서라 결과는 같다
fn multipart_parse(boundary: &[u8], data: &[u8], sink: &mut impl Sink) -> Result<(), Stop> {
    if boundary.len() > MAX_BOUNDARY_LENGTH {
        return Err(Stop::Parser); // FormParserError
    }
    let mut bnd = b"\r\n--".to_vec();
    bnd.extend_from_slice(boundary);
    let bl = bnd.len() as isize;
    let length = data.len() as isize;
    let mut state = State::Start;
    let mut index: isize = 0;
    let mut flags: u8 = 0;
    let mut header_count = 0usize;
    let mut header_size = 0usize;
    let mut marks = Marks::default();
    let mut i: isize = 0;

    // data_callback — 표시부터 end_i까지 (한 번에 쓰므로 표시는 늘 0 이상)
    fn emit(
        marks: &mut Marks,
        m: Mark,
        data: &[u8],
        end_i: isize,
        remaining: bool,
        length: isize,
        sink: &mut impl Sink,
    ) -> Result<(), Stop> {
        let Some(marked) = *marks.slot(m) else {
            return Ok(());
        };
        if end_i > marked && marked >= 0 {
            let d = &data[marked as usize..end_i as usize];
            match m {
                Mark::HeaderField => sink.header_field(d),
                Mark::HeaderValue => sink.header_value(d),
                Mark::PartData => sink.part_data(d)?,
            }
        }
        *marks.slot(m) = remaining.then_some(end_i - length);
        Ok(())
    }

    while i < length {
        let mut c = data[i as usize];
        match state {
            State::Start => {
                if c == CR || c == LF {
                    i = bfind(data, b"-", i, length);
                    if i == -1 {
                        break; // 끝까지 읽은 것과 같다
                    }
                    continue;
                }
                index = 0;
                state = State::StartBoundary;
                i -= 1;
            }
            State::StartBoundary => {
                if index == bl - 2 {
                    if c == HYPHEN {
                        state = State::EndBoundary;
                    } else if c != CR {
                        return Err(Stop::Parser);
                    }
                    index += 1;
                } else if index == bl - 1 {
                    if c != LF {
                        return Err(Stop::Parser);
                    }
                    index = 0;
                    sink.part_begin();
                    header_count = 0;
                    header_size = 0;
                    state = State::HeaderFieldStart;
                } else {
                    if c != bnd[(index + 2) as usize] {
                        return Err(Stop::Parser);
                    }
                    index += 1;
                }
            }
            State::HeaderFieldStart => {
                index = 0;
                if c != CR {
                    header_count += 1;
                    if header_count > MAX_HEADER_COUNT {
                        return Err(Stop::Parser);
                    }
                    header_size = 0;
                }
                marks.header_field = Some(i);
                state = State::HeaderField;
                i -= 1;
            }
            State::HeaderField => {
                if c == CR && index == 0 {
                    marks.header_field = None;
                    state = State::HeadersAlmostDone;
                    i += 1;
                    continue;
                }
                let colon = bfind(data, b":", i, length);
                let end = if colon != -1 { colon } else { length };
                header_size += (if colon == -1 { end - i } else { end - i + 1 }) as usize;
                if header_size > MAX_HEADER_SIZE {
                    return Err(Stop::Parser);
                }
                if !data[i as usize..end as usize].iter().all(|&b| is_token(b)) {
                    return Err(Stop::Parser);
                }
                index += end - i;
                if colon == -1 {
                    i = length;
                } else {
                    if index == 0 {
                        return Err(Stop::Parser);
                    }
                    i = colon;
                    emit(&mut marks, Mark::HeaderField, data, i, false, length, sink)?;
                    state = State::HeaderValueStart;
                }
            }
            State::HeaderValueStart => {
                if c == b' ' {
                    header_size += 1;
                    if header_size > MAX_HEADER_SIZE {
                        return Err(Stop::Parser);
                    }
                    i += 1;
                    continue;
                }
                marks.header_value = Some(i);
                state = State::HeaderValue;
                i -= 1;
            }
            State::HeaderValue => {
                let cr = bfind(data, b"\r", i, length);
                let end = if cr != -1 { cr } else { length };
                header_size += (end - i) as usize;
                if header_size > MAX_HEADER_SIZE {
                    return Err(Stop::Parser);
                }
                if cr != -1 {
                    i = cr;
                    emit(&mut marks, Mark::HeaderValue, data, i, false, length, sink)?;
                    sink.header_end();
                    header_size = 0;
                    state = State::HeaderValueAlmostDone;
                } else {
                    i = length;
                }
            }
            State::HeaderValueAlmostDone => {
                if c != LF {
                    return Err(Stop::Parser);
                }
                state = State::HeaderFieldStart;
            }
            State::HeadersAlmostDone => {
                if c != LF {
                    return Err(Stop::Parser);
                }
                sink.headers_finished()?;
                state = State::PartDataStart;
            }
            State::PartDataStart => {
                marks.part_data = Some(i);
                state = State::PartData;
                i -= 1;
            }
            State::PartData => {
                let prev_index = index;
                if index == 0 {
                    let i0 = bfind(data, &bnd, i, length);
                    if i0 >= 0 {
                        index = bl - 1;
                        i = i0 + bl - 1;
                        c = data[i as usize];
                    } else {
                        let k = brfind(data, &bnd[..1], i.max(length - bl + 1), length);
                        if k != -1 && bnd.starts_with(&data[k as usize..]) {
                            index = length - k;
                        }
                        i = length;
                        continue;
                    }
                }
                if index < bl {
                    if bnd[index as usize] == c {
                        index += 1;
                    } else {
                        index = 0;
                    }
                } else if index == bl {
                    index += 1;
                    if c == CR {
                        flags |= FLAG_PART_BOUNDARY;
                    } else if c == HYPHEN {
                        flags |= FLAG_LAST_BOUNDARY;
                    } else {
                        index = 0;
                    }
                } else if index == bl + 1 {
                    if flags & FLAG_PART_BOUNDARY != 0 {
                        if c == LF {
                            flags &= !FLAG_PART_BOUNDARY;
                            emit(
                                &mut marks,
                                Mark::PartData,
                                data,
                                i - index,
                                false,
                                length,
                                sink,
                            )?;
                            sink.part_end();
                            sink.part_begin();
                            header_count = 0;
                            header_size = 0;
                            index = 0;
                            state = State::HeaderFieldStart;
                            i += 1;
                            continue;
                        }
                        index = 0;
                        flags &= !FLAG_PART_BOUNDARY;
                    } else if flags & FLAG_LAST_BOUNDARY != 0 {
                        if c == HYPHEN {
                            emit(
                                &mut marks,
                                Mark::PartData,
                                data,
                                i - index,
                                false,
                                length,
                                sink,
                            )?;
                            sink.part_end();
                            state = State::End;
                        } else {
                            index = 0;
                        }
                    }
                }
                if index == 0 && prev_index > 0 {
                    i -= 1;
                }
            }
            State::EndBoundary => {
                if index == bl - 1 {
                    if c != HYPHEN {
                        return Err(Stop::Parser);
                    }
                    index += 1;
                    state = State::End;
                }
            }
            State::End => {
                break;
            }
        }
        i += 1;
    }
    emit(
        &mut marks,
        Mark::HeaderField,
        data,
        length,
        true,
        length,
        sink,
    )?;
    emit(
        &mut marks,
        Mark::HeaderValue,
        data,
        length,
        true,
        length,
        sink,
    )?;
    emit(
        &mut marks,
        Mark::PartData,
        data,
        length - index,
        true,
        length,
        sink,
    )?;
    Ok(())
}

/// (이름, 값) 바이트 짝들
type RawFields = Vec<(Vec<u8>, Vec<u8>)>;

/// python-multipart `QuerystringParser`(엄격하지 않게) — (이름, 값) 바이트 조각을 starlette `FormParser`처럼 모은다
fn querystring_parse(data: &[u8]) -> Result<RawFields, Stop> {
    #[derive(PartialEq)]
    enum Q {
        BeforeField,
        FieldName,
        FieldData,
    }
    let too_big = || {
        Stop::Starlette(format!(
            "Field exceeded maximum size of {}KB.",
            MAX_PART_SIZE / 1024
        ))
    };
    let mut items = Vec::new();
    let (mut name, mut value) = (Vec::new(), Vec::new());
    let mut size = 0usize;
    let mut fields = 0usize;
    let mut field_end = |name: &mut Vec<u8>, value: &mut Vec<u8>, items: &mut Vec<_>| {
        fields += 1;
        if fields > MAX_FIELDS {
            return Err(Stop::Starlette(format!(
                "Too many fields. Maximum number of fields is {MAX_FIELDS}."
            )));
        }
        items.push((std::mem::take(name), std::mem::take(value)));
        Ok(())
    };
    let length = data.len() as isize;
    let mut state = Q::BeforeField;
    let mut i: isize = 0;
    while i < length {
        let ch = data[i as usize];
        match state {
            Q::BeforeField => {
                // 잇단 `&`는 건너뛴다(엄격하지 않게)
                if ch != b'&' {
                    size = 0;
                    name.clear();
                    value.clear();
                    i -= 1;
                    state = Q::FieldName;
                }
            }
            Q::FieldName => {
                let sep = bfind(data, b"&", i, length);
                let eq = bfind(data, b"=", i, if sep != -1 { sep } else { length });
                let take = |a: isize, b: isize, out: &mut Vec<u8>, size: &mut usize| {
                    if a < b {
                        *size += (b - a) as usize;
                        if *size > MAX_PART_SIZE {
                            return Err(too_big());
                        }
                        out.extend_from_slice(&data[a as usize..b as usize]);
                    }
                    Ok(())
                };
                if eq != -1 {
                    take(i, eq, &mut name, &mut size)?;
                    i = eq;
                    state = Q::FieldData;
                } else if sep != -1 {
                    take(i, sep, &mut name, &mut size)?;
                    field_end(&mut name, &mut value, &mut items)?;
                    i = sep - 1;
                    state = Q::BeforeField;
                } else {
                    take(i, length, &mut name, &mut size)?;
                    i = length;
                }
            }
            Q::FieldData => {
                let sep = bfind(data, b"&", i, length);
                let end = if sep != -1 { sep } else { length };
                if i < end {
                    size += (end - i) as usize;
                    if size > MAX_PART_SIZE {
                        return Err(too_big());
                    }
                    value.extend_from_slice(&data[i as usize..end as usize]);
                }
                if sep != -1 {
                    field_end(&mut name, &mut value, &mut items)?;
                    i = sep - 1;
                    state = Q::BeforeField;
                } else {
                    i = length;
                }
            }
        }
        i += 1;
    }
    if state != Q::BeforeField {
        field_end(&mut name, &mut value, &mut items)?;
    }
    Ok(items)
}

/// starlette `MultiPartParser`의 콜백
struct Parts {
    charset: String,
    items: Vec<(String, FormValue)>,
    files: usize,
    fields: usize,
    partial_name: Vec<u8>,
    partial_value: Vec<u8>,
    disposition: Option<Vec<u8>>,
    field_name: String,
    data: Vec<u8>,
    file: Option<Upload>,
    item_headers: Vec<(Vec<u8>, Vec<u8>)>,
}

impl Sink for Parts {
    fn part_begin(&mut self) {
        self.disposition = None;
        self.field_name = String::new();
        self.data = Vec::new();
        self.file = None;
        self.item_headers = Vec::new();
    }

    fn part_data(&mut self, d: &[u8]) -> Result<(), Stop> {
        match &mut self.file {
            None => {
                if self.data.len() + d.len() > MAX_PART_SIZE {
                    return Err(Stop::Starlette(format!(
                        "Part exceeded maximum size of {}KB.",
                        MAX_PART_SIZE / 1024
                    )));
                }
                self.data.extend_from_slice(d);
            }
            Some(f) => f.data.extend_from_slice(d),
        }
        Ok(())
    }

    fn part_end(&mut self) {
        let name = std::mem::take(&mut self.field_name);
        let value = match self.file.take() {
            None => FormValue::Text(safe_decode(&self.data, &self.charset)),
            Some(f) => FormValue::File(f),
        };
        self.items.push((name, value));
    }

    fn header_field(&mut self, d: &[u8]) {
        self.partial_name.extend_from_slice(d);
    }

    fn header_value(&mut self, d: &[u8]) {
        self.partial_value.extend_from_slice(d);
    }

    fn header_end(&mut self) {
        let field = std::mem::take(&mut self.partial_name).to_ascii_lowercase();
        let value = std::mem::take(&mut self.partial_value);
        if field == b"content-disposition" {
            self.disposition = Some(value.clone());
        }
        self.item_headers.push((field, value));
    }

    fn headers_finished(&mut self) -> Result<(), Stop> {
        let raw = self.disposition.as_deref().map(latin1);
        let (_, options) = parse_options_header(raw.as_deref());
        let Some(name) = options.get("name") else {
            return Err(Stop::Starlette(
                "The Content-Disposition header field \"name\" must be provided.".into(),
            ));
        };
        self.field_name = safe_decode(&latin1_bytes(name), &self.charset);
        if let Some(filename) = options.get("filename") {
            self.files += 1;
            if self.files > MAX_FILES {
                return Err(Stop::Starlette(format!(
                    "Too many files. Maximum number of files is {MAX_FILES}."
                )));
            }
            let content_type = self
                .item_headers
                .iter()
                .find(|(k, _)| k == b"content-type")
                .map(|(_, v)| latin1(v));
            self.file = Some(Upload {
                filename: Some(safe_decode(&latin1_bytes(filename), &self.charset)),
                content_type,
                data: Vec::new(),
            });
        } else {
            self.fields += 1;
            if self.fields > MAX_FIELDS {
                return Err(Stop::Starlette(format!(
                    "Too many fields. Maximum number of fields is {MAX_FIELDS}."
                )));
            }
            self.file = None;
        }
        Ok(())
    }
}

/// starlette `Request.form()` + FastAPI가 덮는 400 — multipart·urlencoded, 그 밖의 종류는 빈 폼. 받은 차례 그대로
pub fn read_form(headers: &HeaderMap, body: &[u8]) -> Result<Vec<(String, FormValue)>, Problem> {
    let ct = first_header(headers, "content-type");
    let (ctype, _) = parse_options_header(ct.as_deref());
    if ctype == "multipart/form-data" {
        let (_, params) = parse_options_header(ct.as_deref());
        let charset = params
            .get("charset")
            .cloned()
            .unwrap_or_else(|| "utf-8".into());
        let Some(boundary) = params.get("boundary") else {
            return Err(Stop::Starlette("Missing boundary in multipart.".into()).problem());
        };
        let mut parts = Parts {
            charset,
            items: Vec::new(),
            files: 0,
            fields: 0,
            partial_name: Vec::new(),
            partial_value: Vec::new(),
            disposition: None,
            field_name: String::new(),
            data: Vec::new(),
            file: None,
            item_headers: Vec::new(),
        };
        multipart_parse(&latin1_bytes(boundary), body, &mut parts).map_err(Stop::problem)?;
        Ok(parts.items)
    } else if ctype == "application/x-www-form-urlencoded" {
        let items = querystring_parse(body).map_err(Stop::problem)?;
        Ok(items
            .into_iter()
            .map(|(n, v)| {
                let plus = |b: &[u8]| unquote(&latin1(b).replace('+', " "));
                (plus(&n), FormValue::Text(plus(&v)))
            })
            .collect())
    } else {
        Ok(Vec::new())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderValue;
    use base64::Engine;
    use base64::engine::general_purpose::STANDARD;

    fn render(r: Result<Vec<(String, FormValue)>, Problem>) -> serde_json::Value {
        match r {
            Err(p) => serde_json::json!({"error": p.title()}),
            Ok(items) => serde_json::json!({"items": items.into_iter().map(|(n, v)| match v {
                FormValue::Text(t) => serde_json::json!([n, {"t": t}]),
                FormValue::File(f) => serde_json::json!([n, {"f": [f.filename, f.content_type, STANDARD.encode(&f.data)]}]),
            }).collect::<Vec<_>>()}),
        }
    }

    fn part(name: &str, value: &[u8], filename: Option<&str>) -> Vec<u8> {
        let mut disp = format!("Content-Disposition: form-data; name=\"{name}\"");
        if let Some(f) = filename {
            disp.push_str(&format!("; filename=\"{f}\""));
        }
        let mut out = format!("--XyZ-bnd\r\n{disp}\r\n\r\n").into_bytes();
        out.extend_from_slice(value);
        out.extend_from_slice(b"\r\n");
        out
    }

    fn outcome(ct: &str, body: &[u8]) -> Result<usize, String> {
        let mut headers = HeaderMap::new();
        headers.insert("content-type", HeaderValue::from_str(ct).expect("머리"));
        read_form(&headers, body)
            .map(|v| v.len())
            .map_err(|p| p.title())
    }

    /// 상한 — 파이썬 판에서 잰 답(본문이 커서 정답 파일 밖)
    #[test]
    fn limits_like_starlette() {
        const M: usize = 1024 * 1024;
        let mp = "multipart/form-data; boundary=XyZ-bnd";
        let q = "application/x-www-form-urlencoded";
        let end = b"--XyZ-bnd--\r\n";
        let many = |n: usize, file: Option<&str>| {
            let mut b: Vec<u8> = (0..n).flat_map(|_| part("a", b"1", file)).collect();
            b.extend_from_slice(end);
            b
        };
        let one = |v: &[u8], file: Option<&str>| [part("a", v, file), end.to_vec()].concat();
        assert_eq!(outcome(mp, &one(&vec![b'x'; M], None)), Ok(1));
        assert_eq!(
            outcome(mp, &one(&vec![b'x'; M + 1], None)),
            Err("Part exceeded maximum size of 1024KB.".into())
        );
        assert_eq!(outcome(mp, &one(&vec![b'x'; M + 1], Some("f"))), Ok(1));
        assert_eq!(
            outcome(q, &[b"a=".as_slice(), &vec![b'x'; M - 1]].concat()),
            Ok(1)
        );
        assert_eq!(
            outcome(q, &[b"a=".as_slice(), &vec![b'x'; M]].concat()),
            Err("Field exceeded maximum size of 1024KB.".into())
        );
        let fields = |n: usize| vec!["a=1"; n].join("&").into_bytes();
        assert_eq!(outcome(q, &fields(1000)), Ok(1000));
        assert_eq!(
            outcome(q, &fields(1001)),
            Err("Too many fields. Maximum number of fields is 1000.".into())
        );
        assert_eq!(
            outcome(mp, &many(1001, None)),
            Err("Too many fields. Maximum number of fields is 1000.".into())
        );
        assert_eq!(
            outcome(mp, &many(1001, Some("f"))),
            Err("Too many files. Maximum number of files is 1000.".into())
        );
    }

    /// 파이썬 starlette 1.6.0 + python-multipart 0.0.32가 낸 답과 같다 — `xtask/py/form_cases.py`
    #[test]
    fn same_as_starlette() {
        let raw = include_str!("../../tests/golden/form.json");
        let cases: Vec<serde_json::Value> = serde_json::from_str(raw).expect("정답");
        assert!(cases.len() > 100);
        for (n, case) in cases.iter().enumerate() {
            let mut headers = HeaderMap::new();
            if let Some(ct) = case["ct"].as_str() {
                let bytes = latin1_bytes(ct);
                headers.insert(
                    "content-type",
                    HeaderValue::from_bytes(&bytes).expect("머리"),
                );
            }
            let body = STANDARD
                .decode(case["body"].as_str().expect("본문"))
                .expect("base64");
            let got = render(read_form(&headers, &body));
            assert_eq!(got, case["out"], "사례 {n}: {}", case["ct"]);
        }
    }
}
