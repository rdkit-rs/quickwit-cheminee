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

// Folded-stack conversion follows pprof 0.15 (Copyright 2019 TiKV Project Authors,
// Apache-2.0). Keep its collector and report semantics while using patched inferno.
use std::fmt::Write as _;

fn folded_stack(frames: &pprof::Frames, count: isize) -> String {
    let mut line = frames.thread_name_or_id();
    line.push(';');
    for frame in frames.frames.iter().rev() {
        for symbol in frame.iter().rev() {
            write!(&mut line, "{symbol};").expect("writing to a String cannot fail");
        }
    }
    line.pop();
    write!(&mut line, " {count}").expect("writing to a String cannot fail");
    line
}

pub(super) fn render(report: &pprof::Report, writer: impl std::io::Write) -> anyhow::Result<()> {
    let lines: Vec<_> = report
        .data
        .iter()
        .map(|(frames, count)| folded_stack(frames, *count))
        .collect();
    // Preserve the previous empty-profile response, without invoking the renderer.
    if !lines.is_empty() {
        inferno::flamegraph::from_lines(
            &mut inferno::flamegraph::Options::default(),
            lines.iter().map(String::as_str),
            writer,
        )?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample(thread_name: &str) -> pprof::Frames {
        let symbol = |name: &str| pprof::Symbol {
            name: Some(name.as_bytes().to_vec()),
            addr: None,
            lineno: None,
            filename: None,
        };
        pprof::Frames {
            frames: vec![
                vec![symbol("leaf"), symbol("inlined")],
                vec![symbol("root")],
            ],
            thread_name: thread_name.into(),
            thread_id: 42,
            sample_timestamp: std::time::SystemTime::UNIX_EPOCH,
        }
    }

    #[test]
    fn preserves_frame_order_thread_identity_and_sample_counts() {
        assert_eq!(
            folded_stack(&sample("worker"), 7),
            "worker;root;inlined;leaf 7"
        );
        assert_eq!(folded_stack(&sample(""), 3), "42;root;inlined;leaf 3");
        let mut frames = sample("worker");
        frames.frames.clear();
        assert_eq!(folded_stack(&frames, 2), "worker 2");
    }

    #[test]
    fn renders_profile_and_preserves_empty_profile() {
        let mut report = pprof::Report {
            data: Default::default(),
            timing: Default::default(),
        };
        let mut svg = Vec::new();
        render(&report, &mut svg).unwrap();
        assert!(svg.is_empty());
        report.data.insert(sample("worker"), 7);
        render(&report, &mut svg).unwrap();
        let svg = String::from_utf8(svg).unwrap();
        assert!(svg.contains("<svg"));
        assert!(svg.contains("leaf (7 samples, 100.00%)"));
    }

    #[test]
    fn propagates_writer_failure_without_panicking() {
        struct FailingWriter;
        impl std::io::Write for FailingWriter {
            fn write(&mut self, _: &[u8]) -> std::io::Result<usize> {
                Err(std::io::Error::other("test writer failure"))
            }
            fn flush(&mut self) -> std::io::Result<()> {
                Ok(())
            }
        }
        let report = pprof::Report {
            data: [(sample("worker"), 7)].into(),
            timing: Default::default(),
        };
        assert!(render(&report, FailingWriter).is_err());
    }
}
