use anyhow::{anyhow, Context, Result};
use pyo3::prelude::*;
use pyo3::types::PyDict;
use rusqlite::{params, Connection, OptionalExtension};
use serde::Deserialize;
use std::cell::RefCell;
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use tantivy::collector::TopDocs;
use tantivy::query::QueryParser;
use tantivy::schema::{Field, Schema, Value, STORED, TEXT};
use tantivy::{doc, Index, IndexReader, IndexWriter, TantivyDocument};
use usearch::Index as USearchIndex;

#[derive(Debug, Clone, Deserialize)]
struct DocInput {
    path: String,
    content: String,
    embedding: Option<Vec<f32>>,
    updated_at_unix_ms: Option<i64>,
}

struct TextIndex {
    index: Index,
    reader: IndexReader,
    writer: IndexWriter,
    fields: TextIndexFields,
}

#[derive(Clone)]
struct TextIndexFields {
    id: Field,
    collection: Field,
    path: Field,
    content: Field,
}

impl TextIndex {
    fn open_or_create(dir: &Path) -> Result<Self> {
        std::fs::create_dir_all(dir).context("create tantivy dir")?;

        let mut schema_builder = Schema::builder();
        schema_builder.add_u64_field("id", STORED);
        schema_builder.add_text_field("collection", TEXT | STORED);
        schema_builder.add_text_field("path", TEXT | STORED);
        schema_builder.add_text_field("content", TEXT);
        let schema = schema_builder.build();

        let index = Index::open_in_dir(dir)
            .or_else(|_| Index::create_in_dir(dir, schema.clone()))
            .context("open or create tantivy index")?;

        let fields = TextIndexFields {
            id: index.schema().get_field("id").context("id field")?,
            collection: index.schema().get_field("collection").context("collection field")?,
            path: index.schema().get_field("path").context("path field")?,
            content: index.schema().get_field("content").context("content field")?,
        };

        let reader = index.reader().context("create reader")?;
        let writer = index.writer(50_000_000).context("create writer")?;

        Ok(Self {
            index,
            reader,
            writer,
            fields,
        })
    }
}

struct VectorIndex {
    index: USearchIndex,
    dim: usize,
    index_path: PathBuf,
}

impl VectorIndex {
    fn open_or_create(index_path: PathBuf, dim: usize, capacity: usize) -> Result<Self> {
        let index = USearchIndex::new(&usearch::IndexOptions {
            dimensions: dim,
            metric: usearch::MetricKind::L2sq,
            quantization: usearch::ScalarKind::F32,
            connectivity: 16,
            expansion_add: 128,
            expansion_search: 64,
            multi: false,
        })
        .map_err(|e| anyhow!("create usearch index: {:?}", e))?;

        if index_path.exists() {
            index
                .load(index_path.to_string_lossy().as_ref())
                .map_err(|e| anyhow!("load usearch index: {:?}", e))?;
        } else {
            std::fs::create_dir_all(index_path.parent().unwrap_or(Path::new(".")))
                .context("create usearch parent dir")?;
            index
                .reserve(capacity)
                .map_err(|e| anyhow!("reserve usearch: {:?}", e))?;
        }

        Ok(Self {
            index,
            dim,
            index_path,
        })
    }

    fn save(&self) -> Result<()> {
        let tmp = self
            .index_path
            .with_extension(format!("{}.tmp", self.index_path.extension().and_then(|s| s.to_str()).unwrap_or("bin")));

        self.index
            .save(tmp.to_string_lossy().as_ref())
            .map_err(|e| anyhow!("save usearch index: {:?}", e))?;
        std::fs::rename(&tmp, &self.index_path).context("rename usearch index")?;
        Ok(())
    }
}

