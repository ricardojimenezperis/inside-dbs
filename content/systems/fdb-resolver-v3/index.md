+++
title = "Resolver v3: a temporal B+ tree for FoundationDB's conflict history, from routing to reclamation"
seoTitle = "FoundationDB Resolver v3: Budgeted Conflict History"
date = "2026-11-06"
lastmod = "2026-11-09"
draft = false
description = "Final Resolver v3 retains 2.20× more FoundationDB conflict history in the same 6 GiB, with the stale-rank fix, 232 tests and final Intel and AMD evaluation."
summary = """FoundationDB rejects a transaction once its read version is more than five seconds old because the resolver keeps only that much write history. Resolver v3 replaces that history with a temporal B+ tree under a memory budget and processes each batch in two phases: one descent routes every read and write begin together and checks the reads, then the accepted writes are applied in key order by cooperative tasks that search and prefetch ahead of a single writer.

**Under the same 6 GiB budget, final v3 retains 582.9–584.7 seconds of conflict history in the measured tail—2.20× FoundationDB's calibrated 265-second window.** The 5,400-second trace replays in 0.77× FoundationDB's time in two Intel pairs. AMD reproduces every decision and the same retention curve; its single pair is not used to infer a performance ratio. Every published v3 performance run verifies that the complete pool is in HugeTLB pages."""
tags = ["foundationdb", "resolver", "b+ tree", "prefetching", "transactions", "beyond-5s"]
series = ["FoundationDB", "Beyond 5s"]
channels = ["linkedin", "fdb-forum", "medium", "dev"]
snapshot = "resolver/v3"
ShowToc = true
math = true
[cover]
  image = "cover.jpg"
  alt = "The series' tree, green and flowering on one side and amber on the other, with a sundial at its foot and a small temple whose pediment reads BY5"
  relative = true
+++

FoundationDB decides whether a transaction commits by checking its reads against the writes committed since its read version. The resolver that does this keeps the recent write history in memory, in a skip list that it prunes by age, and the age it keeps is what fixes the limit every FoundationDB user knows: a transaction whose read version is more than five seconds old is rejected, because the history it would have to be checked against is gone.

Beyond 5s replaces that history with a structure bounded by memory instead of time. This post describes the resolver that results after three milestones, as one design: first the four design pillars it rests on, then the structure that stores write-conflict intervals under a budget, the way a batch of reads is checked through it, the way the batch's accepted writes are applied, and what the measurements say. The earlier posts on [v1](https://github.com/ricardojimenezperis/fdb-beyond-5s/tree/main/resolver/v1) and [v2](https://github.com/ricardojimenezperis/fdb-beyond-5s/tree/main/resolver/v2) tell how the pieces arrived; this one tells how they fit. Every mechanism described here is present in the [v3 snapshot](https://github.com/ricardojimenezperis/fdb-beyond-5s/tree/main/resolver/v3), whose design document records the invariants and twenty-one implementation figures; this article adds seven explanatory figures carried forward from v1 and v2.

> **Results at a glance.** *Retention:* under the same 6 GiB budget, final v3 retains 582.9–584.7 seconds in the measured tail, 2.20× FoundationDB's calibrated 265-second window. *Intel:* the 5,400-second trace replays in 0.77× FoundationDB's time; the paired short session gives 0.81× in `conflictset` points, 0.92× in integrated ranges and 0.74–0.91× across seven `skiplisttest` layouts, with integrated points level at 1.00× and `conflictset` ranges slower at 1.12×. *AMD:* `skiplisttest` spans 0.95–1.01× and integrated ranges is 0.99×; points, `conflictset` ranges and integrated points are slower at 1.05×, 1.29× and 1.32×. AMD's one long-trace pair validates decisions and retention but supports no timing ratio. Final v3 uses its published HugeTLB configuration; the other implementations use their native ordinary-memory configurations.

*Figures can be opened at full resolution by clicking them.*

## Four design pillars

Resolver v3 combines four mechanisms developed across the v1, v2 and v3 milestones. Together, they form the four pillars of the design.

<span class="pillar">Pillar 1</span> — **Temporal B+ tree without cascading splits.** Starting from FoundationDB's skip list, the goal was an in-memory index that retains versioned conflict intervals compactly and keeps searches and writes practical as history grows. A B+ tree groups entries in nodes, but its conventional update and separator costs needed to be addressed.

- *Reduce pointer chasing and per-entry reclamation work → paged nodes.* Each node holds many intervals and navigation decisions. When an entire subtree has expired, it can be detached and its blocks recycled without locating each interval individually.
- *Reduce the CPU and memory cost of inline separators → references to stored keys.* Internal nodes reuse existing key records instead of keeping separate copies of their bytes.
- *Prevent cascading splits → proactive split preparation.* Reserving capacity in parents for pending child splits limits each write to splitting at most one existing node.
- *Reduce the cost of updates and in-node expiry cleanup → order permutation and free bitmap.* The tree moves small order indices and reuses physical slots instead of shifting full descriptors.

<span class="pillar">Pillar 2</span> — **Compact shared block pool with budgeted reclamation.** A longer conflict history is useful only if its memory consumption remains predictable. Nodes and key bytes have different lifetimes, so the design lets them share capacity and reclaims the oldest history when new writes need space. The retention window is determined by the configured budget and the workload, rather than fixed in seconds.

- *Avoid stranded capacity between nodes and keys → one shared pool of reusable blocks.* Pages are divided into blocks that can hold either a tree node or key records. A block freed by one can be reused by the other.
- *Bound history memory → reclaim on allocation pressure.* Before a write mutates the tree, it reserves the blocks it may need. If the pool lacks space, reclamation advances the cutoff and releases the oldest eligible history.
- *Reduce reclamation work → retire expired blocks and subtrees.* Key blocks are reclaimed in allocation order; fully expired subtrees can be detached and their nodes released. Mixed-age nodes remain until their live entries can be preserved or cleaned.
- *Keep references safe as blocks are reused → version checks and generations.* The tree checks whether an entry has expired before following its key reference. Every saved write rank carries its leaf generation and mutation epoch, and node and key-block generations use disjoint spaces, so reclamation or cross-role block reuse cannot validate a stale destination.
- *Reduce TLB misses → HugeTLB backing.* The same logical pool is mapped with 2 MiB pages, covering more blocks per TLB entry without changing the tree or its memory budget.

<span class="pillar">Pillar 3</span> — **Batched traversal with recursive partitioning.** The Resolver receives many read and write ranges in one batch. Searching the tree independently for every range would repeat navigation through the same nodes and separators. Instead, it routes their sorted begin keys together, sharing work while preserving the order needed to check reads and prepare writes.

- *Avoid repeated independent descents → route a sorted batch through the tree.* Each task owns a consecutive slice of begin keys. When it reaches an internal node, it distributes that slice among the node's children.
- *Reduce routing comparisons → recursive partitioning.* A selected child boundary divides the slice into smaller subproblems. Each boundary is resolved once for its subproblem, and empty slices are skipped; when boundaries and begins are similarly numerous, routing takes a linear number of key comparisons within that node.
- *Share navigation between reads and writes → one mixed descent.* Read and write begins take part in the same routing. At a leaf, reads are checked for conflicts and write destinations are recorded for later use; no write is applied during this phase.
- *Avoid restarting long range reads at the root → scan linked leaves.* Once a read reaches a leaf, the scan follows the relevant history entries and continues into the next leaf when needed, keeping track of reads that remain unresolved.

<span class="pillar">Pillar 4</span> — **Read and write tasks with a non-preemptive scheduler for cooperative software prefetching.** The Resolver processes batches on one core. Its throughput depends on how many instructions and key comparisons it executes, how often branches are mispredicted, and how long the core waits for nodes and key bytes missing from cache. In a tree traversal, those memory accesses are dependent: the next address becomes known only after the current node arrives. The scheduler turns each traversal into a task that runs while its data is available. When it reaches a dependency, it issues a prefetch hint and yields so other tasks can work while the data is fetched.

