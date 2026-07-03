# Troubleshooting

## conda base environment conflict

When running `conda activate vip`, conda may try to activate the base environment first.

**Solution**: Use `conda config --set auto_activate_base false` or explicitly use full paths:
```bash
source /opt/conda/etc/profile.d/conda.sh
conda activate vip
```

## scipy version not found

The `scipy` version pinned in the environment YAML may not be available for the target Python version.

**Solution**: Remove the version pin or update to a version compatible with your Python:
```bash
mamba install scipy
```

## mamba parameter incompatibility

Older versions of `mamba` use different CLI syntax than newer versions.

**Solution**: Pin `mamba` version or use `conda` directly:
```bash
conda install -y -c conda-forge mamba=0.15.3
```

## Rplots.pdf cannot be written

R scripts may fail when they cannot write `Rplots.pdf` to the current directory.

**Solution**: Ensure the working directory is writable, or set a temp directory:
```bash
export R_USER=`whoami`
mkdir -p /tmp/Rplots && cd /tmp/Rplots
```

## Node version warning

During cellxgene build, Node.js may emit deprecation warnings.

**Solution**: Set the Node.js legacy provider flag:
```bash
export NODE_OPTIONS=--openssl-legacy-provider
```

## cellxgene checkout issue

The Docker build checks out a specific commit of cellxgene. If the commit is no longer available (rebased/force-pushed upstream), the build fails.

**Solution**: Update the commit hash in `install_VIPlight_indocker.sh` to a valid one:
```bash
# In install_VIPlight_indocker.sh:
git checkout <new-valid-commit-hash>
```