fn sqlite_open_or_create(db_path: &Path) -> Result<Connection> {
    std::fs::create_dir_all(db_path.parent().unwrap_or(Path::new("."))).context("create db parent")?;
    let conn = Connection::open(db_path).context("open sqlite")?;
    conn.pragma_update(None, "journal_mode", "WAL")?;
    conn.execute_batch(
        r#"
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  collection TEXT NOT NULL,
  path TEXT NOT NULL,
  content TEXT NOT NULL,
  updated_at_unix_ms INTEGER,
  indexed_at_unix_ms INTEGER,
  embedding_json TEXT,
  UNIQUE(collection, path)
);

CREATE TABLE IF NOT EXISTS index_tasks (
  doc_id INTEGER PRIMARY KEY,
  need_text INTEGER NOT NULL,
  need_vector INTEGER NOT NULL,
  status TEXT NOT NULL,
  retries INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  updated_at_unix_ms INTEGER NOT NULL
);
"#,
    )?;
    let cols: HashSet<String> = {
        let mut stmt = conn.prepare("PRAGMA table_info(documents)")?;
        let mut rows = stmt.query([])?;
        let mut cols: HashSet<String> = HashSet::new();
        while let Some(r) = rows.next()? {
            let name: String = r.get(1)?;
            cols.insert(name);
        }
        cols
    };
    if !cols.contains("indexed_at_unix_ms") {
        let _ = conn.execute("ALTER TABLE documents ADD COLUMN indexed_at_unix_ms INTEGER", []);
    }
    if !cols.contains("embedding_json") {
        let _ = conn.execute("ALTER TABLE documents ADD COLUMN embedding_json TEXT", []);
    }
    Ok(conn)
}

#[pyclass(unsendable)]
struct MemosCore {
    base_dir: PathBuf,
    db: RefCell<Connection>,
    text: RefCell<TextIndex>,
    vectors: RefCell<VectorIndex>,
}

#[pymethods]
impl MemosCore {
    #[new]
    fn new(base_dir: String, embedding_dim: usize, capacity: usize) -> PyResult<Self> {
        let base_dir = PathBuf::from(base_dir);
        let db_path = base_dir.join("memoscore.sqlite");
        let tantivy_dir = base_dir.join("tantivy_index");
        let usearch_path = base_dir.join("usearch_index.bin");

        let db = sqlite_open_or_create(&db_path).map_err(to_pyerr)?;
        let text = TextIndex::open_or_create(&tantivy_dir).map_err(to_pyerr)?;
        let vectors = VectorIndex::open_or_create(usearch_path, embedding_dim, capacity).map_err(to_pyerr)?;

        Ok(Self {
            base_dir,
            db: RefCell::new(db),
            text: RefCell::new(text),
            vectors: RefCell::new(vectors),
        })
    }