- *Overlap dependent cache misses → interleave independent tasks.* A task hints its next node or key bytes and yields. Other tasks make progress before it is visited again, giving the requested data time to arrive.
- *Avoid unnecessary scheduling → chain local steps within one visit.* When the next step's data is already available, the task continues directly instead of yielding after every state transition.
- *Keep batched reads moving → schedule a bounded set of traversal tasks.* Each task owns a key slice; tasks waiting for memory yield to other runnable slices.
- *Prefetch future writes while preserving write order → search and park younger tasks.* They locate and hint their destinations, then wait at SearchReady. Only the oldest task of the oldest group mutates the tree.
- *Provide prefetch lead time → stagger two groups of eight write tasks.* The next group is hinted early and begins searching while the current group is still writing. Tasks run cooperatively on one thread; a prefetch is a hint, not a guarantee that the data will be cached on the next visit.

## Inside the Resolver's in-memory conflict index

The history is a set of disjoint half-open key intervals, each carrying the commit version (CV) of the last write that covered it. A read of [rb, re) at read version RV conflicts with an interval [wb, we) at CV when the two overlap and CV is above RV. Applying a write overlays its interval: [30, 60) at version 120 over [10, 90) at version 100 leaves [10, 30) and [60, 90) at 100 around the new interval, and covers any gap that had no entry. Nothing else about the database is stored; the resolver holds keys and versions, never values.

The intervals live in a B+ tree whose leaves are linked in key order. Nodes and key bytes draw their blocks from one pool: 64 KiB pages cut into 2 KiB blocks, with one free list, so a block freed by a node can next hold keys and the budget is a single number. A leaf holds up to 59 interval descriptors in this layout, an internal node up to 40 children. Inside a node the descriptors stay where they were written and a one-byte order array gives their sorted rank, so an insertion or a deletion shifts one-byte indices and leaves the records in place. Keys are variable-length records appended to linked key blocks; a descriptor refers to its record by block, offset and lengths, and a separator in an internal node reuses the record of its child's minimum instead of owning a copy. A point write [k, k\0) stores its endpoint once and reads its begin as the prefix, so a key of L bytes costs L + 1 bytes of payload instead of 2L + 1.

{{< figure src="fig-v3-storage.png" alt="Node blocks hold descriptors, versions and references; linked key blocks hold key bytes; both draw from one shared block pool" link="fig-v3-storage.png" >}}

<p class="figure-caption"><em>Figure 1. The shared pool. Node blocks hold interval descriptors, commit versions and references; key blocks hold the bytes; a separator reuses the range record of its child's first entry. Nodes and keys compete for the same budget.</em></p>

{{< figure src="fig-v3-order-bytes.png" alt="A conventional sorted descriptor array moves full records on insertion and deletion; Resolver v3 keeps descriptors in fixed physical slots and shifts one-byte order indices" link="fig-v3-order-bytes.png" >}}

<p class="figure-caption"><em>Figure 2. Keeping key order without moving descriptors. A conventional sorted array moves full records on insertion and deletion. Resolver v3 keeps descriptors in fixed physical slots, represents sorted order with one-byte indices and returns deleted slots to a free bitmap. Updates therefore move small indices rather than keys, versions and references.</em></p>

Three facts about an entry are kept apart because they change at different times. An entry expires logically when its CV falls below the reclamation cutoff. Its key bytes are reclaimed physically when the block that holds them is released, in allocation order, and a generation number on each range reference tells whether the block it names has been reclaimed since, without reading it. And the node that held the entry is released on its own schedule, with its own generation that guards the deferred cleanup records. Node allocations use odd generation values and key-block allocations use even values. The address can therefore cross roles after reuse, but its generation cannot be mistaken for the former role. Every algorithm below checks the version before it touches the bytes.

{{< figure src="fig-v3-generation.png" alt="Node blocks use odd generations and key blocks use even generations, so an address reused across roles cannot satisfy an old generation check" link="fig-v3-generation.png" >}}

<p class="figure-caption"><em>Figure 3. Logical expiry and physical reference validity are separate checks. The commit version determines whether an entry still belongs to readable history. The generation stored in a `RangeRef` determines whether the referenced key block has since been released and reused. Node generations provide the corresponding protection for deferred leaf-cleanup records. Final v3 assigns odd generations to nodes and even generations to key blocks, so cross-role reuse cannot produce a false match. A mismatch rejects the reference without dereferencing reclaimed memory.</em></p>

## One batch, two phases

A resolver batch arrives with its conflict ranges sorted by key, together with the transaction records. The tree exposes two calls. `checkReads` consumes the sorted endpoints, checks the eligible reads, and routes every read and write begin in one mixed descent. At each leaf it records one prepared destination for the first write of every write-bearing slice; it applies nothing and never moves the reclamation cutoff. Once the transactions' decisions are complete, `addWrites` drops the writes of rejected and too-old transactions, unions the accepted intervals, and applies them in key order, reserving space and reclaiming the oldest history when a write needs room.

{{< figure src="fig-v3-batch-phases.png" alt="The two batch phases: checkReads checks reads and prepares write destinations; addWrites applies accepted writes after transaction decisions are complete" link="fig-v3-batch-phases.png" >}}

<p class="figure-caption"><em>Figure 4. One batch, two phases. During checkReads no key block is reclaimed and reclaimCV does not move, so every pointer a task holds stays valid; addWrites starts only when all transaction decisions are complete, and every destination saved in the first phase is validated before it is used.</em></p>

The boundary between the phases is what makes the rest safe. Reads are checked against history that cannot change under them; writes are applied against decisions that cannot change either; and the destinations carried across the boundary are hints, batch-local and checked before use, because the writes applied before a given one may have split, emptied or reclaimed the leaf it pointed to.

## Recursive partitioning: fewer routing comparisons

Tree descent is one of the Resolver's main CPU costs. A batch contains many range begins already sorted by key, but searching the tree independently for every begin would repeat separator comparisons in the same upper nodes. Recursive partitioning turns the sorted batch into shared routing work.

A task starts at the root owning the complete slice of read and write begins. At an internal node, it selects a middle child boundary and binary-searches its slice for the first begin at or above that boundary. This produces two smaller routing problems: the lower begins against the lower boundaries, and the remaining begins against the higher boundaries. Each nonempty slice becomes a task responsible for one subtree; an empty slice creates no work. Once a slice has no boundary left, its task descends to the corresponding child. Equal begins go right, so duplicate keys remain together.

The relationship between begins and separators changes as the batch moves down the tree. Near the root, a few separators classify a large slice of begins. At intermediate levels, each node receives a smaller slice and the two ordered sequences can have similar sizes. Near the leaves, most reached nodes receive one begin, and recursive partitioning naturally becomes an ordinary binary search. Tasks preserve the slices created along the way, so the same algorithm handles all three regimes without starting an independent root-to-leaf search for every begin.

{{< figure src="fig-v3-batch-descent.png" alt="A sorted batch is divided into progressively smaller task slices as it descends from the root to the leaves." link="fig-v3-batch-descent.png" >}}

<p class="figure-caption"><em>Figure 5. A sorted batch descending through the tree. Near the root, a few separators classify large slices; farther down, each nonempty slice becomes a task for one subtree; near the leaves, most tasks carry one begin and perform an ordinary binary search. Empty slices create no task.</em></p>

Within one node, the operation is a recursive partition of two sorted sequences. After a boundary divides the begins, that boundary belongs to neither subproblem and is never compared again. The left and right subproblems repeat the rule over smaller boundary and begin slices until every nonempty group has one child destination.

{{< figure src="fig-v3-recursive-partition.svg" alt="The middle child boundary divides sorted begins into two smaller subproblems, which are recursively assigned to children." link="fig-v3-recursive-partition.svg" >}}

<p class="figure-caption"><em>Figure 6. Recursive partitioning within one internal node. Boundary 40 divides the sorted begins into lower and upper slices; the smaller subproblems then resolve boundaries 20 and 60. Equal begins go right, into the child whose minimum is that boundary.</em></p>

With $S$ child boundaries and $K$ begins at a node, independent searches require
$O(K\log(S+1))$ routing comparisons. Recursive partitioning requires

$$
O\!\left(m\log\!\left(1+\frac{M}{m}\right)\right),
\qquad m=\min(K,S),\quad M=\max(K,S).
$$

This gives $O(S\log(1+K/S))$ when $K\gg S$, linear work when $K$ and $S$ are
comparable, and $O(K\log(1+S/K))$ when $K\ll S$. For $K=1$, it is the usual
$O(\log(S+1))$ binary search.

{{< figure src="fig-v3-partition-balance.png" alt="Expected routing comparisons by tree level for independent searches and recursive partitioning in a tree sized like the 6 GiB evaluation." link="fig-v3-partition-balance.png" >}}

