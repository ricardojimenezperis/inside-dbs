+++
title = "FoundationDB: the architecture, seen through a transaction"
seoTitle = "FoundationDB Transaction Architecture"
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

The next illustrations in each section use the same city metaphor as the cover. Cars are transactions, each color a different transaction, and where a car is tells you which stage the transaction is in; vans are the batched messages between components; trucks carry mutations. The version numbers are illustrative, but they are consistent across the figures.

## Versions

FoundationDB retains multiple versions of key-value data so that transactions can read consistent snapshots. Versions are tagged with monotonically increasing commit versions that fix the order in which transactions serialize. The component that hands out those versions is the master, and there is one active master at a time.

To keep client applications from overwhelming a singleton — the master — they never talk to it directly; the GRV and commit proxies do it for them.

Versioning gives each transaction a snapshot of the database as of its start. A client starting a transaction asks a GRV proxy for a read version. The proxy batches these requests and fetches one version from the master for the whole batch, which is what keeps traffic to the singleton master bounded.

{{< figure src="read-version.png" alt="Three transactions wait at the GRV proxy while one van fetches a read version from the master" link="read-version.png" >}}

<p class="figure-caption"><em>Figure 2. Getting a read version. Three transactions are waiting at the GRV proxy; one request (1) goes to the master for all of them, and one version comes back (2) — 1037, the latest version known to be committed.</em></p>

## Execution

Reads go straight to the storage servers, carrying the read version. A storage server returns, for each key, the value with the highest commit version less than or equal to that read version.

**Example.** Suppose key `k5` has three versions:

| Version | Commit version |
|---|---|
| `k5` v1 | 1010 |
| `k5` v2 | 1030 |
| `k5` v3 | 1042 |

A transaction with read version 1037 reading `k5` gets **v2**: 1030 is the highest commit version for `k5` that is less than or equal to 1037. Version 3 committed at 1042, after the transaction's snapshot, so the transaction cannot see it. A transaction that started later, with read version 1051, reads the same key and gets **v3**.

{{< figure src="execution.png" alt="Two transactions read k5 from the storage servers with different read versions and get different versions back" link="execution.png" >}}

<p class="figure-caption"><em>Figure 3. Execution. Two transactions read `k5` with different read versions (snapshot glasses in the metaphor): the blue transaction (messages 1, 2) gets v2, the green transaction (3, 4) gets v3. Each one sees the database as of its own snapshot.</em></p>

Writes are different: they are buffered in the client. To give read-your-own-writes semantics, reads have to be merged with whatever is sitting in that write buffer.

**Example.** Suppose storage holds `k0`, `k1`, `k8` and `k9`, and the transaction writes `k5`.

A point read of `k5` returns the value the transaction just wrote. `k5` does not exist in storage at all, so without the merge the read would come back empty.

A range read over `[k1, k9)` returns `k1`, `k5` and `k8`. Two of them, `k1` and `k8`, come from the storage servers; `k5` comes from the write buffer and has to be spliced into the result in key order. `k0` falls before the start of the range and `k9` is its exclusive end.

## Commit

A read-only transaction is finished at this point — there is nothing left to do.

If the transaction wrote, the client asks a commit proxy to do the rest.

{{< figure src="commit-version.png" alt="Two transactions wait at the commit proxy while a van obtains a commit version from the master" link="commit-version.png" >}}

<p class="figure-caption"><em>Figure 4. Getting a commit version. The commit proxy batches the transactions that want to commit and asks the master for one version for the batch (1); the master answers with the version and the previous one it handed out (2).</em></p>

The commit proxy first obtains a commit version from the master. It then sends the transaction's conflict ranges to the resolvers, which check whether any write committed after the transaction's read version intersects its read conflict ranges. That check is what enforces isolation. The guarantee is strict serializability: read versions come from a single master and reflect everything committed before them, so a transaction that begins after another has committed is guaranteed to observe it.

{{< figure src="conflict-resolution.png" alt="At the resolvers one transaction passes and another is aborted" link="conflict-resolution.png" >}}

<p class="figure-caption"><em>Figure 5. Conflict resolution. Both transactions have commit version 1042. The blue one read `k5` at 1037 and nothing touched `k5` since, so it passes conflict-free to the next stage and its write becomes `k5` v3. The orange one read `k5` at 1025; `k5` was written at 1030 — and again by the blue one in the same batch — so it is aborted.</em></p>

If no conflict is found, the write set — mutations, in FoundationDB's vocabulary — is made durable in the transaction logs. That is the point of no return: once it completes, the transaction is committed.

Storage servers continuously pull mutations from the transaction logs and apply them asynchronously. Transactions whose read version is at or beyond a mutation's commit version observe that change; if a storage server has not yet reached the requested read version, the read waits until it catches up.

{{< figure src="durability.png" alt="Mutations become durable in the transaction logs and are pulled by the storage servers" link="durability.png" >}}

<p class="figure-caption"><em>Figure 6. Durability. The mutations of the blue transaction's batch are written to the transaction logs (1); once they are durable the transaction is committed. The storage servers pull the blue transaction's mutations from the logs and apply them (2), and `k5` v3 becomes readable to transactions with read version 1042 or higher.</em></p>

## Master

The master has appeared twice in this path, and it is worth closing with what it actually does, because it is less than its name suggests. It hands out commit versions to the commit proxies — one monotonically increasing sequence. Commit versions establish the global serialization order. The master also keeps track of how far that sequence has become durable. Assigning a commit version is not committing: after the master hands one out, the transaction still has to pass the resolvers and reach the transaction logs, and it may abort along the way. So each commit proxy, once its batch is durable in the logs, reports the version back to the master before replying to the client. The master keeps the highest durable version reported so far, called the live committed version, and that — not the latest version it has assigned — is what it returns to a GRV proxy asking for a read version. A read version therefore never covers a transaction that is still committing and not yet durable, and it always covers every transaction whose commit has been acknowledged to its client (a durable transaction), which is the property behind the strict serializability guarantee above. The master is a sequencer, and keeping it that small — with the proxies absorbing all the client traffic — is what lets it be in the path of every transaction without becoming the bottleneck.

{{< figure src="master.png" alt="The master with its two screens, live committed version and commit version, and the two proxies" link="master.png" >}}

<p class="figure-caption"><em>Figure 7. The master. Its two counters are the live committed version, handed to GRV proxies (messages 1, 2), and the next commit version, handed to commit proxies (3, 4). The gap between them is the transactions still in flight.</em></p>