    fn upsert_documents(&self, py: Python<'_>, collection: String, docs: Vec<Py<PyAny>>) -> PyResult<u64> {
        let mut parsed: Vec<DocInput> = Vec::with_capacity(docs.len());
        for d in docs {
            let any = d.bind(py);
            let dict: &Bound<'_, PyDict> = any.downcast()?;
            let path: String = dict
                .get_item("path")?
                .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("missing path"))?
                .extract()?;
            let content: String = dict
                .get_item("content")?
                .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("missing content"))?
                .extract()?;
            let embedding: Option<Vec<f32>> = match dict.get_item("embedding")? {
                Some(v) => Some(v.extract()?),
                None => None,
            };
            let updated_at_unix_ms: Option<i64> = match dict.get_item("updated_at_unix_ms")? {
                Some(v) => Some(v.extract()?),
                None => None,
            };
            parsed.push(DocInput {
                path,
                content,
                embedding,
                updated_at_unix_ms,
            });
        }

        let db = self.db.borrow_mut();
        let mut changed = 0u64;

        for d in parsed {
            let updated_at = d
                .updated_at_unix_ms
                .unwrap_or_else(|| chrono_unix_ms());
            let embedding_json: Option<String> = match d.embedding.as_ref() {
                Some(v) => Some(serde_json::to_string(v).map_err(|e| to_pyerr(anyhow!("serialize embedding_json: {:?}", e)))?),
                None => None,
            };

            db.execute(
                r#"
INSERT INTO documents(collection, path, content, updated_at_unix_ms, indexed_at_unix_ms, embedding_json)
VALUES (?1, ?2, ?3, ?4, NULL, ?5)
ON CONFLICT(collection, path) DO UPDATE SET
  content=excluded.content,
  updated_at_unix_ms=excluded.updated_at_unix_ms,
  indexed_at_unix_ms=NULL,
  embedding_json=excluded.embedding_json
"#,
                params![collection, d.path, d.content, updated_at, embedding_json],
            )
            .map_err(to_pyerr)?;

            let id: i64 = db
                .query_row(
                    "SELECT id FROM documents WHERE collection=?1 AND path=?2",
                    params![collection, d.path],
                    |row| row.get(0),
                )
                .map_err(to_pyerr)?;

            db.execute(
                r#"
INSERT INTO index_tasks(doc_id, need_text, need_vector, status, retries, last_error, updated_at_unix_ms)
VALUES (?1, 1, 1, 'pending', 0, NULL, ?2)
ON CONFLICT(doc_id) DO UPDATE SET
  need_text=1,
  need_vector=1,
  status='pending',
  updated_at_unix_ms=excluded.updated_at_unix_ms
"#,
                params![id, updated_at],
            )
            .map_err(to_pyerr)?;

            changed += 1;
        }

        Ok(changed)
    }

    #[pyo3(signature=(limit=200))]
    fn sync_index_tasks(&self, limit: usize) -> PyResult<u64> {
        let db = self.db.borrow_mut();
        let mut text = self.text.borrow_mut();
        let vectors = self.vectors.borrow_mut();

        let ids: Vec<i64> = {
            let mut stmt = db
                .prepare("SELECT doc_id FROM index_tasks WHERE status!='done' ORDER BY updated_at_unix_ms ASC LIMIT ?1")
                .map_err(to_pyerr)?;
            let ids_iter = stmt
                .query_map(params![limit as i64], |row| row.get::<_, i64>(0))
                .map_err(to_pyerr)?;
            let mut out: Vec<i64> = Vec::new();
            for r in ids_iter {
                out.push(r.map_err(to_pyerr)?);
            }
            out
        };
        if ids.is_empty() {
            return Ok(0);
        }

        let mut changed = 0u64;
        let now = chrono_unix_ms();

        for id in ids {
            let row = db
                .query_row(
                    "SELECT collection, path, content, embedding_json FROM documents WHERE id=?1",
                    params![id],
                    |r| {
                        let collection: String = r.get(0)?;
                        let path: String = r.get(1)?;
                        let content: String = r.get(2)?;
                        let embedding_json: Option<String> = r.get(3)?;
                        Ok((collection, path, content, embedding_json))
                    },
                )
                .optional()
                .map_err(to_pyerr)?;

            let Some((collection, path, content, embedding_json)) = row else {
                let _ = db.execute("UPDATE index_tasks SET status='done' WHERE doc_id=?1", params![id]);
                continue;
            };

            let mut err: Option<String> = None;

            text.writer
                .delete_term(tantivy::Term::from_field_u64(text.fields.id, id as u64));
            if let Err(e) = text.writer.add_document(doc!(
                text.fields.id => id as u64,
                text.fields.collection => collection.as_str(),
                text.fields.path => path.as_str(),
                text.fields.content => content.as_str(),
            )) {
                err = Some(format!("tantivy add_document: {:?}", e));
            }

            let _ = vectors.index.remove(id as u64);
            if err.is_none() {
                if let Some(s) = embedding_json.as_ref() {
                    match serde_json::from_str::<Vec<f32>>(s) {
                        Ok(embedding) => {
                            if embedding.len() != vectors.dim {
                                err = Some(format!("embedding dim mismatch: expected {}, got {}", vectors.dim, embedding.len()));
                            } else if let Err(e) = vectors.index.add(id as u64, &embedding) {
                                err = Some(format!("usearch add failed: {:?}", e));
                            }
                        }
                        Err(e) => {
                            err = Some(format!("embedding_json parse: {:?}", e));
                        }
                    }
                }
            }

            if let Some(err_msg) = err {
                let _ = db.execute(
                    "UPDATE index_tasks SET status='failed', retries=retries+1, last_error=?2 WHERE doc_id=?1",
                    params![id, err_msg],
                );
                continue;
            }

            let _ = db.execute(
                "UPDATE index_tasks SET status='done', last_error=NULL WHERE doc_id=?1",
                params![id],
            );
            let _ = db.execute(
                "UPDATE documents SET indexed_at_unix_ms=?2 WHERE id=?1",
                params![id, now],
            );
            changed += 1;
        }

        if changed > 0 {
            text.writer.commit().map_err(to_pyerr)?;
            let _ = text.reader.reload();
            vectors.save().map_err(to_pyerr)?;
        }

        Ok(changed)
    }

    #[pyo3(signature=(collection=None, query_text=None, query_vec=None, top_k=8))]
    fn search(
        &self,
        collection: Option<String>,
        query_text: Option<String>,
        query_vec: Option<Vec<f32>>,
        top_k: usize,
    ) -> PyResult<Vec<PyObject>> {
        let db = self.db.borrow();
        let text = self.text.borrow();
        let vectors = self.vectors.borrow();

        let mut score_map: HashMap<u64, (f64, f64)> = HashMap::new();

        if let Some(q) = query_text.as_ref() {
            let searcher = text.reader.searcher();
            let parser = QueryParser::for_index(&text.index, vec![text.fields.content, text.fields.path]);
            let query = parser.parse_query(q).map_err(to_pyerr)?;

            let top_docs = searcher
                .search(&query, &TopDocs::with_limit(top_k.saturating_mul(4).max(top_k)))
                .map_err(to_pyerr)?;

            let mut max_score = 0.0;
            for (score, _) in &top_docs {
                if *score as f64 > max_score {
                    max_score = *score as f64;
                }
            }
            let denom = if max_score <= 0.0 { 1.0 } else { max_score };
            for (score, addr) in top_docs {
                let doc: TantivyDocument = searcher.doc(addr).map_err(to_pyerr)?;
                let id = doc
                    .get_first(text.fields.id)
                    .and_then(|v| v.as_u64())
                    .ok_or_else(|| pyo3::exceptions::PyRuntimeError::new_err("tantivy doc missing id"))?;
                let norm = (score as f64) / denom;
                let e = score_map.entry(id).or_insert((0.0, 0.0));
                e.0 = norm;
            }
        }

        if let Some(vec) = query_vec.as_ref() {
            if vec.len() != vectors.dim {
                return Err(pyo3::exceptions::PyValueError::new_err(format!(
                    "query_vec dim mismatch: expected {}, got {}",
                    vectors.dim,
                    vec.len()
                )));
            }
            let matches = vectors
                .index
                .search(vec, top_k.saturating_mul(4).max(top_k))
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("usearch search failed: {:?}", e)))?;

            let mut best = 0.0;
            let mut scored: Vec<(u64, f64)> = Vec::with_capacity(matches.keys.len());
            for (id, dist) in matches.keys.iter().zip(matches.distances.iter()) {
                let sim = 1.0 / (1.0 + (*dist as f64).max(0.0));
                if sim > best {
                    best = sim;
                }
                scored.push((*id, sim));
            }
            let denom = if best <= 0.0 { 1.0 } else { best };
            for (id, sim) in scored {
                let norm = sim / denom;
                let e = score_map.entry(id).or_insert((0.0, 0.0));
                e.1 = norm;
            }
        }

        let mut merged: Vec<(u64, f64, String)> = score_map
            .into_iter()
            .map(|(id, (t, v))| {
                let score = t * 0.55 + v * 0.45;
                let source = if t > 0.0 && v > 0.0 {
                    "hybrid"
                } else if t > 0.0 {
                    "bm25"
                } else {
                    "ann"
                };
                (id, score, source.to_string())
            })
            .collect();

        merged.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        merged.truncate(top_k);

        let mut out: Vec<PyObject> = Vec::with_capacity(merged.len());
        for (id, score, source) in merged {
            let (col, path, content): (String, String, String) = db
                .query_row(
                    "SELECT collection, path, content FROM documents WHERE id=?1",
                    params![id as i64],
                    |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
                )
                .map_err(to_pyerr)?;

            if let Some(filter_col) = collection.as_ref() {
                if &col != filter_col {
                    continue;
                }
            }

            Python::with_gil(|py| {
                let d = PyDict::new(py);
                d.set_item("id", id).map_err(to_pyerr)?;
                d.set_item("collection", col).map_err(to_pyerr)?;
                d.set_item("path", path).map_err(to_pyerr)?;
                d.set_item("content", content).map_err(to_pyerr)?;
                d.set_item("score", score).map_err(to_pyerr)?;
                d.set_item("source", source).map_err(to_pyerr)?;
                out.push(d.into_py(py));
                Ok::<(), PyErr>(())
            })?;
        }

        Ok(out)
    }

    fn base_dir(&self) -> PyResult<String> {
        Ok(self.base_dir.to_string_lossy().to_string())
    }
}

#[pymodule]
fn memoscore(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<MemosCore>()?;
    Ok(())
}

fn to_pyerr<E: std::fmt::Display>(e: E) -> PyErr {
    pyo3::exceptions::PyRuntimeError::new_err(e.to_string())
}

fn chrono_unix_ms() -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