<p class="figure-caption"><em>Figure 7. Analytical comparison for 10,000 uniformly distributed begins in a tree sized like the 6 GiB campaign. Most comparisons disappear in the upper levels, where many begins share each node. Recursive partitioning reduces the modelled internal-routing comparisons from 204,286 to 90,463; including the initial searches inside the reached leaves, the reduction is from 258,920 to 144,877. These are routing-key comparisons, not elapsed-time measurements.</em></p>

The comparison model excludes the cost of accessing external key bytes, refreshing expired separators, scanning leaves, scheduling tasks and issuing prefetch hints. Uniformly distributed begins are also an unfavorable case for sharing: clustered begins reach fewer subtrees and continue sharing their descent deeper into the tree.

## One mixed descent for reads and write destinations

Recursive partitioning reduces the cost of routing one sorted batch. The Resolver would still duplicate much of that work if it descended the tree once to check reads and again to locate the writes that survive admission. `checkReads` therefore extracts one begin-sorted sequence containing both read and write begins, tagged by type, and routes them together.

Both types participate in partitioning and determine which slices reach each child. At a leaf, the task checks the eligible reads against conflict history and records the destination of the slice's first write. A write begin is a routing item: it receives no read-conflict result, and no write is applied during `checkReads`. Read-only slices produce no write destination; write-only slices still benefit from the same batched descent.

{{< figure src="fig-v3-mixed-descent-col.png" alt="Read and write begins are recursively partitioned together; leaf tasks check reads and record write destinations." link="fig-v3-mixed-descent.png" class="col" >}}

<p class="figure-caption"><em>Figure 8. One mixed descent. Read begins (R) and write begins (W) are partitioned together. At a leaf, reads are checked and the slice's first write destination is recorded. Write begins receive no conflict result, and nothing is applied during this phase.</em></p>

Leaf tasks can finish out of order, so their prepared write destinations carry tickets in begin order and pass through an ordered frontier. Once all transaction decisions are complete, `addWrites` discards rejected and too-old writes, unions the accepted intervals and applies them in increasing begin order. A recorded destination is only a batch-local hint: it is validated or redirected before any saved tree pointer is consumed, because earlier accepted writes may have changed the tree.

## Hiding memory latency with cooperative software prefetching

Tree traversal is CPU work punctuated by dependent memory accesses. After
reading one node, the Resolver discovers which node or key bytes it needs next;
if that data is outside the cache, a conventional traversal stalls until it
arrives. The Resolver hides part of this latency by turning independent
traversal slices into cooperative tasks. A task runs while its current data is
available, prefetches its next dependency and yields. Other tasks execute
during that memory wait, giving the prefetched data time to arrive before the
first task is visited again.

Each traversal task carries a tree node, a contiguous slice of the batch's
begin-sorted operations, and the bounds and cursors needed to continue its
work. The whole sequence starts as one task at the root. As partitioning
creates sibling tasks, up to `G` tasks—sixteen in final v3—are resident at once
and visited in rounds on one non-preemptive thread; further tasks wait until a
resident slot becomes available.

{{< figure src="fig-v3-task-admission.png" alt="Round-end admission: new right-hand tasks are interleaved after their parents in range order, the first G are admitted into resident records and the rest wait on a pending stack" link="fig-v3-task-admission.png" >}}

<p class="figure-caption"><em>Figure 9. Round-end admission keeps range order without moving resident tasks. At most `G` traversal tasks occupy resident records. Tasks created during a round wait for its end, when available records admit them in slice order. Existing tasks retain their records and saved state; excess tasks remain pending until a later round releases capacity.</em></p>

The implementation expresses the traversal as a set of resumable states: a
state names the next operation the task must perform when the scheduler visits
it again. Handlers whose inputs are already local may chain within the same
visit. When the next handler depends on data that may not be local, the task
hints that dependency, records the state that will consume it and yields.

1. **Partition and descend — `InspectNode` and `CompareKeys`.**
   `InspectNode` consumes the hinted node and determines whether it is internal
   or a leaf. At an internal node, `CompareKeys` compares the node's ordered
   separators with the ordered begins in the task's slice. It repeatedly
   narrows or partitions both sequences until each resulting slice belongs to
   one child. The current task continues down one nonempty child, while every
   other nonempty child slice becomes a sibling task; an empty slice creates
   no task. Each task hints its child and returns to `InspectNode` when that
   child is consumed.

2. **Establish the leaf position and predecessor — `CompareLeafKey`,
   `FindPrev` and `CheckPrev`.**
   When `InspectNode` reaches a leaf, it records that leaf as the prepared
   destination of the slice's first write, if the slice contains one; no write
   is applied. A write-only slice can complete at this point. Otherwise,
   `CompareLeafKey` performs one lower-bound search for the first read begin
   among the leaf's ordered interval begins. An exact match can proceed
   directly to `StartScan`. If there is no exact match, the task looks for the
   nearest live predecessor. A predecessor found in the destination leaf
   leads to `CheckPrev`; if the search must cross a leaf boundary, `FindPrev`
   consumes the hinted left leaf and may continue following left links until
   it finds a live interval or reaches the end of the chain. `CheckPrev` tests
   that single predecessor against the ordered reads it may overlap, marks any
   conflict using the rule below and then advances to `StartScan`.

3. **Scan forward — `StartScan`, `ScanLeaf` and `Done`.**
   `StartScan` initializes the active chain of unresolved reads and the cursors
   used by the merge-like scan. `ScanLeaf` walks the leaf's ordered intervals
   against that chain, discarding impossible overlaps by key order and
   comparing commit versions where intervals overlap. Figure 10 shows how
   decided reads leave the active chain without moving their records, and how
   the scan avoids repeating begin/end relations that have already been
   established. At a leaf boundary, the task preserves its scan state, hints
   the right neighbour and yields; when no unresolved read remains or the leaf
   chain ends, it enters `Done`.

{{< figure src="fig-v3-leaf-scan.png" alt="A leaf scan walks the stored write intervals in key order against a linked list of unresolved reads; decided reads are unlinked without moving their records" link="fig-v3-leaf-scan.png" >}}

<p class="figure-caption"><em>Figure 10. A leaf scan keeps only unresolved reads active. Read records remain in their fixed begin-sorted slice, while `nextBegin` links only those whose result is still unknown. Deciding a read unlinks its index without moving the record or changing the task's routing bounds. A separate cursor remembers the prefix of read begins already passed by the advancing stored-interval end.</em></p>

**Deciding and recording conflicts.** `CheckPrev` and `ScanLeaf` apply the
same rule. A stored write interval `[wb, we)` at commit version `CV` conflicts
with a read interval `[rb, re)` at read version `RV` exactly when the intervals
overlap,

`wb < re && rb < we`,

and the stored write is newer than the read,

`CV > RV`.

The ordering of the intervals determines which cursor advances. If
`we <= rb`, the stored interval ends before the read begins, so the scan moves
to the next stored interval. If `re <= wb`, the read ends before the current
stored interval begins and cannot overlap it or any later interval, so the read
is removed from the active scan chain. Otherwise the intervals overlap and
their versions are compared. A stored interval at or below the read version
does not conflict, but the read remains active because it may still overlap a
later, newer interval.

When a conflict is found, `markConflict` marks both levels of the result:
`conflicts[rangeIndex]` identifies the conflicting read range, and
`transactionConflictStatus[transaction]` rejects the transaction. For an
ordinary transaction, the remaining reads need not be checked after the first
conflict. If the caller requested conflicting-range reporting, traversal
continues so that every conflicting read range can be marked. A read whose
version is already below `reclaimCV` is handled before traversal by marking its
transaction too old, because the retained tree no longer contains enough
history to decide it. `addWrites` later discards the writes of transactions
that were rejected or marked too old.

A visit is not limited to one state transition. It advances a task through as
much already-local work as possible. When the next transition depends on data
that may not be local, the task issues the corresponding prefetch hints,
records the state that will consume them and yields. A node block is hinted in
64-byte steps; separator keys, stored interval keys and read keys receive at
most two cache-line hints, so later blocks of a long key may still miss. While
the other tasks take their visits, the hints have time to complete. The useful
distance between a hint and its use is therefore made of other tasks' work,
which is why interleaving can hide memory latency even on a single thread.
Prefetch remains advisory: correctness does not depend on a hinted line having
arrived or still being cached when the task resumes.

