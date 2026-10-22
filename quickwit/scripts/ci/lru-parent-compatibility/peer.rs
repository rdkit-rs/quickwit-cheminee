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

use std::collections::BTreeMap;
use std::io::Write;
use std::net::SocketAddr;
use std::time::Duration;

use anyhow::{Context, bail};
use chitchat::{Chitchat, ChitchatConfig, ChitchatHandle, ChitchatId, FailureDetectorConfig};
use serde_json::{Value, json};
use tokio::io::AsyncBufReadExt;

mod observed_udp;

use observed_udp::ObservedUdpTransport;

const GOSSIP_MILLIS: u64 = 100;
const DEAD_NODE_GRACE_MILLIS: u64 = 4_000;
const KEY_GRACE_MILLIS: u64 = 2_000;

fn config_from_args() -> anyhow::Result<ChitchatConfig> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 6 {
        bail!("expected node-id, generation, listen-address, comma-separated seeds and cluster-id");
    }
    let listen_addr: SocketAddr = args[3].parse()?;
    if !listen_addr.ip().is_loopback() {
        bail!("peer must listen on loopback");
    }
    let seed_nodes: Vec<String> = args[4].split(',').map(str::to_string).collect();
    for seed in &seed_nodes {
        let seed_addr: SocketAddr = seed.parse()?;
        if !seed_addr.ip().is_loopback() {
            bail!("seed must use loopback");
        }
    }
    Ok(ChitchatConfig {
        chitchat_id: ChitchatId::new(args[1].clone(), args[2].parse()?, listen_addr),
        cluster_id: args[5].clone(),
        gossip_interval: Duration::from_millis(GOSSIP_MILLIS),
        listen_addr,
        seed_nodes,
        failure_detector_config: FailureDetectorConfig {
            phi_threshold: 8.0,
            sampling_window_size: 100,
            max_interval: Duration::from_secs(1),
            initial_interval: Duration::from_millis(GOSSIP_MILLIS),
            dead_node_grace_period: Duration::from_millis(DEAD_NODE_GRACE_MILLIS),
        },
        marked_for_deletion_grace_period: Duration::from_millis(KEY_GRACE_MILLIS),
        catchup_callback: None,
        extra_liveness_predicate: None,
    })
}

fn snapshot(chitchat: &Chitchat) -> Value {
    let mut nodes = Vec::new();
    for (node_id, state) in chitchat.node_states() {
        let values: BTreeMap<&str, &str> = state.key_values().collect();
        let all_keys: Vec<&str> = state
            .key_values_including_deleted()
            .map(|(key, _)| key)
            .collect();
        nodes.push(json!({
            "id": node_id,
            "heartbeat": u64::from(state.heartbeat()),
            "max_version": state.max_version(),
            "last_gc_version": state.last_gc_version(),
            "values": values,
            "all_keys": all_keys,
        }));
    }
    json!({
        "nodes": nodes,
        "live": chitchat.live_nodes().collect::<Vec<_>>(),
        "dead": chitchat.dead_nodes().collect::<Vec<_>>(),
    })
}

fn emit(value: Value) -> anyhow::Result<()> {
    let mut stdout = std::io::stdout().lock();
    serde_json::to_writer(&mut stdout, &value)?;
    writeln!(stdout)?;
    stdout.flush()?;
    Ok(())
}

async fn apply_command(
    handle: &ChitchatHandle,
    transport: &ObservedUdpTransport,
    command: Value,
) -> anyhow::Result<bool> {
    let operation = command["op"].as_str().context("missing operation")?;
    match operation {
        "snapshot" => {
            let mut state = handle.with_chitchat(|chitchat| snapshot(chitchat)).await;
            state["wire"] = transport.snapshot()?;
            emit(state)?;
        }
        "set" => {
            let values = command["values"].as_object().context("missing values")?;
            let mut validated = Vec::new();
            for (key, value) in values {
                let text = value.as_str().context("values must be strings")?;
                validated.push((key.as_str(), text));
            }
            handle
                .with_chitchat(|chitchat| {
                    for (key, value) in &validated {
                        chitchat.self_node_state().set(key, value);
                    }
                })
                .await;
            emit(json!({"ok": true}))?;
        }
        "delete" => {
            let key = command["key"].as_str().context("missing key")?;
            handle
                .with_chitchat(|chitchat| chitchat.self_node_state().delete(key))
                .await;
            emit(json!({"ok": true}))?;
        }
        "gossip" => {
            let address: SocketAddr = command["address"]
                .as_str()
                .context("missing address")?
                .parse()?;
            if !address.ip().is_loopback() {
                bail!("gossip target must use loopback");
            }
            handle.gossip(address)?;
            emit(json!({"ok": true}))?;
        }
        "shutdown" => return Ok(false),
        _ => bail!("unknown operation"),
    }
    Ok(true)
}

async fn commands(handle: &ChitchatHandle, transport: &ObservedUdpTransport) -> anyhow::Result<()> {
    let mut lines = tokio::io::BufReader::new(tokio::io::stdin()).lines();
    while let Some(line) = lines.next_line().await? {
        if line.len() > 1_048_576 {
            bail!("control request exceeds limit");
        }
        if !apply_command(handle, transport, serde_json::from_str(&line)?).await? {
            break;
        }
    }
    Ok(())
}

#[tokio::main(flavor = "multi_thread", worker_threads = 1)]
async fn main() -> anyhow::Result<()> {
    let config = config_from_args()?;
    let identity = config.chitchat_id.clone();
    let transport = ObservedUdpTransport::default();
    let handle = chitchat::spawn_chitchat(config, Vec::new(), &transport).await?;
    emit(json!({
        "ready": identity,
        "parent_version": "0.11.1",
        "transport": "chitchat::transport::UdpSocket with passive observation",
        "gossip_millis": GOSSIP_MILLIS,
        "dead_node_grace_millis": DEAD_NODE_GRACE_MILLIS,
        "key_grace_millis": KEY_GRACE_MILLIS,
        "quickwit_runtime_qualification": false,
    }))?;
    let result = tokio::select! {
        command_result = commands(&handle, &transport) => command_result,
        server_result = handle.termination_watcher() => {
            bail!("peer transport server terminated: {server_result:?}")
        }
    };
    handle.shutdown().await?;
    result?;
    emit(json!({"stopped": true}))?;
    Ok(())
}
