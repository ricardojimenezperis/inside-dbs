+++
title = "About"
description = "Database systems researcher, founder, and hands-on systems engineer. Who writes Inside DBs."
ShowToc = false
hidemeta = true
ShowBreadCrumbs = false
+++

Database systems researcher, founder, and hands-on systems engineer.

I’m [Ricardo Jimenez-Peris](https://www.linkedin.com/in/ricardojimenezperis/) — Ric. I design and build distributed database systems, from transaction protocols and storage engines to query processing and execution.

I’m currently building [Beyond 5 Seconds](https://github.com/ricardojimenezperis/fdb-beyond-5s), a public open-source project that redesigns the mechanisms behind FoundationDB’s five-second transaction window. I work directly in C++ and publish the implementation, design invariants, experimental history, and reproducible evaluation.

The current published milestone replaces the Resolver’s age-bounded conflict history with a memory-budgeted temporal B+ tree. Under the same 6 GiB budget, it retains 2.20× more history while delivering similar or lower processing cost on most measured paths across two different processor architectures. The next milestones extend the work into transaction-version management and Storage Server history retention.

Before this, I founded LeanXcale and spent 11 years leading it as CEO and CTO. We turned a research prototype into a distributed HTAP SQL database and deployed it on demanding real-world workloads. Taking a database from research to production changes the questions you ask: not only whether an idea is correct, but how it behaves under load, how it fails, how it scales, what it costs to operate, and which architectural decisions become difficult to undo.

Before LeanXcale, I spent 25 years in academia at the Universidad Politécnica de Madrid, researching distributed databases, replication, transaction processing, and MVCC. I also taught distributed systems and spent a postdoc at ETH Zürich with Gustavo Alonso. During my final five years at the university, I built the prototype that eventually became LeanXcale.

Inside DBs combines two kinds of work. One follows concrete execution paths through production database systems to explain how their components and invariants fit together. The other develops, implements, and evaluates new mechanisms for pushing those systems beyond their current limits. The first series does both with FoundationDB.

If you want to discuss database architecture, transaction processing, storage engines, or this work, [LinkedIn](https://www.linkedin.com/in/ricardojimenezperis/) is the easiest way to reach me.