{{< figure src="fig-v3-key-prefetch-col.png" alt="A stored key is hinted with at most two cache-line prefetches in its first block; a key that continues through a linked block has its continuation line hinted after the reference is validated" link="fig-v3-key-prefetch.png" class="col" >}}

<p class="figure-caption"><em>Figure 11. Hinting a stored key without walking it synchronously. The first key block is hinted with at most two cache-line prefetches. A short key can then be compared directly; when the stored key continues through linked blocks, `KeyMore` saves the interrupted state, hints the next block, yields and later returns control to the comparison it was serving.</em></p>

{{< figure
  src="fig-v3-single-dispatch-col.png"
  alt="Cooperative traversal tasks consume previously hinted memory accesses, advance through resumable states and prefetch their next dependencies before yielding"
  link="fig-v3-single-dispatch.svg"
  class="col"
>}}

<p class="figure-caption"><em>Figure 12. One dispatch per task visit. Dashed
arrows are prefetch hints, each consumed on the same task's next visit.
New right-hand tasks become eligible for admission at the end of the round. A
task scans a whole leaf in one visit, then hints the next leaf and
yields.</em></p>

Two hazards come with checking reads this way over a structure that is also
being compacted.

First, several tasks can reach the same leaf: by descending into it, by
scanning forward from its left neighbour or by searching backward for a
predecessor from its right neighbour. Each task saves positions as leaf ranks,
so changing the leaf's order after one task has saved a rank would invalidate
that task's cursor. A leaf is therefore compacted at most once per read batch,
on its first visit, and stamped. Later arrivals observe the same compacted
order and can safely use their saved ranks. Leaves emptied by compaction remain
linked until every traversal task has finished; the scheduler then releases
them through a pending-cleanup queue whose entries are checked by generation.

Second, an internal separator is a copied reference to a child's former
minimum. The referenced key block may have been reclaimed even though the
child still contains live history. The separator's version is therefore
checked before its key is hinted. If it has expired, the separator is refreshed
from the child's first live entry before any task reads the referenced bytes.

{{< figure src="fig-v3-read-maintenance-col.png" alt="Two panels: a leaf is compacted once per read batch and stamped before any task saves a rank into it; an expired internal separator is refreshed from the child's first live entry before its key bytes are hinted" link="fig-v3-read-maintenance.png" class="col" >}}

<p class="figure-caption"><em>Figure 13. Read-phase maintenance preserves saved ranks and prevents stale key dereferences. A leaf is compacted at most once per read batch, before any task saves a rank into it. Separately, an internal separator is checked by version before its referenced bytes are hinted; an expired separator is rebuilt from the child's first live entry.</em></p>

## Hiding write-path memory latency while preserving serial mutation order

Accepted intervals are applied in increasing begin order. This makes mutation
advance monotonically through the tree and prevents a later interval from
modifying, splitting or redirecting a leaf before an earlier interval reaches
it. Without that order, a later write could invalidate the earlier task's
prepared destination, search position or split candidate, forcing another
search and making interval application more expensive. The ordering constraint
applies only to mutation, however: younger tasks may search their destination
leaves, prefetch stored keys and prepare their comparisons while the older
writer is still running.

The read phase has already routed the batch's read and write begins together
and recorded one prepared destination for every write-bearing slice that
reached a leaf. `addWrites` reuses those destinations as batch-local hints,
filters and unions the accepted intervals, and runs their remaining leaf
searches as cooperative tasks. Only the oldest task of the oldest group may
mutate the tree; the younger tasks use otherwise idle visits to validate
destinations, prefetch leaves and stored keys, and park until their turn. The
design therefore overlaps write-path memory latency while retaining a single,
forward-moving mutation order.

### The write frontier

When the read scheduler completes, every write-bearing slice has a prepared-destination record covering the write begins routed with that slice. Leaf tasks finish in whatever order their memory dependencies arrive, so each result is stored in an arrival buffer and the slice's first write records a ticket to it. A write frontier walks the write-bearing slices in begin order and emits only the contiguous prefix whose destinations are known: a slice whose leaf was found early waits for every earlier write-bearing slice, while read-only slices are skipped. An arrival-buffer slot is recycled only after its ticket and every earlier buffer ticket have been released.

{{< figure
  src="fig-v3-write-frontier.png"
  alt="Write-leaf results arrive out of order and an ordered frontier emits only the known prefix"
  link="fig-v3-write-frontier.png"
>}}

<p class="figure-caption"><em>Figure 14. The write frontier. Prepared destinations become known out of begin order, and each write-bearing slice records a ticket to its buffered result. The frontier walks the slices in begin order, emits only the contiguous known prefix and skips read-only slices. An arrival-buffer slot is recycled only after its ticket and every earlier buffer ticket have been released. The emitted destinations remain hints.</em></p>

When the read scheduler finishes, the emitted records form `writeLeaves`, an
ordered vector of prepared destination groups rather than merely a list of raw
leaf pointers. Several groups may name the same leaf. At the phase boundary
they are linked to one representative, and the leaf temporarily identifies
that representative. The representative carries the current anchor, the first
accepted write and an external mutation counter.

Those destinations remain live while `addWrites` changes the tree. A split,
leaf removal or subtree reclamation redirects every affected representative to
a replacement leaf, or marks it as having no current leaf. If two redirected
groups meet at the same leaf, their representative links are joined. The
redirection also invalidates any saved split candidate, records that a
right-neighbour check may be required and increments the representative's
mutation counter. The active writer's cursor is redirected immediately.

A younger task validates a saved destination at two levels, in order. The
first compares batch-owned metadata without touching the leaf: its
representative, anchor address, prepared mutation counter and saved
`reclaimCV`. If any value changed, the task parks, and when it becomes the
writer it resolves the current representative, starts again from the
redirected destination and reissues the required hints. Only if that metadata
still holds does the second level read the block itself: first its generation,
which must be odd and equal to the one saved with the rank, and only then the
leaf's mutation epoch. Node generations are odd and key-block generations even,
from disjoint sequences, so a block released from a leaf and reused for key
bytes fails the generation check before any leaf-only field is read; a
matching leaf whose epoch moved keeps its identity but loses its rank, and the
task searches it again. The destination records can therefore survive earlier
splits and reclamation without turning a reused block into a valid-looking
leaf pointer.

### From decisions to accepted intervals

`addWrites` receives the final transaction decisions and one commit version
for the call. Rejected and too-old transactions contribute no write. Accepted
write begins are streamed in endpoint order, and overlapping intervals are
unioned by index into the caller's endpoint array. No key bytes are copied and
no object is allocated per interval; adjacent intervals may remain distinct.
The first begin of a merged interval retains its prepared destination, and
groups that currently resolve to the same leaf share one representative.

{{< figure
  src="fig-v3-accepted-union.png"
  alt="Transaction decisions filter write intervals before overlapping accepted intervals are unioned"
  link="fig-v3-accepted-union.png"
>}}

<p class="figure-caption"><em>Figure 15. From decisions to accepted intervals.
Rejected and too-old transactions drop out; overlapping accepted intervals
merge by endpoint index, while adjacent intervals may remain distinct. The
first begin of each merged interval retains the prepared destination produced
by the shared read/write descent.</em></p>

### One writer, fifteen scouts

Applying writes was where v1 and v2 spent most of their time: every write
performed its own descent and exposed its dependent memory accesses
serially. V3.8 applies the accepted intervals through two groups of eight
cooperative tasks on one thread. The oldest task of the oldest group is the
only task allowed to mutate the tree.

Whenever it is safe to do so, younger tasks inspect their prepared leaves,
prefetch stored keys, search for their insertion positions and park at
`SearchReady`, outside the runnable bitmap. If a task encounters work that
would mutate or repair the tree—cleanup, destination redirection or a required
right-neighbour walk—it parks earlier and leaves that work to its turn as
writer. The successor group is filled and its leaves are hinted in advance.
Its searches become runnable after half of the oldest group has completed.
When the oldest group finishes, its slot is refilled and the group roles
rotate. This gives a task's leaf and key data several intervening visits in
which to reach the cache before its write turn.

{{< figure
  src="fig-v3-write-groups.png"
  alt="Two groups of cooperative write tasks overlap destination searches with the work of the single writer"
  link="fig-v3-write-groups.png"
>}}

