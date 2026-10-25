+++
title = "Resolver v1: a temporal B+ tree for FoundationDB's conflict history"
seoTitle = "FoundationDB Resolver as a Temporal B+ Tree"
date = 2026-10-25T12:00:00+02:00
draft = false
description = "The first Beyond 5s milestone: FoundationDB's resolver conflict history rebuilt as a temporal B+ tree under a memory budget, with its design, its figures and its measured trade-off."
summary = "FoundationDB keeps conflict history for five seconds. Resolver v1 keeps it under a memory budget instead, in a temporal B+ tree whose nodes and key bytes share one pool. Under 6 GiB it retains 2.2× the history of the original skip list, at 2.7× the resolution time; this post explains the design and the measurement."
tags = ["foundationdb", "resolver", "b+ tree", "transactions", "mvcc", "beyond-5s"]
series = ["FoundationDB", "Beyond 5s"]
channels = ["linkedin", "fdb-forum", "medium", "dev"]
snapshot = "resolver/v1"
ShowToc = true
[cover]
  image = "cover.jpg"
  alt = "A tree shaped like a B+ tree: a short trunk, a few thick branches and a flat, dense canopy; the leaves grow green on one side, turn amber toward the other and fall into identical crates beside a sundial"
  relative = true
  hidden = false
  hiddenInList = false
+++

FoundationDB rejects any transaction that tries to commit more than five seconds after it started. The previous post followed a transaction through the system; this one starts a series about removing that limit, called Beyond 5s, and reports its first milestone: the resolver's conflict history rebuilt as a temporal B+ tree under a memory budget.

The five seconds are a budget in disguise. Resolvers keep a history of recently written key ranges, each with the version that wrote it, so that a committing transaction can be checked against writes that landed after its read version. FoundationDB keeps that history in a skip list and discards it by age: anything older than the window goes. The window is fixed; the memory it consumes depends on the workload. Resolver v1 turns this around. It keeps history under a fixed memory budget and discards the oldest entries only when space is needed, so the retained window is whatever the budget affords.

This post covers the data structure, the mechanisms that make it work under a budget, and what the first measurement says. The complete milestone record, with the design as implemented, the decision record, the journal and the evaluation, is linked at the end.

## What a resolver stores

The history does not contain values. It records which regions of the key space were written and at which commit version. Writes from accepted transactions are overlaid on it: the part of an old interval covered by a new write takes the new version, and the parts outside it, its exteriors, keep their old version. A read-conflict check is then a range query: a transaction at read version RV conflicts if any interval overlapping one of its read ranges has a commit version greater than RV.

Writing `[c, g)` at version 20 over `[a, z)` at version 10 therefore produces `[a, c)@10`, `[c, g)@20`, `[g, z)@10`. Giving the whole old interval version 20 would create false conflicts on the exteriors; leaving the interior at version 10 would miss real ones. This is the same semantics as FoundationDB's skip list; what changes in v1 is the representation.

## Where everything lives

Resolver v1 keeps the history in a B+ tree. Leaves hold intervals with their commit versions; internal nodes hold separators and child pointers. Key bytes are never stored inside a node: a leaf entry references its key record, and a separator references the same record as the first entry of the child it routes to. Nodes and key records are allocated from one pool of fixed-size blocks, so a block released by a node can hold key records next, and the reverse.

{{< figure src="fig-v1-storage.png" alt="A small B+ tree whose leaf entries and separators reference key records in linked key blocks, and the page pool where nodes and key blocks are blocks of the same kind" link="fig-v1-storage.png" >}}

<p class="figure-caption"><em>Figure 1. Nodes hold descriptors and references; key bytes live in key records appended to key blocks; both kinds of block come from one pool. Separators reuse the key bytes referenced by the corresponding leaf entry.</em></p>

Two consequences follow. Node capacity does not depend on key length, so a 2 KiB block holds 40 children in an internal node or 59 entries in a leaf whatever the keys look like. And point writes, which dominate many workloads, cost one record: the interval `[k, k\0)` stores `k\0` once and reads the begin key as its prefix, where the skip list keeps two boundary nodes with two copies of `k`.

The price is that comparing a separator means reading bytes outside the node. V1 pays it on every descent. A later version will keep several searches in flight and prefetch the keys each one is about to compare; the representation is prepared for that, and the sequential version measured here does not do it yet.

## Keeping order without moving entries

Within a node, entries stay in the physical slot where they were written. A bitmap says which slots are occupied, and a small permutation array, `order[]`, lists the occupied slots in key order. Inserting an entry writes it into a free slot and shifts one-byte indices; deleting one clears a bit and shifts indices the other way. Nothing else moves.

{{< figure src="fig-order-bytes.png" alt="A sorted descriptor array shifts whole 32-byte descriptors on insertion and deletion, while v1 shifts one-byte slot indices in order[] and leaves descriptors in their physical slots" link="fig-order-bytes.png" >}}

<p class="figure-caption"><em>Figure 2. What moves on an insertion or a deletion. A sorted array shifts 32-byte descriptors; v1 writes the new descriptor into a free slot and shifts one-byte indices in order[].</em></p>

In a leaf of 59 entries, an insertion in the middle shifts about 29 bytes instead of about 930. The same property keeps parent links cheap: a child records the physical slot of its entry in the parent, and that slot does not change when siblings are inserted or removed.

## Splits that never cascade

A conventional B+ tree splits a node when it overflows. The new sibling needs a slot in the parent; if the parent is full it splits too, and the chain can run up to the root. The work of one insertion then depends on how many of its ancestors happen to be full.

{{< figure src="fig-split-conventional.png" alt="Conventional B+ tree splits: one insertion into a full leaf under a full root splits two existing nodes and creates a new root" link="fig-split-conventional.png" >}}

