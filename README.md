# PeachPie

A federated discussion and link aggregation platform, forked from PieFed.

## About This Fork

**PeachPie** is a fork of [PieFed](https://codeberg.org/rimu/pyfedi) that maintains compatibility with the upstream project while adding additional features and enhancements. This fork will largely follow the PieFed upstream development.

### Key Differences from PieFed

- **Enhanced Admin API**: Comprehensive administrative API with private registration, user management, and monitoring capabilities
- **Advanced Rate Limiting**: Redis-backed sliding window rate limiting with Prometheus metrics
- **Extended Monitoring**: Real-time performance metrics, health checks, and audit trails
- **Improved Security**: Enhanced authentication systems and IP whitelisting support

### Relationship to Upstream

PeachPie tracks the main PieFed repository and regularly merges upstream changes to stay current with the latest developments. All core functionality remains compatible with standard PieFed instances, ensuring federation compatibility across the network.

## About PieFed

A Lemmy/Mbin alternative written in Python with Flask.

 - Clean, simple code that is easy to understand and contribute to. No fancy design patterns or algorithms.
 - Easy setup, easy to manage - few dependencies and extra software required.
 - AGPL.
 - [First class moderation tools](https://join.piefed.social/2024/06/22/piefed-features-for-growing-healthy-communities/).

## Project goals

To build a federated discussion and link aggregation platform, similar to Reddit, Lemmy, Mbin interoperable with as
much of the fediverse as possible.

## For developers

- [Screencast: overview of the PieFed codebase](https://join.piefed.social/2024/01/22/an-introduction-to-the-piefed-codebase/)
- [Database / entity relationship diagram](https://join.piefed.social/wp-content/uploads/2024/02/PieFed-entity-relationships.png)
- API Documentation:
  - Stable branch: [https://stable.wjs018.xyz/api/alpha/swagger](https://stable.wjs018.xyz/api/alpha/swagger)
  - Development branch: [https://crust.piefed.social/api/alpha/swagger](https://crust.piefed.social/api/alpha/swagger) or [https://piefed.wjs018.xyz/api/alpha/swagger](https://piefed.wjs018.xyz/api/alpha/swagger)
- see [INSTALL.md](INSTALL.md) or [INSTALL-docker.md](INSTALL-docker.md)
- see docs/project_management/* for a project roadmap, contributing guide and much more.