<p class="figure-caption"><em>Figure 16. Two groups of write tasks on one
cooperative thread, drawn with four tasks per group for legibility; final v3 uses
eight. Only the oldest task writes. Younger tasks search, prefetch and park,
and the successor group starts after the oldest group reaches its halfway
point.</em></p>

### The state machine of one write task

Each write task carries its accepted interval, destination group, resolved
representative, anchor leaf, mutation counter, reclamation cutoff, insertion
bounds, scan position and a cursor that can be redirected by structural
changes. Its state machine has five stages.

1. **Validate and reach the current destination — `Inspect`, `Route`,
   `InspectRight` and `CompareRight`.**
   Before any saved leaf or key pointer is consumed, the task validates its
   representative, anchor, mutation counter and saved cutoff against the
   current batch metadata. If they changed, a younger task parks; the oldest
   task resets its search from the redirected destination. `Inspect` then
   consumes the hinted leaf. If the read-phase partition still proves that the
   write belongs there, the task can begin its local search. Otherwise,
   `Route`, `InspectRight` and `CompareRight` inspect the first live entry of
   successive right neighbours until the write's begin is again bounded by
   the correct leaf.

2. **Search and park — `Search`, `CompareSearch`, `KeyMore` and
   `SearchReady`.**
   `Search` and `CompareSearch` perform a prefetched binary search for the
   write begin in the destination leaf. `KeyMore` is the continuation used
   when a stored key spans linked key blocks: one block is hinted, the task
   yields, and the next visit resumes the comparison. Once the insertion rank
   is known, a younger task enters `SearchReady` and leaves the runnable set.
   It is woken only when it becomes the oldest task of the oldest group.

3. **Acquire the write turn, reserve and prepare the split —
   `PrepareInput`.**
   On wake-up, the task validates the leaf generation and mutation epoch saved
   with its speculative rank before consuming it. `PrepareInput` rejects an empty interval and
   reserves the key blocks, up to two leaf slots and any structural work the
   write may require. Reservation may reclaim the oldest history. If that
   changes the destination leaf or advances `reclaimCV`, the task returns to
   `Inspect` and searches again with the reservation already holding. Only
   after the reservation holds is the split state prepared. A split
   candidate saved during `checkReads` is reused while its epoch remains
   valid; otherwise the task rebuilds the candidate by walking the parent
   chain.

4. **Preserve the left exterior and insert — `Previous`,
   `InspectPrevious`, `KeyMore` and `Insert`.**
   If the write begin does not exactly match an existing interval, `Previous`
   checks the immediately preceding live interval. The predecessor may be in
   the destination leaf or, through `InspectPrevious`, in a leaf to its left.
   If the predecessor overlaps the new write, the part before the write begin
   is preserved with its original commit version. `KeyMore` fetches the rest
   of a predecessor key that crosses block boundaries. `Insert` then appends
   the new interval at the call's commit version. If the write lies wholly
   inside its predecessor, the right exterior can also be preserved here and
   the interval is complete.

5. **Scan, preserve the right exterior and erase — `Scan`, `CompareEnd`,
   `Erase`, `KeyMore` and `Done`.**
   Otherwise, `Scan` advances from the insertion position through the
   intervals covered by the new write, following right-leaf links as needed.
   `CompareEnd` compares the write end with the current stored interval. If the
   write ends inside that interval, its surviving right exterior is preserved
   with the old commit version and this accepted interval is complete.
   Intervals covered completely by the write pass through `Erase`; a possible
   successor leaf is hinted before deletion can redirect the scan. `KeyMore`
   resumes comparisons whose stored interval spans linked key blocks. The next
   accepted interval in the same destination group returns through
   `PrepareInput` and reuses the current rank as its lower search bound. When
   the group has no interval left, the task enters `Done` and wakes its
   successor.

Steps whose data are already local chain within one visit. A state that needs
a leaf or key block issues its prefetch hints and yields, allowing the other
tasks to provide the distance between the hint and its use. The state machine
therefore overlaps memory latency while preserving the same serial mutation
order as the accepted intervals.

{{< figure
  src="fig-v3-write-task-states.png"
  alt="State machine of a cooperative write task from speculative destination search through insertion and forward erasure"
  link="fig-v3-write-task-states.png"
>}}

<p class="figure-caption"><em>Figure 17. The state machine of one write task. Each box gives the conceptual
operation and the exact implementation states beneath it. Green transitions
chain already-local work within one visit; dashed orange transitions yield
after issuing a prefetch hint. A younger task searches speculatively when it
can do so without modifying the tree and normally parks at `SearchReady`; if
inspection or right routing would require mutation, it parks at `Inspect`
instead. When the task becomes the writer, the entry guard validates its
representative, anchor, saved leaf generation, mutation epoch and reclamation cutoff before any
saved rank or pointer is consumed, and `PrepareInput` validates the accepted interval
and reserves all space required by the mutation. If reservation changes the
destination or cutoff, the task returns to `Inspect` with the reservation
already holding. `KeyMore` prefetches the required stored-key bytes across
linked blocks and then resumes its saved target state. `Done` is reached
locally when the destination group has no accepted interval left; the
scheduler then wakes its successor.</em></p>

## Proactive splits and space reservation

{{< figure src="fig-v3-split-conventional.png" alt="In a conventional B+ tree a single leaf insertion can split the leaf, its full parent and further full ancestors in a chain" link="fig-v3-split-conventional.png" >}}

<p class="figure-caption"><em>Figure 18. Why conventional B+ tree splitting is unsuitable for the write path. In a full path, one leaf insertion can propagate a split through several full ancestors. The number of structural changes and required allocations is then discovered only while the mutation is already in progress.</em></p>

Two mechanisms keep a write's structural cost bounded. The first came with v1: every internal node keeps free child slots for the children that will need to split, maintained as an invariant, so that a write splits at most one existing node and never cascades up a full path. A leaf needs a split when it has at most one free slot, because one write can add its own interval and a surviving right exterior; an internal node needs one when all its free slots are spoken for. The arithmetic that keeps the invariant is small: splitting a child consumes one free slot in the parent and removes one pending split, so the balance is unchanged.

{{< figure src="fig-v3-split-proactive.png" alt="A pending child split has a reserved parent slot, so a write splits at most one existing node" link="fig-v3-split-proactive.png" >}}

<p class="figure-caption"><em>Figure 19. Resolver v3 reserves the structural consequence in advance. A child that may need to split already has a free slot reserved in its parent. Triggering the split consumes that slot and may mark the parent as a future split candidate, but the current write splits at most one existing node.</em></p>

The second is the reservation. Before the oldest task mutates, `reserveWrite` checks space for the write's key bytes, up to two leaf slots and the split work it may need, and reclaims the oldest history if the pool lacks it; the reserve is never below 35 blocks and grows with the longest key seen, which is what lets a 30,001-byte system key be stored into a full pool. Only after the reservation holds does the task prepare its split state, reusing the candidate saved during the read phase while its epoch is valid. A reservation that fails throws, and the writes already applied in the call stay applied; the batch is not rolled back.

{{< figure src="fig-v3-reserve-before-mutate.png" alt="The oldest write task reserves pool space before mutation and restarts destination inspection if reservation reclaims history" link="fig-v3-reserve-before-mutate.png" >}}

<p class="figure-caption"><em>Figure 20. Reserve before mutate. With room in the pool the validated position is used; when reclaiming was needed, the destination, its generation or the cutoff may have changed and the task inspects again. Split state is prepared only after the reservation holds.</em></p>

Destinations are validated because the writes before a given one can change its leaf, and reservation can reclaim it. Final v3 saves the destination leaf generation and mutation epoch with every rank. A rank is reusable only if the same leaf generation still occupies the block and that leaf has not mutated; otherwise the task searches again. Node and key-block generation values are disjoint, so a block reclaimed as a node and reused for keys cannot accidentally satisfy the leaf check. A split can also move the insertion point beyond the leaf's new upper boundary, in which case a right-neighbour check moves the search to the new right leaf. Figure 21 shows these cases.

{{< figure src="fig-v3-destination-validation-col.png" alt="A write task validates its speculative destination before reusing a saved search position or following a changed leaf boundary" link="fig-v3-destination-validation.png" class="col" >}}

<p class="figure-caption"><em>Figure 21. Validating a destination. A still-valid generation and mutation epoch allow the saved rank to be reused. A mutation, reclamation or cross-role block reuse forces a new search; a split that moved the insertion point past the leaf's new boundary sends the write to the right neighbour.</em></p>

