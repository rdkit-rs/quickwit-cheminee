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

fn main() {
    let native = pkg_config::Config::new()
        .exactly_version("2026.09.1")
        .probe("rdkit")
        .expect(
            "tantivy-rdkit-mapper requires RDKit 2026.09.1 development files; install \
             librdkit-rs-dev=2026.09.1+ds1-1~ubuntu26.04 from the rdkit-rs repository on Ubuntu \
             26.04",
        );
    let mut build = cxx_build::bridge("src/native.rs");
    for include in native.include_paths {
        build.include(include);
    }
    build
        .include(".")
        .std("c++20")
        .compile("tantivy_rdkit_version_bridge");
    println!("cargo:rerun-if-changed=src/native.rs");
    println!("cargo:rerun-if-changed=src/native.h");
}
