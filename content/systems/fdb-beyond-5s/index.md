+++
title = "Beyond 5s: extending FoundationDB past its five-second window"
seoTitle = "Beyond 5s, FoundationDB Without the Five-Second Limit"
date = 2026-10-25T11:00:00+02:00
draft = false
description = "Index of the Beyond 5s series: the project that replaces FoundationDB's five-second transaction window with memory budgets, one component milestone at a time."
summary = "FoundationDB rejects any transaction older than five seconds. Beyond 5s replaces that fixed window with budgets, component by component: the resolver's conflict history, the storage server's version retention, and the protocol that coordinates them. This page lists the milestones in order."
tags = ["foundationdb", "beyond-5s", "transactions"]
series = ["FoundationDB", "Beyond 5s"]
channels = []
ShowToc = false
+++

FoundationDB rejects any transaction that tries to read or commit more than five seconds after it obtained its read version. The limit is not in the transaction model; it comes from how long two components keep the history that an older transaction needs. Resolvers keep the write-conflict history used to validate commits, and storage servers keep the old versions of the data that a read at an old version must still see. Both keep it for a fixed window, whatever the memory available.

Beyond 5s replaces the window with a budget. Each component retains history under a configured memory budget and discards the oldest entries only when space is needed; a transaction completes as long as the history it needs is still retained, and is rejected as too old otherwise. The work proceeds one component at a time, and each milestone is published with its design as implemented, its decision record, its journal and its measured result.

## Milestones

**Resolver v1: a temporal B+ tree for conflict history** (October 2026). The resolver's history rebuilt as a B+ tree of disjoint intervals under a memory budget, with nodes and key bytes sharing one block pool, proactive splits and generation-checked reclamation. Under 6 GiB it retains 2.2× the history of the original skip list, at 2.7× the resolution time of the sequential first version. [Read the article](/systems/fdb-resolver-v1/).

Next: grouped read checks with selective prefetch in the resolver; then version retention in the storage server; then the protocol that coordinates both with the transaction's read version.

## Where things live

The [design and milestone snapshots](https://github.com/ricardojimenezperis/fdb-beyond-5s) are in one repository: `design/` holds the current design of each component, and each milestone is an immutable snapshot under its component. The code is published in a FoundationDB fork, tagged per milestone and linked from each snapshot's evidence register. Articles on this site are the readable account of each milestone and cite the snapshot they describe.
