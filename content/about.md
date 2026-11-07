+++
title = "About"
description = "Researcher, founder, and systems engineer working on database architecture. Who writes Inside DBs."
ShowToc = false
hidemeta = true
ShowBreadCrumbs = false
+++

Researcher, founder, and systems engineer working on database architecture.

I’m [Ricardo Jimenez-Peris](https://www.linkedin.com/in/ricardojimenezperis/) — Ric. I have spent my career researching, designing, implementing, and operating distributed database systems.

I spent 25 years in academia at the Universidad Politécnica de Madrid, researching distributed databases, replication, transaction processing, and MVCC. I also taught distributed systems and spent a postdoc at ETH Zürich with Gustavo Alonso. During my final five years at the university, I built the research prototype that became LeanXcale.

I then founded LeanXcale and spent 11 years leading it as CEO and CTO. We turned that prototype into a distributed HTAP SQL database and deployed it on demanding real-world workloads. Taking a database from research to production changes the questions you ask: not only whether an idea is correct, but how it behaves under load, how it fails, how it scales, what it costs to operate, and which architectural decisions become difficult to undo.

I’m currently building [Beyond 5 Seconds](https://github.com/ricardojimenezperis/fdb-beyond-5s), a public open-source systems project that redesigns the mechanisms behind FoundationDB’s five-second transaction window. Its published Resolver replaces age-bounded conflict history with a memory-budgeted temporal B+ tree, retaining 2.20× more history in the same memory while delivering similar or lower processing cost on most measured paths across two different processor architectures. The next milestones extend the same work into transaction-version management and Storage Server history retention.

Inside DBs combines two kinds of work. One follows concrete execution paths through production database systems to explain how their components and invariants fit together. The other develops, implements, and evaluates new mechanisms for pushing those systems beyond their current limits. The first series does both with FoundationDB.

If you want to discuss database architecture, transaction processing, storage engines, or this work, [LinkedIn](https://www.linkedin.com/in/ricardojimenezperis/) is the easiest way to reach me.
