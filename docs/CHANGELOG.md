# Changelog

## [Unreleased] — Gateway Integration

### Added
- **cellxgene-gateway integration**: vendored and modified with custom UI
- **Gateway API endpoints**: `/api/datasets` (JSON), dataset launch/terminate/relaunch/delete, annotation creation
- **Dataset browser UI**: subfolder-organized card grid with search, sort, and status badges
- **Dataset status display**: live status polling (Stopped/Loading/Loaded/Error) with port info
- **Action buttons**: Launch, Stop, Restart, Delete per dataset
- **Annotation management**: view existing annotations, create new annotations per dataset
- **Dark mode**: one-click toggle with persistence via localStorage
- **Nginx reverse proxy**: Basic Auth authentication layer, WebSocket support
- **docker-compose.yml**: vip service + nginx service, internal networking
- **Helper scripts**: `build.sh`, `run.sh`, `run-gateway.sh`, `compose-up.sh`, `clean.sh`
- **Documentation**: `INSTALL.md`, `DOCKER.md`, `TROUBLESHOOT.md`, `CHANGELOG.md`

### Changed
- **vip-entrypoint**: now supports `gateway` subcommand (`docker run ... bxgenomics_vip gateway --host 0.0.0.0 --port 5005 /datasets`)
- **Dockerfile**: installs vendored cellxgene-gateway after VIP setup