<p class="figure-caption"><em>Figure 3. Conventional splits. Inserting j into a full leaf under a full root splits the leaf, then the root, and creates a new root.</em></p>

V1 reserves capacity before it is needed. A leaf needs a split when it has at most one free slot, because a write can add two entries, the write itself and a surviving right exterior. Each internal node counts its children that need a split, `P`, and keeps one free slot reserved for each; it needs a split itself when `P` equals its free-slot count `F`. Before inserting, a write splits the deepest node on its path that needs one. Splitting a pending child consumes one free parent slot and removes one pending child, so `F − P` is unchanged and the parent never has to split in the same write.

{{< figure src="fig-split-proactive.png" alt="Proactive splits in v1 through three insertions: each write splits at most one existing node, and absorbing a child split leaves the parent's split state unchanged" link="fig-split-proactive.png" >}}

<p class="figure-caption"><em>Figure 4. Proactive splits. A pending leaf is split before the write that targets it; the parent absorbs the sibling in a reserved slot. The parent is split by a later write, before it is full of demand.</em></p>

A write therefore splits at most one existing node. Other costs remain, copying key bytes, removing covered entries, cleanup and reclamation, so this is a bound on structural work, and the write is not constant-time.

## Reclaiming history under a budget

Nodes are kept in an age list ordered by a conservative maximum of the versions below them; key blocks are released in allocation order. When the pool runs out, reclamation compares the oldest key block with the oldest node, takes whichever is older, and advances the reclamation cutoff `reclaimCV`. Reads with a read version below the cutoff are rejected as too old for the retained history, exactly as FoundationDB rejects reads older than its window.

Releasing a block does not clean every reference to it. A separator or a leaf entry may still name a key record whose block has been reused. Each reference carries the generation of the block it points to, and the tree remembers the generation of the last block it released; a reference is valid exactly when its generation is greater. One integer compare settles it, and the block is never read.

{{< figure src="fig-generation.png" alt="After reclaiming the two oldest key blocks, a reference is valid exactly when its generation exceeds lastReclaimedKeyGeneration; stale references are detected with one compare and never dereferenced" link="fig-generation.png" >}}

<p class="figure-caption"><em>Figure 5. Validating a reference after reclamation. Key blocks are released in allocation order, so one counter bounds every released block; a reference at or below it is invalid, even when its pool block has been reused.</em></p>

Stale references are cleaned when a search meets them: expired leaf entries are removed, expired separators are refreshed from their child, and empty subtrees are detached as a unit.

## What the measurement says

The comparison replays a 5,400-second trace of resolver work, 65,536 transactions per second with 16–64-byte keys, through FoundationDB's original skip list and through v1, both under a 6 GiB history budget. The skip list has no budget of its own, so its window was calibrated first: 265 seconds is the largest window whose history fits in 6 GiB on this trace; 270 seconds exceeds it. Both implementations process the same offered work and produce the same recorded conflict decisions, and neither rejects a read for age or memory.

Under that budget, v1 first discards history 703 seconds into the trace and never retains less than 583 seconds afterwards: 2.2 times the calibrated window. Its retention declines slowly over the run, by about 0.6% over the last 600 seconds, while the skip list's memory use at its fixed window grows slowly; both are reported as measured rather than extrapolated.

Resolution time goes the other way. Over the full trace, v1 takes 3,376 seconds to the skip list's 1,241, a ratio of 2.7. Writes take 2.7 times as long and reads 5.1 times. This was expected of a sequential first version that resolves each read and write individually, with every separator comparison paying for an external key access. Grouped traversal and selective prefetch are the next milestone; the measurement identifies where the time goes without yet attributing it.

The result, then, is a trade-off stated under equal memory: substantially more history for a higher cost per batch, with matching decisions. Retention is the design's first objective, and it holds over the measured horizon. Resolution speed is now the target.

## What comes next

The read path is where the gap is. The next milestone groups the read checks of a batch, keeps several descents in flight, and prefetches the key bytes each one will compare, so that the latency of one external access overlaps useful work on others. After the resolver, the series moves to the storage server, which must keep the data versions that a longer-lived transaction reads, and then to the protocol that coordinates both with the transaction's read version.

## Milestone record

Everything above is a reading of the milestone snapshot, which is the source for every number here. The snapshot is immutable; the current design of each component evolves separately.

The [design as implemented](https://github.com/ricardojimenezperis/fdb-beyond-5s/blob/main/resolver/v1/03-resolver-v1-design.md) describes the representation, invariants and operations, with the figures used here. The [decision record](https://github.com/ricardojimenezperis/fdb-beyond-5s/blob/main/resolver/v1/04-decisions-and-evolution.md) gives, for each mechanism, the problem, the choice and its cost. The [journal](https://github.com/ricardojimenezperis/fdb-beyond-5s/blob/main/resolver/v1/05-engineering-journal.md) records when things happened and what each step changed. The [evaluation](https://github.com/ricardojimenezperis/fdb-beyond-5s/blob/main/resolver/v1/06-evaluation.md) has the configuration, the tables and the limits of the measurement, and the [evidence register](https://github.com/ricardojimenezperis/fdb-beyond-5s/blob/main/resolver/v1/07-evidence-and-validation.md) ties the claims to revisions, hashes and validation scope. The [engineering overview](https://github.com/ricardojimenezperis/fdb-beyond-5s/blob/main/resolver/v1/01-engineering-overview.md) is the five-minute version. The [code, tests and evaluation harness](https://github.com/ricardojimenezperis/foundationdb/tree/resolver-v1) are published in a FoundationDB fork under the tag `resolver-v1`, and the [release of the same name](https://github.com/ricardojimenezperis/foundationdb/releases/tag/resolver-v1) carries the evidence archive of the measurement runs.