## Reclaiming history within a fixed budget

History retention is bounded by the shared pool rather than by a fixed time
window. Reclamation has to coordinate two independently allocated stores: node
blocks and key blocks. Each store maintains its own age-ordered intrusive list,
and every list entry carries a reclamation CV. For a node or subtree, that CV is
its conservative maximum commit version. For a key block, it is the maximum
commit version stored in the block. The node list is ordered by its conservative
maximums; the key-block list follows allocation order and exposes the oldest
reclaimable key block at its head.

When a write cannot reserve the space it needs, the tree examines the heads of
both lists and chooses the lower reclamation CV. Reclamation therefore
progresses by commit version, not by block type: whichever store contains the
oldest reclaimable history determines the next cutoff. The cutoff advances
monotonically to that CV, and reclamation continues at the same cutoff until
neither list has another entry whose reclamation CV is at or below it.

Figure 22 follows two successive allocation shortages. The first selects CV 401
from the key-block list and returns that whole block to the shared free list.
Both stores then expose CV 403. Advancing the cutoff to 403 removes every node,
subtree and key block reclaimable at that version, not just the first object
found. The mixed-age node with maximum CV 408 survives, but its entries at or
below 403 are compacted and only its newer history remains.

{{< figure src="fig-v3-reclamation-by-cv.png" alt="Version-wide reclamation from the node and key-block lists" link="fig-v3-reclamation-by-cv.png" >}}

<p class="figure-caption"><em>Figure 22. Version-wide reclamation from two independently allocated stores.
Each shortage compares the reclamation CVs at the two list heads. Once a CV is
selected, reclamation continues at the same cutoff until neither list contains
another entry reclaimable at that version or earlier. Whole key blocks, nodes
and subtrees are released; surviving mixed-age nodes compact their expired
entries.</em></p>

Advancing the cutoff makes all history at or below that CV unusable, not merely
the object that triggered the advance. Keeping another node or key block that
contains only that history would consume memory without preserving any
additional readable state. This is why a cutoff advance is a version-wide
operation rather than a one-block eviction.

A whole key block returns to the shared free list when its maximum commit
version is at or below the cutoff. A node or complete subtree can likewise be
released when its conservative maximum proves that it contains nothing newer.
Mixed-age nodes remain allocated, but their entries at or below the cutoff are
compacted while their newer history is preserved.

The cutoff never decreases. A transaction whose read version falls below it is
rejected as too old because the history required to decide its conflicts is no
longer available. This is the same safety boundary that FoundationDB exposes
today, but its position is determined by actual memory pressure and workload
history rather than by a fixed five-second clock.

## Reducing TLB misses with HugeTLB pages

A multi-gigabyte pool creates a second memory problem even when its byte budget is under control. Tree descent, predecessor inspection and key comparison perform irregular accesses across the pool. With ordinary 4 KiB virtual-memory pages, the 6 GiB pool requires 1,572,800 page mappings, far beyond the coverage of the processor's TLB. A cache miss can therefore be accompanied by an address-translation miss, adding another dependent memory access to operations already limited by memory latency.

V3.8 addresses this by allowing the pool to be backed by explicit 2 MiB HugeTLB pages. The same 6 GiB then requires only 3,072 page mappings—512 times fewer—greatly increasing the fraction of the pool addressable through cached translations. This changes neither the temporal B+ tree nor its 64 KiB logical pages, 2 KiB blocks, shared free list, reclamation policy or memory budget; it changes only how the pool's virtual addresses are mapped to physical memory.

`RESOLVER1_PAGE_MODE` selects the backing when the pool is constructed: ordinary heap allocation, advised 4 KiB pages, transparent huge pages, or explicit HugeTLB pages taken from the operating system's reserved pool. Transparent huge pages are opportunistic and provide no coverage guarantee. Explicit HugeTLB makes the choice deterministic and visible: if the reserved pool cannot satisfy the mapping, construction fails rather than silently falling back to smaller pages.

{{< figure src="fig-v3-hugetlb.png" alt="One shared pool with four backing modes: logical 64 KiB pages contain reusable 2 KiB blocks, while HugeTLB can map the pool using 2 MiB pages" link="fig-v3-hugetlb.png" >}}

<p class="figure-caption"><em>Figure 23. One pool, four memory backings. The geometry, the free list and the budget do not depend on the backing; the number of page mappings that cover the pool does, and with it the translation cost of random accesses.</em></p>

## What the measurements show

### Why two testbeds

Memory behaviour is part of the result rather than incidental testbed detail. The same single-threaded Resolver was therefore evaluated on two Linux processors with materially different cache, SMT and memory organizations. Each timed benchmark process was pinned to one physical core; the remaining cores provided no parallelism to the measured Resolver operation. Figure 24 reports the controlled campaign setup and the dependent-pointer latency measured on both testbeds. Figure 25 then expands the two cache and package organizations, separating properties recorded by the campaigns from details taken from the vendors' published microarchitectures.

{{< figure src="fig-v3-memory-testbeds.png" alt="Two controlled Resolver testbeds: an Intel Core Ultra 9 285K and an AMD Ryzen 7 7700, their recorded cache, memory and execution configurations, and the dependent-pointer latency measured on both, from 0.70 to 163.23 nanoseconds per access on Intel and 0.75 to 103.83 on AMD" link="fig-v3-memory-testbeds.png" >}}

<p class="figure-caption"><em>Figure 24. Two contrasting memory systems and their measured dependent-access latency. The same byte-identical pointer-chase binary runs pinned to one core on both machines, with one dependent pointer per 64-byte line, ordinary 4 KiB pages, no software prefetch and five timed repetitions per working-set size. At 26.9 KiB the processors are close; at 45.3 KiB Intel remains within its 48 KiB L1 while AMD has exceeded its 32 KiB L1; at 1 MiB Intel is faster; and at 16 and 512 MiB AMD has the lower serial access latency. The 512 MiB-to-L1 increase is 231.9× on Intel and 137.9× on AMD. The AMD 1 MiB value is from the preselected primary process; complete-process medians ranged from 5.49 to 6.42 ns.</em></p>

At 26.9 KiB, a working set that fits comfortably in both L1 data caches, the median dependent-access latency is similar: 0.70 ns on Intel and 0.75 ns on AMD. The curves then separate. At 45.3 KiB, Intel remains on its 48 KiB L1 plateau at 0.71 ns, while AMD has exceeded its 32 KiB L1 and rises to 2.74 ns, 3.9× Intel's latency. At 1 MiB, which fits within Intel's 3 MiB private L2 but lies at the capacity boundary of AMD's 1 MiB L2, the primary-process medians are 3.64 and 6.28 ns respectively.

The ordering reverses for larger working sets. At 16 MiB, with a working set that fits within the nominal shared last-level-cache capacity of both processors, AMD takes 11.99 ns per dependent access against Intel's 19.21 ns. At 512 MiB, where accesses reach DRAM and include address-translation cost, AMD takes 103.83 ns against Intel's 163.23 ns. From the common L1-resident point to 512 MiB, latency grows by 231.9× on Intel and 137.9× on AMD. AMD is therefore not a uniformly slower memory system: it has a smaller and more expensive private-cache region in this experiment, but lower last-level-cache and large-working-set latency.

This difference is consistent with the Resolver's cross-machine behaviour. Cooperative scheduling has a fixed cost in task state, dispatch, branches and instructions, and it increases the set of leaves, keys and task records that are live between a prefetch and its use. Intel's larger private caches provide more room for that active set, while its much higher large-working-set latency leaves more time and more cost for recursive partitioning and cooperative prefetching to remove or hide. On AMD, the smaller private caches leave less capacity in which prefetched data can survive the intervening visits, while a miss that reaches the shared cache or DRAM is cheaper. This combination would give the scheduler both less far-memory latency to hide and less private-cache headroom with which to hide it. The pointer-chase measurements are consistent with that interpretation, although they do not measure prefetch survival directly.

