# SPDX-License-Identifier: Apache-2.0
"""The instrumentation chain's client side: the manifest, the engine, the verifier.

Article 9 says the open project ships the instrumentation engine, the
instrumentation verifier and the convenience packs. Two of the three live here.

Layer 1 is `manifest`, `engine` and `launch`: they read what a pack declares,
install it in front of the named operations, and hand the program over. Layer 3
is `verify` and `harness`: they run the program again under the interpreter's
own audit hook and ask the daemon's chain whether every effect of a named kind
was decided. The two do not meet — the verifier consumes audit events and
evidence and nothing the engine kept — because a proof that trusts the thing it
is proving is not a proof.
"""
