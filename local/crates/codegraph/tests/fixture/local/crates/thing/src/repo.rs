//! 리포지토리

pub struct Repo {
    pub rows: Vec<String>,
}

impl Repo {
    pub fn new() -> Repo {
        Repo { rows: Vec::new() }
    }

    pub fn find(&self, id: usize) -> Option<&String> {
        self.rows.get(id)
    }
}
