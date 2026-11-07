+++
title = "Beyond 5s: extending FoundationDB past its five-second window"
seoTitle = "Beyond 5s, FoundationDB Without the Five-Second Limit"
date = 2026-10-25T11:00:00+02:00
draft = false
description = "Index of the Beyond 5s series: the project that replaces FoundationDB's five-second transaction window with memory budgets, one component milestone at a time."
summary = "FoundationDB rejects a transaction once its read version is more than five seconds old. Beyond 5s replaces that fixed window with budgets, component by component: the resolver's conflict history, the storage server's version retention, and the protocol that coordinates them. This page lists the milestones in order."
tags = ["foundationdb", "beyond-5s", "transactions"]
series = ["FoundationDB", "Beyond 5s"]
channels = []
ShowToc = false
+++

FoundationDB rejects any transaction that tries to read or commit more than five seconds after it obtained its read version. The limit is not in the transaction model; it comes from how long two components keep the history that an older transaction needs. Resolvers keep the write-conflict history used to validate commits, and storage servers keep the old versions of the data that a read at an old version must still see. Both keep it for a fixed window, whatever the memory available.

Beyond 5s replaces the window with a budget. Each component retains history under a configured memory budget and discards the oldest entries only when space is needed; a transaction completes as long as the history it needs is still retained, and is rejected as too old otherwise. The work proceeds one component at a time, and each milestone is published with its design as implemented, its decision record, its journal and its measured result.

## Milestones

**Resolver v1: a temporal B+ tree for conflict history** (October 2026). The resolver's history rebuilt as a B+ tree of disjoint intervals under a memory budget, with nodes and key bytes sharing one block pool, proactive splits and generation-checked reclamation. Under 6 GiB it retains 2.2× the history of the original skip list, at 2.7× the resolution time of the sequential first version. [Read the article](/systems/fdb-resolver-v1/).

**Resolver v2: recursive partitioning, grouped reads and prefetching** (October 2026). Sorted read begins are partitioned recursively among a node's children, so a boundary compared once classifies a whole group of reads; reads that reach the same leaf are checked together, sharing the in-leaf search and the predecessor lookup; and up to sixteen resumable tasks interleave on one thread so that a memory access hinted in one visit is consumed in a later one. In the Intel standalone benchmark v2 checks point reads at 2.1× and range reads at 1.5× v1's throughput, with the same retention; writes remain sequential and now dominate the remaining cost. [Read the article](/systems/fdb-resolver-v2/).

**Resolver v3: a temporal B+ tree for FoundationDB's conflict history, from routing to reclamation** (November 2026). The complete design after three milestones, told as one: a batch is processed in two phases, one mixed descent that routes every read and write begin together, checks the reads and records each write's destination, then the accepted writes applied in key order by two groups of cooperative tasks that search and prefetch ahead of a single writer; history is reclaimed by commit version within a fixed budget and the pool is backed by 2 MiB HugeTLB pages. Under the same 6 GiB budget v3.8 retains 2.20× FoundationDB's calibrated window, and the 5,400-second trace replays in 0.76× FoundationDB's time on Intel and comparable time on AMD, in a comparison that crosses sessions. [Read the article](/systems/fdb-resolver-v3/).

Next: version retention in the storage server; then the protocol that coordinates both with the transaction's read version.

## Where things live

The [design and milestone snapshots](https://github.com/ricardojimenezperis/fdb-beyond-5s) are in one repository: `design/` holds the current design of each component, and each milestone is an immutable snapshot under its component (`resolver/v1/`, `resolver/v2/`, `resolver/v3/`). The code is published in a [FoundationDB fork](https://github.com/ricardojimenezperis/foundationdb), tagged per milestone (`resolver-v1` for the first) and linked from each snapshot's evidence register. Articles on this site are the readable account of each milestone and cite the snapshot they describe.
