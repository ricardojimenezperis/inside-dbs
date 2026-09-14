+++
title = "FoundationDB: the architecture, seen through a transaction"
date = 2026-09-12T10:00:00+02:00
draft = false
description = "FoundationDB's components introduced by following one transaction through them — from read version to readable."
summary = "FoundationDB separates transaction processing from storage. Rather than list its components, this post follows a single transaction through them, from the moment it starts to the moment its writes become readable."
tags = ["foundationdb", "architecture", "transactions", "mvcc"]
series = ["FoundationDB"]
channels = ["linkedin", "medium", "dev", "fdb-forum", "hn", "lobsters"]
ShowToc = true
[cover]
  image = "cover.jpg"
  alt = "An isometric city where a transaction travels FoundationDB's commit path: GRV proxy, commit proxy, resolvers, TLogs and storage servers"
  relative = true
  hidden = false
  hiddenInList = false
+++

FoundationDB is a transactional database with an unusual shape: its architecture separates transaction processing from storage, allowing the two to scale independently. There is another database, LeanXcale, that took the same route. The two share enough that they look like twins who agreed on the overall approach, were then separated, and made slightly different decisions because they were solving different problems. That story is for another post. Here the goal is to introduce FoundationDB's components by following a transaction through them, from the moment it starts to the moment its writes become readable. The next post will explain FoundationDB's five-second read-version window and how it constrains transactions.

The first architectural point is that FoundationDB is a transactional key-value store. There is no SQL engine inside it. A SQL interface exists — the Record Layer's relational layer — but it is a library that runs inside the application, not a server-side component.

The second distinctive point is that there is no single server side that performs operations on the client's behalf. The client library talks to the storage servers directly, and to two components that orchestrate transactions: GRV proxies, which provide read versions, and commit proxies, which commit transactions.

{{< figure src="transaction-lifecycle.png" alt="FoundationDB's components and the messages exchanged during a transaction" link="transaction-lifecycle.png" >}}

<p class="figure-caption"><em>Figure 1. FoundationDB's components and the messages exchanged during a transaction, from read version to readable.</em></p>

The figure names the actual requests the components exchange. You don't need any of them to follow what comes next — they are there for a second reading, and for the next post.

## Versions

FoundationDB retains multiple versions of key-value data so that transactions can read consistent snapshots. Versions are tagged with monotonically increasing commit versions that fix the order in which transactions serialize. The component that hands out those versions is the master, and there is one active master at a time.

To keep client applications from overwhelming a singleton, they never talk to the master directly — the proxies do it for them.

This gives each transaction a snapshot of the database as of its start. A client starting a transaction asks a GRV proxy for a read version. The proxy batches these requests and fetches one version from the master for the whole batch, which is what keeps traffic to the singleton bounded.

## Execution

Reads go straight to the storage servers, carrying the read version. A storage server returns, for each key, the value with the highest commit version less than or equal to that read version.

**Example.** Suppose key `k5` has three versions:

| Version | Commit version |
|---|---|
| `k5` v1 | 10 |
| `k5` v2 | 15 |
| `k5` v3 | 20 |

A transaction with read version 16 reading `k5` gets **v2**: 15 is the highest commit version for `k5` that is less than or equal to 16. Version 3 committed at 20, after the transaction's snapshot, so the transaction cannot see it.

Writes are different: they are buffered in the client. To give read-your-own-writes semantics, reads have to be merged with whatever is sitting in that write buffer.

**Example.** Suppose storage holds `k0`, `k1`, `k8` and `k9`, and the transaction writes `k5`.

A point read of `k5` returns the value the transaction just wrote. `k5` does not exist in storage at all, so without the merge the read would come back empty.

A range read over `[k1, k9)` returns `k1`, `k5` and `k8`. Two of them, `k1` and `k8`, come from the storage servers; `k5` comes from the write buffer and has to be spliced into the result in key order. `k0` falls before the start of the range and `k9` is its exclusive end.

## Commit

A read-only transaction is finished at this point — there is nothing left to do.

If the transaction wrote, the client asks a commit proxy to do the rest.

The commit proxy first obtains a commit version from the master. It then sends the transaction's conflict ranges to the resolvers, which check whether any write committed after the transaction's read version intersects its read conflict ranges. That check is what enforces isolation. The guarantee is strict serializability: read versions come from a single master and reflect everything committed before them, so a transaction that begins after another has committed is guaranteed to observe it.

If no conflict is found, the write set — mutations, in FoundationDB's vocabulary — is made durable in the transaction logs. That is the point of no return: once it completes, the transaction is committed.

Storage servers continuously pull mutations from the transaction logs and apply them asynchronously. Transactions whose read version is at or beyond a mutation's commit version observe that change; if a storage server has not yet reached the requested read version, the read waits until it catches up.