That combination provides a plausible explanation for the observed pattern: final v3 obtains its clearest gains on Intel, while AMD's short workloads cluster closer to FoundationDB except for the integrated point and `conflictset` range regressions. The final AMD long trace is a correctness and retention replica, not a timing conclusion. The pointer chase does not, by itself, explain the `conflictset` range result. That workload commits only 16.5% of its transactions, so FoundationDB's ability to terminate after an early conflict remains an independent algorithmic advantage. Nor does the pointer chase prove causality: it permits only one outstanding dependent access and uses ordinary 4 KiB pages, whereas final v3 interleaves several tasks and maps its pool with HugeTLB. Establishing the complete attribution would require paired measurements of cache residency, load waits, prefetch timeliness, branch behaviour and CPU-frontend starvation.

The AMD 1 MiB point is less stable across process launches than the other selected sizes. The preselected primary process measured 6.28 ns, while the medians of five complete processes ranged from 5.49 to 6.42 ns. The cause was not established; physical-page placement is consistent with the observation but was not controlled or recorded. The figure reports the primary process and exposes the cross-process range.

The contrast is structural rather than merely a difference in cache capacity. The timed Intel P-core traverses a two-stage private data-cache hierarchy before its private L2 and the compute tile's shared L3. The AMD core has a conventional private L1 and L2 followed by the CCD's shared L3. In both processors, an access that reaches DRAM must leave the die containing the timed core. The same irregular tree access can therefore encounter different cache residency, sharing, translation and prefetch timing on the two systems.

{{< figure src="fig-v3-memory-hierarchies.png" alt="The cache and package memory hierarchies of the Intel Core Ultra 9 285K and AMD Ryzen 7 7700 testbeds, showing the private caches of the timed core, shared last-level caches, separate memory-controller dies and DRAM" link="fig-v3-memory-hierarchies.png" >}}

<p class="figure-caption"><em>Figure 25. Where the Resolver's bytes can reside on the two testbeds. A cache drawn inside a core is private to it; an enclosing cache is shared by the cores it contains, and × n denotes replicated units. Only the highlighted core executes the timed Resolver. Campaign-recorded properties are distinguished from cache and package structure taken from the vendors' published microarchitectures. Intel's 48 KiB DL0, 192 KiB DL1 and private 3 MiB L2 lead to a 36 MiB L3 shared across the compute tile; AMD's private 32 KiB L1 data cache and 1 MiB L2 lead to a 32 MiB L3 shared by the eight-core CCD. Both processors place the memory controller outside the die containing the timed core.</em></p>

The dependent-pointer experiment isolates serial data-access latency; it is not a measurement of final v3's HugeTLB-backed pool or of the Resolver's ability to overlap several accesses. The byte-identical binary runs with ordinary 4 KiB pages, one dependent pointer per 64-byte line and no software prefetch. Recursive partitioning removes some such dependencies, while cooperative scheduling attempts to overlap the remaining ones. The measured curves make the cross-machine performance pattern intelligible, but the workload profiles—not this diagnostic alone—determine how much of each cache and memory regime the Resolver actually experiences.

Scheduling and write-group alternatives were swept independently on both systems. Both campaigns retained the same 2 × 8 configuration because no alternative delivered a repeatable improvement in the complete point and range workloads. Results are therefore reported separately: an effect that appears on only one processor is preserved rather than averaged into a synthetic machine.

### Controlling code-layout sensitivity

Late experiments exposed a second source of architectural sensitivity: the placement of the generated machine code. Small source changes sometimes produced timing differences much larger than the work they added or removed, and the sign of those differences could change between Intel and AMD. The resulting binary was functionally identical—transaction decisions and conflicts were unchanged—but its functions and hot loops no longer occupied the same instruction addresses or cache-line boundaries.

The effect first became clear in the comparison between v3.15 and v3.16. V3.16 shortened `addWrites` by only 51 bytes, but in the ordinary build that moved every function emitted after it by 48 bytes and changed its offset modulo 64. On AMD, the unaligned 32-writer comparison made v3.16 appear about 7% faster in the write phase. Rebuilding both versions with `-falign-functions=64` removed that apparent point-workload gain: their ratio became 1.0002. The Intel control behaved differently—the v3.16 point gain remained with aligned builds—which established that code placement was an architecture-dependent confounder rather than a portable optimization.

A later padding control isolated the effect more directly. V3.17 enlarged `addWrites` by 23,735 bytes and consequently moved every later function by 23,744 bytes. A copy of v3.16 was assembled with padding after `addWrites`, changing no executable logic but placing every other function at the same address as in v3.17. That padding-only binary reproduced the apparent gain. Once v3.17 was compared with the address-matched v3.16 control, the write ratios were 1.003 in points and 0.999 in ranges, and the read ratios were 0.999 and 1.000. The change itself was therefore neutral; the earlier difference came from layout.

The counters showed that these layout effects changed observed load-wait cycles even when instruction counts and decisions were unchanged. They did not identify one universal microarchitectural cause, and function-entry alignment does not make internal branch targets or loop placement identical. The lesson is methodological: without controlling layout, a source edit can move unrelated hot code and be credited for a speedup or regression that it did not cause.

From that point onward, custom production comparisons record text hashes and function layouts, use `-falign-functions=64` where the experimental protocol requires it, and employ a padding-only address-matching control when a change inside a large function can still move the code that follows. The rule does not claim that 64-byte alignment is always fastest; it prevents incidental shifts of later function entries from being credited to a source change. The final fix A/B additionally uses alternating AB/BA pairs and a byte-identical A/A control. The final headline evaluation uses its own common build and pairing protocol, specified in the consolidated report.

Dedicated CPU-frontend recordings measured instruction-cache and decoded-op-cache misses, decoder use, and cycles or slots in which the frontend delivered no operations on both processors. Later experimental versions with substantially larger write-path code did incur more instruction-cache and op-cache misses, but frontend starvation remained a small fraction of the write phase and did not track the observed timing differences. The varying component was instead the time spent waiting for data. Instruction-side layout therefore remained an important experimental control, but it was not identified as the limiting resource of the selected scheduling design.

### What the benchmarks exercise

Five benchmark paths separate the main sources of Resolver cost:

- **The long trace** replays 5,400 seconds of production-shaped traffic under a fixed 6 GiB history budget. It is the primary retention experiment and measures the cost of maintaining that history through the complete replay.
- **`conflictset`** exercises FoundationDB's integrated conflict-detection path with point and range transactions. Its range workload commits only 16.5% of transactions, making early termination after an abort unusually important.
- **The integrated custom workload** runs controlled point and range traffic through the complete Resolver interface, exercising both `checkReads` and `addWrites`.
- **`skiplisttest`** compares the tree with FoundationDB's skip list over several key sizes and layouts, stressing searches, key comparisons and history updates at high rate.
- **The standalone workload** isolates the temporal tree and reports its read, write and cleanup phases. It is diagnostic rather than a headline comparison where the archived runs did not time exactly the same regions.

Every run verifies the resulting transaction decisions, conflicts and replay hashes; the comparisons below are performance comparisons of implementations that produced the same result.

### Retaining 2.2× more history in the same memory

Retention is the primary result. Under the same 6 GiB budget, FoundationDB's calibrated window retains 265 seconds of the long trace. Final v3 first discards history at batch 22,492, about 703 seconds into the trace, and retains 582.9–584.7 seconds in the measured tail.

The resulting retained window is **2.20× FoundationDB's for the same memory budget**. This capacity gain comes from the temporal representation and budgeted reclamation introduced in v1. V2 and final v3 preserve the same retention behaviour while reducing the CPU cost of maintaining it.

{{< figure src="fig-v3-retention.png" alt="Retained history under a 6 GiB budget: FoundationDB 265 seconds, final v3 at least 582.9 seconds in the measured tail" link="fig-v3-retention.png" class="col" >}}

<p class="figure-caption"><em>Figure 26. History retained under the same 6 GiB budget. FoundationDB's window is calibrated to 265 seconds; final v3 retains 582.9–584.7 seconds in the measured tail, or 2.20× FoundationDB's window. Its boundary first advances at batch 22,492, about 703 seconds. V1 and v2 follow the same retention curve and are omitted because their identical bars add no information.</em></p>

### From v1 to v2 to final v3

Each milestone attacks a different part of the cost.

**V1 made long retention possible.** The temporal B+ tree, shared node-and-key pool, version-ordered reclamation and proactive splits replaced per-entry skip-list history with compact paged storage. It reached the 582.9-second retained window, but independent traversals and exposed memory latency made it expensive.

