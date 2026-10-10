# Ubuntu 26.04 Kerberos compatibility

The all-feature lint build enables `vendored-kafka`, which pulls in
`krb5-src 0.3.4` and its bundled MIT Kerberos 1.19.2. Ubuntu 26.04's glibc 2.43
implements C23 const-preserving string searches. Kerberos enables `_GNU_SOURCE`,
so selecting GNU C17 alone does not restore compatibility. The lint job also
selects GNU C17 for the bundled library's pre-C23 function declarations.

`krb5-c23.patch` backports the library changes from MIT Kerberos commit
[`ad4dcf1856dadc4b352b5c8ff08e51c7290fb41f`](https://github.com/krb5/krb5/commit/ad4dcf1856dadc4b352b5c8ff08e51c7290fb41f).
The hunks are adapted to 1.19.2; PKINIT plugins and responder tests are omitted
because `krb5-src` does not build them. The extracted source retains its upstream
license notices. The patch also corrects the Rust build script's misspelled
`dragonflybsd` target and removes its obsolete `bitrig` target condition, so the
local source override passes the lint job's strict Rust warning flags.

From the Quickwit workspace, run:

```sh
CFLAGS=-std=gnu17 bash scripts/ci/with-krb5-c23.sh clippy --locked --workspace --tests --all-features
```

The wrapper verifies the locked crate version and archive checksum, applies the
patch without fuzz in a temporary directory, and uses Cargo's documented
[`paths` override](https://doc.rust-lang.org/cargo/reference/overriding-dependencies.html#paths-overrides).
It preserves the dependency graph, lockfile, registry cache, warning flags and
all-feature coverage. This override is local to the requested Cargo invocation;
RDKit package selection and C++ compilation are unchanged. Remove the wrapper
when the locked Kerberos dependency incorporates the upstream fix.
