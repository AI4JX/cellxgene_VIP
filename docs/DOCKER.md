# Docker Usage

## 1. Default VIP Mode (single dataset)

```bash
./scripts/run.sh /path/to/dataset.h5ad [port]
```

Example:
```bash
./scripts/run.sh ./data/pbmc3k.h5ad 5005
```

## 2. Gateway Mode (multiple datasets)

```bash
./scripts/run-gateway.sh [data-dir] [port]
```

Example:
```bash
./scripts/run-gateway.sh ./data 5005
```

The gateway scans `data-dir` for `.h5ad` files recursively and serves them at `http://localhost:5005`.

## 3. Docker Compose with Nginx (recommended for production)

### 3.1 Generate htpasswd

```bash
bash nginx/generate-htpasswd.sh
```

This creates `nginx/.htpasswd` with a username/password for Basic Auth.

### 3.2 Start services

```bash
./scripts/compose-up.sh
```

### 3.3 Access

Open `http://server-ip:8080` in your browser. You'll be prompted for the username/password you set in step 3.1.

### 3.4 Data directory

Place `.h5ad` files in `./data/`. The gateway will scan this directory recursively, including subdirectories.

```
data/
├── pbmc3k.h5ad
├── samples/
│   ├── brain.h5ad
│   └── liver.h5ad
└── spatial/
    └── visium_1.h5ad
```

## 4. Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GATEWAY_PORT` | `5005` | Gateway listen port |
| `GATEWAY_ENABLE_ANNOTATIONS` | `false` | Enable cellxgene annotations |
| `GATEWAY_ENABLE_BACKED_MODE` | `false` | Load AnnData in file-backed mode |
| `GATEWAY_EXPIRE_SECONDS` | `3600` | Idle timeout for cellxgene processes |

## 5. Stop Services

```bash
docker compose down
```
