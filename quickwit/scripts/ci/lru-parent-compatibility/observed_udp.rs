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
use std::net::SocketAddr;
use std::sync::{Arc, Mutex};

use anyhow::anyhow;
use async_trait::async_trait;
use chitchat::transport::{Socket, Transport, UdpSocket};
use chitchat::{ChitchatId, ChitchatMessage, Deserializable, Serializable};
use serde_json::{Value, json};

#[derive(Default)]
struct Evidence {
    received_messages: u64,
    sent_messages: u64,
    received_syn: BTreeMap<SocketAddr, Value>,
}

#[derive(Clone, Default)]
pub struct ObservedUdpTransport {
    evidence: Arc<Mutex<Evidence>>,
}

impl ObservedUdpTransport {
    pub fn snapshot(&self) -> anyhow::Result<Value> {
        let evidence = self
            .evidence
            .lock()
            .map_err(|_| anyhow!("wire evidence lock poisoned"))?;
        Ok(json!({
            "received_messages": evidence.received_messages,
            "sent_messages": evidence.sent_messages,
            "received_syn": evidence.received_syn,
        }))
    }
}

struct ObservedUdpSocket {
    socket: UdpSocket,
    evidence: Arc<Mutex<Evidence>>,
}

#[async_trait]
impl Transport for ObservedUdpTransport {
    async fn open(&self, listen_addr: SocketAddr) -> anyhow::Result<Box<dyn Socket>> {
        Ok(Box::new(ObservedUdpSocket {
            socket: UdpSocket::open(listen_addr).await?,
            evidence: self.evidence.clone(),
        }))
    }
}

fn syn_nodes(message: &ChitchatMessage) -> anyhow::Result<Option<Value>> {
    let ChitchatMessage::Syn { digest, .. } = message else {
        return Ok(None);
    };
    // The accepted message has already passed the production UDP decoder. Decode
    // its serialized digest with the parent's public types solely for observation.
    let mut encoded_digest = Vec::new();
    digest.serialize(&mut encoded_digest);
    let mut input = encoded_digest.as_slice();
    let count = u16::deserialize(&mut input)?;
    let mut nodes = Vec::with_capacity(count as usize);
    for _ in 0..count {
        let identity = ChitchatId::deserialize(&mut input)?;
        let heartbeat = u64::deserialize(&mut input)?;
        let last_gc_version = u64::deserialize(&mut input)?;
        let max_version = u64::deserialize(&mut input)?;
        nodes.push(json!({
            "id": identity,
            "heartbeat": heartbeat,
            "last_gc_version": last_gc_version,
            "max_version": max_version,
        }));
    }
    anyhow::ensure!(input.is_empty(), "unexpected digest suffix");
    Ok(Some(json!(nodes)))
}

#[async_trait]
impl Socket for ObservedUdpSocket {
    async fn send(&mut self, address: SocketAddr, message: ChitchatMessage) -> anyhow::Result<()> {
        self.socket.send(address, message).await?;
        let mut evidence = self
            .evidence
            .lock()
            .map_err(|_| anyhow!("wire evidence lock poisoned"))?;
        evidence.sent_messages += 1;
        Ok(())
    }

    async fn recv(&mut self) -> anyhow::Result<(SocketAddr, ChitchatMessage)> {
        let (address, message) = self.socket.recv().await?;
        let nodes = syn_nodes(&message)?;
        let mut evidence = self
            .evidence
            .lock()
            .map_err(|_| anyhow!("wire evidence lock poisoned"))?;
        evidence.received_messages += 1;
        if let Some(nodes) = nodes {
            let sequence = evidence.received_messages;
            evidence
                .received_syn
                .insert(address, json!({"sequence": sequence, "nodes": nodes}));
        }
        Ok((address, message))
    }
}
