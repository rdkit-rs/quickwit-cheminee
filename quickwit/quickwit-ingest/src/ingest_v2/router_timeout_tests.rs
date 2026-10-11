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

use std::collections::HashSet;
use std::sync::{Arc, Mutex as StdMutex};

use quickwit_proto::control_plane::MockControlPlaneService;
use quickwit_proto::ingest::ingester::{
    IngesterServiceClient, IngesterStatus, MockIngesterService, PersistSuccess,
};
use quickwit_proto::ingest::router::IngestSubrequest;
use quickwit_proto::ingest::{DocBatchV2, Shard, ShardState};
use quickwit_proto::types::{DocUid, IndexUid, Position, ShardId};

use super::*;
use crate::IngesterPoolEntry;

async fn delayed_router(
    delay: Duration,
    return_timeout: bool,
) -> (IngestRouter, Arc<StdMutex<Vec<DocUid>>>) {
    let persisted = Arc::new(StdMutex::new(Vec::new()));
    let recorded = persisted.clone();
    let layer = tower::layer::layer_fn(move |_inner| {
        let recorded = recorded.clone();
        tower::service_fn(move |request: PersistRequest| {
            let recorded = recorded.clone();
            let task = tokio::spawn(async move {
                tokio::time::sleep(delay).await;
                let mut successes = Vec::new();
                for subrequest in request.subrequests {
                    let ids: Vec<_> = subrequest
                        .doc_batch
                        .unwrap()
                        .docs()
                        .map(|(id, _)| id)
                        .collect();
                    recorded.lock().unwrap().extend(ids.iter().copied());
                    successes.push(PersistSuccess {
                        subrequest_id: subrequest.subrequest_id,
                        index_uid: subrequest.index_uid,
                        source_id: subrequest.source_id,
                        shard_id: Some(ShardId::from(1)),
                        replication_position_inclusive: Some(Position::offset(ids.len() as u64)),
                        num_persisted_docs: ids.len() as u32,
                        parse_failures: Vec::new(),
                    });
                }
                if return_timeout {
                    Err(IngestV2Error::Timeout("acknowledgement lost".to_string()))
                } else {
                    Ok(PersistResponse {
                        leader_id: request.leader_id,
                        successes,
                        failures: Vec::new(),
                        routing_update: None,
                    })
                }
            });
            async move { task.await.unwrap() }
        })
    });
    let client = IngesterServiceClient::tower()
        .stack_persist_layer(layer)
        .build_from_mock(MockIngesterService::new());
    let pool = IngesterPool::default();
    pool.insert(
        NodeId::from_str("ingester"),
        IngesterPoolEntry {
            client,
            availability_zone: None,
            status: IngesterStatus::Ready,
        },
    );
    let router = IngestRouter::new(
        NodeId::from_str("router"),
        ControlPlaneServiceClient::from_mock(MockControlPlaneService::new()),
        pool,
        1,
        EventBroker::default(),
        None,
    );
    let index_uid = IndexUid::for_test("index", 0);
    router.state.lock().await.routing_table.merge_from_shards(
        index_uid.clone(),
        "source".to_string(),
        vec![Shard {
            index_uid: Some(index_uid),
            source_id: "source".to_string(),
            shard_id: Some(ShardId::from(1)),
            shard_state: ShardState::Open as i32,
            leader_id: "ingester".to_string(),
            ..Default::default()
        }],
    );
    (router, persisted)
}

fn request() -> IngestRequestV2 {
    IngestRequestV2 {
        subrequests: vec![IngestSubrequest {
            subrequest_id: 0,
            index_id: "index".to_string(),
            source_id: "source".to_string(),
            doc_batch: Some(DocBatchV2::for_test(["id-1", "id-2", "id-3"])),
        }],
        commit_type: CommitTypeV2::Auto as i32,
    }
}

fn assert_ids_once(persisted: &StdMutex<Vec<DocUid>>) {
    let ids = persisted.lock().unwrap();
    assert_eq!(ids.len(), 3);
    assert_eq!(ids.iter().copied().collect::<HashSet<_>>().len(), 3);
    assert_eq!(
        *ids,
        vec![
            DocUid::for_test(0),
            DocUid::for_test(1),
            DocUid::for_test(2)
        ]
    );
}

#[tokio::test(start_paused = true)]
async fn slow_persist_keeps_original_acknowledgement_and_ids() {
    let (router, persisted) = delayed_router(Duration::from_secs(1), false).await;
    let response = router
        .retry_batch_persist(request(), MAX_PERSIST_ATTEMPTS)
        .await;
    assert!(response.failures.is_empty());
    assert_eq!(response.successes.len(), 1);
    assert_eq!(response.successes[0].num_ingested_docs, 3);
    tokio::time::sleep(Duration::from_secs(5)).await;
    assert_ids_once(&persisted);
}

#[tokio::test(start_paused = true)]
async fn persist_deadline_does_not_replay_a_late_append() {
    let (router, persisted) = delayed_router(Duration::from_secs(3), false).await;
    let start = tokio::time::Instant::now();
    let response = router
        .retry_batch_persist(request(), MAX_PERSIST_ATTEMPTS)
        .await;
    assert_eq!(start.elapsed(), PERSIST_REQUEST_TIMEOUT);
    assert!(response.successes.is_empty());
    assert_eq!(response.failures.len(), 1);
    assert_eq!(response.failures[0].reason(), IngestFailureReason::Timeout);
    tokio::time::sleep(Duration::from_secs(5)).await;
    assert_ids_once(&persisted);
}

#[tokio::test(start_paused = true)]
async fn returned_persist_timeout_does_not_replay_committed_ids() {
    let (router, persisted) = delayed_router(Duration::from_millis(10), true).await;
    let response = router
        .retry_batch_persist(request(), MAX_PERSIST_ATTEMPTS)
        .await;
    assert!(response.successes.is_empty());
    assert_eq!(response.failures.len(), 1);
    assert_eq!(response.failures[0].reason(), IngestFailureReason::Timeout);
    assert_ids_once(&persisted);
}