**V2 reduced the read-side cost.** Recursive partitioning routes a sorted batch through the tree without repeating the same upper-level separator comparisons, while cooperative read tasks prefetch nodes and keys and overlap their memory waits. In the final paired Intel short session, relative to v1, v2 takes 0.51× in integrated points, 0.68× in integrated ranges and 0.61–0.63× in the two illustrated `skiplisttest` layouts.

**V3 reduced the write-side cost.** The mixed descent locates write destinations while checking reads, the write frontier restores begin order, and two groups of cooperative write tasks prefetch destinations and stored keys while preserving serial mutation. Relative to v2 in that same session, final v3 takes 0.74× in integrated points, 0.88× in integrated ranges and 0.68–0.69× in the two illustrated `skiplisttest` layouts.

The final long-trace campaign compares FDB and v3 directly; it does not contain new v1 or v2 arms, so the evolution figure does not carry the older cross-session long-trace ratios forward.

{{< figure src="fig-v3-evolution.png" alt="Final-session time of v1, v2 and final v3 on Intel across six short workloads, normalized to v1" link="fig-v3-evolution.png" class="col" >}}

<p class="figure-caption"><em>Figure 27. Evolution from v1 to final v3 in the paired Intel short-benchmark session, normalized to v1. V2 primarily removes repeated read-side traversal work; v3 additionally removes the second write descent and overlaps write-path memory latency. The long trace is omitted because its final campaign contains only FDB and v3.</em></p>

### Final v3 against FoundationDB

The final design obtains the additional history at a similar or lower processing cost, depending on the processor and workload.

On Intel, final v3 takes 0.81× FoundationDB's time for `conflictset` points, 0.74–0.91× across seven `skiplisttest` layouts and 0.77× on the long trace. Integrated points is level at 1.00×, integrated ranges takes 0.92× and `conflictset` ranges is slower at 1.12×.

On AMD, final v3 takes 0.95–1.01× FoundationDB across seven `skiplisttest` layouts and 0.99× in integrated ranges. It is slower in `conflictset` points at 1.05×, integrated points at 1.32× and `conflictset` ranges at 1.29×. The AMD long trace has one measured pair: its times are published, but no performance ratio is inferred from a single pair.

The result is therefore not a universal speedup claim. It is that the Resolver retains **2.20× more history** while taking less time on most Intel paths; on AMD the result depends on workload, with `skiplisttest` and integrated ranges near FoundationDB and three slower workloads identified explicitly.

{{< figure src="fig-v3-vs-fdb.png" alt="Final v3 time relative to FoundationDB on Intel and AMD across six workloads, with equal cost marked at 1.0 and no AMD long-trace ratio inferred" link="fig-v3-vs-fdb.png" class="col" >}}

<p class="figure-caption"><em>Figure 28. Final v3 time relative to FoundationDB in the paired Intel and AMD sessions; lower is better. The vertical line marks equal cost; for `skiplisttest` the bar reaches the fastest of the seven key layouts and the note gives the slowest. AMD's long trace carries no ratio because its single pair supports correctness and retention replication, not a timing inference.</em></p>

### How to read the ratios

The final short benchmarks measure FDB, v1, v2 and v3 in one rotated session per machine. The Intel long trace uses two FDB/v3 pairs; the AMD replica has one. Final v3 uses its published HugeTLB-backed pool, while FDB, v1 and v2 use their native ordinary-memory implementations. The ratios therefore compare deployed configurations rather than isolating page mode. The short tables report the minimum and maximum of five paired ratios, not confidence intervals; no sub-1% difference is attributed to code.

## What was tried and set aside

The nine versions after v3.8 explored whether the remaining write-side work
could be reduced further. Their common objective was to reuse more of the
speculative search, avoid scheduling tasks that could not yet make progress and
replace entry-by-entry work with larger operations when an accepted interval
covered complete leaves. The aim was not to change the retained history or the
result of conflict detection, but to perform less work while applying the same
accepted writes.

The series tried several ways of reaching that objective: a fast path for
write-search continuations; a runnable ring instead of fixed groups; concurrent
progress by writes believed to be on independent leaves; components prepared
from leaf footprints; state-based dispatch and alternative state orderings; and
the retirement of fully covered leaves as a single operation. These experiments
also exposed their costs. Parked searches could occupy ring slots while few
tasks were runnable; determining independent writes required an admission rule
strong enough to preserve the split invariant; constructing leaf-footprint
components introduced a preparation pass that paid the memory latency it was
intended to hide; and the additional dispatch, validation and bookkeeping
consumed work even when the corresponding fast path was not useful.

By the end of the series, the intended larger-grained operations and safe
scheduling rules had been made to work. The work they avoided, however, was
approximately balanced by the work required to prepare, validate and dispatch
them. V3.16 and v3.17 therefore did not consistently improve on v3.8 in either
the point or range workloads on Intel or AMD. Retiring a fully covered leaf was
also rarely exercised by the measured workloads. Because the later designs
added states, metadata and invariants without producing a repeatable end-to-end
gain, the v3.8 scheduling design was retained.

That design shipped with one defect, found after v3.8 was tagged. A saved
write rank carried neither the identity nor the revision of its leaf, so a
rank prepared during the read phase could be reused after pressure reclamation
had freed the leaf and the pool had handed its block to another role. In a
two-page pool the regression case loses 60 accepted writes with 2×8 write
tasks and aborts at commit version 21 with 2×4; the block-size sweep finds 17
bad sizes under 2×8 and all 400 configurations aborting under 2×4, with the
same outcomes in assertion, optimized and sanitizer builds. The correctness fix
`f866c98d` saves the leaf generation and mutation epoch with every rank and
validates them, in that order, before the rank is consumed; a stale rank is
discarded and the search is repeated. It changes no scheduling decision, and
its paired A/B medians lie between −0.49% and +0.60%, with an A/A control of
the same size.

The experimental branches remain part of the snapshot because they record both
the attempted optimizations and the conditions under which they failed to pay
for themselves. The design document distinguishes final v3 from mechanisms
that belong only to the experimental series.

## What comes next

The Resolver can retain conflict history within a fixed memory budget without tracking active transactions. Completing the removal of the five-second limit requires a different policy in Storage Servers. They will keep historical versions in pages that can spill to disk, while the transaction-management path tracks and propagates `minRV`, the oldest read version still needed by an active transaction. A Storage Server can reclaim a historical page once its contents are no longer needed at or above that version.

Configured memory and disk budgets remain hard limits. If capacity runs out while an older transaction is active, the affected Storage Server advances its local availability boundary, and a read that needs discarded history returns `transaction_too_old`. Commit Proxies will separately retain the versioned Resolver assignments needed to route conflict checks and reject commits when that routing history is no longer available. The Resolver continues to manage its conflict history by budget, independently of `minRV`. Implementing and validating these paths, including failure and recovery, is the next milestone.

## Milestone record

The [v3 snapshot](https://github.com/ricardojimenezperis/fdb-beyond-5s/tree/main/resolver/v3) holds the [final design](https://github.com/ricardojimenezperis/fdb-beyond-5s/blob/main/resolver/v3/03-resolver-v3-design.md), [decision record](https://github.com/ricardojimenezperis/fdb-beyond-5s/blob/main/resolver/v3/04-decisions-and-evolution.md), [validation register](https://github.com/ricardojimenezperis/fdb-beyond-5s/blob/main/resolver/v3/05-validation-and-evidence.md) and [final evaluation](https://github.com/ricardojimenezperis/fdb-beyond-5s/blob/main/resolver/v3/06-evaluation.md). The production code is `f866c98d8585a77280adbf44c72650f16e975f86`; regression and mixed-batch tests are `18260afe5f80e00ae2b5cd4952f49522c07cbd0e` and `2a68fc9b90670bea84c7a458e85d582c7f4eb816`. They are published on the [`resolver-v3`](https://github.com/ricardojimenezperis/foundationdb/tree/resolver-v3) branch and in the [`resolver-v3-final`](https://github.com/ricardojimenezperis/foundationdb/releases/tag/resolver-v3-final) release, whose seven assets contain the consolidated evidence. The older tag `resolver-v3` remains the historical v3.8 milestone; the [mapping](https://github.com/ricardojimenezperis/fdb-beyond-5s/blob/main/resolver/v3/mapping.tsv) records it and the final fix. The [v1](https://github.com/ricardojimenezperis/fdb-beyond-5s/tree/main/resolver/v1) and [v2](https://github.com/ricardojimenezperis/fdb-beyond-5s/tree/main/resolver/v2) snapshots remain as published.
