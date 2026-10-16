// Copyright 2021-Present Datadog, Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

use tantivy::query::Scorer;
use tantivy::{DocId, DocSet, Score, TERMINATED};

/// Fallible verification completes before the infallible DocSet API exposes matches.
/// Only candidate documents are verified, without a top-k truncation.
pub(crate) struct CandidateScores {
    scores: Vec<(DocId, Score)>,
    cursor: usize,
    boost: Score,
}
impl CandidateScores {
    pub(crate) fn new(scores: Vec<(DocId, Score)>, boost: Score) -> Self {
        debug_assert!(scores.windows(2).all(|pair| pair[0].0 < pair[1].0));
        Self {
            scores,
            cursor: 0,
            boost,
        }
    }
}
impl DocSet for CandidateScores {
    fn advance(&mut self) -> DocId {
        self.cursor = (self.cursor + 1).min(self.scores.len());
        self.doc()
    }
    fn seek(&mut self, target: DocId) -> DocId {
        self.cursor += self.scores[self.cursor..].partition_point(|(doc, _)| *doc < target);
        self.doc()
    }
    fn doc(&self) -> DocId {
        self.scores
            .get(self.cursor)
            .map(|(doc, _)| *doc)
            .unwrap_or(TERMINATED)
    }
    fn size_hint(&self) -> u32 {
        (self.scores.len() - self.cursor) as u32
    }
}
impl Scorer for CandidateScores {
    fn score(&mut self) -> Score {
        self.scores
            .get(self.cursor)
            .map(|(_, score)| score * self.boost)
            .unwrap_or(0.0)
    }
}
